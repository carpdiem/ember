from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "docs/experiments/3400k-light-thin-marks"
sys.path.insert(0, str(EXPERIMENT))

import phase3_optimizer as p3


@pytest.fixture(scope="module")
def inputs() -> p3.Phase3Inputs:
    return p3.load_inputs(EXPERIMENT)


@pytest.fixture(scope="module")
def contract(inputs: p3.Phase3Inputs) -> dict:
    loaded = p3.load_contract(EXPERIMENT / "phase3-search-contract.json")
    p3.validate_search_contract(loaded, inputs)
    return loaded


def copy_guard_inputs(destination: Path) -> Path:
    destination.mkdir()
    for name in p3.INPUT_FILENAMES.values():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(EXPERIMENT / name, target)
    return destination


def baseline_bank(inputs: p3.Phase3Inputs) -> tuple[str, ...]:
    return tuple(inputs.baseline["family"]["categorical"][role] for role in p3.ROLE_NAMES)


@pytest.fixture(scope="module")
def authentic_pipeline(tmp_path_factory, inputs, contract) -> dict:
    root = tmp_path_factory.mktemp("phase3-authentic")
    coarse_paths = []
    for seed in (3400, 3401, 3402, 3403):
        output = root / f"coarse-{seed}"
        p3.run_search(
            inputs,
            contract,
            output_dir=output,
            stage="coarse",
            seed=seed,
            budget=8,
            chunk_size=3,
            max_seconds=60,
            workers=1,
            final_selection=False,
        )
        coarse_paths.append(output / "coarse-survivors.json")
    combined_path = root / "combined.json"
    p3.combine_coarse_artifacts(
        coarse_paths, output_path=combined_path, inputs=inputs, contract=contract
    )
    refine = root / "refine"
    p3.run_search(
        inputs,
        contract,
        output_dir=refine,
        stage="refine",
        seed=4400,
        budget=1,
        chunk_size=1,
        max_seconds=120,
        workers=1,
        final_selection=False,
        survivor_artifact=combined_path,
    )
    return {
        "root": root,
        "coarse_paths": coarse_paths,
        "combined_path": combined_path,
        "combined": json.loads(combined_path.read_text()),
        "refine": refine,
        "frontier_path": refine / "frontier-manifest.json",
        "frontier": json.loads((refine / "frontier-manifest.json").read_text()),
        "rows_path": refine / "frontier-rows.json",
        "rows": json.loads((refine / "frontier-rows.json").read_text()),
        "search_manifest_path": refine / "search-manifest.json",
    }


def authentic_browser_result(request: dict, inputs: p3.Phase3Inputs) -> dict:
    masks = {row["id"]: row for row in inputs.raster_masks["records"]}
    observations = [
        {
            "request_observation_id": row["id"],
            "status": "PASS",
            "sample_count": 1,
            "observed_rgb8_median": p3._expected_browser_rgb8(
                row, request, inputs, mask_lookup=masks
            ),
            "delta_e_ok": 0.0,
        }
        for row in request["requested_role_observations"]
    ]
    replay = {
        "schema_version": 1,
        "status": "PASS",
        "request_sha256": p3.sha256_json(request),
        "candidate_id": request["candidate_id"],
        "input_chain_sha256": request["input_chain_sha256"],
        "observation_count": len(observations),
        "pass_count": len(observations),
        "fail_count": 0,
        "error_count": 0,
        "maximum_delta_e_ok": 0.0,
    }
    return {
        "schema_version": p3.BROWSER_SCHEMA_VERSION,
        "request_sha256": p3.sha256_json(request),
        "candidate_id": request["candidate_id"],
        "serialized_bank_sha256": request["serialized_bank_sha256"],
        "input_chain_sha256": request["input_chain_sha256"],
        "status": "PASS",
        "observations": observations,
        "source_provenance": {
            "browser": "test-browser",
            "browser_version": "1.0",
            "probe_sha256": inputs.source_sha256["browser_probe"],
        },
        "replay_receipt": replay,
        "replay_sha256": p3.sha256_json(replay),
        "full_image_hash_used": False,
        "human_width_capacity": None,
    }


