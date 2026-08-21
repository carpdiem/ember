#!/usr/bin/env python3
"""Bounded exact-Hex8 search for the dark foreground-warmth experiment.

The foregrounds are fixed hypotheses.  Only dependent categorical, terminal,
and sequential banks are searched.  Every proposal is an exact consumer Hex8
value before scoring; two deterministic local-search seeds are retained for
all 3 profiles x 3 warmth lanes x 3 dependent banks.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from ember.color import (
    contrast_ratio,
    hex_to_srgb,
    oklab_to_srgb,
    pairwise_distances,
    perceived_lab,
    srgb_to_hex,
    srgb_to_oklab,
    warm_transform,
)
from ember.definitions import (
    BACKGROUND_SURFACE_ROLES,
    DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST,
    FAMILIES,
    GAIN_SENSITIVITY_FRACTION,
    MINIMUM_SHIFTED_FOREGROUND_CONTRAST,
    FamilyDefinition,
)
from ember.generate import _sequential_colors

PROFILE_SLUGS = ("3400k-dark", "2000k-dark", "1200k-dark")
LANES = {"current": 0.0, "halfway": 0.5, "full": 1.0}
BANKS = ("categorical", "terminal", "sequential")
LIGHT_TARGET = next(family for family in FAMILIES if family.slug == "3400k-light")
DEFAULT_ITERATIONS = {"categorical": 900, "terminal": 900, "sequential": 180}
SEED_BASES = {"categorical": 17000, "terminal": 27000, "sequential": 37000}
TERMINAL_HUE_CENTERS = np.asarray((20.0, 140.0, 82.0, 275.0, 335.0, 185.0))
# These bounds preserve the visual-maturity choices recorded in the prior
# Pareto pass.  Chroma alone did not reject the candy-like clipped frontiers.
CATEGORY_CHANNEL_CEILINGS = {
    "2000k-dark": {(1, 0): 233},  # rose red byte
    "1200k-dark": {(1, 1): 240},  # cyan green byte
}
DEEP_CATEGORY_CORNER_FOREGROUND_FLOORS = {"2000k-dark": 5.2, "1200k-dark": 4.7}


def family(slug: str) -> FamilyDefinition:
    return next(item for item in FAMILIES if item.slug == slug)


def hex_array(values: tuple[str, ...] | list[str]) -> np.ndarray:
    return np.asarray([hex_to_srgb(value) for value in values])


def bytes_from_hex(values: tuple[str, ...] | list[str]) -> np.ndarray:
    return np.asarray(
        [[int(value[index : index + 2], 16) for index in (1, 3, 5)] for value in values],
        dtype=np.int16,
    )


def hex_from_bytes(values: np.ndarray) -> tuple[str, ...]:
    clipped = np.clip(np.rint(values), 0, 255).astype(np.uint8)
    return tuple("#" + "".join(f"{channel:02X}" for channel in row) for row in clipped)


def transform_hex(value: str, gains: tuple[float, float, float]) -> str:
    return srgb_to_hex(warm_transform(hex_to_srgb(value), gains))


def foreground_lane(base: FamilyDefinition, weight: float) -> tuple[str, ...]:
    """Move only each role's Oklab a/b toward 3400K Light, preserving current L."""

    selected = []
    for index in range(3):
        current = srgb_to_oklab(hex_to_srgb(base.surfaces[f"fg_{index}"]))
        target = srgb_to_oklab(hex_to_srgb(LIGHT_TARGET.surfaces[f"fg_{index}"]))
        lab = np.array(
            [
                current[0],
                current[1] + weight * (target[1] - current[1]),
                current[2] + weight * (target[2] - current[2]),
            ]
        )
        selected.append(srgb_to_hex(np.clip(oklab_to_srgb(lab), 0.0, 1.0)))
    return tuple(selected)


def candidate_family(
    base: FamilyDefinition,
    foregrounds: tuple[str, ...],
    categorical: tuple[str, ...] | None = None,
    terminal: tuple[str, ...] | None = None,
    sequential: tuple[str, ...] | None = None,
) -> FamilyDefinition:
    surfaces = dict(base.surfaces)
    surfaces.update({f"fg_{index}": value for index, value in enumerate(foregrounds)})
    categorical_values = categorical or base.categorical_colors
    terminal_values = terminal or base.terminal_colors
    return replace(
        base,
        surfaces=surfaces,
        categorical_colors=categorical_values,
        categorical_transformed_targets=tuple(
            transform_hex(value, base.profile.gains) for value in categorical_values
        ),
        terminal_colors=terminal_values,
        terminal_transformed_targets=tuple(
            transform_hex(value, base.profile.gains) for value in terminal_values
        ),
        sequential_anchors=sequential or base.sequential_anchors,
    )


def hue_gap(lab: np.ndarray) -> float:
    chromatic = lab[np.linalg.norm(lab[:, 1:], axis=1) >= 0.02]
    if len(chromatic) < 2:
        return 0.0
    hues = np.degrees(np.arctan2(chromatic[:, 2], chromatic[:, 1])) % 360.0
    return min(
        abs((hues[left] - hues[right] + 180.0) % 360.0 - 180.0)
        for left in range(len(hues))
        for right in range(left + 1, len(hues))
    )


