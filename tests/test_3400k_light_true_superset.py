from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEVEN = ROOT / "docs/experiments/3400k-light-thin-marks/seven-point"
SPEC = importlib.util.spec_from_file_location("true_superset_test", SEVEN / "true_superset.py")
assert SPEC is not None and SPEC.loader is not None
superset = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = superset
SPEC.loader.exec_module(superset)


@pytest.fixture(scope="module")
def result():
    original = superset.source_binding
    superset.source_binding = lambda path: {
        "file": path.name,
        "sha256": "0" * 64,
        "commit": "0" * 40,
    }
    try:
        return superset.run()
    finally:
        superset.source_binding = original


def test_true_superset_explicitly_includes_required_seeds(result) -> None:
    assert [(row["name"], row["categories"]) for row in result["seeds"]] == [
        ("ORIGINAL-A", list(superset.seven.canonical_categories(superset.ORIGINAL_A))),
        (
            "FIXED-FOUR-YELLOW",
            list(superset.seven.canonical_categories(superset.FIXED_FOUR_YELLOW)),
        ),
        (
            "BOUNDED-GOLDEN-CHALLENGE",
            list(superset.seven.canonical_categories(superset.BOUNDED_GOLDEN)),
        ),
    ]
    assert result["best_included_seed"]["name"] == "ORIGINAL-A"


def test_every_seed_search_is_monotonic_under_tolerant_full_objective(result) -> None:
    for row in result["searches"]:
        assert not superset.objective_better(row["seed_objective"], row["final_objective"])
        assert row["hard_gate_failures"] == []
        for event in row["ledger"]:
            assert superset.objective_better(event["after_objective"], event["before_objective"])
    original = next(row for row in result["searches"] if row["seed"] == "ORIGINAL-A")
    assert original["final_categories"] == original["seed_categories"]
    assert original["passes_accepted"] == 0


def test_unrestricted_relaxation_finds_genuinely_new_proxy_nondominated_candidate(
    result,
) -> None:
    assert result["hue_family_restriction"] is None
    assert result["proximity_or_churn_objective"] is False
    assert result["proxy_nondominated_improvement"] is True
    assert result["genuinely_new_candidate"] is True
    assert result["new_chromium_authorized_by_result"] is True
    assert result["browser_non_regression_claim"] is False
    assert result["best_result"]["final_categories"] == [
        "#790C1A",
        "#7F8404",
        "#0A6109",
        "#2B8CAD",
        "#5D53AE",
        "#AC507C",
    ]
    assert superset.objective_better(
        result["best_result"]["final_objective"],
        result["best_included_seed"]["objective"],
    )


def test_fixed_three_and_boundedness_are_explicit(result) -> None:
    assert result["fixed_fg0"] == "#342F2C"
    assert result["fixed_three"] == list(superset.FIXED_THREE)
    assert result["free_role_count"] == 3
    assert result["boundedness"] == {
        "method": "multi-seed monotonic full-catalog coordinate search",
        "pass_cap_per_seed": 6,
        "exact_primary_tie_cap_per_sweep": 24,
        "objective_equality_tolerance": 0.001,
        "global_optimum_claim": False,
    }


def test_source_has_no_hue_proximity_or_churn_restriction() -> None:
    source = (SEVEN / "true_superset.py").read_text()
    assert "target_distance" not in source
    assert "60.0 <=" not in source
    assert "hue_family_restriction" in source
    assert "global_optimum_claim" in source
    assert "assert " not in source


def test_true_superset_is_byte_deterministic(result) -> None:
    original = superset.source_binding
    superset.source_binding = lambda path: {
        "file": path.name,
        "sha256": "0" * 64,
        "commit": "0" * 40,
    }
    try:
        replay = superset.run()
    finally:
        superset.source_binding = original
    assert superset.json_bytes(replay) == superset.json_bytes(result)
