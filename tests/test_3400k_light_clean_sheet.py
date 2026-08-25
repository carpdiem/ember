from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "docs/experiments/3400k-light-thin-marks"
CLEAN_SHEET = EXPERIMENT / "clean-sheet"
sys.path.insert(0, str(CLEAN_SHEET))

import optimizer as clean


def tracked_hashes() -> dict[str, str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    paths = [path for path in completed.stdout.split(b"\0") if path]
    return {
        path.decode(): hashlib.sha256((ROOT / path.decode()).read_bytes()).hexdigest()
        for path in paths
    }


@pytest.fixture(scope="module")
def inputs():
    return clean.load_authorized_inputs(EXPERIMENT, replay=False)


@pytest.fixture(scope="module")
def contract(inputs):
    value = clean.load_contract(CLEAN_SHEET / "search-contract.json")
    clean.validate_contract(value, inputs)
    return value


@pytest.fixture(scope="module")
def result(inputs, contract):
    return clean.run_optimizer(inputs, contract, reduced=True)


@pytest.fixture(scope="module")
def full_result(inputs, contract):
    return clean.run_optimizer(inputs, contract, reduced=False)


def test_exact_g1_chain_and_exact_hex8_boundary(inputs, contract) -> None:
    authorization = clean.authorization_receipt(inputs, replay=False)
    assert authorization["status"] == "PASS"
    assert authorization["approved_head"] == clean.p3.APPROVED_G1_HEAD
    assert contract["authorization"]["input_chain_sha256"] == clean.p3.input_chain_sha256(inputs)
    with pytest.raises(ValueError, match="canonical Hex8"):
        clean.evaluate_bank(("#ffffff",) * 6, inputs, contract)


def test_contract_structurally_forbids_historical_search_constraints(contract) -> None:
    serialized = json.dumps(contract, sort_keys=True).lower()
    forbidden = (
        "per_role_l",
        "hue_half_width",
        "mean_chroma",
        "baseline_relative",
        "baseline_ratio",
        "j_prime_envelope",
        "m_prime_envelope",
        "baseline_seed",
        "churn_objective",
        "retention_envelope",
    )
    assert not [term for term in forbidden if term in serialized]
    assert set(contract["exploration"]) == {
        "lightness",
        "chroma",
        "hue_degrees",
        "exact_catalog",
    }
    assert "l_max" not in contract["exploration"]
    assert contract["hard_gates"] == {
        "commanded_category_pair_delta_e_ok": 16.0,
        "commanded_category_foreground_delta_e_ok": 8.0,
        "commanded_minimum_hue_gap_degrees": 30.0,
        "graphics_contrast_ratio": 3.0,
        "nominal_transformed_category_foreground_delta_e_ok": 5.0,
        "nominal_transformed_category_pair_delta_e_ok": 8.0,
        "minimum_commanded_oklab_lightness": 0.3,
        "minimum_nominal_transformed_luminance": 0.003,
    }
    assert contract["report_only"] == {
        "baseline_churn": True,
        "gain_and_viewing_sensitivity": True,
    }


@pytest.mark.parametrize("python_flags", [[], ["-O"]], ids=["normal", "optimized"])
def test_contract_rejects_forbidden_fields_with_explicit_exceptions(
    tmp_path: Path, contract, python_flags: list[str]
) -> None:
    corrupted = deepcopy(contract)
    corrupted["exploration"]["l_max"] = 0.61
    path = tmp_path / "corrupted.json"
    path.write_text(json.dumps(corrupted))
    completed = subprocess.run(
        [
            sys.executable,
            *python_flags,
            str(CLEAN_SHEET / "optimizer.py"),
            "validate-contract",
            "--contract",
            str(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "exploration keys" in completed.stderr


def test_catalog_is_broad_exact_and_contrast_derives_its_upper_lightness(inputs, contract) -> None:
    catalog, summary = clean.build_catalog(inputs, contract, reduced=True)
    assert summary["exact_hex8_count"] == len(catalog)
    assert summary["exact_hex8_count"] >= 250
    assert summary["support"]["lightness_bins_occupied"] >= 6
    assert summary["support"]["chroma_bins_occupied"] >= 4
    assert summary["support"]["hue_bins_occupied"] >= 12
    assert summary["support"]["non_baseline_fraction"] > 0.99
    assert summary["requested_domain"]["lightness"] == [0.3, 0.64]
    assert summary["requested_domain"]["chroma"] == [0.04, 0.14]
    assert summary["requested_domain"]["hue_degrees"] == [0.0, 360.0]
    assert summary["admission"]["uniform_lightness_ceiling"] is None
    assert summary["admission"]["upper_lightness_derived_from_exact_background_contrast"] is True
    assert all(clean.p3.parse_exact_hex8(row.hex8).shape == (3,) for row in catalog)


def test_metrics_name_fg0_separately_and_bind_every_exact_minimum(result) -> None:
    candidate = result["candidates"][0]
    metrics = candidate["metrics"]
    required = {
        "commanded_category_pair",
        "commanded_category_fg_0",
        "commanded_category_fg_1_fg_2",
        "nominal_transformed_solid_category_pair",
        "nominal_transformed_category_fg_0",
        "nominal_transformed_category_fg_1_fg_2",
        "graphics_contrast_by_background_state",
        "nominal_transformed_j_prime_pair",
        "nominal_transformed_luminance_pair",
        "commanded_hue_topology",
        "raster_category_pair",
        "raster_category_fg_0",
        "sensitivity_report",
        "churn_report",
    }
    assert set(metrics) == required
    for name in required - {
        "graphics_contrast_by_background_state",
        "sensitivity_report",
        "churn_report",
    }:
        assert metrics[name]["binding"]
    raster = metrics["raster_category_fg_0"]
    assert raster["mask_count"] == 720
    assert raster["exact_binding"] is True
    assert set(raster["minimum_by_width_state_background"])
    assert all(
        "fg_0" in row["binding"] for row in raster["minimum_by_width_state_background"].values()
    )
    assert "fg_0" in metrics["commanded_category_fg_0"]["binding"]
    assert "fg_0" in metrics["nominal_transformed_category_fg_0"]["binding"]
    assert any(
        foreground in metrics["commanded_category_fg_1_fg_2"]["binding"]
        for foreground in ("fg_1", "fg_2")
    )
    assert any(
        foreground in metrics["nominal_transformed_category_fg_1_fg_2"]["binding"]
        for foreground in ("fg_1", "fg_2")
    )


def test_search_has_three_materially_distinct_lanes_then_role_permutation(result) -> None:
    candidates = result["candidates"]
    assert [row["lane"] for row in candidates] == ["A", "B", "C"]
    assert [row["lane_method"] for row in candidates] == [
        "constructive-cool-lighter-warm-darker",
        "transformed-native-targets-inverted-through-gains",
        "continuity-compromise-zero-to-two-broad-anchors",
    ]
    assert len({tuple(sorted(row["bank"])) for row in candidates}) == 3
    assert len({tuple(row["bank"]) for row in candidates}) == 3
    assert all(row["bank_discovery_precedes_role_permutation"] is True for row in candidates)
    assert all(row["role_permutation"] for row in candidates)
    assert candidates[2]["broad_anchor_count"] <= 2
    assert candidates[0]["continuity_anchor_matches"] == []
    assert candidates[1]["continuity_anchor_matches"] == []
    assert len(candidates[2]["continuity_anchor_matches"]) == 2
    assert all(
        row["hue_delta_degrees"] <= row["half_width_degrees"]
        for row in candidates[2]["continuity_anchor_matches"]
    )
    for row in candidates:
        assert row["hard_gate_failures"] == []
        assert row["metrics"]["commanded_hue_topology"]["minimum_circular_gap_degrees"] >= 30.0
        admission = row["materiality_admission"]
        assert admission["policy"] == "deterministic search targets; NOT human floors"
        assert admission["selected_weakest_three_dark_cluster_analog"]["pass"] is True
        assert admission["full_bank_1_5px_thin_proxy"]["pass"] is True
        assert admission["category_fg_0_distinctiveness"]["pass"] is True
    assert result["selection"] is None


def test_full_search_support_admits_only_material_candidates(full_result) -> None:
    assert [row["lane"] for row in full_result["candidates"]] == ["A", "B", "C"]
    for candidate in full_result["candidates"]:
        assert candidate["hard_gate_failures"] == []
        assert all(
            candidate["materiality_admission"][name]["pass"] is True
            for name in (
                "selected_weakest_three_dark_cluster_analog",
                "full_bank_1_5px_thin_proxy",
                "category_fg_0_distinctiveness",
            )
        )


def test_artifact_validation_rejects_unexpected_directories(tmp_path, inputs, contract) -> None:
    output = tmp_path / "closed-artifacts"
    clean.build_artifacts(output, inputs, contract, reduced=True)
    (output / "unexpected-directory").mkdir()
    with pytest.raises(ValueError, match="non-file entry"):
        clean.validate_artifacts(output, inputs, contract, reduced=True)


def test_bank_discovery_is_role_neutral_and_winners_are_not_hardcoded(result) -> None:
    discovery_source = inspect.getsource(clean._discover_bank)
    permutation_source = inspect.getsource(clean._permute_roles)
    module_source = (CLEAN_SHEET / "optimizer.py").read_text()
    assert "_baseline_bank" not in discovery_source
    assert "role_reference" not in discovery_source
    assert "_baseline_bank" in permutation_source
    for candidate in result["candidates"]:
        assert candidate["discovered_bank"] == sorted(candidate["discovered_bank"])
        assert set(candidate["discovered_bank"]) == set(candidate["bank"])
        assert not [hex8 for hex8 in candidate["bank"] if hex8 in module_source]


def test_objective_order_is_lexicographic_worst_case_and_churn_is_absent(contract, result) -> None:
    objective = contract["objective"]["lexicographic_worst_case"]
    assert objective[:5] == [
        "nominal_transformed_1_5px_raster_category_pair",
        "nominal_transformed_1_5px_raster_category_fg_0",
        "nominal_transformed_j_prime_luminance_pair",
        "nominal_transformed_solid_category_pair",
        "commanded_solid_category_pair",
    ]
    assert objective[5:] == [
        "raster_2px_then_3px",
        "hue_breadth_topology_sensitivity",
    ]
    assert "churn" not in json.dumps(result["objective_policy"], sort_keys=True).lower()


def test_objective_maps_2px_then_3px_and_hue_topology_independently(result) -> None:
    metrics = deepcopy(result["candidates"][0]["metrics"])
    baseline = clean._candidate_objective(metrics)

    for key, row in metrics["raster_category_pair"]["minimum_by_width_state_background"].items():
        if key.startswith("3/nominal-transformed/"):
            row["calibrated_delta_e_ok"] += 100.0
    changed_3px = clean._candidate_objective(metrics)
    assert changed_3px != baseline
    assert changed_3px[7] > baseline[7]

    metrics = deepcopy(result["candidates"][0]["metrics"])
    metrics["commanded_hue_topology"]["minimum_circular_gap_degrees"] += 10.0
    changed_hue = clean._candidate_objective(metrics)
    assert changed_hue != baseline
    assert changed_hue[8] > baseline[8]


@pytest.mark.parametrize("python_flags", [[], ["-O"]], ids=["normal", "optimized"])
def test_cli_build_is_compact_deterministic_and_rejects_tampering(
    tmp_path: Path, python_flags: list[str]
) -> None:
    repository_before = tracked_hashes()
    first = tmp_path / "first"
    second = tmp_path / "second"
    command = [
        sys.executable,
        *python_flags,
        str(CLEAN_SHEET / "optimizer.py"),
        "build",
        "--reduced",
    ]
    subprocess.run([*command, "--output-dir", str(first)], cwd=ROOT, check=True)
    subprocess.run([*command, "--output-dir", str(second)], cwd=ROOT, check=True)
    expected = ["catalog-summary.json", "candidates.json", "metrics.json"]
    assert sorted(path.name for path in first.iterdir()) == sorted(expected)
    for name in expected:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    candidates = json.loads((first / "candidates.json").read_text())
    metrics = json.loads((first / "metrics.json").read_text())
    assert candidates["selection"] is None
    assert len(candidates["candidates"]) == 3
    assert metrics["candidate_ids"] == [row["candidate_id"] for row in candidates["candidates"]]

    candidates["candidates"][0]["bank"][0] = "#000000"
    (first / "candidates.json").write_text(json.dumps(candidates))
    corrupted = subprocess.run(
        [
            sys.executable,
            *python_flags,
            str(CLEAN_SHEET / "optimizer.py"),
            "validate-artifacts",
            "--artifact-dir",
            str(first),
            "--reduced",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert corrupted.returncode != 0
    assert "recomputation" in corrupted.stderr
    assert tracked_hashes() == repository_before