def circular_hue_error(lab: np.ndarray, reference: np.ndarray) -> np.ndarray:
    hue = np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360.0
    ref = np.degrees(np.arctan2(reference[:, 2], reference[:, 1])) % 360.0
    return np.abs((hue - ref + 180.0) % 360.0 - 180.0)


def hue_span(lab: np.ndarray) -> float:
    chromatic = lab[np.linalg.norm(lab[:, 1:], axis=1) >= 0.02]
    if len(chromatic) < 2:
        return 0.0
    hues = np.sort(np.degrees(np.arctan2(chromatic[:, 2], chromatic[:, 1])) % 360.0)
    gaps = np.diff(np.concatenate((hues, hues[:1] + 360.0)))
    return float(360.0 - gaps.max())


def minimum_chroma_vector_cosine(lab: np.ndarray) -> float:
    chroma = lab[:, 1:]
    unit = chroma / np.linalg.norm(chroma, axis=1, keepdims=True)
    similarities = unit @ unit.T
    return float(similarities[np.triu_indices(len(lab), k=1)].min())


def violation(value: float, floor: float | None = None, ceiling: float | None = None) -> float:
    if floor is not None and value < floor:
        return floor - value
    if ceiling is not None and value > ceiling:
        return value - ceiling
    return 0.0


def penalty(violations: list[float]) -> float:
    values = np.asarray(violations, dtype=float)
    return 1e8 * float(np.dot(values, values))


def foreground_metrics(base: FamilyDefinition, foregrounds: tuple[str, ...]) -> dict[str, Any]:
    rgb = hex_array(foregrounds)
    day = srgb_to_oklab(rgb)
    night = perceived_lab(rgb, base.profile.gains)
    day_vectors = np.diff(day, axis=0)
    night_vectors = np.diff(night, axis=0)
    day_steps = np.linalg.norm(day_vectors, axis=1) * 100.0
    night_steps = np.linalg.norm(night_vectors, axis=1) * 100.0
    backgrounds = hex_array(tuple(base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES))
    transformed_backgrounds = warm_transform(backgrounds, base.profile.gains)
    transformed_foregrounds = warm_transform(rgb, base.profile.gains)
    contrasts = np.asarray(
        [
            [contrast_ratio(foreground, background) for background in transformed_backgrounds]
            for foreground in transformed_foregrounds
        ]
    )
    day_chroma = np.linalg.norm(day[:, 1:], axis=1)
    current_day = srgb_to_oklab(
        hex_array(tuple(base.surfaces[f"fg_{index}"] for index in range(3)))
    )
    current_mean = float(np.linalg.norm(current_day[:, 1:], axis=1).mean())
    day_gaps = np.abs(np.diff(day[:, 0]))
    night_gaps = np.abs(np.diff(night[:, 0]))
    return {
        "normal_adjacent_delta_e_ok": day_steps.tolist(),
        "shifted_adjacent_delta_e_ok": night_steps.tolist(),
        "normal_lightness": day[:, 0].tolist(),
        "normal_chroma": day_chroma.tolist(),
        "normal_mean_chroma": float(day_chroma.mean()),
        "normal_mean_plus_b": float(day[:, 2].mean()),
        "chroma_reduction_vs_current_percent": float(
            100.0 * (current_mean - day_chroma.mean()) / current_mean
        ),
        "normal_lightness_gap_ratio": float(day_gaps.min() / day_gaps.max()),
        "shifted_lightness_gap_ratio": float(night_gaps.min() / night_gaps.max()),
        "normal_lightness_share": (
            np.abs(day_vectors[:, 0]) / np.linalg.norm(day_vectors, axis=1)
        ).tolist(),
        "shifted_lightness_share": (
            np.abs(night_vectors[:, 0]) / np.linalg.norm(night_vectors, axis=1)
        ).tolist(),
        "normal_hue_span_degrees": hue_span(day),
        "shifted_hue_span_degrees": hue_span(night),
        "normal_chroma_vector_cosine": minimum_chroma_vector_cosine(day),
        "shifted_chroma_vector_cosine": minimum_chroma_vector_cosine(night),
        "shifted_chroma": np.linalg.norm(night[:, 1:], axis=1).tolist(),
        "worst_surface_shifted_contrast": contrasts.min(axis=1).tolist(),
    }


def gain_corners(gains: tuple[float, float, float]) -> list[tuple[float, float, float]]:
    red, green, blue = gains
    scales = (1.0 - GAIN_SENSITIVITY_FRACTION, 1.0 + GAIN_SENSITIVITY_FRACTION)
    return [
        (red, green * green_scale, blue * blue_scale if blue else 0.0)
        for green_scale in scales
        for blue_scale in scales
    ]


