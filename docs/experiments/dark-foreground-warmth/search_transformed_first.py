"""Transformed-first variable-surface search for the fourth experiment pass.

The seen (transformed) state is designed first: even background distinctness,
foreground/background clearance, and every contrast floor bind as hard gates in
the transformed state. Whatever exact-Hex8 freedom remains is spent on commanded
warmth: a soft halfway pull toward the 3400K Light Mid-Depth counterparts for
both ink and surfaces. Surface count per profile is a search variable (never
below three). Dependent categorical, terminal, and sequential banks are then
searched fresh against each lane's selected exact system, including an attempt
to widen the categorical bank beyond its shipped count.

Bounded exact-Hex8 evidence only; no global-optimality or feasibility claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from itertools import permutations
from pathlib import Path
from typing import Any

import colour
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ember.color import (
    contrast_ratio,
    hex_to_srgb,
    oklab_to_srgb,
    srgb_to_hex,
    srgb_to_oklab,
    warm_transform,
    wcag_luminance,
)
from ember.definitions import (
    DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST,
    DARK_SURFACE_MAXIMUM_COMMANDED_LUMINANCE,
    FAMILIES,
)

EXPERIMENT = Path(__file__).resolve().parent
RESULTS_PATH = EXPERIMENT / "transformed-first-results.json"

PROFILES = ("3400k-dark", "2000k-dark", "1200k-dark")
LANES: dict[str, float] = {"current": 0.0, "halfway": 0.5}
LIGHT_SLUG = "3400k-light"

TRANSFORMED_ADJACENT_FLOOR = 2.5
TRANSFORMED_BG_STEP_FLOOR = 3.3
TRANSFORMED_FG_STEP_FLOOR = 7.0
BG_STEP_PARITY_RATIO = 0.8
TRANSFORMED_UNIFORMITY_RATIO = 1.25
CAM16_ADAPTATION_LUMINANCE = 8.0
CAM16_BACKGROUND_LUMINANCE = 3.0
FLARE_FRACTION = 0.0075
MIN_ADJACENT_DJ = 1.0
MIN_ADJACENT_DJ_TARGET = 2.0
GEOMETRIC_LADDER_BY_COUNT = {
    # Fable-recommended geometric okL ladders: bottom gap widest to counteract
    # CAM16 J compression at the dark end of the transformed state.
    4: (0.105, 0.155, 0.20, 0.245),
    5: (0.10, 0.128, 0.162, 0.198, 0.238),
    6: (0.095, 0.115, 0.14, 0.17, 0.205, 0.245),
}


def cam16_ucs(rgb01: np.ndarray, gains) -> np.ndarray:
    """Flare-included CAM16-UCS under the transformed sRGB, dim viewing conditions."""

    transformed = np.clip(rgb01 * np.asarray(gains), 0.0, 1.0)
    xyz = colour.sRGB_to_XYZ(transformed)
    flare = FLARE_FRACTION * colour.sRGB_to_XYZ(np.ones_like(transformed))
    return np.asarray(
        colour.XYZ_to_CAM16UCS(
            xyz + flare,
            L_A=CAM16_ADAPTATION_LUMINANCE,
            Y_b=CAM16_BACKGROUND_LUMINANCE,
        )
    )


SURFACE_LIGHTNESS_DRIFT = 0.02
FOREGROUND_LIGHTNESS_RADIUS = 0.12
MINIMUM_BG_COUNT = 3
MAXIMUM_BG_COUNT = 6
CATEGORICAL_MARGIN = 0.05

SYSTEM_SEED_BASE = 7000
CATEGORY_SEED_BASE = 17000
TERMINAL_SEED_BASE = 27000
SEQUENTIAL_SEED_BASE = 37000

CATEGORICAL_SEMANTIC_SLOTS = (
    ("warm amber", 65.0),
    ("cool blue/cyan", 225.0),
    ("rose/magenta", 350.0),
    ("green/mint", 150.0),
    ("teal", 185.0),
    ("earth/brown", 45.0),
)

BACKGROUND_ROLE_ALIAS_INDICES = {
    # Preserve the high-use canvas/sidebar distinction and bg_2→bg_3 active-state
    # edge.  Missing roles collapse bg_1→bg_2 first, then bg_4→bg_5.
    3: (0, 1, 1, 1, 2, 2),
    4: (0, 1, 1, 2, 3, 3),
    5: (0, 1, 2, 3, 4, 4),
    6: (0, 1, 2, 3, 4, 5),
}

TERMINAL_INITIAL_PROPOSALS = {
    "2000k-dark": (
        ("#EB8DA6", "#74E5C0", "#C39B65", "#A2D0FF"),
        ("#EC8B96", "#74E5C0", "#C39B55", "#9FC7FC"),
    ),
    "1200k-dark": (
        ("#F39399", "#CCFFB4", "#DEC671"),
        ("#F19299", "#E6FFAF", "#DBC370"),
    ),
}

FULL_TARGET_CHROMA_SCALES = np.asarray((1.2, 1.0, 0.8))


def family(slug: str):
    return next(item for item in FAMILIES if item.slug == slug)


def hex_array(values) -> np.ndarray:
    return np.asarray([hex_to_srgb(value) for value in values], dtype=float)


def bytes_from_hex(values) -> np.ndarray:
    return np.asarray(
        [[int(value[i : i + 2], 16) for i in (1, 3, 5)] for value in values],
        dtype=np.int16,
    )


def hex_from_bytes(values: np.ndarray) -> tuple[str, ...]:
    clipped = np.clip(np.rint(values), 0, 255).astype(np.uint8)
    return tuple("#" + "".join(f"{c:02X}" for c in row) for row in clipped)


def transform_hex(value: str, gains: tuple[float, float, float]) -> str:
    return srgb_to_hex(warm_transform(hex_to_srgb(value), gains))


def violation(
    value: float,
    floor: float | None = None,
    ceiling: float | None = None,
) -> float:
    if floor is not None and value < floor:
        return floor - value
    if ceiling is not None and value > ceiling:
        return value - ceiling
    return 0.0


def penalty(violations: list[float]) -> float:
    array = np.asarray(violations, dtype=float)
    return 1e8 * float(np.dot(array, array))


def light_target() -> Any:
    return family(LIGHT_SLUG)


def role_ladder(base: Any, count: int) -> np.ndarray:
    """Shipped dark L values resampled to `count` roles by index fraction."""

    shipped = srgb_to_oklab(hex_array([base.surfaces[f"bg_{i}"] for i in range(6)]))[:, 0]
    positions = np.linspace(0.0, 1.0, count)
    anchors = np.linspace(0.0, 1.0, len(shipped))
    return np.interp(positions, anchors, shipped)


def surface_warmth_target(base: Any, weight: float, count: int) -> tuple[np.ndarray, np.ndarray]:
    """Halfway Oklab a/b toward the Light Mid-Depth counterpart per role."""

    shipped = srgb_to_oklab(hex_array([base.surfaces[f"bg_{i}"] for i in range(6)]))
    light = srgb_to_oklab(hex_array([light_target().surfaces[f"bg_{i}"] for i in range(6)]))
    ab = shipped[:, 1:] + weight * (light[:, 1:] - shipped[:, 1:])
    ladder = role_ladder(base, count)
    positions = np.linspace(0.0, 1.0, count)
    anchors = np.linspace(0.0, 1.0, 6)
    blended = np.column_stack([np.interp(positions, anchors, ab[:, channel]) for channel in (0, 1)])
    return blended, ladder


def foreground_pattern() -> tuple[np.ndarray, float, np.ndarray]:
    light = srgb_to_oklab(hex_array([light_target().surfaces[f"fg_{i}"] for i in range(3)]))
    chroma = np.linalg.norm(light[:, 1:], axis=1)
    direction = light[:, 1:].mean(axis=0)
    direction = direction / np.linalg.norm(direction)
    mean_chroma = float(chroma.mean())
    pattern = FULL_TARGET_CHROMA_SCALES[:, None] * mean_chroma * direction
    return pattern, mean_chroma, direction


def foreground_target(base: Any, weight: float) -> np.ndarray:
    shipped = srgb_to_oklab(hex_array([base.surfaces[f"fg_{i}"] for i in range(3)]))
    full_ab, _, _ = foreground_pattern()
    return shipped[:, 1:] + weight * (full_ab - shipped[:, 1:])


def transformed_metrics(surfaces: tuple[str, ...], fg: tuple[str, ...], gains) -> dict:
    surf_rgb = hex_array(surfaces)
    fg_rgb = hex_array(fg)
    t_surf = warm_transform(surf_rgb, gains)
    t_fg = warm_transform(fg_rgb, gains)
    t_surf_ucs = cam16_ucs(surf_rgb, gains)
    t_fg_ucs = cam16_ucs(fg_rgb, gains)
    adjacent = np.linalg.norm(np.diff(t_surf_ucs, axis=0), axis=1).tolist()
    fg_adjacent = np.linalg.norm(np.diff(t_fg_ucs, axis=0), axis=1).tolist()
    fg_bg_clearance = (
        np.linalg.norm(t_surf_ucs[:, None, :] - t_fg_ucs[None, :, :], axis=2).min(axis=0)
    ).tolist()
    contrasts = [min(contrast_ratio(f, b) for b in t_surf) for f in t_fg]
    span = float(np.linalg.norm(t_surf_ucs[-1] - t_surf_ucs[0]))
    return {
        "adjacent": adjacent,
        "adjacent_min": float(min(adjacent)),
        "fg_adjacent": fg_adjacent,
        "fg_adjacent_min": float(min(fg_adjacent)),
        "uniformity_ratio": float(max(adjacent) / max(min(adjacent), 1e-9)),
        "span": span,
        "fg_bg_clearance": fg_bg_clearance,
        "fg_bg_clearance_min": float(min(fg_bg_clearance)),
        "contrast": contrasts,
    }


def commanded_metrics(surfaces: tuple[str, ...], fg: tuple[str, ...]) -> dict:
    surf_lab = srgb_to_oklab(hex_array(surfaces))
    fg_lab = srgb_to_oklab(hex_array(fg))
    return {
        "surf_ab": surf_lab[:, 1:],
        "fg_ab": fg_lab[:, 1:],
        "mean_chroma": float(np.linalg.norm(fg_lab[:, 1:], axis=1).mean()),
        "mean_plus_b": float(fg_lab[:, 2].mean()),
    }


def system_violations(
    base: Any,
    surfaces: tuple[str, ...],
    fg: tuple[str, ...],
    count: int,
    weight: float,
) -> tuple[list[float], float]:
    metrics = transformed_metrics(surfaces, fg, base.profile.gains)
    values: list[float] = []
    soft_terms: list[float] = []
    values.extend(violation(v, TRANSFORMED_BG_STEP_FLOOR) for v in metrics["adjacent"])
    # Fable gate: minimum absolute transformed J' separation per adjacent pair so
    # distance cannot be satisfied by chromatic residue alone.
    t_surf_ucs = cam16_ucs(hex_array(surfaces), base.profile.gains)
    dj = np.abs(np.diff(t_surf_ucs[:, 0]))
    values.extend(violation(float(d), MIN_ADJACENT_DJ) for d in dj)
    soft_terms.extend([violation(float(d), MIN_ADJACENT_DJ_TARGET) * 10 for d in dj])
    # Transformed J' must increase strictly up the ladder.
    values.extend(violation(float(d), floor=0.0) for d in np.diff(t_surf_ucs[:, 0]))
    values.extend(violation(v, FG_STEP_FLOOR_CURRENT_REFERENCE) for v in metrics["fg_adjacent"])
    values.append(violation(metrics["uniformity_ratio"], ceiling=TRANSFORMED_UNIFORMITY_RATIO))
    values.append(violation(metrics["span"], 6.0))
    primary_floor = max(4.5, DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST.get(base.slug, 4.5))
    # Tiny margin so Hex8 quantization can land exactly on the floor and still
    # pass downstream strict comparisons.
    floors_by_role = {
        "fg_0": max(4.5, primary_floor) * 1.02,
        "fg_1": 3.5 * 1.02,
        "fg_2": 2.4 * 1.02,
    }
    for contrast, floor_key in zip(metrics["contrast"], ("fg_0", "fg_1", "fg_2"), strict=True):
        family_floor = floors_by_role[floor_key]
        values.append(violation(contrast, family_floor))

    # Commanded-state structural gates.
    luminance = np.asarray(wcag_luminance(hex_array(surfaces)))
    values.extend(violation(float(d), -1e-12) for d in np.diff(luminance))
    # Map each surface's ladder position to the shipped six-role ceiling so a
    # compressed count still uses the ceiling of the depth band it occupies.
    # The floating light anchor buys span with a little ceiling headroom on the
    # lightest role (user-directed: endpoints may float).
    position_ceilings = np.asarray(
        [DARK_SURFACE_MAXIMUM_COMMANDED_LUMINANCE[f"bg_{i}"] for i in range(6)]
    )
    position_ceilings[-1] += 0.005
    positions = np.linspace(0.0, 1.0, 6)
    role_ceilings = np.interp(np.linspace(0.0, 1.0, count), positions, position_ceilings)
    for index in range(count):
        values.append(violation(float(luminance[index]), ceiling=float(role_ceilings[index])))

    # Commanded hue corridor: interiors must stay on the warm-neutral axis spanned
    # by the ladder endpoints — no green/cyan excursions even when CAM16 spacing
    # would reward them.
    if weight > 0.0 and count >= 3:
        surf_lab = srgb_to_oklab(hex_array(surfaces))
        endpoint_lab = srgb_to_oklab(hex_array((surfaces[0], surfaces[-1])))
        hues = np.degrees(np.arctan2(endpoint_lab[:, 2], endpoint_lab[:, 1])) % 360.0
        low, high = min(hues), max(hues)
        tol = 12.0
        lo, hi = (low - tol, high + tol) if abs(high - low) < 180 else (high - tol, low + tol)
        for index in range(1, count - 1):
            hue = float(np.degrees(np.arctan2(surf_lab[index, 2], surf_lab[index, 1])) % 360.0)
            in_corridor = lo <= hue <= hi if lo <= hi else (hue >= lo or hue <= hi)
            values.append(violation(float(in_corridor), 1.0))

    # Commanded warmth soft target and L pinning. The shared-anchor halfway path
    # pins interiors to the endpoint-interpolated commanded L ladder (which for
    # the fable plan is geometric: bottom gap widest).
    target_ab, ladder = surface_warmth_target(base, weight, count)
    surf_lab = srgb_to_oklab(hex_array(surfaces))
    cmd = commanded_metrics(surfaces, fg)
    if weight > 0.0:
        anchor_lab = srgb_to_oklab(hex_array((surfaces[0], surfaces[-1])))
        anchors = np.linspace(0.0, 1.0, count)
        ladder = np.column_stack(
            [np.interp(anchors, (0.0, 1.0), anchor_lab[:, c]) for c in range(3)]
        )
    drift_ceiling = SURFACE_LIGHTNESS_DRIFT + 0.02 if weight > 0.0 else SURFACE_LIGHTNESS_DRIFT
    for index in range(count):
        values.append(
            violation(
                abs(float(surf_lab[index, 0] - ladder[index][0])),
                ceiling=drift_ceiling,
            )
        )
    soft_terms.append(float(np.linalg.norm(cmd["surf_ab"] - target_ab)))
    fg_target = foreground_target(base, weight)
    shipped_fg = srgb_to_oklab(hex_array([base.surfaces[f"fg_{i}"] for i in range(3)]))
    fg_lab = srgb_to_oklab(hex_array(fg))
    for index in range(3):
        values.append(
            violation(
                abs(float(fg_lab[index, 0] - shipped_fg[index, 0])),
                ceiling=FOREGROUND_LIGHTNESS_RADIUS,
            )
        )

    soft_terms.append(float(np.linalg.norm(fg_lab[:, 1:] - fg_target)))

    direction = 1.0
    chroma = np.linalg.norm(fg_lab[:, 1:], axis=1)

    # Hard halfway caps on foreground warmth/chroma: fg must move TOWARD the
    # light palette's near-neutral ink, not away from it. Cap +b and chroma at
    # the midpoint between shipped and the light reference (+ small tolerance).
    light_fg_lab = srgb_to_oklab(hex_array([light_target().surfaces[f"fg_{i}"] for i in range(3)]))
    for index in range(3):
        halfway_b = (shipped_fg[index, 2] + light_fg_lab[index, 2]) / 2
        halfway_c = (
            np.linalg.norm(shipped_fg[index, 1:]) + np.linalg.norm(light_fg_lab[index, 1:])
        ) / 2
        values.append(violation(float(fg_lab[index, 2]), ceiling=float(halfway_b) + 0.01))
        values.append(
            violation(
                float(chroma[index]),
                ceiling=float(halfway_c) + 0.01,
            )
        )

    values.extend(violation(float(-d), 0.0) for d in np.diff(chroma) * direction)

    # Foreground hue corridor: same warm-neutral arc as shipped.
    shipped_fg_hues = np.degrees(np.arctan2(shipped_fg[:, 2], shipped_fg[:, 1])) % 360.0
    fg_hues = np.degrees(np.arctan2(fg_lab[:, 2], fg_lab[:, 1])) % 360.0
    for index in range(3):
        lo = min(shipped_fg_hues[index], shipped_fg_hues[min(index + 1, 2)])
        hi = max(shipped_fg_hues[index], shipped_fg_hues[min(index + 1, 2)])
        tol = 15.0
        span = hi - lo
        corridor_lo, corridor_hi = (lo - tol, hi + tol) if span < 180 else (hi - tol, lo + tol)
        in_corridor = (
            corridor_lo <= fg_hues[index] <= corridor_hi
            if corridor_lo <= corridor_hi
            else (fg_hues[index] >= corridor_lo or fg_hues[index] <= corridor_hi)
        )
        values.append(violation(float(in_corridor), 1.0))

    # Commanded lightness hierarchy: fg_0 > fg_1 > fg_2 must hold in the commanded
    # state exactly as it does in every shipped dark palette.
    values.extend(violation(float(-gap), 0.0) for gap in np.diff(fg_lab[:, 0]))

    # Commanded background chroma must follow the halfway step DOWN toward the
    # light palette's low-chroma surfaces — reduced warmth means reduced color,
    # not more. Ceiling: the tighter of current-lane max and per-role halfway
    # interpolation; plus a soft pull toward the halfway value itself.
    proposed_chroma = np.linalg.norm(surf_lab[:, 1:], axis=1)
    shipped_surf = srgb_to_oklab(hex_array([base.surfaces[f"bg_{i}"] for i in range(6)]))
    anchors = np.linspace(0.0, 1.0, len(shipped_surf))
    positions = np.linspace(0.0, 1.0, count)
    halfway_chroma = np.interp(
        positions,
        anchors,
        np.linalg.norm(
            srgb_to_oklab(hex_array([light_target().surfaces[f"bg_{i}"] for i in range(6)]))[:, 1:],
            axis=1,
        )
        * 0.5
        + np.linalg.norm(shipped_surf[:, 1:], axis=1) * 0.5,
    )
    for index in range(count):
        values.append(
            violation(
                float(proposed_chroma[index]),
                ceiling=float(halfway_chroma[index]) * 1.3 + 0.003,
            )
        )
        soft_terms.append(40.0 * abs(float(proposed_chroma[index] - halfway_chroma[index])))
    return values, 90.0 * float(np.sum(soft_terms))


def system_objective(
    base: Any,
    surfaces: tuple[str, ...],
    fg: tuple[str, ...],
    count: int,
    weight: float,
) -> float:
    violations, _ = system_violations(base, surfaces, fg, count, weight)
    score = penalty(violations)
    if score > 0:
        return 1e14 + score
    gains = base.profile.gains
    metrics = transformed_metrics(surfaces, fg, gains)
    cmd = commanded_metrics(surfaces, fg)
    target_ab, _ = surface_warmth_target(base, weight, count)
    fg_target = foreground_target(base, weight)
    fg_lab = srgb_to_oklab(hex_array(fg))
    return (
        -2.0 * metrics["fg_bg_clearance_min"]
        - 0.05 * metrics["adjacent_min"]
        + 60.0 * metrics["uniformity_ratio"]
        + 900.0 * float(np.linalg.norm(cmd["surf_ab"] - target_ab))
        + 90.0 * float(np.linalg.norm(fg_lab[:, 1:] - fg_target))
        + 8.0
        * float(
            np.mean(np.abs(srgb_to_oklab(hex_array(surfaces))[:, 0] - role_ladder(base, count)))
        )
        + 2.0 * cmd["mean_chroma"]
    )


def bounded_system_search(
    base: Any,
    count: int,
    weight: float,
    *,
    seed: int,
    iterations: int,
    init_surfaces: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    shipped_surfaces = [base.surfaces[f"bg_{i}"] for i in range(6)]
    shipped_fg = [base.surfaces[f"fg_{i}"] for i in range(3)]
    if init_surfaces is not None:
        origin_surfaces = list(init_surfaces)
    elif count == 6:
        origin_surfaces = shipped_surfaces
    else:
        ladder = role_ladder(base, count)
        target_ab, _ = surface_warmth_target(base, weight, count)
        lab = np.column_stack((ladder, target_ab))
        rgb = oklab_to_srgb(lab)
        origin_surfaces = [srgb_to_hex(v) for v in np.clip(rgb, 0.0, 1.0)]
    origin = bytes_from_hex(origin_surfaces + shipped_fg)
    best_values = hex_from_bytes(origin)
    best_score = system_objective(base, best_values[:count], best_values[count:], count, weight)
    best = origin.copy()
    accepted = 0
    evaluated = 1
    radius = np.full(origin.shape, 24, dtype=np.int16)
    for iteration in range(iterations):
        progress = iteration / max(1, iterations - 1)
        step = max(1, round(9.0 * (1.0 - progress) + 1.0))
        proposal = best.copy()
        edits = 1 + int(rng.integers(0, 5))
        flat = proposal.reshape(-1)
        indices = rng.choice(flat.size, size=edits, replace=False)
        flat[indices] += rng.integers(-step, step + 1, size=edits, dtype=np.int16)
        proposal = np.clip(proposal, origin - radius, origin + radius).reshape(origin.shape)
        values = hex_from_bytes(proposal)
        score = system_objective(base, values[:count], values[count:], count, weight)
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
            "surfaces": list(best_values[:count]),
            "foregrounds": list(best_values[count:]),
        },
    }


SHARED_DARK_ANCHOR = "#050404"
SHARED_LIGHT_ANCHOR = "#322926"
FLOATING_LIGHT_ANCHOR = "#322926"
FG_STEP_PARITY_RATIO = 0.8
BG_STEP_FLOOR_LIGHT_REFERENCE = 3.84
FG_STEP_FLOOR_CURRENT_REFERENCE = 7.0


def constructive_halfway_ladder(
    base: Any, count: int, dark_anchor: str, light_anchor: str
) -> tuple[str, ...]:
    """Fable constructive algorithm: even transformed J' steps at halfway chroma.

    Places each interior surface by solving commanded Oklab L (1-D bisection)
    such that its flare-included transformed CAM16 J' hits an evenly spaced
    target, holding commanded a/b on the anchor hue axis at per-role halfway
    chroma. Falls back toward anchors when inversion leaves gamut.
    """

    gains = base.profile.gains
    anchor_lab = srgb_to_oklab(hex_array((dark_anchor, light_anchor)))
    dark_anchor_chroma = float(np.linalg.norm(anchor_lab[0, 1:]))
    light_anchor_chroma = float(np.linalg.norm(anchor_lab[1, 1:]))
    ts = np.linspace(0.0, 1.0, count)

    def j_of_l(l_value: float, t: float, chroma: float) -> float:
        ab = anchor_lab[0] * (1 - t) + anchor_lab[1] * t
        direction = ab[1:] / max(np.linalg.norm(ab[1:]), 1e-9)
        okl = np.concatenate(([l_value], direction * chroma)).reshape(1, 3)
        rgb = np.clip(oklab_to_srgb(okl), 0.0, 1.0)
        return float(cam16_ucs(rgb, gains)[0][0])

    # Even J' targets between the endpoints' transformed J'.
    endpoints_rgb = hex_array((dark_anchor, light_anchor))
    j_lo = float(cam16_ucs(endpoints_rgb[:1], gains)[0][0])
    j_hi = float(cam16_ucs(endpoints_rgb[1:], gains)[0][0])

    surfaces = [dark_anchor]
    for index in range(1, count - 1):
        t = ts[index]
        target_j = j_lo + (j_hi - j_lo) * t
        interp_chroma = dark_anchor_chroma + t * (light_anchor_chroma - dark_anchor_chroma)
        lo_l, hi_l = float(anchor_lab[0, 0]), float(anchor_lab[1, 0])
        for _ in range(40):
            mid = (lo_l + hi_l) / 2
            if j_of_l(mid, t, interp_chroma) < target_j:
                lo_l = mid
            else:
                hi_l = mid
        ab = anchor_lab[0] * (1 - t) + anchor_lab[1] * t
        direction_ab = ab[1:] / max(np.linalg.norm(ab[1:]), 1e-9)
        okl = np.concatenate(([(lo_l + hi_l) / 2], direction_ab * interp_chroma)).reshape(1, 3)
        rgb = np.clip(oklab_to_srgb(okl), 0.0, 1.0)
        if np.any((rgb <= 0.001) | (rgb >= 0.999)):
            # Out of gamut: fall back to linear interpolation at this role.
            fallback = oklab_to_srgb(
                np.concatenate(([ladder_l_for(count)[index]], ab[1:])).reshape(1, 3)
            )
            surfaces.append(srgb_to_hex(np.clip(fallback, 0.0, 1.0)[0]))
        else:
            surfaces.append(srgb_to_hex(rgb[0]))
    surfaces.append(light_anchor)
    return tuple(surfaces)


def ladder_l_for(count: int):
    ladder = np.asarray(GEOMETRIC_LADDER_BY_COUNT[count])
    return ladder


def pinned_endpoint_surfaces(base: Any, count: int) -> tuple[str, ...]:
    """Shared-anchor halfway shape: common dark/light endpoints, N surfaces between."""

    lab = srgb_to_oklab(hex_array((SHARED_DARK_ANCHOR, SHARED_LIGHT_ANCHOR)))
    ts = np.linspace(0.0, 1.0, count)
    inner = [
        srgb_to_hex(np.clip(oklab_to_srgb(lab[0] * (1 - t) + lab[1] * t), 0.0, 1.0))
        for t in ts[1:-1]
    ]
    return (SHARED_DARK_ANCHOR, *inner, SHARED_LIGHT_ANCHOR)


def refine_foregrounds(
    base: Any,
    surfaces: tuple[str, ...],
    fg: tuple[str, ...],
    *,
    seed: int,
    iterations: int,
) -> dict[str, Any]:
    """Hill-climb only the foreground roles against fixed surfaces."""

    rng = np.random.default_rng(seed)
    origin = bytes_from_hex(fg)
    best = origin.copy()
    best_values = hex_from_bytes(best)
    count = len(surfaces)

    def gate_score(fg_values: tuple[str, ...]) -> float:
        violations, _soft = system_violations(base, surfaces, fg_values, count, 0.5)
        return penalty(violations)

    best_score = gate_score(best_values)
    # Walk from the shipped foregrounds so the starting point is gate-feasible;
    # never accept a proposal that is infeasible when the current best is feasible.
    best_feasible = best_score < 1e13
    accepted = 0
    evaluated = 1
    for iteration in range(iterations):
        progress = iteration / max(1, iterations - 1)
        step = max(1, round(9.0 * (1.0 - progress) + 1.0))
        proposal = best.copy()
        edits = 1 + int(rng.integers(0, 4))
        flat = proposal.reshape(-1)
        indices = rng.choice(flat.size, size=edits, replace=False)
        flat[indices] += rng.integers(-step, step + 1, size=edits, dtype=np.int16)
        proposal = np.clip(proposal, origin - 48, origin + 48).reshape(origin.shape)
        values = hex_from_bytes(proposal)
        score = gate_score(values)
        evaluated += 1
        feasible = score < 1e13
        if best_feasible and not feasible:
            continue
        if score < best_score - 1e-12 or (
            abs(score - best_score) <= 1e-12 and values < best_values
        ):
            best = proposal
            best_values = values
            best_score = score
            best_feasible = feasible
            accepted += 1
    return {
        "seed": seed,
        "iterations": iterations,
        "evaluated_exact_hex8_candidates": evaluated,
        "accepted_moves": accepted,
        "objective": float(best_score),
        "selected": {"surfaces": list(surfaces), "foregrounds": list(best_values)},
    }


def refine_pinned_intermediates(
    base: Any,
    surfaces: tuple[str, ...],
    fg: tuple[str, ...],
    *,
    seed: int,
    iterations: int,
) -> dict[str, Any]:
    """Hill-climb only the interior surfaces; endpoints and foregrounds stay fixed."""

    rng = np.random.default_rng(seed)
    origin = bytes_from_hex(surfaces)
    best = origin.copy()
    best_values = hex_from_bytes(best)
    best_score = system_objective(base, best_values, fg, len(surfaces), 0.5)
    accepted = 0
    evaluated = 1
    radius = np.full(origin.shape, 24, dtype=np.int16)
    radius[0] = 0
    radius[-1] = 0
    for iteration in range(iterations):
        progress = iteration / max(1, iterations - 1)
        step = max(1, round(9.0 * (1.0 - progress) + 1.0))
        proposal = best.copy()
        edits = 1 + int(rng.integers(0, min(4, len(surfaces) - 2)))
        rows = rng.choice(len(surfaces) - 2, size=edits, replace=False)
        for row in rows:
            channel = rng.choice(3, size=1)
            proposal[row + 1, channel] += rng.integers(-step, step + 1, size=1, dtype=np.int16)
        proposal = np.clip(proposal, origin - radius, origin + radius).reshape(origin.shape)
        values = hex_from_bytes(proposal)
        score = system_objective(base, values, fg, len(surfaces), 0.5)
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
        "selected": {"surfaces": list(best_values), "foregrounds": list(fg)},
    }


def select_two_seed_runs(runs: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    selected = min(
        runs,
        key=lambda r: (
            r["objective"],
            tuple(r["selected"]["surfaces"]),
            tuple(r["selected"]["foregrounds"]),
        ),
    )
    return selected, selected


def load_full_palette_module() -> dict[str, Any]:
    import runpy

    return runpy.run_path(str(EXPERIMENT / "search_full_palette.py"))


def categorical_seed_origins(
    full: dict[str, Any],
    base: Any,
    foregrounds: tuple[str, ...],
    count: int,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Deterministic transformed-CAM16 maximin seeds over an admissible OkLCh shell."""

    labs = []
    for lightness in np.linspace(0.48, 0.78, 7):
        for chroma in np.linspace(0.09, 0.105, 4):
            for hue in np.arange(0.0, 360.0, 10.0):
                radians = np.radians(hue)
                lab = np.asarray((lightness, chroma * np.cos(radians), chroma * np.sin(radians)))
                rgb = oklab_to_srgb(lab.reshape(1, 3))[0]
                if np.all((rgb >= 0.0) & (rgb <= 1.0)):
                    labs.append(lab)
    pool_lab = np.asarray(labs)
    pool_rgb = np.clip(oklab_to_srgb(pool_lab), 0.0, 1.0)
    transformed = full["cam16_ucs"](pool_rgb, base.profile.gains)
    fg_transformed = full["cam16_ucs"](hex_array(foregrounds), base.profile.gains)
    transformed_bg0 = warm_transform(hex_to_srgb(base.surfaces["bg_0"]), base.profile.gains)
    contrast = np.asarray(
        [
            contrast_ratio(warm_transform(color, base.profile.gains), transformed_bg0)
            for color in pool_rgb
        ]
    )
    eligible = contrast >= 3.0
    pool_lab = pool_lab[eligible]
    pool_rgb = pool_rgb[eligible]
    transformed = transformed[eligible]

    def select(first_offset: int) -> tuple[str, ...]:
        clearance = np.linalg.norm(
            transformed[:, None, :] - fg_transformed[None, :, :], axis=2
        ).min(axis=1)
        ordered = np.argsort(-clearance, kind="stable")
        chosen = [int(ordered[first_offset % min(24, len(ordered))])]
        while len(chosen) < count:
            transformed_pair = np.linalg.norm(
                transformed[:, None, :] - transformed[chosen][None, :, :], axis=2
            ).min(axis=1)
            day_pair = (
                np.linalg.norm(pool_lab[:, None, :] - pool_lab[chosen][None, :, :], axis=2).min(
                    axis=1
                )
                * 100.0
            )
            score = np.minimum(transformed_pair, clearance) + 0.15 * day_pair
            score[chosen] = -np.inf
            chosen.append(int(np.argmax(score)))
        return tuple(srgb_to_hex(pool_rgb[index]) for index in chosen)

    return select(0), select(11)


