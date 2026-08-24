#!/usr/bin/env python3
"""Bounded exact-Hex8 full-system search for the foreground-warmth experiment.

Each lane jointly searches the six surfaces and three foreground roles before
rerunning every dependent bank.  Foreground warmth is a soft Oklab target;
lightness and the restrained surfaces remain optimization variables.  Every
proposal is scored at the exact consumer Hex8 boundary and retains two
deterministic search runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import replace
from itertools import product
from pathlib import Path
from typing import Any

import colour
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
    wcag_luminance,
)
from ember.definitions import (
    BACKGROUND_SURFACE_ROLES,
    DARK_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK,
    DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST,
    DARK_SURFACE_MAXIMUM_COMMANDED_LUMINANCE,
    FAMILIES,
    GAIN_SENSITIVITY_FRACTION,
    MINIMUM_SHIFTED_FOREGROUND_CONTRAST,
    FamilyDefinition,
)
from ember.generate import _interpolate_polyline, _sequential_colors, _smooth_polyline

PROFILE_SLUGS = ("3400k-dark", "2000k-dark", "1200k-dark")
LANES = {"current": 0.0, "halfway": 0.5, "full": 1.0}
BANKS = ("categorical", "terminal", "sequential")
LIGHT_TARGET = next(family for family in FAMILIES if family.slug == "3400k-light")
DEFAULT_ITERATIONS = {
    "full_system": 2400,
    "categorical": 900,
    "terminal": 900,
    "sequential": 180,
}
SEED_BASES = {
    "full_system": 7000,
    "categorical": 17000,
    "terminal": 27000,
    "sequential": 37000,
}
SURFACE_BYTE_RADIUS = 24
FOREGROUND_BYTE_RADIUS = 48
FOREGROUND_LIGHTNESS_RADIUS = 0.06
SURFACE_LIGHTNESS_DRIFT = 0.0125
TERMINAL_HUE_CENTERS = np.asarray((20.0, 140.0, 82.0, 275.0, 335.0, 185.0))
TERMINAL_ROLE_NAMES = ("red", "green", "yellow", "blue", "magenta", "cyan")
TERMINAL_HUE_BY_ROLE = dict(zip(TERMINAL_ROLE_NAMES, TERMINAL_HUE_CENTERS, strict=True))
FULL_TARGET_CHROMA_SCALES = np.asarray((1.2, 1.0, 0.8))
CAM16_ADAPTATION_LUMINANCE = 8.0
CAM16_BACKGROUND_LUMINANCE = 3.0
CAM16_FLARE_FRACTION = 0.0075
DEPENDENT_PARITY_RATIO = 0.90
SAMPLED_GAIN_MARGIN = 0.05
SEQUENTIAL_PLOT_CANVAS_ROLE = "bg_0"
SEQUENTIAL_COMMANDED_CV_CEILING = 0.18
SEQUENTIAL_TRANSFORMED_CV_TARGET = 0.05
SEQUENTIAL_TRANSFORMED_CV_CEILING = 0.12
SEQUENTIAL_SAMPLED_GAIN_CV_CEILING = 0.10
SEQUENTIAL_1200_NOMINAL_CV_CEILING = 0.10
TERMINAL_CHROMA_CEILINGS = {
    # Absolute maturity ceiling: permits modest redistribution above each
    # shipped bank's 0.115–0.118 maximum without admitting candy-like fronts.
    "3400k-dark": 0.125,
    "2000k-dark": 0.125,
    "1200k-dark": 0.125,
}
# Exact maturity vetoes carried forward from visual review.  These prevent the
# maximin search from buying a small CAM16 gain by clipping key terminal roles.
TERMINAL_CHANNEL_CEILINGS = {
    "3400k-dark": {(0, 0): 247, (3, 2): 252},
    "2000k-dark": {(0, 0): 244, (3, 2): 252},
    "1200k-dark": {(0, 0): 246},
}
TERMINAL_INITIAL_PROPOSALS = {
    # Deterministic feasible fronts discovered in the bounded deep-profile
    # probe. They are proposals only: every lane/seed still scores them from
    # exact Hex8 and may reject or refine them.
    "2000k-dark": (
        ("#EB8DA6", "#74E5C0", "#C39B65", "#A2D0FF"),
        ("#EC8B96", "#74E5C0", "#C39B55", "#9FC7FC"),
    ),
    "1200k-dark": (
        ("#F39399", "#CCFFB4", "#DEC671"),
        ("#F19299", "#E6FFAF", "#DBC370"),
    ),
}
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


def full_foreground_pattern() -> tuple[np.ndarray, float, np.ndarray]:
    """Return the shared Light Mid-Depth direction and decreasing dark chroma pattern."""

    light = srgb_to_oklab(
        hex_array(tuple(LIGHT_TARGET.surfaces[f"fg_{index}"] for index in range(3)))
    )
    chroma = np.linalg.norm(light[:, 1:], axis=1)
    direction = light[:, 1:].mean(axis=0)
    direction /= np.linalg.norm(direction)
    mean_chroma = float(chroma.mean())
    return FULL_TARGET_CHROMA_SCALES[:, None] * mean_chroma * direction, mean_chroma, direction


def foreground_target(base: FamilyDefinition, weight: float) -> np.ndarray:
    """Interpolate shipped a/b toward the shared full pattern; L is deliberately untargeted."""

    current = srgb_to_oklab(hex_array(tuple(base.surfaces[f"fg_{index}"] for index in range(3))))
    full_ab, _, _ = full_foreground_pattern()
    return current[:, 1:] + weight * (full_ab - current[:, 1:])


def surface_target(base: FamilyDefinition, weight: float) -> np.ndarray:
    """Interpolate each background role's a/b toward its Light Mid-Depth counterpart; L stays dark."""

    shipped = srgb_to_oklab(
        hex_array(tuple(base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES))
    )
    light_lab = srgb_to_oklab(
        hex_array(tuple(LIGHT_TARGET.surfaces[role] for role in BACKGROUND_SURFACE_ROLES))
    )
    return shipped[:, 1:] + weight * (light_lab[:, 1:] - shipped[:, 1:])