def accent_metrics(
    base: FamilyDefinition,
    values: tuple[str, ...],
    foregrounds: tuple[str, ...],
    *,
    terminal: bool,
) -> dict[str, Any]:
    rgb = hex_array(values)
    foreground_rgb = hex_array(foregrounds)
    backgrounds = hex_array(tuple(base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES))
    day = srgb_to_oklab(rgb)
    night = perceived_lab(rgb, base.profile.gains)
    foreground_day = srgb_to_oklab(foreground_rgb)
    foreground_night = perceived_lab(foreground_rgb, base.profile.gains)
    day_fg = np.linalg.norm(day[:, None] - foreground_day[None, :], axis=2).min(axis=0) * 100.0
    night_fg = (
        np.linalg.norm(night[:, None] - foreground_night[None, :], axis=2).min(axis=0) * 100.0
    )
    transformed = warm_transform(rgb, base.profile.gains)
    transformed_backgrounds = warm_transform(backgrounds, base.profile.gains)
    day_contrast = np.asarray(
        [[contrast_ratio(color, background) for background in backgrounds] for color in rgb]
    )
    night_contrast = np.asarray(
        [
            [contrast_ratio(color, background) for background in transformed_backgrounds]
            for color in transformed
        ]
    )
    if terminal:
        groups = np.asarray(base.terminal_night_groups)
        centers = np.asarray(
            [night[groups == group].mean(axis=0) for group in sorted(set(groups.tolist()))]
        )
        night_pair = float(pairwise_distances(centers).min()) if len(centers) > 1 else 0.0
    else:
        night_pair = float(pairwise_distances(night).min())
    corner_rows = []
    for corner in gain_corners(base.profile.gains):
        corner_lab = perceived_lab(rgb, corner)
        if terminal:
            groups = np.asarray(base.terminal_night_groups)
            corner_centers = np.asarray(
                [corner_lab[groups == group].mean(axis=0) for group in sorted(set(groups.tolist()))]
            )
            corner_pair = (
                float(pairwise_distances(corner_centers).min()) if len(corner_centers) > 1 else 0.0
            )
        else:
            corner_pair = float(pairwise_distances(corner_lab).min())
        corner_fg = perceived_lab(foreground_rgb, corner)
        shifted_background = warm_transform(backgrounds[0], corner)
        corner_rows.append(
            {
                "gains": list(corner),
                "pair_delta_e_ok": corner_pair,
                "foreground_clearance_delta_e_ok": float(
                    np.linalg.norm(corner_lab[:, None] - corner_fg[None, :], axis=2).min() * 100.0
                ),
                "background_contrast": min(
                    contrast_ratio(warm_transform(color, corner), shifted_background)
                    for color in rgb
                ),
            }
        )
    return {
        "normal_pair_delta_e_ok": float(pairwise_distances(day).min()),
        "shifted_pair_delta_e_ok": night_pair,
        "normal_foreground_clearance_by_role": day_fg.tolist(),
        "shifted_foreground_clearance_by_role": night_fg.tolist(),
        "normal_foreground_clearance_min": float(day_fg.min()),
        "shifted_foreground_clearance_min": float(night_fg.min()),
        "normal_background_contrast_min": float(day_contrast.min()),
        "shifted_background_contrast_bg0_min": float(night_contrast[:, 0].min()),
        "shifted_background_contrast_all_surfaces_min": float(night_contrast.min()),
        "normal_hue_gap_degrees": float(hue_gap(day)),
        "normal_mean_chroma": float(np.linalg.norm(day[:, 1:], axis=1).mean()),
        "normal_max_chroma": float(np.linalg.norm(day[:, 1:], axis=1).max()),
        "normal_semantic_hue_error_max": (
            float(
                np.abs(
                    (
                        (np.degrees(np.arctan2(day[:, 2], day[:, 1])) % 360.0)
                        - TERMINAL_HUE_CENTERS[: len(day)]
                        + 180.0
                    )
                    % 360.0
                    - 180.0
                ).max()
            )
            if terminal
            else None
        ),
        "gain_corner_samples": corner_rows,
        "gain_corner_pair_min": min(row["pair_delta_e_ok"] for row in corner_rows),
        "gain_corner_foreground_clearance_min": min(
            row["foreground_clearance_delta_e_ok"] for row in corner_rows
        ),
        "gain_corner_background_contrast_min": min(
            row["background_contrast"] for row in corner_rows
        ),
    }


def sequential_metrics(
    base: FamilyDefinition, anchors: tuple[str, ...]
) -> tuple[dict[str, Any], np.ndarray]:
    candidate = replace(base, sequential_anchors=anchors)
    sequence = np.round(_sequential_colors(candidate), 10)
    day = srgb_to_oklab(sequence)
    night = perceived_lab(sequence, base.profile.gains)
    day_steps = np.linalg.norm(np.diff(day, axis=0), axis=1) * 100.0
    night_steps = np.linalg.norm(np.diff(night, axis=0), axis=1) * 100.0
    day_direction = 1.0 if day[-1, 0] >= day[0, 0] else -1.0
    night_direction = 1.0 if night[-1, 0] >= night[0, 0] else -1.0
    corner_rows = []
    for corner in gain_corners(base.profile.gains):
        lab = perceived_lab(sequence, corner)
        steps = np.linalg.norm(np.diff(lab, axis=0), axis=1) * 100.0
        direction = 1.0 if lab[-1, 0] >= lab[0, 0] else -1.0
        corner_rows.append(
            {
                "gains": list(corner),
                "cv": float(steps.std() / steps.mean()),
                "max_to_min": float(steps.max() / steps.min()),
                "minimum_signed_lightness_step": float((np.diff(lab[:, 0]) * direction).min()),
            }
        )
    metrics = {
        "normal_cv": float(day_steps.std() / day_steps.mean()),
        "normal_max_to_min": float(day_steps.max() / day_steps.min()),
        "shifted_cv": float(night_steps.std() / night_steps.mean()),
        "shifted_max_to_min": float(night_steps.max() / night_steps.min()),
        "normal_lightness_range": float(np.ptp(day[:, 0])),
        "shifted_lightness_range": float(np.ptp(night[:, 0])),
        "normal_minimum_signed_lightness_step": float((np.diff(day[:, 0]) * day_direction).min()),
        "shifted_minimum_signed_lightness_step": float(
            (np.diff(night[:, 0]) * night_direction).min()
        ),
        "gain_corner_samples": corner_rows,
        "gain_corner_cv_max": max(row["cv"] for row in corner_rows),
        "gain_corner_max_to_min_max": max(row["max_to_min"] for row in corner_rows),
        "gain_corner_minimum_signed_lightness_step": min(
            row["minimum_signed_lightness_step"] for row in corner_rows
        ),
    }
    return metrics, sequence


