from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEVEN = ROOT / "docs/experiments/3400k-light-thin-marks/seven-point"
SPEC = importlib.util.spec_from_file_location("forbidden_arc_test", SEVEN / "forbidden_arc.py")
assert SPEC is not None and SPEC.loader is not None
arc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = arc
SPEC.loader.exec_module(arc)


@dataclass
class Row:
    hue_degrees: float


def test_forbidden_arc_is_closed_and_role_neutral() -> None:
    values = [Row(91.999), Row(92.0), Row(105.0), Row(118.0), Row(118.001)]
    assert [row.hue_degrees for row in arc.filter_catalog(values)] == [91.999, 118.001]
    assert arc.FORBIDDEN_HUE_ARC == (92.0, 118.0)


def test_full_quality_search_parameters_are_preserved() -> None:
    assert arc.DISCOVERY_THRESHOLD_ITERATIONS == 16
    assert arc.DISCOVERY_FINALIST_LIMIT == 24
    assert arc.OBJECTIVE_EQUALITY_TOLERANCE == 0.001
    assert arc.POLISH_PASS_CAP == 6


def test_objective_comparison_ignores_float_noise_but_not_material_change() -> None:
    baseline = (8.0, 12.0, 13.0, 14.0, 15.0, 16.0)
    noise = (8.0001, 11.0, 13.0, 14.0, 15.0, 16.0)
    material = (8.01, 1.0, 1.0, 1.0, 1.0, 1.0)
    assert arc.objective_better(noise, baseline) is False
    assert arc.objective_better(material, baseline) is True


def test_source_has_exact_21_pair_accounting_and_no_baseline_eligibility() -> None:
    source = (SEVEN / "forbidden_arc.py").read_text()
    assert '"total_unordered_pairs": 21' in source
    assert '"category_category_pairs": 15' in source
    assert '"fg0_category_pairs": 6' in source
    assert '"lane_directions": 2' in source
    assert '"eligibility_uses_a_or_prior_c": False' in source
    assert "target_distance" not in source
    assert "churn" not in source.lower()
    assert "assert " not in source


def test_bounded_alternative_is_explicit_not_global_optimum_claim() -> None:
    source = (SEVEN / "forbidden_arc.py").read_text()
    assert "prior full-catalog clique materialized O(n^2) graphs" in source
    assert '"global_optimum_claim": False' in source
    assert "broad 940-color exact catalog" in source
    assert "monotonic exact one-color coordinate search" in source


def test_committed_forbidden_arc_artifact_is_closed_and_gate_clean() -> None:
    directory = SEVEN / "forbidden-arc"
    assert {path.name for path in directory.iterdir()} == {
        "catalog-summary.json",
        "results.json",
    }
    result = json.loads((directory / "results.json").read_text())
    assert result["catalog"]["smoke_before"] == 940
    assert result["catalog"]["smoke_after"] == 928
    assert result["catalog"]["full_before"] == 7184
    assert result["catalog"]["full_after"] == 7024
    assert result["pair_accounting"] == {
        "role_count": 7,
        "total_unordered_pairs": 21,
        "category_category_pairs": 15,
        "fg0_category_pairs": 6,
        "lane_directions": 2,
    }
    assert len(result["candidates"]) == 3
    assert len({tuple(row["categories"]) for row in result["candidates"]}) == 3
    for row in result["candidates"]:
        assert row["hard_gate_failures"] == []
        assert len(row["objective"]) == 6
        assert row["metrics"]["raster_all_21"]["1.5"]["pair_count"] == 21
        for value in row["categories"]:
            lab = arc.srgb_to_oklab(arc.p3.parse_exact_hex8(value))
            assert arc.hue_allowed(arc.seven._hue(lab))