def candidate_family(
    base: FamilyDefinition,
    surfaces: tuple[str, ...],
    foregrounds: tuple[str, ...],
    categorical: tuple[str, ...] | None = None,
    terminal: tuple[str, ...] | None = None,
    sequential: tuple[str, ...] | None = None,
) -> FamilyDefinition:
    candidate_surfaces = dict(base.surfaces)
    candidate_surfaces.update(dict(zip(BACKGROUND_SURFACE_ROLES, surfaces, strict=True)))
    candidate_surfaces.update({f"fg_{index}": value for index, value in enumerate(foregrounds)})
    categorical_values = categorical or base.categorical_colors
    terminal_values = terminal or base.terminal_colors
    return replace(
        base,
        surfaces=candidate_surfaces,
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


def foreground_metrics(
    base: FamilyDefinition,
    surfaces: tuple[str, ...],
    foregrounds: tuple[str, ...],
) -> dict[str, Any]:
    rgb = hex_array(foregrounds)
    day = srgb_to_oklab(rgb)
    night = perceived_lab(rgb, base.profile.gains)
    day_vectors = np.diff(day, axis=0)
    night_vectors = np.diff(night, axis=0)
    day_steps = np.linalg.norm(day_vectors, axis=1) * 100.0
    night_steps = np.linalg.norm(night_vectors, axis=1) * 100.0
    backgrounds = hex_array(surfaces)
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


def surface_metrics(
    base: FamilyDefinition,
    surfaces: tuple[str, ...],
    foregrounds: tuple[str, ...],
) -> dict[str, Any]:
    rgb = hex_array(surfaces)
    shifted = warm_transform(rgb, base.profile.gains)
    lab = srgb_to_oklab(rgb)
    shifted_lab = srgb_to_oklab(shifted)
    foreground_shifted = warm_transform(hex_array(foregrounds), base.profile.gains)
    contrasts = np.asarray(
        [
            [contrast_ratio(foreground, background) for background in shifted]
            for foreground in foreground_shifted
        ]
    )
    return {
        "normal_relative_luminance": wcag_luminance(rgb).tolist(),
        "shifted_relative_luminance": wcag_luminance(shifted).tolist(),
        "normal_adjacent_delta_e_ok": (
            np.linalg.norm(np.diff(lab, axis=0), axis=1) * 100.0
        ).tolist(),
        "shifted_adjacent_delta_e_ok": (
            np.linalg.norm(np.diff(shifted_lab, axis=0), axis=1) * 100.0
        ).tolist(),
        "normal_span_delta_e_ok": float(np.linalg.norm(lab[-1] - lab[0]) * 100.0),
        "shifted_span_delta_e_ok": float(np.linalg.norm(shifted_lab[-1] - shifted_lab[0]) * 100.0),
        "shifted_foreground_contrast": contrasts.tolist(),
    }


def surface_lightness_drift(base: FamilyDefinition, surfaces: tuple[str, ...]) -> float:
    """Maximum Oklab L deviation of proposed surfaces from the shipped dark ladder."""

    shipped = srgb_to_oklab(
        hex_array(tuple(base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES))
    )
    proposed = srgb_to_oklab(hex_array(surfaces))
    return float(np.max(np.abs(proposed[:, 0] - shipped[:, 0])))


def cam16_ucs(rgb01: np.ndarray, gains: tuple[float, ...]) -> np.ndarray:
    """Flare-aware CAM16-UCS for the exact transformed encoded-sRGB signal."""

    rgb = np.asarray(rgb01, dtype=float)
    transformed = np.clip(rgb * np.asarray(gains, dtype=float), 0.0, 1.0)
    xyz = colour.sRGB_to_XYZ(transformed)
    flare = CAM16_FLARE_FRACTION * colour.sRGB_to_XYZ(np.ones_like(transformed))
    return np.asarray(
        colour.XYZ_to_CAM16UCS(
            xyz + flare,
            L_A=CAM16_ADAPTATION_LUMINANCE,
            Y_b=CAM16_BACKGROUND_LUMINANCE,
        )
    )


def sampled_gain_grid(
    gains: tuple[float, float, float], *, dense: bool = False
) -> list[tuple[float, ...]]:
    """Unique sampled gain grid; diagnostic evidence, not a continuous box bound."""

    delta = GAIN_SENSITIVITY_FRACTION
    scales = np.linspace(1.0 - delta, 1.0 + delta, 5 if dense else 3)
    axes = [scales if gain != 0.0 else np.asarray((1.0,)) for gain in gains]
    rows = {
        tuple(float(gain * scale) for gain, scale in zip(gains, combo, strict=True))
        for combo in product(*axes)
    }
    return [tuple(row) for row in sorted(rows)]


def _minimum_pair(points: np.ndarray) -> float:
    distances = [
        float(np.linalg.norm(points[left] - points[right]))
        for left in range(len(points))
        for right in range(left + 1, len(points))
    ]
    return min(distances) if distances else 0.0


def terminal_role_contract(base: FamilyDefinition) -> dict[str, Any]:
    """Explicit authored-role and ANSI-alias contract for one profile."""

    authored_roles = TERMINAL_ROLE_NAMES[: len(base.terminal_colors)]
    ansi_mapping = {
        role: authored_roles[index]
        for role, index in zip(TERMINAL_ROLE_NAMES, base.terminal_ansi_indices, strict=True)
    }
    return {
        "authored_roles": list(authored_roles),
        "ansi_mapping": ansi_mapping,
        "intentional_aliases": {
            role: target for role, target in ansi_mapping.items() if role != target
        },
    }


def accent_metrics(
    base: FamilyDefinition,
    values: tuple[str, ...],
    foregrounds: tuple[str, ...],
    *,
    terminal: bool,
    sample_grid: bool | str = False,
) -> dict[str, Any]:
    rgb = hex_array(values)
    foreground_rgb = hex_array(foregrounds)
    backgrounds = hex_array(tuple(base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES))
    day = srgb_to_oklab(rgb)
    transformed_ucs = cam16_ucs(rgb, base.profile.gains)
    foreground_day = srgb_to_oklab(foreground_rgb)
    foreground_ucs = cam16_ucs(foreground_rgb, base.profile.gains)
    day_fg = np.linalg.norm(day[:, None] - foreground_day[None, :], axis=2).min(axis=0) * 100.0
    transformed_fg = np.linalg.norm(transformed_ucs[:, None] - foreground_ucs[None, :], axis=2).min(
        axis=0
    )
    transformed = warm_transform(rgb, base.profile.gains)
    transformed_backgrounds = warm_transform(backgrounds, base.profile.gains)
    day_contrast = np.asarray(
        [[contrast_ratio(color, background) for background in backgrounds] for color in rgb]
    )
    transformed_contrast = np.asarray(
        [
            [contrast_ratio(color, background) for background in transformed_backgrounds]
            for color in transformed
        ]
    )
    sampled_rows = []
    gains_to_sample = (
        sampled_gain_grid(base.profile.gains, dense=sample_grid == "dense")
        if sample_grid
        else [base.profile.gains]
    )
    for sampled_gains in gains_to_sample:
        sampled_ucs = cam16_ucs(rgb, sampled_gains)
        sampled_fg = cam16_ucs(foreground_rgb, sampled_gains)
        sampled_background = warm_transform(backgrounds[0], sampled_gains)
        sampled_rows.append(
            {
                "gains": list(sampled_gains),
                "pair_cam16_ucs": _minimum_pair(sampled_ucs),
                "foreground_clearance_cam16_ucs": float(
                    np.linalg.norm(sampled_ucs[:, None] - sampled_fg[None, :], axis=2).min()
                ),
                "background_contrast": min(
                    contrast_ratio(warm_transform(color, sampled_gains), sampled_background)
                    for color in rgb
                ),
            }
        )
    role_contract = terminal_role_contract(base) if terminal else None
    semantic_centers = (
        np.asarray([TERMINAL_HUE_BY_ROLE[role] for role in role_contract["authored_roles"]])
        if terminal
        else None
    )
    return {
        "normal_pair_delta_e_ok": float(pairwise_distances(day).min()),
        "transformed_pair_cam16_ucs": _minimum_pair(transformed_ucs),
        "normal_foreground_clearance_by_role": day_fg.tolist(),
        "transformed_foreground_clearance_by_role_cam16_ucs": transformed_fg.tolist(),
        "normal_foreground_clearance_min": float(day_fg.min()),
        "transformed_foreground_clearance_min_cam16_ucs": float(transformed_fg.min()),
        "normal_background_contrast_min": float(day_contrast.min()),
        "transformed_background_contrast_bg0_min": float(transformed_contrast[:, 0].min()),
        "transformed_background_contrast_all_surfaces_min": float(transformed_contrast.min()),
        "normal_hue_gap_degrees": float(hue_gap(day)),
        "normal_mean_chroma": float(np.linalg.norm(day[:, 1:], axis=1).mean()),
        "normal_max_chroma": float(np.linalg.norm(day[:, 1:], axis=1).max()),
        "normal_semantic_hue_error_max": (
            float(
                np.abs(
                    (
                        (np.degrees(np.arctan2(day[:, 2], day[:, 1])) % 360.0)
                        - semantic_centers
                        + 180.0
                    )
                    % 360.0
                    - 180.0
                ).max()
            )
            if terminal
            else None
        ),
        "terminal_role_contract": role_contract,
        "sampled_gain_grid_kind": (
            "unique 5x5 adaptive scan per nonzero gain axis"
            if sample_grid == "dense"
            else "unique 3x3 per nonzero gain axis"
            if sample_grid
            else "nominal"
        ),
        "sampled_gain_grid": sampled_rows,
        "sampled_gain_pair_min_cam16_ucs": min(row["pair_cam16_ucs"] for row in sampled_rows),
        "sampled_gain_foreground_clearance_min_cam16_ucs": min(
            row["foreground_clearance_cam16_ucs"] for row in sampled_rows
        ),
        "sampled_gain_background_contrast_min": min(
            row["background_contrast"] for row in sampled_rows
        ),
    }


def sequential_metrics(
    base: FamilyDefinition, sequence_or_anchors: np.ndarray | tuple[str, ...]
) -> tuple[dict[str, Any], np.ndarray]:
    if isinstance(sequence_or_anchors, np.ndarray):
        sequence = np.asarray(sequence_or_anchors, dtype=float)
    else:
        candidate = replace(base, sequential_anchors=sequence_or_anchors)
        sequence = _sequential_colors(candidate)
    sequence = np.round(sequence, 10)
    day = srgb_to_oklab(sequence)
    transformed_ucs = cam16_ucs(sequence, base.profile.gains)
    day_steps = np.linalg.norm(np.diff(day, axis=0), axis=1) * 100.0
    transformed_steps = np.linalg.norm(np.diff(transformed_ucs, axis=0), axis=1)
    day_direction = 1.0 if day[-1, 0] >= day[0, 0] else -1.0
    plot_canvas = warm_transform(
        hex_to_srgb(base.surfaces[SEQUENTIAL_PLOT_CANVAS_ROLE]), base.profile.gains
    )
    sampled_rows = []
    for sampled_gains in sampled_gain_grid(base.profile.gains):
        sampled_ucs = cam16_ucs(sequence, sampled_gains)
        steps = np.linalg.norm(np.diff(sampled_ucs, axis=0), axis=1)
        sampled_rows.append(
            {
                "gains": list(sampled_gains),
                "cv": float(steps.std() / steps.mean()),
                "max_to_min": float(steps.max() / steps.min()),
                "minimum_signed_j_step": float(np.diff(sampled_ucs[:, 0]).min()),
            }
        )
    metrics = {
        "normal_cv": float(day_steps.std() / day_steps.mean()),
        "normal_max_to_min": float(day_steps.max() / day_steps.min()),
        "transformed_cam16_cv": float(transformed_steps.std() / transformed_steps.mean()),
        "transformed_cam16_max_to_min": float(transformed_steps.max() / transformed_steps.min()),
        "normal_lightness_range": float(np.ptp(day[:, 0])),
        "transformed_j_range": float(np.ptp(transformed_ucs[:, 0])),
        "plot_canvas_role": SEQUENTIAL_PLOT_CANVAS_ROLE,
        "dark_endpoint_plot_canvas_contrast": contrast_ratio(
            warm_transform(sequence[0], base.profile.gains), plot_canvas
        ),
        "light_endpoint_plot_canvas_contrast": contrast_ratio(
            warm_transform(sequence[-1], base.profile.gains), plot_canvas
        ),
        "normal_minimum_signed_lightness_step": float((np.diff(day[:, 0]) * day_direction).min()),
        "transformed_minimum_signed_j_step": float(np.diff(transformed_ucs[:, 0]).min()),
        "sampled_gain_grid_kind": "unique 3x3 per nonzero gain axis",
        "sampled_gain_grid": sampled_rows,
        "sampled_gain_cv_max": max(row["cv"] for row in sampled_rows),
        "sampled_gain_max_to_min_max": max(row["max_to_min"] for row in sampled_rows),
        "sampled_gain_minimum_signed_j_step": min(
            row["minimum_signed_j_step"] for row in sampled_rows
        ),
    }
    return metrics, sequence


def dependent_bank_floors(base: FamilyDefinition, foregrounds: tuple[str, ...]) -> dict[str, Any]:
    """Parity floors calibrated from the shipped bank under this lane's fixed fg."""

    categorical = accent_metrics(
        base, base.categorical_colors, foregrounds, terminal=False, sample_grid=True
    )
    terminal = accent_metrics(
        base, base.terminal_colors, foregrounds, terminal=True, sample_grid=True
    )
    return {
        "parity_ratio": DEPENDENT_PARITY_RATIO,
        "categorical": {
            "transformed_pair_cam16_ucs": DEPENDENT_PARITY_RATIO
            * categorical["sampled_gain_pair_min_cam16_ucs"],
            "transformed_foreground_by_role_cam16_ucs": [
                DEPENDENT_PARITY_RATIO * value
                for value in categorical["transformed_foreground_clearance_by_role_cam16_ucs"]
            ],
            "sampled_gain_foreground_clearance_min_cam16_ucs": DEPENDENT_PARITY_RATIO
            * categorical["sampled_gain_foreground_clearance_min_cam16_ucs"],
        },
        "terminal": {
            "transformed_pair_cam16_ucs": DEPENDENT_PARITY_RATIO
            * terminal["sampled_gain_pair_min_cam16_ucs"],
            "transformed_foreground_by_role_cam16_ucs": [
                DEPENDENT_PARITY_RATIO * value
                for value in terminal["transformed_foreground_clearance_by_role_cam16_ucs"]
            ],
            "sampled_gain_foreground_clearance_min_cam16_ucs": DEPENDENT_PARITY_RATIO
            * terminal["sampled_gain_foreground_clearance_min_cam16_ucs"],
        },
        "shipped_probe": {"categorical": categorical, "terminal": terminal},
    }


def categorical_objective(
    base: FamilyDefinition,
    foregrounds: tuple[str, ...],
    values: tuple[str, ...],
    floors: dict[str, Any] | None = None,
) -> float:
    floors = floors or dependent_bank_floors(base, foregrounds)
    metrics = accent_metrics(base, values, foregrounds, terminal=False)
    bank_floors = floors["categorical"]
    violations = [
        violation(metrics["normal_pair_delta_e_ok"], base.daylight_minimum_delta_e_ok),
        violation(
            metrics["transformed_pair_cam16_ucs"],
            bank_floors["transformed_pair_cam16_ucs"],
        ),
        violation(
            metrics["normal_hue_gap_degrees"],
            base.daylight_minimum_hue_gap_degrees or 0.0,
        ),
        violation(metrics["transformed_background_contrast_bg0_min"], 3.0),
        violation(metrics["normal_mean_chroma"], 0.09),
        violation(metrics["normal_mean_chroma"], ceiling=0.105),
        violation(metrics["normal_max_chroma"], ceiling=0.111),
    ]
    violations.extend(
        violation(value, base.categorical_daylight_minimum_foreground_delta_e_ok)
        for value in metrics["normal_foreground_clearance_by_role"]
    )
    violations.extend(
        violation(value, floor)
        for value, floor in zip(
            metrics["transformed_foreground_clearance_by_role_cam16_ucs"],
            bank_floors["transformed_foreground_by_role_cam16_ucs"],
            strict=True,
        )
    )
    proposed_bytes = bytes_from_hex(values)
    for (color_index, channel_index), ceiling in CATEGORY_CHANNEL_CEILINGS.get(
        base.slug, {}
    ).items():
        if color_index < len(values):
            violations.append(
                violation(float(proposed_bytes[color_index, channel_index]), ceiling=float(ceiling))
            )
    proposed = srgb_to_oklab(hex_array(values))
    move = 0.0
    if len(values) == len(base.categorical_colors):
        current = srgb_to_oklab(hex_array(base.categorical_colors))
        move = float(np.linalg.norm(proposed - current, axis=1).mean())
    soft = (
        -1.0 * metrics["transformed_pair_cam16_ucs"]
        - 0.25 * metrics["transformed_foreground_clearance_min_cam16_ucs"]
        - 0.05 * metrics["normal_pair_delta_e_ok"]
        + 0.5 * move
    )
    return penalty(violations) + soft


def terminal_objective(
    base: FamilyDefinition,
    foregrounds: tuple[str, ...],
    values: tuple[str, ...],
    floors: dict[str, Any] | None = None,
) -> float:
    floors = floors or dependent_bank_floors(base, foregrounds)
    metrics = accent_metrics(base, values, foregrounds, terminal=True)
    bank_floors = floors["terminal"]
    proposed = srgb_to_oklab(hex_array(values))
    current = srgb_to_oklab(hex_array(base.terminal_colors))
    role_contract = terminal_role_contract(base)
    hue_centers = np.asarray(
        [TERMINAL_HUE_BY_ROLE[role] for role in role_contract["authored_roles"]]
    )
    proposed_hues = np.degrees(np.arctan2(proposed[:, 2], proposed[:, 1])) % 360.0
    hue_errors = np.abs((proposed_hues - hue_centers + 180.0) % 360.0 - 180.0)
    day_floors = (
        base.terminal_daylight_minimum_fg_0_delta_e_ok,
        base.terminal_daylight_minimum_fg_1_delta_e_ok,
        base.terminal_daylight_minimum_fg_2_delta_e_ok,
    )
    violations = [
        violation(metrics["normal_pair_delta_e_ok"], base.terminal_daylight_minimum_delta_e_ok),
        violation(
            metrics["transformed_pair_cam16_ucs"],
            bank_floors["transformed_pair_cam16_ucs"],
        ),
        violation(metrics["transformed_background_contrast_bg0_min"], 4.5),
        violation(float(hue_errors.max()), ceiling=30.0),
        violation(
            float(np.linalg.norm(proposed[:, 1:], axis=1).max()),
            ceiling=TERMINAL_CHROMA_CEILINGS[base.slug],
        ),
    ]
    proposed_bytes = bytes_from_hex(values)
    for (color_index, channel_index), ceiling in TERMINAL_CHANNEL_CEILINGS.get(
        base.slug, {}
    ).items():
        violations.append(
            violation(
                float(proposed_bytes[color_index, channel_index]),
                ceiling=float(ceiling),
            )
        )
    violations.extend(
        violation(value, floor or 0.0)
        for value, floor in zip(
            metrics["normal_foreground_clearance_by_role"], day_floors, strict=True
        )
    )
    violations.extend(
        violation(value, floor)
        for value, floor in zip(
            metrics["transformed_foreground_clearance_by_role_cam16_ucs"],
            bank_floors["transformed_foreground_by_role_cam16_ucs"],
            strict=True,
        )
    )
    move = float(np.linalg.norm(proposed - current, axis=1).mean())
    soft = (
        -1.0 * metrics["transformed_pair_cam16_ucs"]
        - 0.3 * metrics["transformed_foreground_clearance_min_cam16_ucs"]
        - 0.05 * metrics["normal_pair_delta_e_ok"]
        + 0.5 * move
    )
    return penalty(violations) + soft


def construct_sequential(
    base: FamilyDefinition, *, count: int = 256
) -> tuple[np.ndarray, tuple[str, ...], dict[str, Any]]:
    """Resample the approved commanded path by transformed CAM16-UCS arc length."""

    anchor_lab = _smooth_polyline(srgb_to_oklab(hex_array(base.sequential_anchors)))
    dense_lab = _interpolate_polyline(anchor_lab, samples_per_segment=2048)
    dense_rgb = np.clip(oklab_to_srgb(dense_lab), 0.0, 1.0)
    dense_ucs = cam16_ucs(dense_rgb, base.profile.gains)
    monotone = np.concatenate(([True], np.diff(np.maximum.accumulate(dense_ucs[:, 0])) > 1e-12))
    monotone[-1] = True
    dense_lab = dense_lab[monotone]
    dense_rgb = dense_rgb[monotone]
    dense_ucs = dense_ucs[monotone]
    day_steps = np.linalg.norm(np.diff(dense_lab, axis=0), axis=1)
    transformed_steps = np.linalg.norm(np.diff(dense_ucs, axis=0), axis=1)
    transformed_norm = transformed_steps / max(float(transformed_steps.mean()), 1e-12)
    day_norm = day_steps / max(float(day_steps.mean()), 1e-12)
    sampled_step_norms = []
    for sampled_gains in sampled_gain_grid(base.profile.gains):
        sampled_ucs = cam16_ucs(dense_rgb, sampled_gains)
        sampled_steps = np.linalg.norm(np.diff(sampled_ucs, axis=0), axis=1)
        sampled_step_norms.append(sampled_steps / max(float(sampled_steps.mean()), 1e-12))
    sampled_step_norms = np.asarray(sampled_step_norms)
    if base.slug == "1200k-dark":
        transformed_reference = (
            sampled_step_norms.min(axis=0) + sampled_step_norms.max(axis=0)
        ) / 2.0
        selection_policy = (
            "minimize worst sampled-gain transformed CV; transformed nominal CV <= 0.10; "
            "commanded CV <= 0.18"
        )
    else:
        transformed_reference = transformed_norm
        selection_policy = (
            "transformed perceptual sufficiency CV <= 0.05; then minimize commanded CV; "
            "sampled-gain CV <= 0.10"
        )

    path_chroma = np.linalg.norm(dense_lab[:, 1:], axis=1)
    candidates = []
    for transformed_weight in np.linspace(0.0, 1.0, 101):
        blended = transformed_weight * transformed_reference + (1.0 - transformed_weight) * day_norm
        distance = np.concatenate(([0.0], np.cumsum(blended)))
        targets = np.linspace(0.0, float(distance[-1]), count)
        upper = np.clip(np.searchsorted(distance, targets, side="left"), 1, len(dense_lab) - 1)
        lower = upper - 1
        span = distance[upper] - distance[lower]
        fraction = np.divide(
            targets - distance[lower],
            span,
            out=np.zeros_like(targets),
            where=span > 0,
        )[:, None]
        sampled_lab = dense_lab[lower] * (1.0 - fraction) + dense_lab[upper] * fraction
        sequence = np.clip(oklab_to_srgb(sampled_lab), 0.0, 1.0)
        metrics, sequence = sequential_metrics(base, sequence)
        sequence_chroma = np.linalg.norm(srgb_to_oklab(sequence)[:, 1:], axis=1)
        if metrics["normal_cv"] > SEQUENTIAL_COMMANDED_CV_CEILING + 1e-12:
            continue
        if metrics["transformed_minimum_signed_j_step"] <= 0.0:
            continue
        if metrics["sampled_gain_minimum_signed_j_step"] <= 0.0:
            continue
        if float(sequence_chroma.max()) > float(path_chroma.max()) + 1e-6:
            continue
        if float(sequence_chroma.min()) < float(path_chroma.min()) - 1e-6:
            continue
        if base.slug == "1200k-dark":
            if metrics["transformed_cam16_cv"] > SEQUENTIAL_1200_NOMINAL_CV_CEILING + 1e-12:
                continue
            key = (
                metrics["sampled_gain_cv_max"],
                metrics["sampled_gain_max_to_min_max"],
                metrics["transformed_cam16_cv"],
                metrics["normal_cv"],
            )
        else:
            if metrics["transformed_cam16_cv"] > SEQUENTIAL_TRANSFORMED_CV_TARGET + 1e-12:
                continue
            if metrics["sampled_gain_cv_max"] > SEQUENTIAL_SAMPLED_GAIN_CV_CEILING + 1e-12:
                continue
            key = (
                metrics["normal_cv"],
                metrics["sampled_gain_cv_max"],
                metrics["transformed_cam16_cv"],
                -float(transformed_weight),
            )
        candidates.append(
            (
                key,
                float(transformed_weight),
                sequence,
                metrics,
                sequence_chroma,
            )
        )
    if not candidates:
        raise RuntimeError(f"no monotone constructive sequential ramp for {base.slug}")
    _, chosen_weight, chosen_sequence, metrics, sequence_chroma = min(
        candidates, key=lambda row: row[0]
    )
    anchors = tuple(
        srgb_to_hex(chosen_sequence[index])
        for index in np.rint(np.linspace(0, count - 1, 6)).astype(int)
    )
    metrics, chosen_sequence = sequential_metrics(base, chosen_sequence)
    provenance = {
        "construction": (
            "approved commanded OkLCh trajectory; profile-specific nominal/robust "
            "transformed arc-length resampling"
        ),
        "transformed_arc_weight": chosen_weight,
        "selection_policy": selection_policy,
        "transformed_reference": (
            "sampled-gain normalized-step midrange"
            if base.slug == "1200k-dark"
            else "nominal transformed CAM16-UCS arc length"
        ),
        "canonical_samples": count,
        "anchors_are_hex8_preview_exports": True,
        "approved_path_chroma_min": float(path_chroma.min()),
        "approved_path_chroma_max": float(path_chroma.max()),
        "canonical_chroma_min": float(sequence_chroma.min()),
        "canonical_chroma_mean": float(sequence_chroma.mean()),
        "canonical_chroma_max": float(sequence_chroma.max()),
        "chroma_envelope_preserved": True,
        "transformed_cam16_cv_target": SEQUENTIAL_TRANSFORMED_CV_TARGET,
        "transformed_cam16_cv_target_met": (
            metrics["transformed_cam16_cv"] <= SEQUENTIAL_TRANSFORMED_CV_TARGET
        ),
        "target_deviation_reason": (
            None
            if metrics["transformed_cam16_cv"] <= SEQUENTIAL_TRANSFORMED_CV_TARGET
            else (
                "1200K minimizes sampled-gain CV under transformed nominal CV <= 0.10 "
                "and commanded CV <= 0.18"
            )
        ),
    }
    return chosen_sequence, anchors, {**metrics, **provenance}


def sequential_objective(
    base: FamilyDefinition,
    baseline_metrics: dict[str, Any],
    values: tuple[str, ...],
) -> float:
    """Compatibility scorer; transformed-first production uses construct_sequential."""

    del baseline_metrics
    metrics, _ = sequential_metrics(base, values)
    violations = [
        violation(metrics["normal_lightness_range"], 0.5),
        violation(metrics["transformed_j_range"], 10.0),
        violation(metrics["normal_minimum_signed_lightness_step"], 1e-9),
        violation(metrics["transformed_minimum_signed_j_step"], 1e-9),
        violation(metrics["normal_cv"], ceiling=SEQUENTIAL_COMMANDED_CV_CEILING),
        violation(metrics["transformed_cam16_cv"], ceiling=SEQUENTIAL_TRANSFORMED_CV_CEILING),
        violation(metrics["light_endpoint_plot_canvas_contrast"], 4.5),
        violation(metrics["dark_endpoint_plot_canvas_contrast"], 1.02),
    ]
    return penalty(violations) + metrics["transformed_cam16_cv"]


def bounded_exact_search(
    base_values: tuple[str, ...],
    objective: Callable[[tuple[str, ...]], float],
    *,
    seed: int,
    iterations: int,
    radius: int,
    initial_candidates: tuple[tuple[str, ...], ...] = (),
) -> dict[str, Any]:
    """Deterministic bounded stochastic hill-climb over exact byte proposals."""

    rng = np.random.default_rng(seed)
    origin = bytes_from_hex(base_values)
    best = origin.copy()
    best_values = hex_from_bytes(best)
    best_score = objective(best_values)
    accepted = 0
    evaluated = 1
    for candidate in initial_candidates:
        candidate_bytes = bytes_from_hex(candidate)
        if candidate_bytes.shape != origin.shape:
            continue
        if np.any(np.abs(candidate_bytes - origin) > radius):
            continue
        score = objective(candidate)
        evaluated += 1
        if score < best_score - 1e-12 or (
            abs(score - best_score) <= 1e-12 and candidate < best_values
        ):
            best = candidate_bytes
            best_values = candidate
            best_score = score
            accepted += 1
    for iteration in range(iterations):
        progress = iteration / max(1, iterations - 1)
        step = max(1, round(radius * (1.0 - progress)))
        proposal = best.copy()
        edits = 1 + int(rng.integers(0, min(4, proposal.size)))
        flat = proposal.reshape(-1)
        indices = rng.choice(flat.size, size=edits, replace=False)
        flat[indices] += rng.integers(-step, step + 1, size=edits, dtype=np.int16)
        proposal = np.clip(
            proposal, np.maximum(origin - radius, 0), np.minimum(origin + radius, 255)
        )
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


def full_system_violations(
    base: FamilyDefinition,
    surfaces: tuple[str, ...],
    foregrounds: tuple[str, ...],
    terminal_values: tuple[str, ...] | None,
) -> list[float]:
    foreground = foreground_metrics(base, surfaces, foregrounds)
    surface = surface_metrics(base, surfaces, foregrounds)
    values = []
    normal_luminance = np.asarray(surface["normal_relative_luminance"])
    shifted_luminance = np.asarray(surface["shifted_relative_luminance"])
    values.extend(violation(float(value), 0.0) for value in np.diff(normal_luminance))
    values.extend(violation(float(value), 0.0) for value in np.diff(shifted_luminance))
    values.extend(
        violation(value, DARK_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK)
        for value in surface["shifted_adjacent_delta_e_ok"]
    )
    values.append(violation(surface["shifted_span_delta_e_ok"], 6.0))
    values.extend(
        violation(actual, ceiling=DARK_SURFACE_MAXIMUM_COMMANDED_LUMINANCE[role])
        for role, actual in zip(
            BACKGROUND_SURFACE_ROLES,
            surface["normal_relative_luminance"],
            strict=True,
        )
    )

    contrast_floors = (
        max(
            MINIMUM_SHIFTED_FOREGROUND_CONTRAST["fg_0"],
            DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST[base.slug],
        ),
        MINIMUM_SHIFTED_FOREGROUND_CONTRAST["fg_1"],
        MINIMUM_SHIFTED_FOREGROUND_CONTRAST["fg_2"],
    )
    values.extend(
        violation(actual, floor)
        for actual, floor in zip(
            foreground["worst_surface_shifted_contrast"], contrast_floors, strict=True
        )
    )
    values.append(
        violation(surface_lightness_drift(base, surfaces), ceiling=SURFACE_LIGHTNESS_DRIFT)
    )
    for key, floor, ceiling in (
        (
            "normal_adjacent_delta_e_ok",
            base.foreground_daylight_minimum_adjacent_delta_e_ok,
            base.foreground_daylight_maximum_adjacent_delta_e_ok,
        ),
        (
            "shifted_adjacent_delta_e_ok",
            base.foreground_night_minimum_adjacent_delta_e_ok,
            base.foreground_night_maximum_adjacent_delta_e_ok,
        ),
    ):
        values.extend(violation(value, floor, ceiling) for value in foreground[key])
    values.extend(
        (
            violation(
                foreground["normal_lightness_gap_ratio"],
                base.foreground_minimum_lightness_gap_ratio,
            ),
            violation(
                foreground["shifted_lightness_gap_ratio"],
                base.foreground_minimum_lightness_gap_ratio,
            ),
        )
    )
    values.extend(
        violation(value, base.foreground_daylight_minimum_lightness_share)
        for value in foreground["normal_lightness_share"]
    )
    values.extend(
        violation(value, base.foreground_night_minimum_lightness_share)
        for value in foreground["shifted_lightness_share"]
    )
    values.extend(
        (
            violation(
                foreground["normal_hue_span_degrees"],
                ceiling=base.foreground_maximum_hue_span_degrees,
            ),
            violation(
                foreground["shifted_hue_span_degrees"],
                ceiling=base.foreground_night_maximum_hue_span_degrees,
            ),
            violation(
                max(foreground["normal_chroma"]),
                ceiling=base.foreground_maximum_chroma,
            ),
            violation(
                foreground["normal_chroma_vector_cosine"],
                base.foreground_daylight_minimum_chroma_vector_cosine,
            ),
            violation(
                foreground["shifted_chroma_vector_cosine"],
                base.foreground_night_minimum_chroma_vector_cosine,
            ),
        )
    )
    day = srgb_to_oklab(hex_array(foregrounds))
    night = perceived_lab(hex_array(foregrounds), base.profile.gains)
    values.extend(violation(float(value), 0.0) for value in -np.diff(day[:, 0]))
    values.extend(violation(float(value), 0.0) for value in -np.diff(night[:, 0]))
    shipped_l = srgb_to_oklab(hex_array(tuple(base.surfaces[f"fg_{index}"] for index in range(3))))[
        :, 0
    ]
    values.extend(
        violation(
            float(value),
            float(origin - FOREGROUND_LIGHTNESS_RADIUS),
            float(origin + FOREGROUND_LIGHTNESS_RADIUS),
        )
        for value, origin in zip(day[:, 0], shipped_l, strict=True)
    )
    direction = 1.0 if base.foreground_chroma_direction == "decreasing" else -1.0
    tolerance = base.foreground_chroma_order_tolerance or 0.0
    for chroma in (foreground["normal_chroma"], foreground["shifted_chroma"]):
        values.extend(
            violation(float(value), ceiling=tolerance)
            for value in np.diff(np.asarray(chroma)) * direction
        )

    # Initial foreground selection is transformed-usability first and must not
    # be pulled back toward warmth by the shipped terminal bank. Terminal
    # clearance enters only during the post-search coupled refinement/final gate.
    if terminal_values is not None:
        coupled_base = candidate_family(base, surfaces, foregrounds)
        terminal = accent_metrics(coupled_base, terminal_values, foregrounds, terminal=True)
        day_floors = (
            base.terminal_daylight_minimum_fg_0_delta_e_ok,
            base.terminal_daylight_minimum_fg_1_delta_e_ok,
            base.terminal_daylight_minimum_fg_2_delta_e_ok,
        )
        night_floors = dependent_bank_floors(coupled_base, foregrounds)["terminal"][
            "transformed_foreground_by_role_cam16_ucs"
        ]
        values.extend(
            violation(actual, floor or 0.0)
            for actual, floor in zip(
                terminal["normal_foreground_clearance_by_role"], day_floors, strict=True
            )
        )
        values.extend(
            violation(actual, floor or 0.0)
            for actual, floor in zip(
                terminal["transformed_foreground_clearance_by_role_cam16_ucs"],
                night_floors,
                strict=True,
            )
        )
    return values


def full_system_objective(
    base: FamilyDefinition,
    target_ab: np.ndarray,
    surface_target_ab: np.ndarray,
    values: tuple[str, ...],
    terminal_values: tuple[str, ...] | None,
) -> float:
    surfaces = values[:6]
    foregrounds = values[6:]
    violations = full_system_violations(base, surfaces, foregrounds, terminal_values)
    if any(violations):
        return 1e14 + penalty(violations)
    foreground = foreground_metrics(base, surfaces, foregrounds)
    surface = surface_metrics(base, surfaces, foregrounds)
    proposed_surface = srgb_to_oklab(hex_array(surfaces))
    shipped_surface = srgb_to_oklab(
        hex_array(tuple(base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES))
    )
    proposed_fg = srgb_to_oklab(hex_array(foregrounds))
    shipped_fg = srgb_to_oklab(hex_array(tuple(base.surfaces[f"fg_{index}"] for index in range(3))))
    terminal_clearance = 0.0
    if terminal_values is not None:
        coupled_base = candidate_family(base, surfaces, foregrounds)
        terminal = accent_metrics(coupled_base, terminal_values, foregrounds, terminal=True)
        terminal_clearance = terminal["transformed_foreground_clearance_min_cam16_ucs"]
    surface_move = float(np.linalg.norm(proposed_surface - shipped_surface, axis=1).mean())
    foreground_move = float(np.linalg.norm(proposed_fg - shipped_fg, axis=1).mean())
    target_error = float(np.linalg.norm(proposed_fg[:, 1:] - target_ab, axis=1).mean())
    surface_target_error = float(
        np.linalg.norm(proposed_surface[:, 1:] - surface_target_ab, axis=1).mean()
    )
    return (
        -0.30 * min(foreground["worst_surface_shifted_contrast"])
        - 0.035 * min(foreground["shifted_adjacent_delta_e_ok"])
        - 0.020 * terminal_clearance
        + 8.0 * surface_move
        + 8.0 * foreground_move
        + 90.0 * target_error
        + 900.0 * surface_target_error
        + 2.0 * foreground["normal_mean_chroma"]
        - 0.01 * surface["shifted_span_delta_e_ok"]
    )


def system_initialization(
    base: FamilyDefinition,
    target_ab: np.ndarray,
    surface_target_ab: np.ndarray,
    terminal_values: tuple[str, ...] | None,
) -> tuple[str, ...]:
    """Choose a feasible exact-Hex8 L-grid point before stochastic refinement."""

    shipped_surfaces = tuple(base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES)
    shipped_fg = tuple(base.surfaces[f"fg_{index}"] for index in range(3))
    shipped_surface_lab = srgb_to_oklab(hex_array(shipped_surfaces))
    shipped_lab = srgb_to_oklab(hex_array(shipped_fg))
    candidates: list[tuple[str, ...]] = [shipped_surfaces + shipped_fg]
    if np.allclose(target_ab, shipped_lab[:, 1:], rtol=0.0, atol=1e-12) and np.allclose(
        surface_target_ab, shipped_surface_lab[:, 1:], rtol=0.0, atol=1e-12
    ):
        return candidates[0]
    offsets = np.linspace(-FOREGROUND_LIGHTNESS_RADIUS, FOREGROUND_LIGHTNESS_RADIUS, 9)
    mixes = (1.0, 0.875, 0.75, 0.625, 0.5, 0.25, 0.0)
    for mix in mixes:
        fg_ab = shipped_lab[:, 1:] + mix * (target_ab - shipped_lab[:, 1:])
        bg_ab = shipped_surface_lab[:, 1:] + mix * (surface_target_ab - shipped_surface_lab[:, 1:])
        for first in offsets:
            for second in offsets:
                for third in offsets:
                    fg_lab = np.column_stack((shipped_lab[:, 0] + (first, second, third), fg_ab))
                    rgb = oklab_to_srgb(fg_lab)
                    if np.any((rgb < 0.0) | (rgb > 1.0)):
                        continue
                    surface_lab = np.column_stack((shipped_surface_lab[:, 0], bg_ab))
                    surface_rgb = oklab_to_srgb(surface_lab)
                    if np.any((surface_rgb < 0.0) | (surface_rgb > 1.0)):
                        continue
                    candidates.append(
                        tuple(srgb_to_hex(value) for value in surface_rgb)
                        + tuple(srgb_to_hex(value) for value in rgb)
                    )
    return min(
        candidates,
        key=lambda values: (
            full_system_objective(base, target_ab, surface_target_ab, values, terminal_values),
            values,
        ),
    )


def bounded_system_search(
    base: FamilyDefinition,
    target_ab: np.ndarray,
    surface_target_ab: np.ndarray,
    terminal_values: tuple[str, ...] | None,
    *,
    seed: int,
    iterations: int,
) -> dict[str, Any]:
    """Search restrained surfaces and free-L foregrounds at the exact byte boundary."""

    rng = np.random.default_rng(seed)
    shipped = tuple(base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES) + tuple(
        base.surfaces[f"fg_{index}"] for index in range(3)
    )
    origin = bytes_from_hex(shipped)
    radius = np.vstack(
        (
            np.full((6, 3), SURFACE_BYTE_RADIUS, dtype=np.int16),
            np.full((3, 3), FOREGROUND_BYTE_RADIUS, dtype=np.int16),
        )
    )
    best_values = system_initialization(base, target_ab, surface_target_ab, terminal_values)
    best = bytes_from_hex(best_values)
    best_score = full_system_objective(
        base, target_ab, surface_target_ab, best_values, terminal_values
    )
    accepted = 0
    evaluated = 1
    for iteration in range(iterations):
        progress = iteration / max(1, iterations - 1)
        step = max(1, round(7.0 * (1.0 - progress) + 1.0))
        proposal = best.copy()
        edits = 1 + int(rng.integers(0, 5))
        flat = proposal.reshape(-1)
        indices = rng.choice(flat.size, size=edits, replace=False)
        flat[indices] += rng.integers(-step, step + 1, size=edits, dtype=np.int16)
        proposal = np.minimum(np.maximum(proposal, origin - radius), origin + radius)
        values = hex_from_bytes(proposal)
        score = full_system_objective(base, target_ab, surface_target_ab, values, terminal_values)
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
        "selected": {
            "surfaces": list(best_values[:6]),
            "foregrounds": list(best_values[6:]),
        },
    }