def categorical_objective(
    base: FamilyDefinition,
    foregrounds: tuple[str, ...],
    values: tuple[str, ...],
) -> float:
    metrics = accent_metrics(base, values, foregrounds, terminal=False)
    intrinsic_violations = [
        violation(metrics["normal_pair_delta_e_ok"], base.daylight_minimum_delta_e_ok),
        violation(metrics["shifted_pair_delta_e_ok"], base.profile.categorical_threshold),
        violation(
            metrics["normal_hue_gap_degrees"],
            base.daylight_minimum_hue_gap_degrees or 0.0,
        ),
        violation(
            metrics["shifted_background_contrast_bg0_min"],
            base.categorical_shifted_background_contrast_minimum or 0.0,
        ),
        violation(metrics["normal_mean_chroma"], 0.09),
        violation(metrics["normal_mean_chroma"], ceiling=0.105),
    ]
    proposed_lab = srgb_to_oklab(hex_array(values))
    intrinsic_violations.append(
        violation(float(np.linalg.norm(proposed_lab[:, 1:], axis=1).max()), ceiling=0.111)
    )
    proposed_bytes = bytes_from_hex(values)
    for (color_index, channel_index), ceiling in CATEGORY_CHANNEL_CEILINGS.get(
        base.slug, {}
    ).items():
        intrinsic_violations.append(
            violation(float(proposed_bytes[color_index, channel_index]), ceiling=float(ceiling))
        )
    if base.slug in DEEP_CATEGORY_CORNER_FOREGROUND_FLOORS:
        intrinsic_violations.extend(
            (
                violation(metrics["gain_corner_pair_min"], base.profile.categorical_threshold),
                violation(metrics["gain_corner_background_contrast_min"], 3.0),
            )
        )
    if any(intrinsic_violations):
        return 1e14 + penalty(intrinsic_violations)
    violations = []
    if base.slug in DEEP_CATEGORY_CORNER_FOREGROUND_FLOORS:
        violations.append(
            violation(
                metrics["gain_corner_foreground_clearance_min"],
                DEEP_CATEGORY_CORNER_FOREGROUND_FLOORS[base.slug],
            )
        )
    violations.extend(
        violation(value, base.categorical_daylight_minimum_foreground_delta_e_ok)
        for value in metrics["normal_foreground_clearance_by_role"]
    )
    violations.extend(
        violation(value, base.categorical_night_minimum_foreground_delta_e_ok)
        for value in metrics["shifted_foreground_clearance_by_role"]
    )
    current = srgb_to_oklab(hex_array(base.categorical_colors))
    proposed = srgb_to_oklab(hex_array(values))
    move = float(np.linalg.norm(proposed - current, axis=1).mean())
    soft = (
        -0.020 * metrics["normal_pair_delta_e_ok"]
        - 0.055 * metrics["shifted_pair_delta_e_ok"]
        - 0.030 * metrics["shifted_foreground_clearance_min"]
        - 0.18 * metrics["shifted_background_contrast_all_surfaces_min"]
        - 0.020 * metrics["gain_corner_pair_min"]
        + 9.0 * move
    )
    return penalty(violations) + soft


def terminal_objective(
    base: FamilyDefinition,
    foregrounds: tuple[str, ...],
    values: tuple[str, ...],
) -> float:
    metrics = accent_metrics(base, values, foregrounds, terminal=True)
    day_floors = (
        base.terminal_daylight_minimum_fg_0_delta_e_ok,
        base.terminal_daylight_minimum_fg_1_delta_e_ok,
        base.terminal_daylight_minimum_fg_2_delta_e_ok,
    )
    night_floors = (
        base.terminal_night_minimum_fg_0_delta_e_ok,
        base.terminal_night_minimum_fg_1_delta_e_ok,
        base.terminal_night_minimum_fg_2_delta_e_ok,
    )
    proposed = srgb_to_oklab(hex_array(values))
    current = srgb_to_oklab(hex_array(base.terminal_colors))
    proposed_hues = np.degrees(np.arctan2(proposed[:, 2], proposed[:, 1])) % 360.0
    hue_errors = np.abs(
        (proposed_hues - TERMINAL_HUE_CENTERS[: len(values)] + 180.0) % 360.0 - 180.0
    )
    terminal_chroma_ceiling = float(np.linalg.norm(current[:, 1:], axis=1).max()) + 1e-12
    intrinsic_violations = [
        violation(metrics["normal_pair_delta_e_ok"], base.terminal_daylight_minimum_delta_e_ok),
        violation(
            metrics["shifted_pair_delta_e_ok"], base.terminal_night_minimum_delta_e_ok or 0.0
        ),
        violation(metrics["shifted_background_contrast_bg0_min"], 4.5),
        violation(float(hue_errors.max()), ceiling=30.0),
        violation(
            float(np.linalg.norm(proposed[:, 1:], axis=1).max()),
            ceiling=terminal_chroma_ceiling,
        ),
    ]
    if any(intrinsic_violations):
        return 1e14 + penalty(intrinsic_violations)
    violations = []
    violations.extend(
        violation(value, floor or 0.0)
        for value, floor in zip(
            metrics["normal_foreground_clearance_by_role"], day_floors, strict=True
        )
    )
    violations.extend(
        violation(value, floor or 0.0)
        for value, floor in zip(
            metrics["shifted_foreground_clearance_by_role"], night_floors, strict=True
        )
    )
    move = float(np.linalg.norm(proposed - current, axis=1).mean())
    soft = (
        -0.020 * metrics["normal_pair_delta_e_ok"]
        - 0.060 * metrics["shifted_pair_delta_e_ok"]
        - 0.035 * metrics["shifted_foreground_clearance_min"]
        - 0.20 * metrics["shifted_background_contrast_all_surfaces_min"]
        - 0.020 * metrics["gain_corner_pair_min"]
        + 10.0 * move
    )
    return penalty(violations) + soft


