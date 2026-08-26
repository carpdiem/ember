from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from artifact_freshness import (
    NUMERIC_ABSOLUTE_TOLERANCE,
    assert_semantic_equal,
)


def fixture() -> dict:
    return {
        "schema_version": 1,
        "candidate_id": "a" * 64,
        "categories": ["#7C140A", "#857D0B"],
        "counts": {"observations": 30_240, "pairs": 90_720},
        "production": False,
        "metrics": {"primary": 8.679595273141931},
    }


def test_semantic_comparator_accepts_only_tiny_float_drift() -> None:
    expected = fixture()
    actual = deepcopy(expected)
    actual["metrics"]["primary"] += NUMERIC_ABSOLUTE_TOLERANCE * 0.5
    assert_semantic_equal(actual, expected)


def test_changed_candidate_hex_fails() -> None:
    expected = fixture()
    actual = deepcopy(expected)
    actual["categories"][1] = "#857D0C"
    with pytest.raises(AssertionError, match="exact scalar differs"):
        assert_semantic_equal(actual, expected)


def test_changed_candidate_id_fails() -> None:
    expected = fixture()
    actual = deepcopy(expected)
    actual["candidate_id"] = "b" * 64
    with pytest.raises(AssertionError, match="exact scalar differs"):
        assert_semantic_equal(actual, expected)


def test_changed_count_fails() -> None:
    expected = fixture()
    actual = deepcopy(expected)
    actual["counts"]["pairs"] += 1
    with pytest.raises(AssertionError, match="integer/count differs"):
        assert_semantic_equal(actual, expected)


def test_materially_changed_float_fails() -> None:
    expected = fixture()
    actual = deepcopy(expected)
    actual["metrics"]["primary"] += 1e-6
    with pytest.raises(AssertionError, match="float differs"):
        assert_semantic_equal(actual, expected)


def test_candidate_order_and_mapping_structure_are_exact() -> None:
    expected = fixture()
    actual = deepcopy(expected)
    actual["categories"] = list(reversed(actual["categories"]))
    with pytest.raises(AssertionError):
        assert_semantic_equal(actual, expected)

    extra = deepcopy(expected)
    extra["forged"] = True
    with pytest.raises(AssertionError, match="mapping keys differ"):
        assert_semantic_equal(extra, expected)
