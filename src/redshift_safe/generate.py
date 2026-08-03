"""Deterministic generation and measurement of the six palette families."""

from __future__ import annotations

from itertools import product
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


def _candidate_grid() -> np.ndarray:
    levels = np.linspace(0.0, 1.0, 29)
    return np.array(tuple(product(levels, repeat=3)), dtype=float)


def _categorical_colors(family: FamilyDefinition, count: int = 8) -> np.ndarray:
    candidates = _candidate_grid()
    warm_lab = perceived_lab(candidates, family.profile.gains)
    normal_lab = srgb_to_oklab(candidates)
    background = hex_to_srgb(family.surfaces["background"])
    warm_background = warm_transform(background, family.profile.gains)
    warm_rgb = warm_transform(candidates, family.profile.gains)
    contrast = np.array([contrast_ratio(color, warm_background) for color in warm_rgb])

    tolerance = {"nightshift": 0.025, "redshift": 0.040, "safelight": 0.055}[
        family.profile.slug
    ]
    wanted_contrast = 3.0
    mask = np.zeros(len(candidates), dtype=bool)
    while mask.sum() < 500 and tolerance <= 0.13:
        mask = (np.abs(warm_lab[:, 0] - family.categorical_lightness) <= tolerance) & (
            contrast >= wanted_contrast
        )
        if mask.sum() < 500:
            tolerance += 0.01
            wanted_contrast = max(2.2, wanted_contrast - 0.1)

    candidates = candidates[mask]
    warm_lab = warm_lab[mask]
    normal_lab = normal_lab[mask]
    chroma = np.linalg.norm(warm_lab[:, 1:], axis=1)
    first = int(np.argmax(chroma))
    chosen = [first]

    while len(chosen) < count:
        warm_delta = np.linalg.norm(warm_lab[:, None, :] - warm_lab[chosen][None, :, :], axis=2)
        normal_delta = np.linalg.norm(
            normal_lab[:, None, :] - normal_lab[chosen][None, :, :], axis=2
        )
        min_warm = warm_delta.min(axis=1)
        min_normal = normal_delta.min(axis=1)
        lightness_penalty = np.abs(warm_lab[:, 0] - family.categorical_lightness)
        normal_weight = 0.20 if family.profile.slug == "nightshift" else 0.05
        score = (
            min_warm
            + normal_weight * min_normal
            + 0.04 * chroma
            - 0.25 * lightness_penalty
        )
        score[chosen] = -np.inf
        chosen.append(int(np.argmax(score)))

    return candidates[chosen]


def _mix_oklab(color: np.ndarray, target: np.ndarray, amount: float) -> np.ndarray:
    mixed = srgb_to_oklab(color) * (1.0 - amount) + srgb_to_oklab(target) * amount
    return np.clip(oklab_to_srgb(mixed), 0.0, 1.0)


def _terminal_colors(family: FamilyDefinition, categories: np.ndarray) -> list[str]:
    surfaces = family.surfaces
    first_neutral = (
        hex_to_srgb(surfaces["background_high"])
        if family.mode == "dark"
        else hex_to_srgb(surfaces["foreground"])
    )
    normal = [
        first_neutral,
        *categories[:6],
        hex_to_srgb(surfaces["foreground_soft"]),
    ]
    target = np.ones(3) if family.mode == "dark" else np.zeros(3)
    bright = [hex_to_srgb(surfaces["foreground_muted"])]
    bright.extend(_mix_oklab(color, target, 0.18) for color in categories[:6])
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


def _metrics(family: FamilyDefinition, categories: np.ndarray, sequential: np.ndarray) -> dict[str, Any]:
    gains = family.profile.gains
    warm_categories = perceived_lab(categories, gains)
    normal_categories = srgb_to_oklab(categories)
    category_metrics: dict[str, Any] = {
        "normal_min_delta_e_ok": round(float(pairwise_distances(normal_categories).min()), 2),
        "shifted_min_delta_e_ok": round(float(pairwise_distances(warm_categories).min()), 2),
        "shifted_lightness_mean": round(float(warm_categories[:, 0].mean()), 4),
        "shifted_lightness_range": round(float(np.ptp(warm_categories[:, 0])), 4),
    }
    for brightness in (0.35, 0.12):
        lab = perceived_lab(categories, gains, brightness)
        category_metrics[f"shifted_min_delta_e_ok_at_{brightness:.2f}_brightness"] = round(
            float(pairwise_distances(lab).min()), 2
        )

    shifted_sequence = perceived_lab(sequential, gains)
    sequence_steps = np.linalg.norm(np.diff(shifted_sequence, axis=0), axis=1) * 100.0
    direction = 1.0 if shifted_sequence[-1, 0] >= shifted_sequence[0, 0] else -1.0
    lightness_steps = np.diff(shifted_sequence[:, 0]) * direction
    sequence_metrics = {
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
                contrast_ratio(transformed_surfaces[foreground], transformed_surfaces[background]), 2
            )

    return {
        "categorical": category_metrics,
        "continuous": sequence_metrics,
        "shifted_text_contrast": text_metrics,
    }


def generate_family(family: FamilyDefinition) -> dict[str, Any]:
    categories = _categorical_colors(family)
    sequential = _sequential_colors(family)
    terminal_values = _terminal_colors(family, categories)
    return {
        "slug": family.slug,
        "name": family.name,
        "mode": family.mode,
        "profile": family.profile.slug,
        "surfaces": family.surfaces,
        "terminal": dict(zip(ANSI_NAMES, terminal_values)),
        "categorical": dict(zip(CATEGORY_NAMES, (srgb_to_hex(c) for c in categories))),
        "continuous": [srgb_to_hex(color) for color in sequential],
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
        "schema_version": 1,
        "project": "Redshift Safe Palettes",
        "model_note": (
            "RGB gains are explicit engineering stress profiles, not device calibrations or "
            "spectral measurements. All derived metrics use the transformed sRGB values."
        ),
        "profiles": profiles,
        "families": {family.slug: generate_family(family) for family in FAMILIES},
    }