def sequential_objective(
    base: FamilyDefinition,
    baseline_metrics: dict[str, Any],
    values: tuple[str, ...],
) -> float:
    metrics, _ = sequential_metrics(base, values)
    violations = [
        violation(metrics["normal_lightness_range"], 0.5),
        violation(metrics["shifted_lightness_range"], 0.5),
        violation(metrics["normal_minimum_signed_lightness_step"], 1e-9),
        violation(metrics["shifted_minimum_signed_lightness_step"], 1e-9),
        violation(
            metrics["normal_cv"],
            ceiling=max(0.18, baseline_metrics["normal_cv"] + 0.002),
        ),
        violation(
            metrics["normal_max_to_min"],
            ceiling=max(1.6, baseline_metrics["normal_max_to_min"] + 0.02),
        ),
        violation(
            metrics["shifted_cv"],
            ceiling=max(0.0001, baseline_metrics["shifted_cv"] + 0.00005),
        ),
        violation(
            metrics["shifted_max_to_min"],
            ceiling=max(1.001, baseline_metrics["shifted_max_to_min"] + 0.001),
        ),
    ]
    current = srgb_to_oklab(hex_array(base.sequential_anchors))
    proposed = srgb_to_oklab(hex_array(values))
    move = float(np.linalg.norm(proposed - current, axis=1).mean())
    soft = (
        0.8 * metrics["normal_cv"]
        + 1.2 * metrics["shifted_cv"]
        + 5.0 * move
        - 0.02 * metrics["normal_lightness_range"]
        - 0.02 * metrics["shifted_lightness_range"]
    )
    return penalty(violations) + soft


def bounded_exact_search(
    base_values: tuple[str, ...],
    objective: Callable[[tuple[str, ...]], float],
    *,
    seed: int,
    iterations: int,
    radius: int,
) -> dict[str, Any]:
    """Deterministic bounded stochastic hill-climb over exact byte proposals."""

    rng = np.random.default_rng(seed)
    origin = bytes_from_hex(base_values)
    best = origin.copy()
    best_values = hex_from_bytes(best)
    best_score = objective(best_values)
    accepted = 0
    evaluated = 1
    for iteration in range(iterations):
        progress = iteration / max(1, iterations - 1)
        step = max(1, round(radius * (1.0 - progress) + 1.0))
        proposal = best.copy()
        edits = 1 + int(rng.integers(0, min(4, proposal.size)))
        flat = proposal.reshape(-1)
        indices = rng.choice(flat.size, size=edits, replace=False)
        flat[indices] += rng.integers(-step, step + 1, size=edits, dtype=np.int16)
        proposal = np.clip(proposal, origin - radius, origin + radius)
        values = hex_from_bytes(proposal)
        score = objective(values)
        evaluated += 1
        if score < best_score - 1e-12 or (
            abs(score - best_score) <= 1e-12 and values < best_values
        ):
            best = proposal
            best_values = values
            best_score = score
            accepted += 1
    return {
        "seed": seed,
        "iterations": iterations,
        "evaluated_exact_hex8_candidates": evaluated,
        "accepted_moves": accepted,
        "objective": float(best_score),
        "selected": list(best_values),
    }


def select_two_seed_runs(runs: list[dict[str, Any]]) -> tuple[tuple[str, ...], dict[str, Any]]:
    selected = min(runs, key=lambda row: (row["objective"], tuple(row["selected"])))
    return tuple(selected["selected"]), selected