def test_committed_g1_chain_authorizes_search_and_freezes_exact_inputs(inputs) -> None:
    receipt = p3.authorize_search(inputs, replay=True)
    assert receipt["status"] == "PASS"
    assert receipt["phase3_search_authorized"] is True
    assert receipt["approved_head"] == p3.APPROVED_G1_HEAD
    assert receipt["frozen_non_categorical_sha256"] == p3.sha256_json(
        p3.frozen_non_categorical(inputs.baseline)
    )


def test_stale_g1_receipt_blocks_before_search(tmp_path: Path) -> None:
    copied = copy_guard_inputs(tmp_path / "stale")
    receipt_path = copied / "raster-verification.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["pair_rows_replayed"] -= 1
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    with pytest.raises(p3.AuthorizationError, match="receipt|hash"):
        p3.authorize_search(p3.load_inputs(copied), replay=False)


def test_one_frozen_non_categorical_role_change_blocks(inputs) -> None:
    changed = deepcopy(inputs.baseline)
    changed["family"]["surfaces"]["fg_1"] = "#4D4541"
    with pytest.raises(p3.FrozenInputError, match="non-categorical"):
        p3.assert_only_categorical_changed(inputs.baseline, changed)


def test_exact_hex8_pipeline_reparses_and_float_good_hex_bad_fails(inputs, contract) -> None:
    lab = p3.bank_oklab(baseline_bank(inputs))
    proposed = lab.copy()
    proposed[1] = proposed[0] + np.array([0.0, 1e-8, -1e-8])
    assert not np.array_equal(proposed[0], proposed[1])
    with pytest.raises(ValueError, match="duplicate"):
        p3.quantize_proposal(proposed)

    bank, reparsed = p3.quantize_proposal(lab)
    assert bank == baseline_bank(inputs)
    assert np.array_equal(reparsed, p3.bank_rgb(bank))
    cheap = p3.evaluate_cheap(bank, inputs, contract)
    assert cheap["serialized_bank_sha256"] == p3.bank_hash(bank)
    assert "proposal_floats" not in cheap


def test_vectorized_contrast_preserves_exact_wcag_ratio_semantics(inputs) -> None:
    banks = [baseline_bank(inputs), tuple(reversed(baseline_bank(inputs)))]
    actual = p3.evaluate_commanded_batch(banks, inputs)["graphics_contrast_min"]
    backgrounds = [
        p3.parse_exact_hex8(inputs.baseline["family"]["surfaces"][name])
        for name in p3.GATE_BACKGROUNDS
    ]
    expected = np.asarray(
        [
            min(
                p3.contrast_ratio(color, background)
                for color in p3.bank_rgb(bank)
                for background in backgrounds
            )
            for bank in banks
        ]
    )
    np.testing.assert_array_equal(actual, expected)


def test_role_hue_neighborhood_and_no_universal_chroma_floor(contract) -> None:
    bounds = contract["proposal_bounds"]
    assert bounds["global_oklab"]["per_role_chroma_min"] is None
    assert bounds["global_oklab"]["l_min"] > 0.0
    assert bounds["global_oklab"]["l_max"] < 1.0
    assert [row["role"] for row in bounds["roles"]] == list(p3.ROLES)
    assert all(0.0 < row["hue_half_width_degrees"] <= 45.0 for row in bounds["roles"])
    assert "numerical optimizer prior" in contract["threshold_policy"]
    assert "human visibility floor" in contract["threshold_policy"]


def test_exact_serialized_bank_dedupe() -> None:
    rows = [
        {"candidate_id": "b", "serialized_bank_sha256": "same", "score": 2},
        {"candidate_id": "a", "serialized_bank_sha256": "same", "score": 1},
        {"candidate_id": "c", "serialized_bank_sha256": "other", "score": 3},
    ]
    assert [row["candidate_id"] for row in p3.dedupe_candidate_rows(rows)] == ["a", "c"]