def select_two_seed_system_runs(
    runs: list[dict[str, Any]],
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, Any]]:
    selected = min(
        runs,
        key=lambda row: (
            row["objective"],
            tuple(row["selected"]["surfaces"]),
            tuple(row["selected"]["foregrounds"]),
        ),
    )
    return (
        tuple(selected["selected"]["surfaces"]),
        tuple(selected["selected"]["foregrounds"]),
        selected,
    )


def coupled_lightness_repair(
    base: FamilyDefinition,
    surfaces: tuple[str, ...],
    foregrounds: tuple[str, ...],
    target_ab: np.ndarray,
    surface_target_ab: np.ndarray,
    terminal_values: tuple[str, ...],
) -> tuple[str, ...]:
    """Deterministically feed terminal clearance back into the three free FG L values."""

    lab = srgb_to_oklab(hex_array(foregrounds))
    shipped_lab = srgb_to_oklab(
        hex_array(tuple(base.surfaces[f"fg_{index}"] for index in range(3)))
    )
    if np.allclose(target_ab, shipped_lab[:, 1:], rtol=0.0, atol=1e-12):
        return foregrounds
    shipped_l = shipped_lab[:, 0]
    candidates = [foregrounds]
    for first in np.linspace(-0.018, 0.018, 13):
        for second in np.linspace(-0.018, 0.018, 13):
            for third in np.linspace(-0.018, 0.018, 13):
                proposal = lab.copy()
                proposal[:, 0] += (first, second, third)
                if np.any(np.abs(proposal[:, 0] - shipped_l) > FOREGROUND_LIGHTNESS_RADIUS):
                    continue
                rgb = oklab_to_srgb(proposal)
                if np.any((rgb < 0.0) | (rgb > 1.0)):
                    continue
                candidates.append(tuple(srgb_to_hex(value) for value in rgb))
    return min(
        candidates,
        key=lambda candidate: (
            full_system_objective(
                base, target_ab, surface_target_ab, surfaces + candidate, terminal_values
            ),
            candidate,
        ),
    )