def _categorical_has_five_percent_margin(
    base: Any, metrics: dict[str, Any], floors: dict[str, Any]
) -> tuple[bool, list[str]]:
    misses = []
    bank = floors["categorical"]

    def floor(label: str, actual: float, required: float) -> None:
        if actual + 1e-12 < required * 1.05:
            misses.append(f"{label} {actual:.4f} < 105% of {required:.4f}")

    def ceiling(label: str, actual: float, required: float) -> None:
        if actual > required / 1.05 + 1e-12:
            misses.append(f"{label} {actual:.4f} > 95.24% of {required:.4f}")

    floor("day pair", metrics["normal_pair_delta_e_ok"], base.daylight_minimum_delta_e_ok)
    floor(
        "transformed sampled-grid pair",
        metrics["sampled_gain_pair_min_cam16_ucs"],
        bank["transformed_pair_cam16_ucs"],
    )
    floor("transformed bg contrast", metrics["transformed_background_contrast_bg0_min"], 3.0)
    for index, value in enumerate(metrics["normal_foreground_clearance_by_role"]):
        floor(f"day fg_{index}", value, base.categorical_daylight_minimum_foreground_delta_e_ok)
    ceiling("mean chroma", metrics["normal_mean_chroma"], 0.105)
    ceiling("maximum chroma", metrics["normal_max_chroma"], 0.111)
    return not misses, misses