def test_average_good_worst_bad_is_rejected() -> None:
    rows = [
        {"id": "corner-a", "pair": 12.0},
        {"id": "interior", "pair": 1.0},
        {"id": "corner-b", "pair": 12.0},
    ]
    assert np.mean([row["pair"] for row in rows]) > 8.0
    failures = p3.gate_every_row(rows, metric="pair", floor=8.0, gate="sampled-pair")
    assert [failure["scenario"] for failure in failures] == ["interior"]
    assert p3.sampled_minimum(rows, "pair") == (1.0, "interior")


def test_gain_interior_sample_worse_than_corners_is_caught() -> None:
    samples = [
        {"id": "g0", "green_gain": 0.70, "blue_gain": 0.50},
        {"id": "g1", "green_gain": 0.74, "blue_gain": 0.53},
        {"id": "g2", "green_gain": 0.78, "blue_gain": 0.56},
    ]

    def metric(row: dict) -> float:
        return 2.0 + 1000.0 * ((row["green_gain"] - 0.74) ** 2 + (row["blue_gain"] - 0.53) ** 2)

    evaluated = p3.evaluate_gain_samples(samples, metric)
    assert p3.sampled_minimum(evaluated, "value") == (2.0, "g1")
    assert evaluated[1]["value"] < evaluated[0]["value"]
    assert evaluated[1]["value"] < evaluated[2]["value"]


def test_report_only_cvd_cannot_veto_or_change_rank(inputs, contract) -> None:
    bank = baseline_bank(inputs)
    left = p3.evaluate_candidate(
        bank,
        inputs,
        contract,
        stage="cheap",
        cvd_report={"protan": 0.0},
    )
    right = p3.evaluate_candidate(
        bank,
        inputs,
        contract,
        stage="cheap",
        cvd_report={"protan": 999.0, "deutan": -1.0},
    )
    assert left["failures"] == right["failures"]
    assert left["pareto"] == right["pareto"]
    assert left["cvd"]["used_as_gate"] is False
    assert right["cvd"]["report_only"] is True


def test_primary_and_full_ladders_never_average_scenarios(inputs, contract) -> None:
    bank = baseline_bank(inputs)
    primary = p3.evaluate_transformed(bank, inputs, contract, full_grid=False)
    full = p3.evaluate_transformed(bank, inputs, contract, full_grid=True)
    assert len(primary["rows"]) == 3
    assert len(full["rows"]) == 9 * 45
    assert primary["scenario_policy"] == "report separately; never average"
    assert full["scenario_policy"] == "report separately; never average"
    assert "average_pair_distance" not in full["summary"]


def test_raster_proxy_reuses_full_g1_mask_set(inputs, contract) -> None:
    result = p3.evaluate_raster_proxy(baseline_bank(inputs), inputs, contract)
    assert result["mask_source"] == "raster-masks.json"
    assert result["mask_sha256"] == inputs.source_sha256["raster_masks"]
    assert result["mask_count"] == 720
    assert result["rerasterized"] is False
    assert set(result["minimum_pair_by_width"]) == {"1.5", "2", "3"}
    assert result["calibrated_error_margin_delta_e_ok"] == 0.75


def test_no_regression_required_for_pareto_claim() -> None:
    baseline = {
        "transformed_pair_min": 10.0,
        "commanded_pair_min": 10.0,
        "neutral_min": 10.0,
        "graphics_contrast_min": 3.0,
        "raster_1_5_min": 8.0,
        "raster_2_min": 9.0,
        "raster_3_min": 10.0,
        "max_commanded_deviation": 0.0,
        "mean_commanded_deviation": 0.0,
    }
    candidate = dict(baseline)
    candidate["transformed_pair_min"] = 11.0
    candidate["raster_1_5_min"] = 7.99
    assert p3.is_strict_pareto_improvement(candidate, baseline) is False
    candidate["raster_1_5_min"] = 8.0
    assert p3.is_strict_pareto_improvement(candidate, baseline) is True