def full_system_failures(
    base: FamilyDefinition,
    surfaces: tuple[str, ...],
    foregrounds: tuple[str, ...],
    terminal_values: tuple[str, ...],
) -> list[str]:
    failures = foreground_failures(base, foreground_metrics(base, surfaces, foregrounds))
    surface = surface_metrics(base, surfaces, foregrounds)
    for state in ("normal", "shifted"):
        luminance = np.asarray(surface[f"{state}_relative_luminance"])
        if np.any(np.diff(luminance) < -1e-12):
            failures.append(f"surface {state} luminance is not monotonic")
    for index, value in enumerate(surface["shifted_adjacent_delta_e_ok"]):
        if value + 1e-12 < DARK_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK:
            failures.append(f"surface transformed adjacent {index} {value:.4f} < 1.8000")
    if surface["shifted_span_delta_e_ok"] + 1e-12 < 6.0:
        failures.append(
            f"surface transformed span {surface['shifted_span_delta_e_ok']:.4f} < 6.0000"
        )
    for role, value in zip(
        BACKGROUND_SURFACE_ROLES, surface["normal_relative_luminance"], strict=True
    ):
        ceiling = DARK_SURFACE_MAXIMUM_COMMANDED_LUMINANCE[role]
        if value > ceiling + 1e-12:
            failures.append(f"{role} commanded luminance {value:.6f} > {ceiling:.6f}")
    drift = surface_lightness_drift(base, surfaces)
    if drift > SURFACE_LIGHTNESS_DRIFT + 1e-12:
        failures.append(
            f"surface Oklab L drifted {drift:.4f} > {SURFACE_LIGHTNESS_DRIFT:.4f}; "
            "surfaces may move in hue only"
        )
    if any(full_system_violations(base, surfaces, foregrounds, terminal_values)) and not failures:
        failures.append("terminal-coupled or explicit foreground bound gate failed")
    return failures