def foreground_failures(base: FamilyDefinition, metrics: dict[str, Any]) -> list[str]:
    failures = []
    contrast_floors = (
        DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST[base.slug],
        MINIMUM_SHIFTED_FOREGROUND_CONTRAST["fg_1"],
        MINIMUM_SHIFTED_FOREGROUND_CONTRAST["fg_2"],
    )
    for index, (actual, floor) in enumerate(
        zip(metrics["worst_surface_shifted_contrast"], contrast_floors, strict=True)
    ):
        if actual + 1e-12 < floor:
            failures.append(f"fg_{index} transformed contrast {actual:.4f} < {floor:.4f}")
    checks = (
        (
            min(metrics["normal_adjacent_delta_e_ok"]),
            base.foreground_daylight_minimum_adjacent_delta_e_ok,
            "foreground day adjacent min",
        ),
        (
            max(metrics["normal_adjacent_delta_e_ok"]),
            base.foreground_daylight_maximum_adjacent_delta_e_ok,
            "foreground day adjacent max",
            "max",
        ),
        (
            min(metrics["shifted_adjacent_delta_e_ok"]),
            base.foreground_night_minimum_adjacent_delta_e_ok,
            "foreground transformed adjacent min",
        ),
        (
            max(metrics["shifted_adjacent_delta_e_ok"]),
            base.foreground_night_maximum_adjacent_delta_e_ok,
            "foreground transformed adjacent max",
            "max",
        ),
        (
            metrics["normal_lightness_gap_ratio"],
            base.foreground_minimum_lightness_gap_ratio,
            "foreground day lightness-gap ratio",
        ),
        (
            metrics["shifted_lightness_gap_ratio"],
            base.foreground_minimum_lightness_gap_ratio,
            "foreground transformed lightness-gap ratio",
        ),
        (
            min(metrics["normal_lightness_share"]),
            base.foreground_daylight_minimum_lightness_share,
            "foreground day lightness share",
        ),
        (
            min(metrics["shifted_lightness_share"]),
            base.foreground_night_minimum_lightness_share,
            "foreground transformed lightness share",
        ),
    )
    for row in checks:
        actual, target, label, *mode = row
        if target is None:
            continue
        if mode and mode[0] == "max":
            if actual > target + 1e-12:
                failures.append(f"{label} {actual:.4f} > {target:.4f}")
        elif actual + 1e-12 < target:
            failures.append(f"{label} {actual:.4f} < {target:.4f}")
    maxima = (
        (
            metrics["normal_hue_span_degrees"],
            base.foreground_maximum_hue_span_degrees,
            "foreground day hue span",
        ),
        (
            metrics["shifted_hue_span_degrees"],
            base.foreground_night_maximum_hue_span_degrees,
            "foreground transformed hue span",
        ),
        (
            max(metrics["normal_chroma"]),
            base.foreground_maximum_chroma,
            "foreground day maximum chroma",
        ),
    )
    for actual, ceiling, label in maxima:
        if ceiling is not None and actual > ceiling + 1e-12:
            failures.append(f"{label} {actual:.4f} > {ceiling:.4f}")
    minima = (
        (
            metrics["normal_chroma_vector_cosine"],
            base.foreground_daylight_minimum_chroma_vector_cosine,
            "foreground day chroma-vector cosine",
        ),
        (
            metrics["shifted_chroma_vector_cosine"],
            base.foreground_night_minimum_chroma_vector_cosine,
            "foreground transformed chroma-vector cosine",
        ),
    )
    for actual, floor, label in minima:
        if floor is not None and actual + 1e-12 < floor:
            failures.append(f"{label} {actual:.4f} < {floor:.4f}")
    direction = 1.0 if base.foreground_chroma_direction == "decreasing" else -1.0
    tolerance = base.foreground_chroma_order_tolerance or 0.0
    for state, values in (
        ("day", metrics["normal_chroma"]),
        ("transformed", metrics["shifted_chroma"]),
    ):
        excess = float((np.diff(np.asarray(values)) * direction).max())
        if excess > tolerance + 1e-12:
            failures.append(
                f"foreground {state} chroma direction excess {excess:.4f} > {tolerance:.4f}"
            )
    return failures