def _synthetic_frontier_row(
    candidate_id: str,
    bank_last_byte: int,
    pareto: dict,
    *,
    failures: list | None = None,
    baseline: bool = False,
) -> dict:
    full_row = {
        "id": "sample",
        "pair_min_cam16_ucs": pareto["transformed_pair_min"],
        "neutral_min_cam16_ucs": pareto["neutral_min"],
        "background_policy": "gate",
        "graphics_contrast": pareto["graphics_contrast_min"],
    }
    bank = [f"#{index:02X}{index:02X}{index:02X}" for index in range(1, 6)] + [
        f"#{bank_last_byte:02X}{bank_last_byte:02X}{bank_last_byte:02X}"
    ]
    return {
        "candidate_id": candidate_id,
        "serialized_bank_sha256": f"{bank_last_byte:064x}",
        "serialized_bank": bank,
        "row_kind": "baseline" if baseline else "candidate",
        "evaluation_stage": "full",
        "full": {"rows": [full_row]},
        "pareto": dict(pareto),
        "failures": list(failures or []),
        "strict_pareto_improvement": False,
        "pareto_frontier_eligible": False,
    }


def test_standard_pareto_tradeoff_is_frontier_eligible() -> None:
    metrics = {
        "transformed_pair_min": 10.0,
        "commanded_pair_min": 10.0,
        "neutral_min": 10.0,
        "graphics_contrast_min": 3.0,
        "raster_1_5_min": 8.0,
        "raster_2_min": 9.0,
        "raster_3_min": 10.0,
        "max_commanded_deviation": 0.0,
        "mean_commanded_deviation": 0.0,
    }
    baseline = _synthetic_frontier_row("baseline", 16, metrics, baseline=True)
    tradeoff_metrics = dict(metrics)
    tradeoff_metrics["raster_1_5_min"] = 8.5
    tradeoff_metrics["transformed_pair_min"] = 9.5
    tradeoff_metrics["max_commanded_deviation"] = 1.0
    tradeoff_metrics["mean_commanded_deviation"] = 0.5
    tradeoff = _synthetic_frontier_row("tradeoff", 17, tradeoff_metrics)
    rows = p3.pareto_front([tradeoff], baseline)
    assert [row["candidate_id"] for row in rows] == ["baseline", "tradeoff"]
    assert rows[1]["pareto_frontier_eligible"] is True
    assert rows[1]["strict_pareto_improvement"] is False


def test_baseline_dominated_and_hard_floor_failure_are_frontier_ineligible() -> None:
    metrics = {
        "transformed_pair_min": 10.0,
        "commanded_pair_min": 10.0,
        "neutral_min": 10.0,
        "graphics_contrast_min": 3.0,
        "raster_1_5_min": 8.0,
        "raster_2_min": 9.0,
        "raster_3_min": 10.0,
        "max_commanded_deviation": 0.0,
        "mean_commanded_deviation": 0.0,
    }
    baseline = _synthetic_frontier_row("baseline", 16, metrics, baseline=True)
    dominated_metrics = dict(metrics)
    dominated_metrics["raster_1_5_min"] = 7.9
    dominated_metrics["max_commanded_deviation"] = 1.0
    dominated = _synthetic_frontier_row("dominated", 17, dominated_metrics)
    failed_metrics = dict(metrics)
    failed_metrics["raster_1_5_min"] = 9.0
    failed = _synthetic_frontier_row(
        "failed", 18, failed_metrics, failures=[{"gate": "protected-floor"}]
    )
    rows = p3.pareto_front([dominated, failed], baseline)
    assert [row["candidate_id"] for row in rows] == ["baseline"]