def _minimum_failure(failures: list[str], label: str, actual: float, floor: float | None) -> None:
    if floor is not None and actual + 1e-12 < floor:
        failures.append(f"{label} {actual:.4f} < {floor:.4f}")


def _maximum_failure(failures: list[str], label: str, actual: float, ceiling: float) -> None:
    if actual > ceiling + 1e-12:
        failures.append(f"{label} {actual:.6f} > {ceiling:.6f}")


def categorical_failures(
    base: FamilyDefinition,
    values: tuple[str, ...],
    metrics: dict[str, Any],
    floors: dict[str, Any],
) -> list[str]:
    """Validate only the categorical bank; no other bank may veto a count trial."""

    failures: list[str] = []
    bank_floors = floors["categorical"]
    _minimum_failure(
        failures,
        "categorical day pair",
        metrics["normal_pair_delta_e_ok"],
        base.daylight_minimum_delta_e_ok,
    )
    _minimum_failure(
        failures,
        "categorical transformed pair CAM16-UCS",
        metrics["sampled_gain_pair_min_cam16_ucs"],
        bank_floors["transformed_pair_cam16_ucs"],
    )
    _minimum_failure(
        failures,
        "categorical day hue gap",
        metrics["normal_hue_gap_degrees"],
        base.daylight_minimum_hue_gap_degrees,
    )
    _minimum_failure(failures, "categorical day mean chroma", metrics["normal_mean_chroma"], 0.09)
    _maximum_failure(failures, "categorical day mean chroma", metrics["normal_mean_chroma"], 0.105)
    _maximum_failure(
        failures, "categorical day maximum chroma", metrics["normal_max_chroma"], 0.111
    )
    _minimum_failure(
        failures,
        "categorical transformed bg_0 contrast",
        metrics["transformed_background_contrast_bg0_min"],
        3.0,
    )
    for index, value in enumerate(metrics["normal_foreground_clearance_by_role"]):
        _minimum_failure(
            failures,
            f"categorical day fg_{index} clearance",
            value,
            base.categorical_daylight_minimum_foreground_delta_e_ok,
        )
    for index, (value, floor) in enumerate(
        zip(
            metrics["transformed_foreground_clearance_by_role_cam16_ucs"],
            bank_floors["transformed_foreground_by_role_cam16_ucs"],
            strict=True,
        )
    ):
        _minimum_failure(
            failures, f"categorical transformed fg_{index} CAM16-UCS clearance", value, floor
        )
    _minimum_failure(
        failures,
        "categorical sampled-grid foreground CAM16-UCS clearance",
        metrics["sampled_gain_foreground_clearance_min_cam16_ucs"],
        bank_floors["sampled_gain_foreground_clearance_min_cam16_ucs"],
    )
    category_bytes = bytes_from_hex(values)
    for (color_index, channel_index), ceiling in CATEGORY_CHANNEL_CEILINGS.get(
        base.slug, {}
    ).items():
        if color_index < len(values):
            _maximum_failure(
                failures,
                f"categorical maturity byte color {color_index} channel {channel_index}",
                float(category_bytes[color_index, channel_index]),
                float(ceiling),
            )
    binding_floor = min(
        bank_floors["transformed_pair_cam16_ucs"],
        bank_floors["sampled_gain_foreground_clearance_min_cam16_ucs"],
    )
    binding_value = min(
        metrics["sampled_gain_pair_min_cam16_ucs"],
        metrics["sampled_gain_foreground_clearance_min_cam16_ucs"],
    )
    if not failures and binding_value < binding_floor * (1.0 + SAMPLED_GAIN_MARGIN):
        foregrounds = tuple(base.surfaces[f"fg_{index}"] for index in range(3))
        dense = accent_metrics(base, values, foregrounds, terminal=False, sample_grid="dense")
        _minimum_failure(
            failures,
            "categorical adaptive-grid pair CAM16-UCS",
            dense["sampled_gain_pair_min_cam16_ucs"],
            bank_floors["transformed_pair_cam16_ucs"],
        )
        _minimum_failure(
            failures,
            "categorical adaptive-grid foreground CAM16-UCS",
            dense["sampled_gain_foreground_clearance_min_cam16_ucs"],
            bank_floors["sampled_gain_foreground_clearance_min_cam16_ucs"],
        )
    return failures