def apply_paired_categorical_ordering(
    full: dict[str, Any], base: Any, profile_record: dict[str, Any]
) -> None:
    """Order fixed categorical sets by cross-profile hue identity and prefix strength."""

    lanes = [profile_record["lanes"][lane] for lane in LANES]
    count = len(lanes[0]["categorical"])
    if any(len(record["categorical"]) != count for record in lanes):
        raise RuntimeError(f"categorical lane counts differ for {base.slug}")

    pair_transformed = np.full((count, count), np.inf)
    pair_commanded = np.full((count, count), np.inf)
    hue_vectors = np.zeros((count, 2), dtype=float)
    for record in lanes:
        values = tuple(record["categorical"])
        day = srgb_to_oklab(hex_array(values))
        day_hues = np.arctan2(day[:, 2], day[:, 1])
        hue_vectors[:, 0] += np.cos(day_hues)
        hue_vectors[:, 1] += np.sin(day_hues)
        for gains in full["sampled_gain_grid"](base.profile.gains):
            transformed = full["cam16_ucs"](hex_array(values), gains)
            for left in range(count):
                for right in range(left + 1, count):
                    distance = float(np.linalg.norm(transformed[left] - transformed[right]))
                    pair_transformed[left, right] = min(pair_transformed[left, right], distance)
                    pair_transformed[right, left] = pair_transformed[left, right]
        for left in range(count):
            for right in range(left + 1, count):
                distance = float(np.linalg.norm(day[left] - day[right]) * 100.0)
                pair_commanded[left, right] = min(pair_commanded[left, right], distance)
                pair_commanded[right, left] = pair_commanded[left, right]

    mean_hues = np.degrees(np.arctan2(hue_vectors[:, 1], hue_vectors[:, 0])) % 360.0
    semantic_slots = CATEGORICAL_SEMANTIC_SLOTS[:count]

    def angular_distance(left: float, right: float) -> float:
        return abs((left - right + 180.0) % 360.0 - 180.0)

    def order_key(order: tuple[int, ...]) -> tuple[Any, ...]:
        semantic_error = sum(
            angular_distance(mean_hues[color_index], semantic_slots[slot_index][1])
            for slot_index, color_index in enumerate(order)
        )
        prefix_tiebreakers = []
        for prefix_count in range(2, count + 1):
            transformed_min = min(
                float(pair_transformed[order[left], order[right]])
                for left in range(prefix_count)
                for right in range(left + 1, prefix_count)
            )
            commanded_min = min(
                float(pair_commanded[order[left], order[right]])
                for left in range(prefix_count)
                for right in range(left + 1, prefix_count)
            )
            prefix_tiebreakers.extend((-transformed_min, -commanded_min))
        return (semantic_error, *prefix_tiebreakers, order)

    order = list(min(permutations(range(count)), key=order_key))

    prefix_pair_minima = []
    for prefix_count in range(2, count + 1):
        prefix_pair_minima.append(
            min(
                float(pair_transformed[order[left], order[right]])
                for left in range(prefix_count)
                for right in range(left + 1, prefix_count)
            )
        )

    for lane, record in zip(LANES, lanes, strict=True):
        record["categorical"] = [record["categorical"][index] for index in order]
        lane_base = full["candidate_family"](
            base,
            expand_to_six(
                tuple(
                    record["surfaces"][key]
                    for key in sorted(
                        record["surfaces"],
                        key=lambda value: int(value.split("_")[1]),
                    )
                )
            ),
            tuple(record["foregrounds"]),
        )
        metrics = full["accent_metrics"](
            lane_base,
            tuple(record["categorical"]),
            tuple(record["foregrounds"]),
            terminal=False,
            sample_grid=True,
        )
        failures = full["categorical_failures"](
            lane_base,
            tuple(record["categorical"]),
            metrics,
            record["dependent_floors"],
        )
        if failures:
            raise RuntimeError(f"categorical ordering invalidated {base.slug}/{lane}: {failures}")
        record["categorical_metrics"] = metrics
        record["categorical_ordering"] = {
            "strategy": (
                "cross-profile broad commanded-hue identity first; paired current+halfway "
                "transformed CAM16-UCS and commanded Oklab prefix separation break ties"
            ),
            "permutation_from_search_order": order,
            "stable_across_lanes": True,
            "semantic_families": [name for name, _hue in semantic_slots],
            "semantic_target_hues_degrees": [hue for _name, hue in semantic_slots],
            "assigned_mean_commanded_hues_degrees": [float(mean_hues[index]) for index in order],
            "prefix_transformed_pair_minima_cam16_ucs": prefix_pair_minima,
        }


