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
)
from .definitions import FAMILIES, FamilyDefinition

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


def _terminal_colors(family: FamilyDefinition) -> list[str]:
    """Return authored day accents that collapse into the configured night groups."""

    surfaces = family.surfaces
    first_neutral = (
        hex_to_srgb(surfaces["background_high"])
        if family.mode == "dark"
        else hex_to_srgb(surfaces["foreground"])
    )
    accents = [hex_to_srgb(value) for value in family.terminal_colors]
    semantic_slots = [accents[index % len(accents)] for index in range(6)]
    normal = [first_neutral, *semantic_slots, hex_to_srgb(surfaces["foreground"])]
    # Bright black is commonly used for comments and metadata. Keep it readable
    # rather than treating it as a decorative low-contrast gray.
    bright = [hex_to_srgb(surfaces["foreground"])]
    bright.extend(semantic_slots)
    bright.append(hex_to_srgb(surfaces["foreground"]))
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
    category_metrics: dict[str, Any] = {
        "normal_min_delta_e_ok": round(float(pairwise_distances(normal_categories).min()), 2),
        "shifted_min_delta_e_ok": round(float(pairwise_distances(warm_categories).min()), 2),
        "shifted_lightness_mean": round(float(warm_categories[:, 0].mean()), 4),
        "shifted_lightness_range": round(float(np.ptp(warm_categories[:, 0])), 4),
        "normal_chroma_max": round(
            float(np.linalg.norm(normal_categories[:, 1:], axis=1).max()), 4
        ),
        "normal_chroma_mean": round(
            float(np.linalg.norm(normal_categories[:, 1:], axis=1).mean()), 4
        ),
    }
    terminal_colors = np.asarray([hex_to_srgb(value) for value in family.terminal_colors])
    normal_terminal = srgb_to_oklab(terminal_colors)
    shifted_terminal = perceived_lab(terminal_colors, gains)
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
        "shifted_group_max_delta_e_ok": round(max(group_spreads), 2),
        "shifted_group_center_min_delta_e_ok": (
            round(float(pairwise_distances(group_centers).min()), 2)
            if len(group_centers) > 1
            else None
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
    text_metrics = {}
    for foreground in ("foreground", "foreground_soft", "foreground_muted"):
        for background in ("background", "background_alt", "background_high"):
            text_metrics[f"{foreground}_on_{background}"] = round(
                contrast_ratio(transformed_surfaces[foreground], transformed_surfaces[background]),
                2,
            )

    return {
        "categorical": category_metrics,
        "terminal": terminal_metrics,
        "continuous": sequence_metrics,
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
        hex_to_srgb(family.surfaces["background"]), family.profile.gains
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
        "terminal_night_groups": list(family.terminal_night_groups),
        "terminal_daylight_minimum_delta_e_ok_target": (
            family.terminal_daylight_minimum_delta_e_ok
        ),
        "terminal_night_minimum_delta_e_ok_target": (family.terminal_night_minimum_delta_e_ok),
        "terminal_minimum_shifted_foreground_contrast": round(
            min(contrast_ratio(value, transformed_background) for value in small_text_terminal),
            2,
        ),
        "categorical": dict(zip(CATEGORY_NAMES, category_hex)),
        "daylight_minimum_delta_e_ok_target": family.daylight_minimum_delta_e_ok,
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
        "schema_version": 4,
        "project": "Ember: Redshift Safe Color Palettes",
        "model_note": (
            "RGB gains are explicit engineering stress profiles, not device calibrations or "
            "spectral measurements. Metrics are explicitly labeled as commanded or transformed."
        ),
        "legacy_aliases": {
            "ember-dark": "3400k-dark",
            "ember-light": "3400k-light",
            "lowfire-dark": "2000k-dark",
            "safelight-dark": "1200k-dark",
        },
        "removed_families": {
            "lowfire-light": "No deep-shift light replacement; use 3400k-light or a dark deep tier.",
            "safelight-light": "No deep-shift light replacement; use 3400k-light or a dark deep tier.",
        },
        "profiles": profiles,
        "families": {family.slug: generate_family(family) for family in FAMILIES},
    }
