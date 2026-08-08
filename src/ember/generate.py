"""Deterministic generation and measurement of the Ember palette families."""

from __future__ import annotations

from typing import Any

import numpy as np

from .color import (
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
from .definitions import (
    BACKGROUND_SURFACE_ROLES,
    DARK_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK,
    DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST,
    DARK_SURFACE_MAXIMUM_COMMANDED_LUMINANCE,
    FAMILIES,
    LIGHT_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK,
    LIGHT_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST,
    LIGHT_MINIMUM_SURFACE_SPAN_DELTA_E_OK,
    MINIMUM_SHIFTED_FOREGROUND_CONTRAST,
    FamilyDefinition,
)

CATEGORY_NAMES = ("one", "two", "three", "four", "five", "six", "seven", "eight")
ANSI_NAMES = (
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    "bright_black",
    "bright_red",
    "bright_green",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
    "bright_white",
)


def _categorical_colors(family: FamilyDefinition) -> np.ndarray:
    """Return the small categorical set composed for day and transformed use."""

    return np.asarray([hex_to_srgb(value) for value in family.categorical_colors])


def _minimum_hue_gap_degrees(colors: np.ndarray) -> float:
    """Return the minimum circular Oklab hue gap among chromatic colors."""

    chromatic = colors[np.linalg.norm(colors[:, 1:], axis=1) >= 0.02]
    hues = np.degrees(np.arctan2(chromatic[:, 2], chromatic[:, 1])) % 360.0
    gaps = [
        abs((hues[left] - hues[right] + 180.0) % 360.0 - 180.0)
        for left in range(len(hues))
        for right in range(left + 1, len(hues))
    ]
    return float(min(gaps))


def _hue_span_degrees(colors: np.ndarray) -> float:
    """Return the smallest circular hue arc containing the chromatic colors."""

    chromatic = colors[np.linalg.norm(colors[:, 1:], axis=1) >= 0.02]
    if len(chromatic) < 2:
        return 0.0
    hues = np.sort(np.degrees(np.arctan2(chromatic[:, 2], chromatic[:, 1])) % 360.0)
    gaps = np.diff(np.concatenate((hues, hues[:1] + 360.0)))
    return float(360.0 - gaps.max())


def _minimum_chroma_vector_cosine(colors: np.ndarray) -> float:
    """Return the least aligned pair of Oklab chroma vectors."""

    chroma = colors[:, 1:]
    unit = chroma / np.linalg.norm(chroma, axis=1, keepdims=True)
    similarities = unit @ unit.T
    return float(similarities[np.triu_indices(len(colors), k=1)].min())


def _terminal_colors(family: FamilyDefinition) -> list[str]:
    """Expand authored semantic accents into the six ANSI color roles."""

    surfaces = family.surfaces
    first_neutral = (
        hex_to_srgb(surfaces["bg_2"]) if family.mode == "dark" else hex_to_srgb(surfaces["fg_0"])
    )
    accents = [hex_to_srgb(value) for value in family.terminal_colors]
    semantic_slots = [accents[index] for index in family.terminal_ansi_indices]
    normal = [first_neutral, *semantic_slots, hex_to_srgb(surfaces["fg_0"])]
    # Bright black is commonly used for comments and metadata. Keep it readable
    # rather than treating it as a decorative low-contrast gray.
    bright = [hex_to_srgb(surfaces["fg_0"])]
    bright.extend(semantic_slots)
    bright.append(hex_to_srgb(surfaces["fg_0"]))
    return [srgb_to_hex(color) for color in normal + bright]


def _smooth_polyline(points: np.ndarray, iterations: int = 3) -> np.ndarray:
    """Round anchor corners with Chaikin subdivision while preserving endpoints."""
    smoothed = points
    for _ in range(iterations):
        left = 0.75 * smoothed[:-1] + 0.25 * smoothed[1:]
        right = 0.25 * smoothed[:-1] + 0.75 * smoothed[1:]
        interior = np.column_stack((left, right)).reshape(-1, smoothed.shape[1])
        smoothed = np.vstack((smoothed[0], interior, smoothed[-1]))
    return smoothed


def _interpolate_polyline(points: np.ndarray, samples_per_segment: int = 512) -> np.ndarray:
    chunks = []
    for index in range(len(points) - 1):
        endpoint = index == len(points) - 2
        steps = samples_per_segment + int(endpoint)
        t = np.linspace(0.0, 1.0, steps, endpoint=endpoint)[:, None]
        chunks.append(points[index] * (1.0 - t) + points[index + 1] * t)
    return np.concatenate(chunks)


def _sequential_colors(family: FamilyDefinition, count: int = 256) -> np.ndarray:
    anchors_rgb = np.array([hex_to_srgb(value) for value in family.sequential_anchors])
    anchor_lab = _smooth_polyline(srgb_to_oklab(anchors_rgb))
    dense_lab = _interpolate_polyline(anchor_lab)

    dense_rgb = np.clip(oklab_to_srgb(dense_lab), 0.0, 1.0)
    shifted_lab = perceived_lab(dense_rgb, family.profile.gains)
    step = np.linalg.norm(np.diff(shifted_lab, axis=0), axis=1)
    distance = np.concatenate(([0.0], np.cumsum(step)))
    targets = np.linspace(0.0, float(distance[-1]), count)
    indices = np.searchsorted(distance, targets, side="left")
    upper = np.clip(indices, 1, len(dense_lab) - 1)
    lower = upper - 1
    span = distance[upper] - distance[lower]
    fraction = np.divide(
        targets - distance[lower],
        span,
        out=np.zeros_like(targets),
        where=span > 0,
    )[:, None]
    sampled_lab = dense_lab[lower] * (1.0 - fraction) + dense_lab[upper] * fraction
    return np.clip(oklab_to_srgb(sampled_lab), 0.0, 1.0)


def _metrics(
    family: FamilyDefinition, categories: np.ndarray, sequential: np.ndarray
) -> dict[str, Any]:
    gains = family.profile.gains
    warm_categories = perceived_lab(categories, gains)
    normal_categories = srgb_to_oklab(categories)
    transformed_background = warm_transform(hex_to_srgb(family.surfaces["bg_0"]), gains)
    foreground_roles = ("fg_0", "fg_1", "fg_2")
    foreground_colors = np.asarray(
        [hex_to_srgb(family.surfaces[role]) for role in foreground_roles]
    )
    normal_foregrounds = srgb_to_oklab(foreground_colors)
    shifted_foregrounds = perceived_lab(foreground_colors, gains)
    categorical_normal_distance_to_foregrounds = {
        role: round(
            float(
                np.linalg.norm(normal_categories - normal_foregrounds[index], axis=1).min() * 100.0
            ),
            2,
        )
        for index, role in enumerate(foreground_roles)
    }
    categorical_shifted_distance_to_foregrounds = {
        role: round(
            float(
                np.linalg.norm(warm_categories - shifted_foregrounds[index], axis=1).min() * 100.0
            ),
            2,
        )
        for index, role in enumerate(foreground_roles)
    }
    categorical_targets = srgb_to_oklab(
        np.asarray([hex_to_srgb(value) for value in family.categorical_transformed_targets])
    )
    category_metrics: dict[str, Any] = {
        "normal_min_delta_e_ok": round(float(pairwise_distances(normal_categories).min()), 2),
        "normal_minimum_hue_gap_degrees": round(_minimum_hue_gap_degrees(normal_categories), 2),
        "shifted_min_delta_e_ok": round(float(pairwise_distances(warm_categories).min()), 2),
        "minimum_shifted_background_contrast": round(
            min(
                contrast_ratio(warm_transform(color, gains), transformed_background)
                for color in categories
            ),
            2,
        ),
        "shifted_lightness_mean": round(float(warm_categories[:, 0].mean()), 4),
        "shifted_lightness_range": round(float(np.ptp(warm_categories[:, 0])), 4),
        "normal_chroma_max": round(
            float(np.linalg.norm(normal_categories[:, 1:], axis=1).max()), 4
        ),
        "normal_chroma_mean": round(
            float(np.linalg.norm(normal_categories[:, 1:], axis=1).mean()), 4
        ),
        "normal_min_delta_e_ok_to_foregrounds": categorical_normal_distance_to_foregrounds,
        "shifted_min_delta_e_ok_to_foregrounds": categorical_shifted_distance_to_foregrounds,
        "transformed_target_max_delta_e_ok": round(
            float(np.linalg.norm(warm_categories - categorical_targets, axis=1).max() * 100.0),
            2,
        ),
    }
    terminal_colors = np.asarray([hex_to_srgb(value) for value in family.terminal_colors])
    normal_terminal = srgb_to_oklab(terminal_colors)
    shifted_terminal = perceived_lab(terminal_colors, gains)
    terminal_targets = srgb_to_oklab(
        np.asarray([hex_to_srgb(value) for value in family.terminal_transformed_targets])
    )
    normal_foreground_vectors = np.diff(normal_foregrounds, axis=0)
    shifted_foreground_vectors = np.diff(shifted_foregrounds, axis=0)
    normal_foreground_adjacent = np.linalg.norm(normal_foreground_vectors, axis=1)
    shifted_foreground_adjacent = np.linalg.norm(shifted_foreground_vectors, axis=1)
    normal_foreground_lightness_gaps = np.abs(np.diff(normal_foregrounds[:, 0]))
    shifted_foreground_lightness_gaps = np.abs(np.diff(shifted_foregrounds[:, 0]))
    foreground_metrics = {
        "normal_adjacent_delta_e_ok": [
            round(float(distance * 100.0), 2) for distance in normal_foreground_adjacent
        ],
        "shifted_adjacent_delta_e_ok": [
            round(float(distance * 100.0), 2) for distance in shifted_foreground_adjacent
        ],
        "normal_adjacent_lightness_share": [
            round(float(abs(vector[0]) / distance), 4)
            for vector, distance in zip(
                normal_foreground_vectors, normal_foreground_adjacent, strict=True
            )
        ],
        "shifted_adjacent_lightness_share": [
            round(float(abs(vector[0]) / distance), 4)
            for vector, distance in zip(
                shifted_foreground_vectors, shifted_foreground_adjacent, strict=True
            )
        ],
        "normal_lightness_gap_ratio": round(
            float(normal_foreground_lightness_gaps.min() / normal_foreground_lightness_gaps.max()),
            4,
        ),
        "shifted_lightness_gap_ratio": round(
            float(
                shifted_foreground_lightness_gaps.min() / shifted_foreground_lightness_gaps.max()
            ),
            4,
        ),
        "normal_lightness": {
            role: round(float(normal_foregrounds[index, 0]), 4)
            for index, role in enumerate(foreground_roles)
        },
        "normal_chroma": {
            role: round(float(np.linalg.norm(normal_foregrounds[index, 1:])), 4)
            for index, role in enumerate(foreground_roles)
        },
        "shifted_chroma": {
            role: round(float(np.linalg.norm(shifted_foregrounds[index, 1:])), 4)
            for index, role in enumerate(foreground_roles)
        },
        "normal_hue_span_degrees": round(_hue_span_degrees(normal_foregrounds), 2),
        "shifted_hue_span_degrees": round(_hue_span_degrees(shifted_foregrounds), 2),
        "normal_minimum_chroma_vector_cosine": round(
            _minimum_chroma_vector_cosine(normal_foregrounds), 4
        ),
        "shifted_minimum_chroma_vector_cosine": round(
            _minimum_chroma_vector_cosine(shifted_foregrounds), 4
        ),
    }
    terminal_normal_distance_to_foregrounds = {}
    terminal_shifted_distance_to_foregrounds = {}
    for index, role in enumerate(foreground_roles):
        terminal_normal_distance_to_foregrounds[role] = round(
            float(
                np.linalg.norm(normal_terminal - normal_foregrounds[index], axis=1).min() * 100.0
            ),
            2,
        )
        terminal_shifted_distance_to_foregrounds[role] = round(
            float(
                np.linalg.norm(shifted_terminal - shifted_foregrounds[index], axis=1).min() * 100.0
            ),
            2,
        )
    group_ids = sorted(set(family.terminal_night_groups))
    group_members = [
        shifted_terminal[np.asarray(family.terminal_night_groups) == group_id]
        for group_id in group_ids
    ]
    group_spreads = [
        float(pairwise_distances(members).max()) if len(members) > 1 else 0.0
        for members in group_members
    ]
    group_centers = np.asarray([members.mean(axis=0) for members in group_members])
    terminal_metrics = {
        "normal_min_delta_e_ok": round(float(pairwise_distances(normal_terminal).min()), 2),
        "normal_min_delta_e_ok_to_foregrounds": terminal_normal_distance_to_foregrounds,
        "shifted_group_max_delta_e_ok": round(max(group_spreads), 2),
        "shifted_group_center_min_delta_e_ok": (
            round(float(pairwise_distances(group_centers).min()), 2)
            if len(group_centers) > 1
            else None
        ),
        "shifted_min_delta_e_ok_to_foregrounds": terminal_shifted_distance_to_foregrounds,
        "transformed_target_max_delta_e_ok": round(
            float(np.linalg.norm(shifted_terminal - terminal_targets, axis=1).max() * 100.0),
            2,
        ),
    }
    shifted_sequence = perceived_lab(sequential, gains)
    sequence_steps = np.linalg.norm(np.diff(shifted_sequence, axis=0), axis=1) * 100.0
    direction = 1.0 if shifted_sequence[-1, 0] >= shifted_sequence[0, 0] else -1.0
    lightness_steps = np.diff(shifted_sequence[:, 0]) * direction
    normal_sequence = srgb_to_oklab(sequential)
    normal_steps = np.linalg.norm(np.diff(normal_sequence, axis=0), axis=1) * 100.0
    normal_direction = 1.0 if normal_sequence[-1, 0] >= normal_sequence[0, 0] else -1.0
    normal_lightness_steps = np.diff(normal_sequence[:, 0]) * normal_direction
    sequence_metrics = {
        "normal_lightness_range": round(float(np.ptp(normal_sequence[:, 0])), 4),
        "normal_minimum_signed_lightness_step": round(float(normal_lightness_steps.min()), 6),
        "normal_delta_e_ok_cv": round(float(normal_steps.std() / normal_steps.mean()), 4),
        "normal_delta_e_ok_max_to_min": round(float(normal_steps.max() / normal_steps.min()), 3),
        "shifted_lightness_direction": "increasing" if direction > 0 else "decreasing",
        "shifted_lightness_range": round(float(np.ptp(shifted_sequence[:, 0])), 4),
        "minimum_signed_lightness_step": round(float(lightness_steps.min()), 6),
        "delta_e_ok_mean": round(float(sequence_steps.mean()), 4),
        "delta_e_ok_cv": round(float(sequence_steps.std() / sequence_steps.mean()), 4),
        "delta_e_ok_max_to_min": round(float(sequence_steps.max() / sequence_steps.min()), 3),
    }

    transformed_surfaces = {
        key: warm_transform(hex_to_srgb(value), gains) for key, value in family.surfaces.items()
    }
    normal_surfaces = {key: hex_to_srgb(family.surfaces[key]) for key in BACKGROUND_SURFACE_ROLES}
    surface_metrics = {
        "normal_relative_luminance": {
            key: round(float(wcag_luminance(value)), 5) for key, value in normal_surfaces.items()
        },
        "shifted_relative_luminance": {
            key: round(float(wcag_luminance(transformed_surfaces[key])), 5)
            for key in normal_surfaces
        },
        "shifted_primary_text_contrast": {
            key: round(
                contrast_ratio(transformed_surfaces["fg_0"], transformed_surfaces[key]),
                2,
            )
            for key in normal_surfaces
        },
    }
    text_metrics = {}
    for foreground in ("fg_0", "fg_1", "fg_2"):
        for background in BACKGROUND_SURFACE_ROLES:
            text_metrics[f"{foreground}_on_{background}"] = round(
                contrast_ratio(transformed_surfaces[foreground], transformed_surfaces[background]),
                2,
            )

    return {
        "categorical": category_metrics,
        "terminal": terminal_metrics,
        "foreground_ladder": foreground_metrics,
        "continuous": sequence_metrics,
        "surface": surface_metrics,
        "shifted_text_contrast": text_metrics,
    }


def generate_family(family: FamilyDefinition) -> dict[str, Any]:
    category_hex = [srgb_to_hex(color) for color in _categorical_colors(family)]
    # Categorical and terminal consumers receive Hex8, so their guarantees must
    # be measured from the reparsed serialized values rather than optimizer floats.
    categories = np.asarray([hex_to_srgb(color) for color in category_hex])
    # The float samples are the canonical colormap.  Round them to a stable JSON
    # representation *before* calculating metrics so the published guarantees
    # describe exactly what downstream consumers receive.  Hex8 is a convenient
    # preview/fallback, but 8-bit quantization is too coarse to carry the strict
    # uniform-step guarantee at 256 samples.
    sequential = np.round(_sequential_colors(family), 10)
    terminal_values = _terminal_colors(family)
    transformed_background = warm_transform(
        hex_to_srgb(family.surfaces["bg_0"]), family.profile.gains
    )
    transformed_terminal = [
        warm_transform(hex_to_srgb(value), family.profile.gains) for value in terminal_values
    ]
    # ANSI black is background-like only in dark themes. Every foreground-capable
    # small-text slot participates in the release floor.
    small_text_terminal = [
        value
        for index, value in enumerate(transformed_terminal)
        if family.mode == "light" or index != 0
    ]
    return {
        "slug": family.slug,
        "name": family.name,
        "mode": family.mode,
        "profile": family.profile.slug,
        "surfaces": family.surfaces,
        "terminal": dict(zip(ANSI_NAMES, terminal_values)),
        "terminal_daylight_color_count": len(family.terminal_colors),
        "terminal_semantic_color_count": family.terminal_color_count,
        "terminal_ansi_indices": list(family.terminal_ansi_indices),
        "terminal_night_groups": list(family.terminal_night_groups),
        "terminal_transformed_targets": list(family.terminal_transformed_targets),
        "terminal_daylight_minimum_delta_e_ok_target": (
            family.terminal_daylight_minimum_delta_e_ok
        ),
        "terminal_night_minimum_delta_e_ok_target": (family.terminal_night_minimum_delta_e_ok),
        "terminal_daylight_minimum_fg_0_delta_e_ok_target": (
            family.terminal_daylight_minimum_fg_0_delta_e_ok
        ),
        "terminal_night_minimum_fg_0_delta_e_ok_target": (
            family.terminal_night_minimum_fg_0_delta_e_ok
        ),
        "terminal_daylight_minimum_fg_1_delta_e_ok_target": (
            family.terminal_daylight_minimum_fg_1_delta_e_ok
        ),
        "terminal_night_minimum_fg_1_delta_e_ok_target": (
            family.terminal_night_minimum_fg_1_delta_e_ok
        ),
        "terminal_daylight_minimum_fg_2_delta_e_ok_target": (
            family.terminal_daylight_minimum_fg_2_delta_e_ok
        ),
        "terminal_night_minimum_fg_2_delta_e_ok_target": (
            family.terminal_night_minimum_fg_2_delta_e_ok
        ),
        "foreground_daylight_minimum_adjacent_delta_e_ok_target": (
            family.foreground_daylight_minimum_adjacent_delta_e_ok
        ),
        "foreground_daylight_maximum_adjacent_delta_e_ok_target": (
            family.foreground_daylight_maximum_adjacent_delta_e_ok
        ),
        "foreground_night_minimum_adjacent_delta_e_ok_target": (
            family.foreground_night_minimum_adjacent_delta_e_ok
        ),
        "foreground_night_maximum_adjacent_delta_e_ok_target": (
            family.foreground_night_maximum_adjacent_delta_e_ok
        ),
        "foreground_minimum_lightness_gap_ratio_target": (
            family.foreground_minimum_lightness_gap_ratio
        ),
        "foreground_daylight_minimum_lightness_share_target": (
            family.foreground_daylight_minimum_lightness_share
        ),
        "foreground_night_minimum_lightness_share_target": (
            family.foreground_night_minimum_lightness_share
        ),
        "foreground_maximum_hue_span_degrees_target": (family.foreground_maximum_hue_span_degrees),
        "foreground_night_maximum_hue_span_degrees_target": (
            family.foreground_night_maximum_hue_span_degrees
        ),
        "foreground_maximum_chroma_target": family.foreground_maximum_chroma,
        "foreground_daylight_minimum_chroma_vector_cosine_target": (
            family.foreground_daylight_minimum_chroma_vector_cosine
        ),
        "foreground_night_minimum_chroma_vector_cosine_target": (
            family.foreground_night_minimum_chroma_vector_cosine
        ),
        "foreground_chroma_direction": family.foreground_chroma_direction,
        "foreground_chroma_order_tolerance": family.foreground_chroma_order_tolerance,
        "terminal_minimum_shifted_foreground_contrast": round(
            min(contrast_ratio(value, transformed_background) for value in small_text_terminal),
            2,
        ),
        "categorical": dict(zip(CATEGORY_NAMES, category_hex)),
        "categorical_transformed_targets": list(family.categorical_transformed_targets),
        "daylight_minimum_delta_e_ok_target": family.daylight_minimum_delta_e_ok,
        "daylight_minimum_hue_gap_degrees_target": (family.daylight_minimum_hue_gap_degrees),
        "categorical_shifted_background_contrast_minimum_target": (
            family.categorical_shifted_background_contrast_minimum
        ),
        "categorical_daylight_minimum_foreground_delta_e_ok_target": (
            family.categorical_daylight_minimum_foreground_delta_e_ok
        ),
        "categorical_night_minimum_foreground_delta_e_ok_target": (
            family.categorical_night_minimum_foreground_delta_e_ok
        ),
        "continuous_rgb": sequential.tolist(),
        "continuous_hex8": [srgb_to_hex(color) for color in sequential],
        "metrics": _metrics(family, categories, sequential),
    }


def generate_manifest() -> dict[str, Any]:
    profiles = {
        slug: {
            "name": profile.name,
            "target": profile.target,
            "rgb_gains": list(profile.gains),
            "categorical_minimum_delta_e_ok_target": profile.categorical_threshold,
            "description": profile.description,
        }
        for slug, profile in {family.profile.slug: family.profile for family in FAMILIES}.items()
    }
    return {
        "schema_version": 12,
        "project": "Ember",
        "model_note": (
            "RGB gains are explicit engineering stress profiles, not device calibrations or "
            "spectral measurements. Metrics are explicitly labeled as commanded or transformed."
        ),
        "quality_targets": {
            "accent_selection_priority": [
                "match authored transformed perceptual outcomes",
                "optimize commanded daytime aesthetics without weakening transformed outcomes",
            ],
            "cross_state_hue_consistency_required": False,
            "terminal_distinguishability_reference_role": "fg_0",
            "terminal_distinguishability_reference_roles": ["fg_0", "fg_1", "fg_2"],
            "joint_terminal_optimization_priority": [
                "primary foreground reading quality",
                "connected foreground hierarchy",
                "accent separation from every foreground role",
                "accent pairwise separation and ANSI semantics",
            ],
            "bg_roles_low_to_high": list(BACKGROUND_SURFACE_ROLES),
            "dark_minimum_adjacent_surface_delta_e_ok": (DARK_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK),
            "minimum_shifted_foreground_contrast": MINIMUM_SHIFTED_FOREGROUND_CONTRAST,
            "dark_surface_maximum_commanded_relative_luminance": (
                DARK_SURFACE_MAXIMUM_COMMANDED_LUMINANCE
            ),
            "dark_minimum_shifted_primary_text_contrast": (
                DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST
            ),
            "light_minimum_shifted_primary_text_contrast": (
                LIGHT_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST
            ),
            "light_minimum_adjacent_surface_delta_e_ok": (
                LIGHT_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK
            ),
            "light_minimum_surface_span_delta_e_ok": LIGHT_MINIMUM_SURFACE_SPAN_DELTA_E_OK,
        },
        "profiles": profiles,
        "families": {family.slug: generate_family(family) for family in FAMILIES},
    }
