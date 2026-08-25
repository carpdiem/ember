from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "docs/experiments/3400k-light-thin-marks"
SEVEN = EXPERIMENT / "seven-point"
SPEC = importlib.util.spec_from_file_location("seven_point_optimizer", SEVEN / "optimizer.py")
assert SPEC and SPEC.loader
seven = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = seven
SPEC.loader.exec_module(seven)


@pytest.fixture(scope="module")
def inputs():
    return seven.load_inputs(replay=False)


@pytest.fixture(scope="module")
def contract(inputs):
    value = seven.load_contract()
    seven.validate_contract(value, inputs)
    return value


@pytest.fixture(scope="module")
def result(inputs, contract):
    return seven.run_optimizer(inputs, contract, smoke=True)


def test_fg0_and_every_non_categorical_byte_are_exactly_frozen(inputs, contract, result) -> None:
    assert contract["fixed"]["fg_0"] == "#342F2C"
    baseline_frozen = seven.p3.frozen_non_categorical(inputs.baseline)
    assert contract["fixed"]["frozen_non_categorical_sha256"] == seven.p3.sha256_json(
        baseline_frozen
    )
    for candidate in result["candidates"]:
        family = seven.candidate_family(candidate["categories"], inputs)
        assert family["family"]["surfaces"]["fg_0"] == "#342F2C"
        assert seven.p3.frozen_non_categorical(family) == baseline_frozen
        assert family["family"]["categorical"] != inputs.baseline["family"]["categorical"]


def test_benchmark_is_recomputed_candidate_c_not_hardcoded(inputs, contract, result) -> None:
    source = (SEVEN / "optimizer.py").read_text()
    categories = seven.benchmark_categories(inputs, contract)
    assert not [hex8 for hex8 in categories if hex8 in source]
    assert result["benchmark"]["proxy"]["metrics"]["primary_raw_symmetric_scalar"] == pytest.approx(
        6.466329045890242
    )
    assert result["benchmark"]["browser_worst_all_21_1_5px_delta_e_ok"] == 7.30273837


def test_primary_is_one_symmetric_all_21_minimum_with_both_directions(result) -> None:
    assert result["objective_policy"]["kind"] == "single-raw-symmetric-minimum"
    assert result["objective_policy"]["class_normalization"] is False
    assert result["objective_policy"]["role_semantics"] is False
    assert result["objective_policy"]["churn"] is False
    for candidate in result["candidates"]:
        metrics = candidate["metrics"]
        raster = metrics["raster_all_21"]["1.5"]
        assert metrics["primary_raw_symmetric_scalar"] == raster["calibrated_delta_e_ok"]
        assert raster["pair_count"] == 21
        assert raster["category_indices"] == list(range(6))
        assert raster["lane_direction_evaluations"] == 120 * 2 * 21 * 2
        assert raster["direction"] in {"lane-0-to-1", "lane-1-to-0"}


def test_only_exact_primary_equality_has_secondary_tiebreaks(contract, result) -> None:
    assert contract["objective"]["secondary_after_exact_primary_equality"] == [
        "transformed_2px_all_21_minimum",
        "transformed_3px_all_21_minimum",
        "nominal_transformed_solid_all_21_minimum",
        "commanded_solid_all_21_minimum",
        "gain_sensitivity_all_21_minimum",
    ]
    for candidate in result["candidates"]:
        assert len(candidate["objective"]) == 6
        assert candidate["objective"][0] == candidate["metrics"]["primary_raw_symmetric_scalar"]


def test_three_structural_clique_lanes_clear_hard_gates_and_materiality(result) -> None:
    assert [(row["lane"], row["method"]) for row in result["candidates"]] == [
        ("A", "single-mid-band"),
        ("B", "bright-band"),
        ("C", "two-tier-lattice"),
    ]
    assert result["infeasible_lanes"] == []
    assert len({tuple(row["categories"]) for row in result["candidates"]}) == 3
    for row in result["candidates"]:
        assert row["hard_gate_failures"] == []
        assert row["proxy_improvement_delta_e_ok"] >= 1.0
        assert row["materiality_pass"] is True
        assert row["search"]["algorithm"] == "deterministic-bitset-maximin-clique"
        assert row["search"]["optimized_threshold_delta_e_ok"] >= row["objective"][0] - 1e-3
        assert (
            row["search"]["materiality_floor_delta_e_ok"]
            > result["benchmark"]["proxy"]["metrics"]["primary_raw_symmetric_scalar"]
        )
        assert row["search"]["exact_catalog_local_swaps"] is False
        assert row["categories"] == list(seven.canonical_categories(row["categories"]))
    c = next(row for row in result["candidates"] if row["lane"] == "C")
    lightness = [
        seven.srgb_to_oklab(seven.p3.parse_exact_hex8(hex8))[0] for hex8 in c["categories"]
    ]
    assert sum(value <= 0.45 for value in lightness) == 3
    assert sum(value >= 0.48 for value in lightness) == 3


def test_catalog_is_broad_exact_and_all_lanes_material(result) -> None:
    summary = result["catalog_summary"]
    assert summary["exact_hex8_count"] >= 250
    assert summary["source_support"]["hue_bins_occupied"] >= 12
    assert all(count >= 250 for count in summary["lane_eligible_counts"].values())
    for row in result["candidates"]:
        assert all(seven.p3.parse_exact_hex8(hex8).shape == (3,) for hex8 in row["categories"])


def test_smoke_build_is_deterministic(result, inputs, contract) -> None:
    again = seven.run_optimizer(inputs, contract, smoke=True)
    assert seven._json_bytes(again) == seven._json_bytes(result)


@pytest.mark.parametrize("flags", [[], ["-O"]], ids=["normal", "optimized"])
def test_closed_contract_rejects_corruption(tmp_path: Path, contract, flags: list[str]) -> None:
    corrupted = deepcopy(contract)
    corrupted["objective"]["category_first"] = True
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(corrupted))
    completed = subprocess.run(
        [
            sys.executable,
            *flags,
            str(SEVEN / "optimizer.py"),
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
    assert "objective keys differ" in completed.stderr


def test_output_path_safety_and_tamper_rejection(
    tmp_path: Path, inputs, contract, result, monkeypatch
) -> None:
    with pytest.raises(ValueError, match="entire Git repository"):
        seven.build_artifacts(ROOT / "scratch", inputs, contract, smoke=True)
    output = tmp_path / "artifacts"
    payloads = seven._payloads(result)
    output.mkdir()
    for name, payload in payloads.items():
        (output / name).write_bytes(seven._json_bytes(payload))
    monkeypatch.setattr(seven, "run_optimizer", lambda *args, **kwargs: result)
    seven.validate_artifacts(output, inputs, contract, smoke=True)
    corrupted = json.loads((output / "results.json").read_text())
    corrupted["production"] = True
    (output / "results.json").write_text(json.dumps(corrupted))
    with pytest.raises(ValueError, match="recomputation"):
        seven.validate_artifacts(output, inputs, contract, smoke=True)