def test_deterministic_shortlist_roles_dedupe_and_use_target_delta() -> None:
    base_metrics = {
        "transformed_pair_min": 10.0,
        "commanded_pair_min": 10.0,
        "neutral_min": 10.0,
        "graphics_contrast_min": 3.0,
        "raster_1_5_min": 8.0,
        "raster_2_min": 9.0,
        "raster_3_min": 10.0,
        "max_commanded_deviation": 0.0,
        "mean_commanded_deviation": 0.0,
    }
    baseline = _synthetic_frontier_row("baseline", 16, base_metrics, baseline=True)
    baseline["pareto_frontier_eligible"] = False
    candidates = []
    for index, (target, deviation, transformed) in enumerate(
        ((9.0, 2.0, 12.0), (8.8, 1.0, 11.0), (8.7, 1.5, 13.0), (8.04, 0.5, 14.0)),
        start=1,
    ):
        values = dict(base_metrics)
        values.update(
            raster_1_5_min=target,
            max_commanded_deviation=deviation,
            mean_commanded_deviation=deviation / 2,
            transformed_pair_min=transformed,
        )
        row = _synthetic_frontier_row(f"candidate-{index}", 16 + index, values)
        row["pareto_frontier_eligible"] = True
        candidates.append(row)
    shortlist = p3.deterministic_g2_shortlist([baseline, *candidates])
    assert [(row["role"], row["candidate_id"]) for row in shortlist] == [
        ("A", "candidate-1"),
        ("B", "candidate-2"),
        ("C", "candidate-3"),
    ]
    assert all(row["deterministic_shortlist_delta_e_ok"] == 0.05 for row in shortlist)
    assert all(row["human_visibility_floor"] is None for row in shortlist)


def test_authentic_frontier_builds_reference_request_and_replays_browser_rows(
    inputs, contract, authentic_pipeline
) -> None:
    baseline = authentic_pipeline["rows"]["rows"][0]
    request = p3.build_browser_oracle_request(
        baseline,
        inputs,
        contract,
        finalist_rank=0,
        frontier=authentic_pipeline["frontier_path"],
        frontier_rows=authentic_pipeline["rows_path"],
        parent_artifact=authentic_pipeline["combined_path"],
        source_search_manifest=authentic_pipeline["search_manifest_path"],
        reference=True,
    )
    assert request["schema_version"] == p3.BROWSER_SCHEMA_VERSION
    assert request["request_kind"] == "baseline-reference"
    assert request["shortlist_role"] == "REFERENCE"
    assert request["deterministic_shortlist_delta_e_ok"] == 0.05
    assert request["human_visibility_floor"] is None
    assert len(request["requested_role_observations"]) == 25_920
    result = authentic_browser_result(request, inputs)
    p3.validate_browser_oracle_result(result, request, inputs, contract)


def test_browser_rejects_all_black_and_every_status_metric_row_contract_tamper(
    inputs, contract, authentic_pipeline
) -> None:
    baseline = authentic_pipeline["rows"]["rows"][0]
    request = p3.build_browser_oracle_request(
        baseline,
        inputs,
        contract,
        finalist_rank=0,
        frontier=authentic_pipeline["frontier_path"],
        frontier_rows=authentic_pipeline["rows_path"],
        parent_artifact=authentic_pipeline["combined_path"],
        source_search_manifest=authentic_pipeline["search_manifest_path"],
        reference=True,
    )
    result = authentic_browser_result(request, inputs)

    all_black = deepcopy(result)
    for row in all_black["observations"]:
        row["observed_rgb8_median"] = [0.0, 0.0, 0.0]
    with pytest.raises(p3.StaleArtifactError, match="metric"):
        p3.validate_browser_oracle_result(all_black, request, inputs, contract)

    variants = []
    wrong_status = deepcopy(result)
    wrong_status["status"] = "FAIL"
    variants.append(wrong_status)
    wrong_metric = deepcopy(result)
    wrong_metric["observations"][0]["delta_e_ok"] = 0.01
    variants.append(wrong_metric)
    missing_row = deepcopy(result)
    missing_row["observations"].pop()
    variants.append(missing_row)
    wrong_order = deepcopy(result)
    wrong_order["observations"][0], wrong_order["observations"][1] = (
        wrong_order["observations"][1],
        wrong_order["observations"][0],
    )
    variants.append(wrong_order)
    for tampered in variants:
        with pytest.raises(p3.StaleArtifactError):
            p3.validate_browser_oracle_result(tampered, request, inputs, contract)