def search_dependent_banks(
    full: dict[str, Any],
    base: Any,
    surfaces: tuple[str, ...],
    foregrounds: tuple[str, ...],
    profile_index: int,
    iterations: dict[str, int],
) -> dict[str, Any]:
    """Optimize three independent dependent banks, then validate their assembly."""

    surfaces_six = expand_to_six(surfaces)
    lane_base = full["candidate_family"](base, surfaces_six, foregrounds)
    floors = full["dependent_bank_floors"](lane_base, foregrounds)
    shipped_count = len(base.categorical_colors)
    cat_trials: dict[str, Any] = {}
    frontiers: list[dict[str, Any]] = []

    for count in range(shipped_count, min(shipped_count + 3, 7)):
        origins = (
            (tuple(base.categorical_colors), tuple(base.categorical_colors))
            if count == shipped_count
            else categorical_seed_origins(full, lane_base, foregrounds, count)
        )
        runs = [
            full["bounded_exact_search"](
                origin,
                lambda values, lb=lane_base, fg=foregrounds, f=floors: full[
                    "categorical_objective"
                ](lb, fg, values, f),
                seed=CATEGORY_SEED_BASE + profile_index * 100 + seed_add,
                iterations=iterations["categorical"],
                radius=18,
            )
            for seed_add, origin in enumerate(origins)
        ]
        values, selected_run = full["select_two_seed_runs"](runs)
        metrics = full["accent_metrics"](
            lane_base, values, foregrounds, terminal=False, sample_grid=True
        )
        failures = full["categorical_failures"](lane_base, values, metrics, floors)
        margin_pass, margin_failures = _categorical_has_five_percent_margin(
            lane_base, metrics, floors
        )
        cat_trials[str(count)] = {
            "selected": list(values),
            "objective": selected_run["objective"],
            "selected_run": {k: v for k, v in selected_run.items() if k != "selected"},
            "metrics": metrics,
            "failures": failures,
            "five_percent_margin_pass": margin_pass,
            "five_percent_margin_failures": margin_failures,
        }
        frontiers.append(
            {
                "count": count,
                "sampled_grid_pair_cam16_ucs": metrics["sampled_gain_pair_min_cam16_ucs"],
                "passes": not failures,
                "five_percent_margin_pass": margin_pass,
            }
        )

    base_trial = cat_trials[str(shipped_count)]
    if base_trial["failures"]:
        shipped_metrics = full["accent_metrics"](
            lane_base,
            tuple(base.categorical_colors),
            foregrounds,
            terminal=False,
            sample_grid=True,
        )
        shipped_failures = full["categorical_failures"](
            lane_base, tuple(base.categorical_colors), shipped_metrics, floors
        )
        if shipped_failures:
            raise RuntimeError(
                f"shipped categorical bank infeasible for {base.slug}: {shipped_failures}"
            )
        categorical = tuple(base.categorical_colors)
        categorical_metrics = shipped_metrics
        adopted_reason = "optimized shipped-count trial infeasible; shipped bank retained"
    else:
        categorical = tuple(base_trial["selected"])
        categorical_metrics = base_trial["metrics"]
        adopted_reason = "shipped count retained after categorical-only validation"

    next_trial = cat_trials.get(str(shipped_count + 1))
    if next_trial and not next_trial["failures"] and next_trial["five_percent_margin_pass"]:
        pair_required = max(
            floors["categorical"]["transformed_pair_cam16_ucs"],
            0.90 * categorical_metrics["sampled_gain_pair_min_cam16_ucs"],
        )
        pair_actual = next_trial["metrics"]["sampled_gain_pair_min_cam16_ucs"]
        if pair_actual + 1e-12 >= pair_required:
            categorical = tuple(next_trial["selected"])
            categorical_metrics = next_trial["metrics"]
            adopted_reason = (
                f"count {shipped_count + 1} adopted: all gates have >=5% margin and "
                f"sampled-grid pair {pair_actual:.3f} >= {pair_required:.3f}"
            )

    for entry in frontiers:
        entry["selected_bank"] = entry["count"] == len(categorical)
        if entry["selected_bank"]:
            trial = cat_trials[str(entry["count"])]
            entry["selected_trial"] = not trial["failures"] and tuple(trial["selected"]) == tuple(
                categorical
            )
            entry["selected_bank_sampled_grid_pair_cam16_ucs"] = categorical_metrics[
                "sampled_gain_pair_min_cam16_ucs"
            ]

    term_runs = [
        full["bounded_exact_search"](
            tuple(base.terminal_colors),
            lambda values, lb=lane_base, fg=foregrounds, f=floors: full["terminal_objective"](
                lb, fg, values, f
            ),
            seed=TERMINAL_SEED_BASE + profile_index * 100 + seed_add,
            iterations=iterations["terminal"],
            radius=36 if slug_has_deep_transform(base.slug) else 16,
            initial_candidates=full["TERMINAL_INITIAL_PROPOSALS"].get(base.slug, ()),
        )
        for seed_add in (0, 1)
    ]
    feasible_terminal = []
    for run in term_runs:
        values = tuple(run["selected"])
        metrics = full["accent_metrics"](
            lane_base, values, foregrounds, terminal=True, sample_grid=True
        )
        failures = full["terminal_failures"](lane_base, values, metrics, floors)
        run["failures"] = failures
        run["metrics"] = metrics
        if not failures:
            feasible_terminal.append(run)
    if feasible_terminal:
        selected_term_run = min(
            feasible_terminal, key=lambda row: (row["objective"], tuple(row["selected"]))
        )
        terminal = tuple(selected_term_run["selected"])
        terminal_metrics = selected_term_run["metrics"]
        terminal_adoption = "feasible optimized terminal bank selected"
    else:
        terminal = tuple(base.terminal_colors)
        terminal_metrics = full["accent_metrics"](
            lane_base, terminal, foregrounds, terminal=True, sample_grid=True
        )
        terminal_fallback_failures = full["terminal_failures"](
            lane_base, terminal, terminal_metrics, floors
        )
        if terminal_fallback_failures:
            raise RuntimeError(
                f"no feasible terminal selection for {base.slug}; optimized failures="
                f"{[run['failures'] for run in term_runs]}; shipped failures="
                f"{terminal_fallback_failures}"
            )
        terminal_adoption = "optimized selections infeasible; shipped terminal bank retained"

    sequence, sequential, sequential_record = full["construct_sequential"](lane_base)
    sequential_bank_failures = full["sequential_failures"](sequential_record)
    if sequential_bank_failures:
        raise RuntimeError(
            f"constructive sequential ramp infeasible for {base.slug}: {sequential_bank_failures}"
        )
    dependency_payload = {
        "surfaces": list(surfaces),
        "foregrounds": list(foregrounds),
        "gains": list(base.profile.gains),
        "metric": {
            "space": "CAM16-UCS",
            "L_A": 8.0,
            "Y_b": 3.0,
            "flare_fraction_untransformed_white": 0.0075,
        },
        "objective": "constructive-transformed-cam16-arc-v2",
    }
    fingerprint = hashlib.sha256(
        json.dumps(dependency_payload, sort_keys=True).encode()
    ).hexdigest()
    final_failures = full["final_assembled_dependent_failures"](
        lane_base,
        categorical,
        categorical_metrics,
        terminal,
        terminal_metrics,
        sequential_record,
        floors,
    )
    if final_failures:
        raise RuntimeError(f"final dependent assembly infeasible for {base.slug}: {final_failures}")
    return {
        "dependent_metric_model": dependency_payload["metric"],
        "dependent_floors": floors,
        "categorical": list(categorical),
        "categorical_trials": cat_trials,
        "categorical_frontier": frontiers,
        "categorical_adoption": adopted_reason,
        "categorical_metrics": categorical_metrics,
        "categorical_failures": [],
        "terminal": list(terminal),
        "terminal_role_contract": full["terminal_role_contract"](lane_base),
        "terminal_adoption": terminal_adoption,
        "terminal_runs": term_runs,
        "terminal_metrics": terminal_metrics,
        "terminal_failures": [],
        "sequential_anchors": list(sequential),
        "sequential_metrics": sequential_record,
        "sequential_failures": [],
        "final_assembled_dependent_failures": final_failures,
        "sequential_dependency_fingerprint": fingerprint,
        "continuous_float_srgb": sequence.tolist(),
        "continuous_hex8": [srgb_to_hex(value) for value in sequence],
    }


