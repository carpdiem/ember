from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "docs/experiments/3400k-light-thin-marks"
SEVEN = EXPERIMENT / "seven-point"
SPEC = importlib.util.spec_from_file_location("seven_point_polish_test", SEVEN / "polish.py")
assert SPEC is not None and SPEC.loader is not None
polish = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = polish
SPEC.loader.exec_module(polish)


@pytest.fixture(scope="module")
def inputs():
    return polish.seven.load_inputs(replay=False)


@pytest.fixture(scope="module")
def contract():
    return polish.seven.load_contract()


@pytest.fixture(scope="module")
def result():
    return polish.run_polish(progress=False)


def test_committed_smoke_seeds_preserve_full_quality_search_contract(inputs, contract) -> None:
    seeds = json.loads((SEVEN / "smoke-seeds.json").read_text())
    rows = polish.validate_seeds(seeds, inputs, contract)
    assert [(row["lane"], row["method"]) for row in rows] == [
        ("A", "single-mid-band"),
        ("B", "bright-band"),
        ("C", "two-tier-lattice"),
    ]
    assert seeds["threshold_iterations"] == 16
    assert seeds["finalist_limit"] == 24
    assert seeds["objective_tolerance"] == 0.001
    assert seeds["fixed_fg_0"] == "#342F2C"
    assert seeds["selection"] is None and seeds["production"] is False


def test_full_catalog_polish_is_bounded_symmetric_and_monotonic(result, inputs) -> None:
    assert result["catalog_summary"]["exact_hex8_count"] >= 7_000
    assert result["fixed_fg0"] == "#342F2C"
    assert result["objective_policy"] == {
        "kind": "single-raw-symmetric-minimum",
        "pair_count": 21,
        "lane_directions": 2,
        "class_normalization": False,
        "role_semantics": False,
        "churn": False,
        "exact_tie_break": "maximum canonical category tuple after six-component objective",
    }
    assert result["bounds"] == {
        "pass_cap": 6,
        "lane_runtime_cap_seconds": 90.0,
        "total_runtime_cap_seconds": 240.0,
        "exact_evaluation_cap_per_lane": 145,
        "exact_finalist_cap_per_sweep": 24,
        "minimum_primary_improvement": 1e-9,
    }
    baseline_frozen = polish.p3.frozen_non_categorical(inputs.baseline)
    for candidate in result["candidates"]:
        primary = candidate["metrics"]["primary_raw_symmetric_scalar"]
        assert primary >= candidate["seed_primary_raw_symmetric_scalar"]
        assert candidate["primary_improvement_over_seed"] >= 0.0
        assert candidate["hard_gate_failures"] == []
        assert candidate["polish"]["passes_accepted"] <= 6
        assert candidate["polish"]["exact_evaluation_count"] <= 145
        ledger = candidate["polish"]["ledger"]
        assert all(row["after_primary"] > row["before_primary"] for row in ledger)
        family = polish.seven.candidate_family(candidate["categories"], inputs)
        assert family["family"]["surfaces"]["fg_0"] == "#342F2C"
        assert polish.p3.frozen_non_categorical(family) == baseline_frozen


def test_polish_replay_is_byte_deterministic(result) -> None:
    replay = polish.run_polish(progress=False)
    assert polish._json_bytes(replay) == polish._json_bytes(result)


def test_exact_objective_tie_uses_maximum_canonical_category_tuple() -> None:
    objective = (8.0, 10.0, 11.0, 12.0, 16.0, 9.0)
    lower = (objective, ("#100000", "#200000"), "lower")
    higher = (objective, ("#100000", "#300000"), "higher")
    assert polish.select_exact_best([higher, lower]) == higher
    assert polish.select_exact_best([lower, higher]) == higher


def test_more_than_24_primary_ties_are_deterministically_truncated_not_aborted() -> None:
    proposals = [(8.0, index % 6, index, (f"#{index:06X}",)) for index in range(30)]
    bounded = polish.bounded_primary_ties(proposals, remaining=144)
    assert len(bounded) == 24
    assert [row[3] for row in bounded] == sorted([row[3] for row in proposals], reverse=True)[:24]


def test_seed_and_result_corruption_reject_with_explicit_exceptions(inputs, contract) -> None:
    seeds = json.loads((SEVEN / "smoke-seeds.json").read_text())
    corrupted = deepcopy(seeds)
    corrupted["threshold_iterations"] = 10
    with pytest.raises(polish.PolishError, match="threshold iterations weakened"):
        polish.validate_seeds(corrupted, inputs, contract)
    corrupted = deepcopy(seeds)
    corrupted["candidates"][0]["categories"][0] = "#000000"
    with pytest.raises(polish.PolishError):
        polish.validate_seeds(corrupted, inputs, contract)
    source = (SEVEN / "polish.py").read_text()
    assert "assert " not in source
    assert "maximum-clique" not in source
    assert "maximin-clique" not in source


def test_closed_external_artifacts_replay_and_reject_extra_entry(tmp_path: Path) -> None:
    output = tmp_path / "polish"
    polish.build(output, progress=False)
    polish.validate(output, progress=False)
    (output / "extra.json").write_text("{}")
    with pytest.raises(polish.PolishError, match="closed filenames"):
        polish.validate(output, progress=False)


def test_committed_full_polish_artifacts_are_fresh() -> None:
    directory = SEVEN / "full-polish"
    actual = {name: json.loads((directory / name).read_text()) for name in polish.EXPECTED_FILES}
    expected = polish._payloads(polish.run_polish(progress=False))
    assert actual == expected


def test_only_new_seven_point_paths_are_in_phase_slice() -> None:
    allowed = {
        "docs/experiments/3400k-light-thin-marks/seven-point/polish.py",
        "docs/experiments/3400k-light-thin-marks/seven-point/smoke-seeds.json",
        "docs/experiments/3400k-light-thin-marks/seven-point/full-polish/catalog-summary.json",
        "docs/experiments/3400k-light-thin-marks/seven-point/full-polish/results.json",
        "docs/experiments/3400k-light-thin-marks/seven-point/full-polish/",
        "tests/test_3400k_light_seven_point_polish.py",
    }
    import subprocess

    completed = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    changed = {line[3:] for line in completed.stdout.splitlines() if line}
    assert changed <= allowed