def dependent_failures(
    base: FamilyDefinition,
    category_values: tuple[str, ...],
    category: dict[str, Any],
    terminal_values: tuple[str, ...],
    terminal: dict[str, Any],
    sequential: dict[str, Any],
    sequential_baseline: dict[str, Any],
) -> list[str]:
    failures = []

    def minimum(label: str, actual: float, floor: float | None) -> None:
        if floor is not None and actual + 1e-12 < floor:
            failures.append(f"{label} {actual:.4f} < {floor:.4f}")

    def maximum(label: str, actual: float, ceiling: float) -> None:
        if actual > ceiling + 1e-12:
            failures.append(f"{label} {actual:.6f} > {ceiling:.6f}")

    minimum(
        "categorical day pair", category["normal_pair_delta_e_ok"], base.daylight_minimum_delta_e_ok
    )
    minimum(
        "categorical transformed pair",
        category["shifted_pair_delta_e_ok"],
        base.profile.categorical_threshold,
    )
    minimum(
        "categorical day hue gap",
        category["normal_hue_gap_degrees"],
        base.daylight_minimum_hue_gap_degrees,
    )
    minimum("categorical day mean chroma", category["normal_mean_chroma"], 0.09)
    maximum("categorical day mean chroma", category["normal_mean_chroma"], 0.105)
    maximum("categorical day maximum chroma", category["normal_max_chroma"], 0.111)
    minimum(
        "categorical transformed bg contrast",
        category["shifted_background_contrast_bg0_min"],
        base.categorical_shifted_background_contrast_minimum,
    )
    for index, value in enumerate(category["normal_foreground_clearance_by_role"]):
        minimum(
            f"categorical day fg_{index} clearance",
            value,
            base.categorical_daylight_minimum_foreground_delta_e_ok,
        )
    for index, value in enumerate(category["shifted_foreground_clearance_by_role"]):
        minimum(
            f"categorical transformed fg_{index} clearance",
            value,
            base.categorical_night_minimum_foreground_delta_e_ok,
        )
    category_bytes = bytes_from_hex(category_values)
    for (color_index, channel_index), ceiling in CATEGORY_CHANNEL_CEILINGS.get(
        base.slug, {}
    ).items():
        maximum(
            f"categorical maturity byte color {color_index} channel {channel_index}",
            float(category_bytes[color_index, channel_index]),
            float(ceiling),
        )
    if base.slug in DEEP_CATEGORY_CORNER_FOREGROUND_FLOORS:
        minimum(
            "categorical sampled-corner pair",
            category["gain_corner_pair_min"],
            base.profile.categorical_threshold,
        )
        minimum(
            "categorical sampled-corner foreground clearance",
            category["gain_corner_foreground_clearance_min"],
            DEEP_CATEGORY_CORNER_FOREGROUND_FLOORS[base.slug],
        )
        minimum(
            "categorical sampled-corner background contrast",
            category["gain_corner_background_contrast_min"],
            3.0,
        )

    minimum(
        "terminal day pair",
        terminal["normal_pair_delta_e_ok"],
        base.terminal_daylight_minimum_delta_e_ok,
    )
    minimum(
        "terminal transformed pair",
        terminal["shifted_pair_delta_e_ok"],
        base.terminal_night_minimum_delta_e_ok,
    )
    minimum(
        "terminal transformed bg contrast", terminal["shifted_background_contrast_bg0_min"], 4.5
    )
    maximum("terminal semantic hue error", terminal["normal_semantic_hue_error_max"], 30.0)
    shipped_terminal_chroma_max = float(
        np.linalg.norm(srgb_to_oklab(hex_array(base.terminal_colors))[:, 1:], axis=1).max()
    )
    maximum(
        "terminal commanded maximum chroma",
        terminal["normal_max_chroma"],
        shipped_terminal_chroma_max + 1e-12,
    )
    day_floors = (
        base.terminal_daylight_minimum_fg_0_delta_e_ok,
        base.terminal_daylight_minimum_fg_1_delta_e_ok,
        base.terminal_daylight_minimum_fg_2_delta_e_ok,
    )
    night_floors = (
        base.terminal_night_minimum_fg_0_delta_e_ok,
        base.terminal_night_minimum_fg_1_delta_e_ok,
        base.terminal_night_minimum_fg_2_delta_e_ok,
    )
    for index, (value, floor) in enumerate(
        zip(terminal["normal_foreground_clearance_by_role"], day_floors, strict=True)
    ):
        minimum(f"terminal day fg_{index} clearance", value, floor)
    for index, (value, floor) in enumerate(
        zip(terminal["shifted_foreground_clearance_by_role"], night_floors, strict=True)
    ):
        minimum(f"terminal transformed fg_{index} clearance", value, floor)

    minimum("sequential day lightness range", sequential["normal_lightness_range"], 0.5)
    minimum("sequential transformed lightness range", sequential["shifted_lightness_range"], 0.5)
    minimum(
        "sequential day monotonic step", sequential["normal_minimum_signed_lightness_step"], 1e-9
    )
    minimum(
        "sequential transformed monotonic step",
        sequential["shifted_minimum_signed_lightness_step"],
        1e-9,
    )
    maximum(
        "sequential day CV",
        sequential["normal_cv"],
        max(0.18, sequential_baseline["normal_cv"] + 0.002),
    )
    maximum(
        "sequential transformed CV",
        sequential["shifted_cv"],
        max(0.0001, sequential_baseline["shifted_cv"] + 0.00005),
    )
    maximum(
        "sequential day max:min",
        sequential["normal_max_to_min"],
        max(1.6, sequential_baseline["normal_max_to_min"] + 0.02),
    )
    maximum(
        "sequential transformed max:min",
        sequential["shifted_max_to_min"],
        max(1.001, sequential_baseline["shifted_max_to_min"] + 0.001),
    )
    return failures