def slug_has_deep_transform(slug: str) -> bool:
    return slug in TERMINAL_INITIAL_PROPOSALS


def expand_to_six(surfaces: tuple[str, ...]) -> tuple[str, ...]:
    """Expand real surfaces through the explicit six-role production contract."""

    try:
        aliases = BACKGROUND_ROLE_ALIAS_INDICES[len(surfaces)]
    except KeyError as error:
        raise ValueError(f"unsupported background surface count: {len(surfaces)}") from error
    return tuple(surfaces[index] for index in aliases)


def background_role_contract(count: int) -> dict[str, str]:
    aliases = BACKGROUND_ROLE_ALIAS_INDICES[count]
    return {f"bg_{role}": f"surface_{index}" for role, index in enumerate(aliases)}


FROZEN_SYSTEM_SHA256 = "1758d76fe90334201efed49fc3f9cb791aa95f5f358eac840facf78ef492ef13"
APPROVED_ARTIFACT_SHA256: str | None = (
    "33f79207c64d9c3b7d49534ed1bac0f8e9f379635999720615852323d9e185fa"
)


def frozen_system_subset(data: dict[str, Any]) -> dict[str, Any]:
    return {
        slug: {
            lane: {
                "bg_count": record["bg_count"],
                "surfaces": record["surfaces"],
                "foregrounds": record["foregrounds"],
            }
            for lane, record in profile["lanes"].items()
        }
        for slug, profile in data["profiles"].items()
    }