def terminal_failures(
    base: FamilyDefinition,
    values: tuple[str, ...],
    metrics: dict[str, Any],
    floors: dict[str, Any],
) -> list[str]:
    """Validate authored terminal roles and explicit ANSI aliases only."""

    failures: list[str] = []
    bank_floors = floors["terminal"]
    _minimum_failure(
        failures,
        "terminal day pair",
        metrics["normal_pair_delta_e_ok"],
        base.terminal_daylight_minimum_delta_e_ok,
    )
    _minimum_failure(
        failures,
        "terminal sampled-grid pair CAM16-UCS",
        metrics["sampled_gain_pair_min_cam16_ucs"],
        bank_floors["transformed_pair_cam16_ucs"],
    )
    _minimum_failure(
        failures,
        "terminal transformed bg_0 contrast",
        metrics["transformed_background_contrast_bg0_min"],
        4.5,
    )
    _maximum_failure(
        failures, "terminal semantic hue error", metrics["normal_semantic_hue_error_max"], 30.0
    )
    _maximum_failure(
        failures,
        "terminal commanded maximum chroma",
        metrics["normal_max_chroma"],
        TERMINAL_CHROMA_CEILINGS[base.slug],
    )
    terminal_bytes = bytes_from_hex(values)
    for (color_index, channel_index), ceiling in TERMINAL_CHANNEL_CEILINGS.get(
        base.slug, {}
    ).items():
        _maximum_failure(
            failures,
            f"terminal maturity byte color {color_index} channel {channel_index}",
            float(terminal_bytes[color_index, channel_index]),
            float(ceiling),
        )
    day_floors = (
        base.terminal_daylight_minimum_fg_0_delta_e_ok,
        base.terminal_daylight_minimum_fg_1_delta_e_ok,
        base.terminal_daylight_minimum_fg_2_delta_e_ok,
    )
    for index, (value, floor) in enumerate(
        zip(metrics["normal_foreground_clearance_by_role"], day_floors, strict=True)
    ):
        _minimum_failure(failures, f"terminal day fg_{index} clearance", value, floor)
    for index, (value, floor) in enumerate(
        zip(
            metrics["transformed_foreground_clearance_by_role_cam16_ucs"],
            bank_floors["transformed_foreground_by_role_cam16_ucs"],
            strict=True,
        )
    ):
        _minimum_failure(
            failures, f"terminal transformed fg_{index} CAM16-UCS clearance", value, floor
        )
    if not failures and metrics["sampled_gain_pair_min_cam16_ucs"] < (
        bank_floors["transformed_pair_cam16_ucs"] * (1.0 + SAMPLED_GAIN_MARGIN)
    ):
        foregrounds = tuple(base.surfaces[f"fg_{index}"] for index in range(3))
        dense = accent_metrics(base, values, foregrounds, terminal=True, sample_grid="dense")
        _minimum_failure(
            failures,
            "terminal adaptive-grid pair CAM16-UCS",
            dense["sampled_gain_pair_min_cam16_ucs"],
            bank_floors["transformed_pair_cam16_ucs"],
        )
    return failures


