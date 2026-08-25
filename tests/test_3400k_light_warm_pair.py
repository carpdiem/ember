from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SEVEN = ROOT / "docs/experiments/3400k-light-thin-marks/seven-point"
SPEC = importlib.util.spec_from_file_location("warm_pair_test", SEVEN / "warm_pair.py")
assert SPEC is not None and SPEC.loader is not None
warm = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = warm
SPEC.loader.exec_module(warm)


@pytest.fixture(scope="module")
def result():
    original = warm.source_binding
    warm.source_binding = lambda path: {"file": path.name, "sha256": "0" * 64, "commit": "0" * 40}
    try:
        return warm.run()
    finally:
        warm.source_binding = original


def test_exact_lane_contract_and_fixed_bytes(result) -> None:
    assert result["fixed_fg0"] == "#342F2C"
    assert result["fixed_four"] == list(warm.FIXED_FOUR)
    assert [row["lane"] for row in result["lanes"]] == [
        "LIFT-ONLY",
        "CLEAN-GOLD",
        "BRIGHT-WARM",
        "PHOTOPIC-2.7",
    ]
    for row in result["lanes"]:
        assert set(warm.FIXED_FOUR) < set(row["categories"])
        assert len(row["categories"]) == 6
        assert row["metrics"]["primary_raw_symmetric_scalar"] >= result["benchmark_prior_c_proxy"]


def test_three_compliant_lanes_have_zero_hard_failures_and_full_contrast(result) -> None:
    for row in result["lanes"][:3]:
        assert row["compliance"] == "FULL_3_0"
        assert row["hard_gate_failures"] == []
        assert (
            min(
                row["contrast"][role][state][background]
                for role in row["contrast"]
                for state in row["contrast"][role]
                for background in row["contrast"][role][state]
            )
            >= 3.0
        )


def test_photopic_lane_has_exactly_one_explicit_2_7_exception(result) -> None:
    row = result["lanes"][3]
    assert row["compliance"] == "TRANSFORMED_BG1_2_7_EXCEPTION"
    assert row["hard_gate_failures"] == [
        {
            "gate": "graphics-contrast/nominal-transformed/bg_1",
            "actual": row["contrast"]["warm_gold"]["transformed"]["bg_1"],
            "threshold": 3.0,
        }
    ]
    assert row["contrast"]["warm_gold"]["transformed"]["bg_1"] >= 2.7
    assert row["contrast"]["warm_gold"]["transformed"]["bg_1"] < 3.0
    assert "2.5" not in (SEVEN / "warm_pair.py").read_text()


def test_lanes_are_materially_distinct_after_transform(result) -> None:
    inputs = warm.seven.load_inputs(replay=False)
    gains = np.asarray(inputs.viewing["transform"]["gains"])
    points = []
    for row in result["lanes"]:
        points.append(
            np.concatenate(
                [
                    warm.srgb_to_oklab(warm.p3.parse_exact_hex8(row["warm_red"]) * gains),
                    warm.srgb_to_oklab(warm.p3.parse_exact_hex8(row["warm_gold"]) * gains),
                ]
            )
        )
    for left in range(len(points)):
        for right in range(left + 1, len(points)):
            assert np.linalg.norm(points[left] - points[right]) * 100.0 >= 2.0


def test_warm_search_is_byte_deterministic(result) -> None:
    original = warm.source_binding
    warm.source_binding = lambda path: {"file": path.name, "sha256": "0" * 64, "commit": "0" * 40}
    try:
        replay = warm.run()
    finally:
        warm.source_binding = original
    assert warm.json_bytes(replay) == warm.json_bytes(result)


def test_search_is_bounded_exact_and_not_exhaustive(result) -> None:
    assert result["catalog_summary"]["exact_hex8_count"] >= 7_000
    assert result["catalog_summary"]["custom_photopic_gold_count"] > 0
    for row in result["lanes"]:
        assert row["search"]["exact_evaluation_count"] <= 256
        assert row["search"]["exact_evaluation_cap"] == 256
        assert row["search"]["pair_evaluation_count"] > 0
    source = (SEVEN / "warm_pair.py").read_text()
    assert "maximum-clique" not in source
    assert "maximin-clique" not in source
    assert "assert " not in source