def frozen_system_sha256(data: dict[str, Any]) -> str:
    payload = json.dumps(frozen_system_subset(data), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def approved_artifact_subset(data: dict[str, Any]) -> dict[str, Any]:
    """Canonical reader-facing palette bytes and semantic slot contracts."""

    return {
        slug: {
            "gains": profile["gains"],
            "lanes": {
                lane: {
                    "bg_count": record["bg_count"],
                    "background_role_alias_indices": record["background_role_alias_indices"],
                    "background_role_contract": record["background_role_contract"],
                    "surfaces": record["surfaces"],
                    "foregrounds": record["foregrounds"],
                    "categorical": record["categorical"],
                    "categorical_semantic_families": record["categorical_ordering"][
                        "semantic_families"
                    ],
                    "terminal": record["terminal"],
                    "terminal_role_contract": record["terminal_role_contract"],
                    "sequential_anchors": record["sequential_anchors"],
                    "continuous_float_srgb": record["continuous_float_srgb"],
                    "continuous_hex8": record["continuous_hex8"],
                    "dependent_metric_model": record["dependent_metric_model"],
                    "sequential_selection": {
                        key: record["sequential_metrics"][key]
                        for key in (
                            "selection_policy",
                            "transformed_reference",
                            "transformed_arc_weight",
                            "approved_path_chroma_min",
                            "approved_path_chroma_max",
                            "chroma_envelope_preserved",
                        )
                    },
                }
                for lane, record in profile["lanes"].items()
            },
        }
        for slug, profile in data["profiles"].items()
    }


def approved_artifact_sha256(data: dict[str, Any]) -> str:
    payload = json.dumps(
        approved_artifact_subset(data), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    previous = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    frozen_sha = frozen_system_sha256(previous)
    if frozen_sha != FROZEN_SYSTEM_SHA256:
        raise RuntimeError(
            f"refusing dependent-bank search: frozen bg/fg hash {frozen_sha} != "
            f"{FROZEN_SYSTEM_SHA256}"
        )
    full = load_full_palette_module()
    iterations = {
        "categorical": 120 if args.quick else 1200,
        "terminal": 240 if args.quick else 2500,
    }
    output: dict[str, Any] = {
        "schema": 5,
        "method": (
            "dependent-bank-only transformed-first redesign: flare-aware CAM16-UCS; "
            "independent categorical/terminal/sequential validators; constructive scalar ramps"
        ),
        "frozen_system": {
            "source": "schema-4 transformed-first-results.json at 55760e8",
            "sha256": FROZEN_SYSTEM_SHA256,
            "covers": "all current+halfway bg counts, surfaces, and foregrounds",
        },
        "profiles": {},
    }
    for profile_index, slug in enumerate(PROFILES):
        base = family(slug)
        previous_profile = previous["profiles"][slug]
        profile_record: dict[str, Any] = {
            "name": previous_profile["name"],
            "gains": previous_profile["gains"],
            "lanes": {},
        }
        for lane, weight in LANES.items():
            print(f"{slug} / {lane}", flush=True)
            frozen_lane = previous_profile["lanes"][lane]
            surfaces = tuple(
                frozen_lane["surfaces"][key]
                for key in sorted(
                    frozen_lane["surfaces"], key=lambda value: int(value.split("_")[1])
                )
            )
            foregrounds = tuple(frozen_lane["foregrounds"])
            banks = search_dependent_banks(
                full,
                base,
                surfaces,
                foregrounds,
                profile_index,
                iterations,
            )
            lane_record: dict[str, Any] = {
                "weight": weight,
                "bg_count": frozen_lane["bg_count"],
                "background_role_alias_indices": list(
                    BACKGROUND_ROLE_ALIAS_INDICES[frozen_lane["bg_count"]]
                ),
                "background_role_contract": background_role_contract(frozen_lane["bg_count"]),
                "surfaces": dict(frozen_lane["surfaces"]),
                "foregrounds": list(foregrounds),
                **banks,
                "search": frozen_lane["search"],
            }
            if "count_choice_rule" in frozen_lane:
                lane_record["count_choice_rule"] = frozen_lane["count_choice_rule"]
            profile_record["lanes"][lane] = lane_record
        apply_paired_categorical_ordering(full, base, profile_record)
        output["profiles"][slug] = profile_record
    output_frozen_sha = frozen_system_sha256(output)
    if output_frozen_sha != FROZEN_SYSTEM_SHA256:
        raise RuntimeError(
            f"generated output moved frozen bg/fg: {output_frozen_sha} != {FROZEN_SYSTEM_SHA256}"
        )
    artifact_sha = approved_artifact_sha256(output)
    if APPROVED_ARTIFACT_SHA256 is not None and artifact_sha != APPROVED_ARTIFACT_SHA256:
        raise RuntimeError(
            f"generated output moved the approved artifact: {artifact_sha} != "
            f"{APPROVED_ARTIFACT_SHA256}"
        )
    output["approved_artifact_freeze"] = {
        "schema": 1,
        "sha256": artifact_sha,
        "covers": (
            "profile gains; current+halfway bg counts/surfaces/foregrounds and production aliases; "
            "ordered categorical semantic slots; terminal banks/aliases; canonical float and "
            "Hex8 sequential ramps; dependent metric and sequential selection contracts"
        ),
    }
    RESULTS_PATH.write_text(json.dumps(output, indent=2, sort_keys=False) + "\n")
    print(RESULTS_PATH)
    return 0


def runs_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "seed": run["seed"],
        "iterations": run["iterations"],
        "evaluated_exact_hex8_candidates": run["evaluated_exact_hex8_candidates"],
        "accepted_moves": run["accepted_moves"],
        "objective": run["objective"],
        "selected": run["selected"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