def test_browser_request_result_versions_extras_and_nested_replay_are_closed(
    inputs, contract, authentic_pipeline
) -> None:
    baseline = authentic_pipeline["rows"]["rows"][0]
    request = p3.build_browser_oracle_request(
        baseline,
        inputs,
        contract,
        finalist_rank=0,
        frontier=authentic_pipeline["frontier_path"],
        frontier_rows=authentic_pipeline["rows_path"],
        parent_artifact=authentic_pipeline["combined_path"],
        source_search_manifest=authentic_pipeline["search_manifest_path"],
        reference=True,
    )
    result = authentic_browser_result(request, inputs)
    for key, value in (("unexpected", True), ("schema_version", 999)):
        tampered = deepcopy(request)
        tampered[key] = value
        with pytest.raises(p3.StaleArtifactError, match="schema"):
            p3.validate_browser_oracle_request(tampered, inputs, contract)
        tampered_result = deepcopy(result)
        tampered_result[key] = value
        with pytest.raises(p3.StaleArtifactError):
            p3.validate_browser_oracle_result(tampered_result, request, inputs, contract)
    nested_extra = deepcopy(result)
    nested_extra["replay_receipt"]["forged"] = True
    nested_extra["replay_sha256"] = p3.sha256_json(nested_extra["replay_receipt"])
    with pytest.raises(p3.StaleArtifactError, match="replay"):
        p3.validate_browser_oracle_result(nested_extra, request, inputs, contract)


def test_deterministic_seed_chunk_order_and_resume_are_identical(
    tmp_path: Path, inputs, contract
) -> None:
    jobs_a = p3.make_search_jobs(seed=3400, count=12, chunk_size=5)
    jobs_b = p3.make_search_jobs(seed=3400, count=12, chunk_size=5)
    assert jobs_a == jobs_b
    shuffled = list(jobs_a)
    random.Random(19).shuffle(shuffled)
    records = [{"candidate_id": f"{job.index:064x}", "job_index": job.index} for job in shuffled]
    merged = p3.merge_chunk_records(records)
    assert [row["job_index"] for row in merged] == list(range(12))

    first = p3.run_search(
        inputs,
        contract,
        output_dir=tmp_path / "first",
        stage="coarse",
        seed=3400,
        budget=2,
        chunk_size=1,
        max_seconds=30.0,
        workers=1,
        final_selection=False,
    )
    resumed = p3.run_search(
        inputs,
        contract,
        output_dir=tmp_path / "first",
        stage="coarse",
        seed=3400,
        budget=2,
        chunk_size=1,
        max_seconds=30.0,
        workers=1,
        final_selection=False,
        resume=True,
    )
    second = p3.run_search(
        inputs,
        contract,
        output_dir=tmp_path / "second",
        stage="coarse",
        seed=3400,
        budget=2,
        chunk_size=2,
        max_seconds=30.0,
        workers=1,
        final_selection=False,
    )
    assert first["records_sha256"] == resumed["records_sha256"] == second["records_sha256"]
    assert first["selected_candidate_id"] is None
    assert all(str(path).startswith(str(tmp_path)) for path in (tmp_path / "first").iterdir())


def test_four_seed_merge_keeps_equal_job_indices_and_exact_bank_dedupes() -> None:
    rows = [
        {
            "run_seed": seed,
            "job_index": index,
            "candidate_id": f"{seed * 10 + index:064x}",
        }
        for seed in (3400, 3401, 3402, 3403)
        for index in range(3)
    ]
    assert len(p3.merge_chunk_records(rows)) == 12


