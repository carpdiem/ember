#!/usr/bin/env python3
"""Prove the cross-theme 3400K categorical slot assignment exhaustively."""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ember.color import hex_to_srgb, srgb_to_oklab
from ember.definitions import FAMILIES

SLOT_COUNT = 6
EXPECTED_ASSIGNMENT_COUNT = 720
PROPOSED_OLD_INDICES_ONE_BASED = (2, 5, 1, 3, 4, 6)
PRODUCTION_OLD_INDICES_ONE_BASED = (2, 5, 6, 3, 4, 1)
SOURCE_HUE_ORDER_COMMANDED = (
    "#70002D",
    "#B25809",
    "#6C8D38",
    "#016869",
    "#4081D2",
    "#84499C",
)
SOURCE_HUE_ORDER_TRANSFORMED = (
    "#700018",
    "#B24105",
    "#6C681E",
    "#014D38",
    "#405F6F",
    "#843653",
)


def _family(slug: str):
    return next(family for family in FAMILIES if family.slug == slug)


def _labs(values: tuple[str, ...]) -> np.ndarray:
    return srgb_to_oklab(np.asarray([hex_to_srgb(value) for value in values]))


def _hues(lab: np.ndarray) -> np.ndarray:
    return np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360.0


def _hue_delta(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.abs((left - right + 180.0) % 360.0 - 180.0)


def score_assignment(permutation: tuple[int, ...]) -> dict[str, Any]:
    """Score one zero-based light-bank permutation against 3400K Dark slots.

    The optimization objective is the sum of exact Oklab ΔE across all six
    commanded slot pairs plus all six exact transformed-target slot pairs.
    Lower is better. Maximum hue mismatch is diagnostic and a deterministic
    secondary key; the permutation tuple is the final canonical tie-break.
    """

    if sorted(permutation) != list(range(SLOT_COUNT)):
        raise ValueError("assignment must be a permutation of six light colors")
    dark = _family("3400k-dark")
    dark_commanded = _labs(dark.categorical_colors)
    light_commanded = _labs(SOURCE_HUE_ORDER_COMMANDED)[list(permutation)]
    dark_transformed = _labs(dark.categorical_transformed_targets)
    light_transformed = _labs(SOURCE_HUE_ORDER_TRANSFORMED)[list(permutation)]
    commanded_distances = np.linalg.norm(dark_commanded - light_commanded, axis=1) * 100.0
    transformed_distances = np.linalg.norm(dark_transformed - light_transformed, axis=1) * 100.0
    commanded_hue_delta = _hue_delta(_hues(dark_commanded), _hues(light_commanded))
    transformed_hue_delta = _hue_delta(_hues(dark_transformed), _hues(light_transformed))
    return {
        "old_indices_one_based": [index + 1 for index in permutation],
        "commanded_slot_delta_e_ok": [float(value) for value in commanded_distances],
        "transformed_slot_delta_e_ok": [float(value) for value in transformed_distances],
        "commanded_total_delta_e_ok": float(commanded_distances.sum()),
        "transformed_total_delta_e_ok": float(transformed_distances.sum()),
        "total_delta_e_ok": float(commanded_distances.sum() + transformed_distances.sum()),
        "maximum_hue_mismatch_degrees": float(
            max(commanded_hue_delta.max(), transformed_hue_delta.max())
        ),
    }


def enumerate_assignments() -> list[dict[str, Any]]:
    rows = [
        score_assignment(permutation) for permutation in itertools.permutations(range(SLOT_COUNT))
    ]
    if len(rows) != EXPECTED_ASSIGNMENT_COUNT:
        raise RuntimeError("six-color assignment enumeration is incomplete")
    return sorted(
        rows,
        key=lambda row: (
            row["total_delta_e_ok"],
            row["maximum_hue_mismatch_degrees"],
            tuple(row["old_indices_one_based"]),
        ),
    )


def proof() -> dict[str, Any]:
    rows = enumerate_assignments()
    proposed = next(
        row for row in rows if tuple(row["old_indices_one_based"]) == PROPOSED_OLD_INDICES_ONE_BASED
    )
    production = rows[0]
    return {
        "schema_version": 1,
        "artifact_kind": "3400k-light-cross-theme-assignment-proof",
        "objective": {
            "direction": "minimize",
            "primary": (
                "sum of exact commanded Oklab delta E across six aligned slots plus "
                "sum of exact transformed-target Oklab delta E across six aligned slots"
            ),
            "secondary": "minimum maximum commanded/transformed circular Oklab hue mismatch",
            "canonical_tie_break": "lexicographically ascending one-based source-index tuple",
        },
        "assignment_count": len(rows),
        "production_rank": 1,
        "production": production,
        "proposed_rank": rows.index(proposed) + 1,
        "proposed": proposed,
    }


def main() -> int:
    print(json.dumps(proof(), indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
