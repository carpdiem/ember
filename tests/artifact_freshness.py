"""Cross-runtime freshness policy for capture-bound numerical artifacts."""

from __future__ import annotations

import math
import sys
from collections.abc import Mapping, Sequence
from typing import Any

NUMERIC_ABSOLUTE_TOLERANCE = 1e-9
CAPTURE_RUNTIME = sys.platform == "darwin" and sys.version_info >= (3, 11)
CAPTURE_RUNTIME_REASON = (
    "committed exact numerical artifact is bound to its Darwin Python 3.11+ capture runtime"
)


def _mismatch(message: str) -> None:
    raise AssertionError(message)


def assert_semantic_equal(
    actual: Any,
    expected: Any,
    *,
    path: str = "$",
    numeric_tolerance: float = NUMERIC_ABSOLUTE_TOLERANCE,
) -> None:
    """Require exact structure/identity and only tightly bounded float drift."""

    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if type(actual) is not type(expected) or actual != expected:
            raise AssertionError(f"{path}: exact scalar differs: {actual!r} != {expected!r}")
        return
    if isinstance(expected, int):
        if type(actual) is not int or actual != expected:
            raise AssertionError(f"{path}: exact integer/count differs: {actual!r} != {expected!r}")
        return
    if isinstance(expected, float):
        if type(actual) is not float:
            raise AssertionError(f"{path}: numeric type differs: {type(actual).__name__} != float")
        if not math.isfinite(actual) or not math.isfinite(expected):
            raise AssertionError(f"{path}: non-finite numerical artifact value")
        if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=numeric_tolerance):
            raise AssertionError(
                f"{path}: float differs by {abs(actual - expected)!r}, "
                f"tolerance={numeric_tolerance!r}"
            )
        return
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            _mismatch(f"{path}: expected mapping, got {type(actual).__name__}")
        if set(actual) != set(expected):
            raise AssertionError(
                f"{path}: mapping keys differ: {sorted(actual)!r} != {sorted(expected)!r}"
            )
        for key in expected:
            assert_semantic_equal(
                actual[key],
                expected[key],
                path=f"{path}.{key}",
                numeric_tolerance=numeric_tolerance,
            )
        return
    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes, bytearray)):
        if type(actual) is not type(expected):
            raise AssertionError(
                f"{path}: sequence type differs: {type(actual).__name__} != "
                f"{type(expected).__name__}"
            )
        if len(actual) != len(expected):
            raise AssertionError(f"{path}: sequence length/count differs")
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected, strict=True)):
            assert_semantic_equal(
                actual_item,
                expected_item,
                path=f"{path}[{index}]",
                numeric_tolerance=numeric_tolerance,
            )
        return
    raise AssertionError(f"{path}: unsupported artifact value type {type(expected).__name__}")


def assert_committed_artifact_fresh(actual: Any, expected: Any) -> None:
    """Use byte-equivalent JSON equality on capture runtime, semantic equality elsewhere."""

    if CAPTURE_RUNTIME:
        if actual != expected:
            raise AssertionError("capture-runtime committed artifact differs exactly")
        return
    assert_semantic_equal(actual, expected)