def test_baseline_anchored_batch_has_plentiful_deduped_cheap_survivors(inputs, contract) -> None:
    jobs = p3.make_search_jobs(seed=3400, count=4_000, chunk_size=4_000)
    rows, _, count = p3._coarse_chunk(jobs, inputs, contract, 3400)
    survivors = p3.select_diverse_survivors(rows)
    assert count == 4_000
    assert rows[0]["baseline_reference"] is True
    assert rows[0]["serialized_bank"] == list(baseline_bank(inputs))
    assert len(survivors) >= 500
    assert len({row["serialized_bank_sha256"] for row in survivors}) == len(survivors)
    assert {row["proposal_mode"] for row in survivors} >= {
        "targeted-1-role",
        "targeted-2-role",
        "baseline-binding-pair-emphasis",
    }


def test_shard_corruption_and_run_binding_changes_block_resume(
    tmp_path: Path, inputs, contract
) -> None:
    output = tmp_path / "resume"
    p3.run_search(
        inputs,
        contract,
        output_dir=output,
        stage="coarse",
        seed=3400,
        budget=12,
        chunk_size=4,
        max_seconds=30,
        workers=1,
        final_selection=False,
    )
    with pytest.raises(p3.StaleArtifactError, match="binding"):
        p3.run_search(
            inputs,
            contract,
            output_dir=output,
            stage="coarse",
            seed=3400,
            budget=12,
            chunk_size=3,
            max_seconds=30,
            workers=1,
            final_selection=False,
            resume=True,
        )
    changed = deepcopy(contract)
    changed["hard_gates"]["commanded_pair_delta_e_ok"] += 0.01
    with pytest.raises(p3.StaleArtifactError, match="binding"):
        p3.run_search(
            inputs,
            changed,
            output_dir=output,
            stage="coarse",
            seed=3400,
            budget=12,
            chunk_size=4,
            max_seconds=30,
            workers=1,
            final_selection=False,
            resume=True,
        )
    shard = output / "shard-000000.json"
    shard.write_bytes(shard.read_bytes() + b" ")
    with pytest.raises(p3.StaleArtifactError, match="corrupt"):
        p3.run_search(
            inputs,
            contract,
            output_dir=output,
            stage="coarse",
            seed=3400,
            budget=12,
            chunk_size=4,
            max_seconds=30,
            workers=1,
            final_selection=False,
            resume=True,
        )


def test_refine_consumes_combined_survivors_and_emits_full_parent_provenance(
    tmp_path: Path, inputs, contract
) -> None:
    artifacts = []
    for seed in (3400, 3401, 3402, 3403):
        output = tmp_path / f"coarse-{seed}"
        p3.run_search(
            inputs,
            contract,
            output_dir=output,
            stage="coarse",
            seed=seed,
            budget=80,
            chunk_size=40,
            max_seconds=30,
            workers=1,
            final_selection=False,
        )
        artifacts.append(output / "coarse-survivors.json")
    combined_path = tmp_path / "combined.json"
    combined = p3.combine_coarse_artifacts(
        artifacts, output_path=combined_path, inputs=inputs, contract=contract
    )
    assert combined["seed_runs"] == [3400, 3401, 3402, 3403]
    assert combined["deduped_survivor_count"] > 0
    output = tmp_path / "refine"
    p3.run_search(
        inputs,
        contract,
        output_dir=output,
        stage="refine",
        seed=4400,
        budget=1,
        chunk_size=1,
        max_seconds=60,
        workers=1,
        final_selection=False,
        survivor_artifact=combined_path,
    )
    shard = json.loads((output / "shard-000000.json").read_text())
    row = shard["records"][0]
    parent = combined["survivor_rows"][0]
    assert row["evaluation_stage"] == "full"
    assert row["full"]["grid_kind"] == "full-45-gain-all-viewing-sensitivities"
    assert row["raster_proxy"]["mask_count"] == 720
    assert row["serialized_bank"] == parent["serialized_bank"]
    assert row["parent_candidate_ids"] == [parent["candidate_id"]]
    assert row["parent_artifact_sha256"] == p3.sha256_json(combined)
    frontier = json.loads((output / "frontier-manifest.json").read_text())
    assert frontier["candidate_ids"][0] == frontier["baseline_candidate_id"]