def sequential_failures(metrics: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    _minimum_failure(
        failures, "sequential day lightness range", metrics["normal_lightness_range"], 0.5
    )
    _minimum_failure(
        failures, "sequential transformed J range", metrics["transformed_j_range"], 10.0
    )
    _minimum_failure(
        failures,
        "sequential day monotonic step",
        metrics["normal_minimum_signed_lightness_step"],
        1e-9,
    )
    _minimum_failure(
        failures,
        "sequential transformed J monotonic step",
        metrics["transformed_minimum_signed_j_step"],
        1e-9,
    )
    _maximum_failure(
        failures, "sequential day CV", metrics["normal_cv"], SEQUENTIAL_COMMANDED_CV_CEILING
    )
    _maximum_failure(
        failures,
        "sequential transformed CAM16-UCS CV",
        metrics["transformed_cam16_cv"],
        SEQUENTIAL_TRANSFORMED_CV_CEILING,
    )
    _minimum_failure(
        failures,
        "sequential light endpoint plot-canvas contrast",
        metrics["light_endpoint_plot_canvas_contrast"],
        4.5,
    )
    _minimum_failure(
        failures,
        "sequential dark endpoint plot-canvas contrast",
        metrics["dark_endpoint_plot_canvas_contrast"],
        1.02,
    )
    _minimum_failure(
        failures,
        "sequential sampled-grid transformed J step",
        metrics["sampled_gain_minimum_signed_j_step"],
        1e-9,
    )
    return failures


def final_assembled_dependent_failures(
    base: FamilyDefinition,
    category_values: tuple[str, ...],
    category: dict[str, Any],
    terminal_values: tuple[str, ...],
    terminal: dict[str, Any],
    sequential: dict[str, Any],
    floors: dict[str, Any],
) -> list[str]:
    return (
        categorical_failures(base, category_values, category, floors)
        + terminal_failures(base, terminal_values, terminal, floors)
        + sequential_failures(sequential)
    )


def dependent_failures(
    base: FamilyDefinition,
    category_values: tuple[str, ...],
    category: dict[str, Any],
    terminal_values: tuple[str, ...],
    terminal: dict[str, Any],
    sequential: dict[str, Any],
    sequential_baseline: dict[str, Any],
) -> list[str]:
    """Compatibility wrapper for the old full-system experiment entry point."""

    del sequential_baseline
    foregrounds = tuple(base.surfaces[f"fg_{index}"] for index in range(3))
    floors = dependent_bank_floors(base, foregrounds)
    return final_assembled_dependent_failures(
        base,
        category_values,
        category,
        terminal_values,
        terminal,
        sequential,
        floors,
    )


def run_experiment(iterations: dict[str, int] | None = None) -> dict[str, Any]:
    iterations = iterations or DEFAULT_ITERATIONS
    output: dict[str, Any] = {
        "schema": 2,
        "method": (
            "fresh two-seed bounded exact-Hex8 joint bg_0..bg_5 + fg_0..fg_2 search "
            "per profile/lane; dependent banks rerun with candidate surfaces and controlled "
            "same-profile seed pairs; bounded evidence only"
        ),
        "foreground_target": (
            "unit direction of the Light Mid-Depth mean Oklab a/b vector at chroma multipliers "
            "[1.2,1.0,0.8]; lane interpolation from shipped a/b; soft target with free L"
        ),
        "surface_target": (
            "each background role's Oklab a/b interpolated toward its Light Mid-Depth "
            "counterpart at the same role; dark L retained; soft target within ±24-byte bounds"
        ),
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
        controlled_seed_offset = profile_index * 100
        sequential_fingerprints: dict[str, tuple[tuple[str, ...], list[dict[str, Any]]]] = {}
        for lane, weight in LANES.items():
            print(f"{slug} / {lane}", flush=True)
            target_ab = foreground_target(base, weight)
            surface_target_ab = surface_target(base, weight)
            system_runs = [
                bounded_system_search(
                    base,
                    target_ab,
                    surface_target_ab,
                    None,
                    seed=SEED_BASES["full_system"] + controlled_seed_offset + seed_add,
                    iterations=iterations["full_system"],
                )
                for seed_add in (0, 1)
            ]
            surfaces, foregrounds, selected_system_run = select_two_seed_system_runs(system_runs)
            lane_base = candidate_family(base, surfaces, foregrounds)
            foreground = foreground_metrics(base, surfaces, foregrounds)
            surface = surface_metrics(base, surfaces, foregrounds)
            sequential_baseline, _ = sequential_metrics(lane_base, base.sequential_anchors)
            cat_runs = []
            term_runs = []
            for seed_add in (0, 1):
                cat_runs.append(
                    bounded_exact_search(
                        base.categorical_colors,
                        lambda values, base=lane_base, foregrounds=foregrounds: (
                            categorical_objective(base, foregrounds, values)
                        ),
                        seed=SEED_BASES["categorical"] + controlled_seed_offset + seed_add,
                        iterations=iterations["categorical"],
                        radius=18,
                    )
                )
                term_runs.append(
                    bounded_exact_search(
                        base.terminal_colors,
                        lambda values, base=lane_base, foregrounds=foregrounds: terminal_objective(
                            base, foregrounds, values
                        ),
                        seed=SEED_BASES["terminal"] + controlled_seed_offset + seed_add,
                        iterations=(
                            (4000 if iterations["terminal"] >= 900 else iterations["terminal"])
                            if slug == "1200k-dark"
                            else iterations["terminal"]
                        ),
                        radius=36 if slug in TERMINAL_INITIAL_PROPOSALS else 16,
                        initial_candidates=TERMINAL_INITIAL_PROPOSALS.get(slug, ()),
                    )
                )
            categorical, selected_cat_run = select_two_seed_runs(cat_runs)
            terminal, selected_term_run = select_two_seed_runs(term_runs)
            for _repair_pass in range(8):
                repaired_foregrounds = coupled_lightness_repair(
                    base, surfaces, foregrounds, target_ab, surface_target_ab, terminal
                )
                if repaired_foregrounds == foregrounds:
                    break
                foregrounds = repaired_foregrounds
                lane_base = candidate_family(base, surfaces, foregrounds)
                foreground = foreground_metrics(base, surfaces, foregrounds)
                cat_runs = [
                    bounded_exact_search(
                        base.categorical_colors,
                        lambda values, base=lane_base, foregrounds=foregrounds: (
                            categorical_objective(base, foregrounds, values)
                        ),
                        seed=SEED_BASES["categorical"] + controlled_seed_offset + seed_add,
                        iterations=iterations["categorical"],
                        radius=18,
                    )
                    for seed_add in (0, 1)
                ]
                term_runs = [
                    bounded_exact_search(
                        base.terminal_colors,
                        lambda values, base=lane_base, foregrounds=foregrounds: terminal_objective(
                            base, foregrounds, values
                        ),
                        seed=SEED_BASES["terminal"] + controlled_seed_offset + seed_add,
                        iterations=(
                            (4000 if iterations["terminal"] >= 900 else iterations["terminal"])
                            if slug == "1200k-dark"
                            else iterations["terminal"]
                        ),
                        radius=36 if slug in TERMINAL_INITIAL_PROPOSALS else 16,
                        initial_candidates=TERMINAL_INITIAL_PROPOSALS.get(slug, ()),
                    )
                    for seed_add in (0, 1)
                ]
                categorical, selected_cat_run = select_two_seed_runs(cat_runs)
                terminal, selected_term_run = select_two_seed_runs(term_runs)
            else:
                raise RuntimeError(
                    "coupled lightness repair did not converge within four passes; "
                    "extend the refinement loop before trusting these results"
                )
            seq_runs = [
                bounded_exact_search(
                    base.sequential_anchors,
                    lambda values, base=lane_base, baseline=sequential_baseline: (
                        sequential_objective(base, baseline, values)
                    ),
                    seed=SEED_BASES["sequential"] + controlled_seed_offset + seed_add,
                    iterations=iterations["sequential"],
                    radius=10,
                )
                for seed_add in (0, 1)
            ]
            sequential, selected_seq_run = select_two_seed_runs(seq_runs)
            sequential_record, sequence = sequential_metrics(lane_base, sequential)
            dependency_payload = {
                "surfaces": list(surfaces),
                "gains": list(base.profile.gains),
                "baseline": sequential_baseline,
                "objective": "surface-dependent-v1",
            }
            dependency_fingerprint = hashlib.sha256(
                json.dumps(dependency_payload, sort_keys=True).encode()
            ).hexdigest()
            prior = sequential_fingerprints.get(dependency_fingerprint)
            invariance = prior is None or (prior[0] == sequential and prior[1] == seq_runs)
            sequential_fingerprints[dependency_fingerprint] = (sequential, seq_runs)
            category_metrics = accent_metrics(lane_base, categorical, foregrounds, terminal=False)
            terminal_metrics = accent_metrics(lane_base, terminal, foregrounds, terminal=True)
            surface = surface_metrics(base, surfaces, foregrounds)
            fg_failures = full_system_failures(base, surfaces, foregrounds, terminal)
            bank_failures = dependent_failures(
                lane_base,
                categorical,
                category_metrics,
                terminal,
                terminal_metrics,
                sequential_record,
                sequential_baseline,
            )
            all_failures = fg_failures + bank_failures
            candidate = candidate_family(
                base, surfaces, foregrounds, categorical, terminal, sequential
            )
            shipped_fg_lab = srgb_to_oklab(
                hex_array(tuple(base.surfaces[f"fg_{index}"] for index in range(3)))
            )
            candidate_fg_lab = srgb_to_oklab(hex_array(foregrounds))
            shipped_surface_lab = srgb_to_oklab(
                hex_array(tuple(base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES))
            )
            candidate_surface_lab = srgb_to_oklab(hex_array(surfaces))
            full_ab, light_mean_chroma, light_direction = full_foreground_pattern()
            profile_record["candidates"][lane] = {
                "weight": weight,
                "surfaces": dict(zip(BACKGROUND_SURFACE_ROLES, surfaces, strict=True)),
                "foregrounds": list(foregrounds),
                "foreground_target_ab": target_ab.tolist(),
                "surface_target_ab": surface_target_ab.tolist(),
                "full_foreground_target_ab": full_ab.tolist(),
                "light_mid_depth_mean_chroma": light_mean_chroma,
                "light_mid_depth_mean_ab_direction": light_direction.tolist(),
                "foreground_lightness_deltas_vs_shipped": (
                    candidate_fg_lab[:, 0] - shipped_fg_lab[:, 0]
                ).tolist(),
                "surface_movement_mean_delta_e_ok": float(
                    np.linalg.norm(candidate_surface_lab - shipped_surface_lab, axis=1).mean()
                    * 100.0
                ),
                "foreground_plus_b_reduction_vs_shipped": float(
                    shipped_fg_lab[:, 2].mean() - candidate_fg_lab[:, 2].mean()
                ),
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
                    "surface": surface,
                    "foreground": foreground,
                    "categorical": category_metrics,
                    "terminal": terminal_metrics,
                    "sequential": sequential_record,
                },
                "search": {
                    "full_system": {
                        "bounds": (
                            "surface shipped bytes ±24; foreground shipped bytes ±48; "
                            "foreground Oklab L within shipped L ±0.06"
                        ),
                        "objective": (
                            "huge exact hard gates; transformed clarity/hierarchy and movement; "
                            "then commanded warmth/chroma/soft target; terminal-coupled L repair"
                        ),
                        "runs": system_runs,
                        "selected_seed": selected_system_run["seed"],
                        "selected": selected_system_run["selected"],
                        "selected_after_coupled_refinement": {
                            "surfaces": list(surfaces),
                            "foregrounds": list(foregrounds),
                        },
                        "changed_from_shipped": (
                            list(surfaces)
                            != [base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES]
                            or list(foregrounds)
                            != [base.surfaces[f"fg_{index}"] for index in range(3)]
                        ),
                    },
                    "categorical": {
                        "bounds": "each shipped sRGB byte ±18, clipped to [0,255]",
                        "objective": "hard release floors, then separation/clearance/contrast/corner evidence/movement",
                        "runs": cat_runs,
                        "selected_seed": selected_cat_run["seed"],
                        "changed_from_shipped": list(categorical) != list(base.categorical_colors),
                    },
                    "terminal": {
                        "bounds": (
                            "each shipped sRGB byte ±36 for 1200k-dark, otherwise ±16; "
                            "clipped to [0,255]"
                        ),
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
                        "surface_dependency_fingerprint": dependency_fingerprint,
                        "controlled_identical_input_invariance": invariance,
                    },
                },
                "failed_gates": all_failures,
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
        {"full_system": 2, "categorical": 2, "terminal": 2, "sequential": 2}
        if args.quick
        else DEFAULT_ITERATIONS
    )
    result = run_experiment(iterations)
    output = Path(__file__).with_name("search-results.json")
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
