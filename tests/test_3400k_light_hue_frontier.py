from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from artifact_freshness import assert_committed_artifact_fresh

ROOT = Path(__file__).resolve().parents[1]
SEVEN = ROOT / "docs/experiments/3400k-light-thin-marks/seven-point"
SPEC = importlib.util.spec_from_file_location("hue_frontier_test", SEVEN / "hue_frontier.py")
assert SPEC is not None and SPEC.loader is not None
frontier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = frontier
SPEC.loader.exec_module(frontier)


@pytest.fixture(scope="module")
def result():
    original = frontier.source_binding
    frontier.source_binding = lambda path: {
        "file": path.name,
        "sha256": "0" * 64,
        "commit": "0" * 40,
    }
    try:
        return frontier.run()
    finally:
        frontier.source_binding = original


def test_frontier_freezes_fg0_and_other_four_exact_colors(result) -> None:
    assert result["fixed_fg0"] == "#342F2C"
    assert result["fixed_four"] == list(frontier.FIXED_FOUR)
    assert result["baseline"]["categories"] == list(
        frontier.seven.canonical_categories(frontier.BASELINE_A)
    )
    for lane in result["lanes"]:
        assert set(frontier.FIXED_FOUR) < set(lane["categories"])
        assert len(lane["categories"]) == 6
        assert lane["hard_gate_failures"] == []


def test_second_free_color_spans_four_material_hue_families(result) -> None:
    assert [lane["lane"] for lane in result["lanes"]] == [
        "AMBER-ORANGE",
        "GOLDEN-YELLOW",
        "YELLOW",
        "YELLOW-GREEN-EDGE",
    ]
    expected_bins = [(60.0, 78.0), (78.0, 90.0), (90.0, 102.0), (102.0, 113.0)]
    for lane, expected in zip(result["lanes"], expected_bins, strict=True):
        assert tuple(lane["hue_bin_degrees"]) == expected
        hue = lane["free_2_oklch"][2]
        assert expected[0] <= hue < expected[1]
        assert lane["search"]["second_bin_pool_count"] > 0
        assert lane["search"]["hard_feasible_pair_count"] > 0


def test_actual_feasible_hue_support_is_reported_without_silent_narrowing(result) -> None:
    support = result["feasible_hue_support"]
    assert support["exact_color_count"] > 200
    assert support["minimum_degrees"] < 31.0
    assert support["maximum_degrees"] > 329.0
    assert [82.109833, 112.528815] in support["intervals_degrees"]
    assert {5, 6, 7, 8, 9} <= set(support["occupied_12_degree_bins"])


def test_each_lane_is_exact_full_objective_winner_and_gate_clean(result) -> None:
    inputs = frontier.seven.load_inputs(replay=False)
    contract = frontier.seven.load_contract()
    for lane in result["lanes"]:
        evaluation = frontier.seven.evaluate(lane["categories"], inputs, contract)
        assert evaluation["hard_gate_failures"] == []
        assert evaluation["objective"] == lane["objective"]
        assert len(lane["objective"]) == 6
        assert lane["search"]["ranking"] == (
            "six-component objective then maximum canonical category tuple"
        )
        contrasts = lane["contrast"]
        assert (
            min(
                contrasts[role][state][background]
                for role in contrasts
                for state in contrasts[role]
                for background in contrasts[role][state]
            )
            >= 3.0
        )


def test_variants_differ_materially_in_transformed_free_pair(result) -> None:
    points = [
        np.concatenate(
            [
                np.asarray(lane["free_1_transformed_oklch"]),
                np.asarray(lane["free_2_transformed_oklch"]),
            ]
        )
        for lane in result["lanes"]
    ]
    for left in range(len(points)):
        for right in range(left + 1, len(points)):
            assert np.linalg.norm(points[left] - points[right]) >= 0.02


def test_ranking_has_no_baseline_proximity_or_named_gold_objective(result) -> None:
    assert result["proximity_or_named_gold_objective"] is False
    assert result["ranking_policy"] == (
        "de novo six-component objective; canonical tuple only after exact equality"
    )
    source = (SEVEN / "hue_frontier.py").read_text()
    assert "target_distance" not in source
    assert "baseline hue" not in source.lower()
    assert "maximin-clique" not in source
    assert "maximum-clique" not in source
    assert "assert " not in source


def test_frontier_is_byte_deterministic(result) -> None:
    original = frontier.source_binding
    frontier.source_binding = lambda path: {
        "file": path.name,
        "sha256": "0" * 64,
        "commit": "0" * 40,
    }
    try:
        replay = frontier.run()
    finally:
        frontier.source_binding = original
    assert frontier.json_bytes(replay) == frontier.json_bytes(result)


def test_committed_hue_frontier_artifacts_are_fresh() -> None:
    directory = SEVEN / "hue-frontier"
    actual = {name: json.loads((directory / name).read_text()) for name in frontier.EXPECTED_FILES}
    expected = frontier.payloads(frontier.run())
    assert_committed_artifact_fresh(actual, expected)