def test_output_guard_rejects_every_repo_path_and_symlink_direction(tmp_path: Path, inputs) -> None:
    with pytest.raises(ValueError, match="entire Git repository"):
        p3.validate_external_output_path(ROOT / "palettes", inputs)
    external_link = tmp_path / "into-repo"
    external_link.symlink_to(ROOT / "palettes", target_is_directory=True)
    with pytest.raises(ValueError, match="entire Git repository"):
        p3.validate_external_output_path(external_link / "search", inputs)
    repo_link = ROOT / ".phase3-output-link-test"
    try:
        os.symlink(tmp_path, repo_link, target_is_directory=True)
        with pytest.raises(ValueError, match="entire Git repository"):
            p3.validate_external_output_path(repo_link / "search", inputs)
    finally:
        repo_link.unlink(missing_ok=True)


def test_baseline_conservation_and_all_pareto_dimensions(inputs, contract) -> None:
    row = p3.evaluate_candidate(baseline_bank(inputs), inputs, contract, stage="full")
    assert row["row_kind"] == "baseline"
    assert row["serialized_bank"] == list(baseline_bank(inputs))
    assert row["strict_pareto_improvement"] is False
    assert row["pareto_frontier_eligible"] is False
    assert set(row["pareto"]) == set(p3.PARETO_DIMENSIONS)
    assert row["pareto"]["max_commanded_deviation"] == 0.0
    assert row["pareto"]["mean_commanded_deviation"] == 0.0


def test_contracts_are_closed_and_forbid_categorical_line() -> None:
    schema_dir = EXPERIMENT / "phase3-schemas"
    paths = sorted(schema_dir.glob("*.schema.json"))
    assert [path.name for path in paths] == [
        "approval-hash-freeze.schema.json",
        "browser-oracle-request.schema.json",
        "browser-oracle-result.schema.json",
        "candidate-row.schema.json",
        "frontier-manifest.schema.json",
        "frontier-receipt.schema.json",
        "search-contract.schema.json",
    ]
    serialized = "\n".join(path.read_text() for path in paths)
    assert "categorical_line" not in serialized
    for path in paths:
        schema = json.loads(path.read_text())
        assert schema["additionalProperties"] is False
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    schemas = {path.name: json.loads(path.read_text()) for path in paths}
    assert schemas["frontier-manifest.schema.json"]["properties"]["seed_runs"]["minItems"] == 4
    assert (
        schemas["search-contract.schema.json"]["properties"]["seed"]["properties"][
            "minimum_independent_runs"
        ]["const"]
        == 4
    )
    assert (
        json.loads((EXPERIMENT / "phase3-search-contract.json").read_text())["bank"]["kind"]
        == "categorical"
    )


def test_benchmark_is_environment_bound_non_gating_and_contains_no_bank_payload() -> None:
    benchmark = json.loads((EXPERIMENT / "phase3-benchmark.json").read_text())
    assert benchmark["artifact_policy"] == {
        "environment_bound": True,
        "gating": False,
        "timings_deterministic": False,
        "wall_clock_timestamp_included": False,
    }
    assert benchmark["bank_payload_included"] is False
    assert not {"timestamp", "generated_at", "created_at"} & set(benchmark)
    assert "serialized_bank" not in json.dumps(benchmark)


def test_report_and_specimen_api_is_deterministic_without_writing_production(
    tmp_path: Path, inputs, contract
) -> None:
    row = p3.evaluate_candidate(baseline_bank(inputs), inputs, contract, stage="cheap")
    first = p3.generate_report_specimen([row], output_dir=tmp_path / "a", selection=None)
    second = p3.generate_report_specimen([row], output_dir=tmp_path / "b", selection=None)
    assert first == second
    assert first["selection"] is None
    assert (tmp_path / "a/phase3-report.json").read_bytes() == (
        tmp_path / "b/phase3-report.json"
    ).read_bytes()
    assert (
        hashlib.sha256((tmp_path / "a/phase3-specimen.svg").read_bytes()).hexdigest()
        == first["specimen_sha256"]
    )