def run_experiment(iterations: dict[str, int] | None = None) -> dict[str, Any]:
    iterations = iterations or DEFAULT_ITERATIONS
    output: dict[str, Any] = {
        "schema": 1,
        "method": (
            "bounded stochastic hill-climb over exact quantized Hex8 candidates; "
            "controlled identical seed pairs for categorical/terminal per profile x lane; "
            "sequential searched once per profile and reused across lanes because its objective "
            "is foreground-invariant; foreground lanes fixed by construction"
        ),
        "foreground_target": "corresponding 3400k-light fg role Oklab a/b, preserving each dark role current Oklab L",
        "lanes": {name: weight for name, weight in LANES.items()},
        "profiles": {},
    }
    for profile_index, slug in enumerate(PROFILE_SLUGS):
        base = family(slug)
        profile_record: dict[str, Any] = {
            "name": base.name,
            "gains": list(base.profile.gains),
            "shipped": {
                "surfaces": {role: base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES},
                "foregrounds": [base.surfaces[f"fg_{index}"] for index in range(3)],
                "categorical": list(base.categorical_colors),
                "terminal": list(base.terminal_colors),
                "terminal_ansi_indices": list(base.terminal_ansi_indices),
                "terminal_night_groups": list(base.terminal_night_groups),
                "sequential_anchors": list(base.sequential_anchors),
            },
            "candidates": {},
        }
        sequential_baseline, _ = sequential_metrics(base, base.sequential_anchors)
        controlled_seed_offset = profile_index * 100
        seq_runs = [
            bounded_exact_search(
                base.sequential_anchors,
                lambda values, base=base, baseline=sequential_baseline: sequential_objective(
                    base, baseline, values
                ),
                seed=SEED_BASES["sequential"] + controlled_seed_offset + seed_add,
                iterations=iterations["sequential"],
                radius=10,
            )
            for seed_add in (0, 1)
        ]
        sequential, selected_seq_run = select_two_seed_runs(seq_runs)
        sequential_record, sequence = sequential_metrics(base, sequential)
        for lane, weight in LANES.items():
            print(f"{slug} / {lane}", flush=True)
            foregrounds = foreground_lane(base, weight)
            foreground = foreground_metrics(base, foregrounds)
            cat_runs = []
            term_runs = []
            for seed_add in (0, 1):
                cat_runs.append(
                    bounded_exact_search(
                        base.categorical_colors,
                        lambda values, base=base, foregrounds=foregrounds: categorical_objective(
                            base, foregrounds, values
                        ),
                        seed=SEED_BASES["categorical"] + controlled_seed_offset + seed_add,
                        iterations=iterations["categorical"],
                        radius=18,
                    )
                )
                term_runs.append(
                    bounded_exact_search(
                        base.terminal_colors,
                        lambda values, base=base, foregrounds=foregrounds: terminal_objective(
                            base, foregrounds, values
                        ),
                        seed=SEED_BASES["terminal"] + controlled_seed_offset + seed_add,
                        iterations=iterations["terminal"],
                        radius=16,
                    )
                )
            categorical, selected_cat_run = select_two_seed_runs(cat_runs)
            terminal, selected_term_run = select_two_seed_runs(term_runs)
            category_metrics = accent_metrics(base, categorical, foregrounds, terminal=False)
            terminal_metrics = accent_metrics(base, terminal, foregrounds, terminal=True)
            fg_failures = foreground_failures(base, foreground)
            bank_failures = dependent_failures(
                base,
                categorical,
                category_metrics,
                terminal,
                terminal_metrics,
                sequential_record,
                sequential_baseline,
            )
            all_failures = fg_failures + bank_failures
            candidate = candidate_family(base, foregrounds, categorical, terminal, sequential)
            profile_record["candidates"][lane] = {
                "weight": weight,
                "surfaces": {role: base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES},
                "foregrounds": list(foregrounds),
                "foreground_target_ab": [
                    srgb_to_oklab(hex_to_srgb(LIGHT_TARGET.surfaces[f"fg_{index}"]))[1:].tolist()
                    for index in range(3)
                ],
                "categorical": list(categorical),
                "categorical_transformed_targets": list(candidate.categorical_transformed_targets),
                "terminal": list(terminal),
                "terminal_transformed_targets": list(candidate.terminal_transformed_targets),
                "terminal_ansi_indices": list(candidate.terminal_ansi_indices),
                "terminal_night_groups": list(candidate.terminal_night_groups),
                "sequential_anchors": list(sequential),
                "continuous_float_srgb": sequence.tolist(),
                "continuous_hex8": [srgb_to_hex(value) for value in sequence],
                "metrics": {
                    "foreground": foreground,
                    "categorical": category_metrics,
                    "terminal": terminal_metrics,
                    "sequential": sequential_record,
                },
                "search": {
                    "categorical": {
                        "bounds": "each shipped sRGB byte ±18, clipped to [0,255]",
                        "objective": "hard release floors, then separation/clearance/contrast/corner evidence/movement",
                        "runs": cat_runs,
                        "selected_seed": selected_cat_run["seed"],
                        "changed_from_shipped": list(categorical) != list(base.categorical_colors),
                    },
                    "terminal": {
                        "bounds": "each shipped sRGB byte ±16, clipped to [0,255]",
                        "objective": "hard release floors and semantic hue recognition, then separation/clearance/contrast/corner evidence/movement",
                        "runs": term_runs,
                        "selected_seed": selected_term_run["seed"],
                        "changed_from_shipped": list(terminal) != list(base.terminal_colors),
                    },
                    "sequential": {
                        "bounds": "each shipped anchor sRGB byte ±10, clipped to [0,255]",
                        "objective": "bi-state monotonicity/range/uniformity floors, then CV/range/movement",
                        "runs": seq_runs,
                        "selected_seed": selected_seq_run["seed"],
                        "changed_from_shipped": list(sequential) != list(base.sequential_anchors),
                    },
                },
                "foreground_failures": fg_failures,
                "dependent_bank_failures": bank_failures,
                "release_failures": all_failures,
                "release_status": "PASS" if not all_failures else "FAIL",
            }
        output["profiles"][slug] = profile_record
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="small deterministic smoke search")
    args = parser.parse_args()
    iterations = (
        {"categorical": 30, "terminal": 30, "sequential": 8} if args.quick else DEFAULT_ITERATIONS
    )
    result = run_experiment(iterations)
    output = Path(__file__).with_name("search-results.json")
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
