from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEVEN = ROOT / "docs/experiments/3400k-light-thin-marks/seven-point"
SPEC = importlib.util.spec_from_file_location(
    "minimal_relaxation_test", SEVEN / "minimal_relaxation.py"
)
assert SPEC is not None and SPEC.loader is not None
relax = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = relax
SPEC.loader.exec_module(relax)


@pytest.fixture(scope="module")
def result():
    original = relax.source_binding
    relax.source_binding = lambda path: {
        "file": path.name,
        "sha256": "0" * 64,
        "commit": "0" * 40,
    }
    try:
        return relax.run()
    finally:
        relax.source_binding = original


def _scenario(result, removed: str):
    return next(
        row for row in result["constraint_influence"] if row["removed_fixed_color"] == removed
    )


def test_constraint_influence_identifies_pink_as_amber_gap_binding(result) -> None:
    assert result["binding_fixed_slot"] == "#B34B71"
    assert "expands exact amber second-color support from 2 to 85" in result["binding_mechanism"]
    baseline = _scenario(result, "NONE")
    assert baseline["bins"][0]["second_color_count"] == 2
    assert baseline["bins"][0]["hard_feasible_pair_count"] == 175
    assert _scenario(result, "#0A6109")["bins"][0]["second_color_count"] == 8
    assert _scenario(result, "#2B8CAD")["bins"][0]["second_color_count"] == 2
    assert _scenario(result, "#5D53AE")["bins"][0]["second_color_count"] == 2
    pink_removed = _scenario(result, "#B34B71")
    assert pink_removed["bins"][0]["second_color_count"] == 85
    assert pink_removed["bins"][0]["hard_feasible_pair_count"] == 55_292


def test_each_influence_bin_reports_full_six_component_winner(result) -> None:
    for scenario in result["constraint_influence"]:
        for bin_row in scenario["bins"]:
            assert len(bin_row["best_reduced_objective"]) == 6
            assert len(bin_row["best_pair"]) == 2
            assert bin_row["exact_objective_tie_count"] > 0
            assert bin_row["hard_feasible_pair_count"] > 0


def test_minimal_relaxation_moves_only_warm_pair_plus_pink_slot(result) -> None:
    row = result["minimal_relaxation"]
    assert row["removed_fixed_color"] == "#B34B71"
    assert row["remaining_fixed_colors"] == list(relax.FIXED_THREE_AFTER_RELAXATION)
    assert set(relax.FIXED_THREE_AFTER_RELAXATION) < set(row["categories"])
    assert "#B34B71" not in row["categories"]
    assert len(row["free_colors"]) == 3
    assert 60.0 <= row["hue_family_oklch"][2] < 90.0
    assert row["hard_gate_failures"] == []
    assert len(row["objective"]) == 6


def test_minimal_relaxation_is_exact_and_full_objective_ranked(result) -> None:
    inputs = relax.seven.load_inputs(replay=False)
    contract = relax.seven.load_contract()
    row = result["minimal_relaxation"]
    evaluation = relax.seven.evaluate(row["categories"], inputs, contract)
    assert evaluation["objective"] == row["objective"]
    assert evaluation["hard_gate_failures"] == []
    assert row["search"] == {
        "pair_beam_cap": 64,
        "pair_beam_evaluated": 64,
        "third_tie_cap": 4,
        "exact_full_bank_count": 64,
        "seed_pair_primary": row["search"]["seed_pair_primary"],
        "seed_pair": row["search"]["seed_pair"],
        "ranking": "full six-component objective then maximum canonical category tuple",
    }


def test_original_and_fixed_four_reviews_remain_inputs_not_mutation_targets(result) -> None:
    assert result["baseline"]["categories"] == list(
        relax.seven.canonical_categories(relax.BASELINE_A)
    )
    fixed = result["fixed_four_frontier"]
    assert fixed["lane"] == "YELLOW"
    assert fixed["categories"] == [
        "#7F180E",
        "#867412",
        "#0A6109",
        "#2B8CAD",
        "#5D53AE",
        "#B34B71",
    ]
    assert result["production"] is False and result["selection"] is None


def test_source_has_no_baseline_proximity_or_all_six_fallback() -> None:
    source = (SEVEN / "minimal_relaxation.py").read_text()
    assert "target_distance" not in source
    assert "churn" not in source.lower()
    assert "all-six" not in source.lower()
    assert "maximum-clique" not in source
    assert "assert " not in source


def test_minimal_relaxation_is_byte_deterministic(result) -> None:
    original = relax.source_binding
    relax.source_binding = lambda path: {
        "file": path.name,
        "sha256": "0" * 64,
        "commit": "0" * 40,
    }
    try:
        replay = relax.run()
    finally:
        relax.source_binding = original
    assert relax.json_bytes(replay) == relax.json_bytes(result)
