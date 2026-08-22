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
TRANSFORMED_BG_STEP_FLOOR = 3.4
TRANSFORMED_FG_STEP_FLOOR = 3.4
TRANSFORMED_UNIFORMITY_RATIO = 1.35
CAM16_ADAPTATION_LUMINANCE = 50.0
CAM16_BACKGROUND_LUMINANCE = 20.0
SURFACE_LIGHTNESS_DRIFT = 0.02
FOREGROUND_LIGHTNESS_RADIUS = 0.06
MINIMUM_BG_COUNT = 3
MAXIMUM_BG_COUNT = 6
CATEGORICAL_MARGIN = 0.05

SYSTEM_SEED_BASE = 7000
CATEGORY_SEED_BASE = 17000
TERMINAL_SEED_BASE = 27000
SEQUENTIAL_SEED_BASE = 37000

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


def cam16_ucs(rgb01: np.ndarray, gains) -> np.ndarray:
    """CAM16-UCS coordinates under transformed sRGB and night viewing conditions."""

    transformed = np.clip(rgb01 * np.asarray(gains), 0.0, 1.0)
    return np.asarray(
        colour.XYZ_to_CAM16UCS(
            colour.sRGB_to_XYZ(transformed),
            L_A=CAM16_ADAPTATION_LUMINANCE,
            Y_b=CAM16_BACKGROUND_LUMINANCE,
        )
    )


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
    values.extend(violation(v, TRANSFORMED_BG_STEP_FLOOR) for v in metrics["adjacent"])
    values.extend(violation(v, TRANSFORMED_FG_STEP_FLOOR) for v in metrics["fg_adjacent"])
    values.append(violation(metrics["uniformity_ratio"], ceiling=TRANSFORMED_UNIFORMITY_RATIO))
    values.append(violation(metrics["span"], 6.0))
    primary_floor = max(4.5, DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST.get(base.slug, 4.5))
    floors_by_role = {"fg_0": max(4.5, primary_floor), "fg_1": 3.5, "fg_2": 2.4}
    for contrast, floor_key in zip(metrics["contrast"], ("fg_0", "fg_1", "fg_2"), strict=True):
        family_floor = floors_by_role[floor_key]
        values.append(violation(contrast, family_floor))

    # Commanded-state structural gates.
    luminance = np.asarray(wcag_luminance(hex_array(surfaces)))
    values.extend(violation(float(d), -1e-12) for d in np.diff(luminance))
    for index in range(count):
        ceiling = DARK_SURFACE_MAXIMUM_COMMANDED_LUMINANCE[f"bg_{min(index, 5)}"]
        values.append(violation(float(luminance[index]), ceiling=ceiling))

    # Commanded warmth soft target and L pinning.
    target_ab, ladder = surface_warmth_target(base, weight, count)
    surf_lab = srgb_to_oklab(hex_array(surfaces))
    cmd = commanded_metrics(surfaces, fg)
    for index in range(count):
        values.append(
            violation(
                abs(float(surf_lab[index, 0] - ladder[index])),
                ceiling=SURFACE_LIGHTNESS_DRIFT,
            )
        )
    soft_terms = [float(np.linalg.norm(cmd["surf_ab"] - target_ab))]
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
        values.append(
            violation(float(shipped_fg[index, 0] - fg_lab[index, 0]), 0.0)
            if fg_lab[index, 0] < shipped_fg[index, 0]
            else 0.0
        )
    soft_terms.append(float(np.linalg.norm(fg_lab[:, 1:] - fg_target)))
    direction = 1.0
    chroma = np.linalg.norm(fg_lab[:, 1:], axis=1)
    values.extend(violation(float(-d), 0.0) for d in np.diff(chroma) * direction)
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
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    shipped_surfaces = [base.surfaces[f"bg_{i}"] for i in range(6)]
    shipped_fg = [base.surfaces[f"fg_{i}"] for i in range(3)]
    if count == 6:
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


def pinned_endpoint_surfaces(base: Any, count: int) -> tuple[str, ...]:
    """User-directed 1200K shape: shipped bg_0/bg_4 endpoints, N=4, even CAM16 steps."""

    endpoints = [base.surfaces["bg_0"], base.surfaces["bg_4"]]
    lab = srgb_to_oklab(hex_array(tuple(endpoints)))
    ts = np.linspace(0.0, 1.0, count)
    inner = [
        srgb_to_hex(np.clip(oklab_to_srgb(lab[0] * (1 - t) + lab[1] * t), 0.0, 1.0))
        for t in ts[1:-1]
    ]
    return (endpoints[0], *inner, endpoints[1])


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


def search_dependent_banks(
    full: dict[str, Any],
    base: Any,
    surfaces: tuple[str, ...],
    foregrounds: tuple[str, ...],
    profile_index: int,
    iterations: dict[str, int],
) -> dict[str, Any]:
    """Fresh categorical (with count bonus), terminal, and sequential searches."""

    surfaces_six = expand_to_six(surfaces)
    lane_base = full["candidate_family"](base, surfaces_six, foregrounds)
    categorical_shipped = len(base.categorical_colors)
    cat_trials: dict[str, Any] = {}
    categorical: tuple[str, ...] | None = None
    categorical_metrics = None
    adopted_reason = "shipped count retained"

    def extended_origin(count: int) -> tuple[str, ...]:
        """Shipped palette extended to `count` entries with deterministic hue-shifted seeds."""

        shipped = list(base.categorical_colors)
        if count <= len(shipped):
            return tuple(shipped[:count])
        extra = []
        lab = srgb_to_oklab(hex_array(tuple(shipped)))
        for index in range(count - len(shipped)):
            source = lab[(index * 2 + 1) % len(lab)]
            shifted = source.copy()
            shifted[2] += 0.035 * (1 if index % 2 == 0 else -1)
            rgb = oklab_to_srgb(shifted.reshape(1, 3))[0]
            extra.append(srgb_to_hex(np.clip(rgb, 0.0, 1.0)))
        return tuple(shipped) + tuple(extra)

    for count in range(categorical_shipped, min(categorical_shipped + 3, 7)):
        origin = extended_origin(count)
        runs = []
        for seed_add in (0, 1):
            runs.append(
                full["bounded_exact_search"](
                    origin,
                    lambda values, lb=lane_base, fg=foregrounds: full["categorical_objective"](
                        lb, fg, values
                    ),
                    seed=CATEGORY_SEED_BASE + profile_index * 100 + seed_add,
                    iterations=iterations["categorical"],
                    radius=18,
                )
            )
        best, _ = full["select_two_seed_runs"](runs)
        values = tuple(best)
        metrics = full["accent_metrics"](lane_base, values, foregrounds, terminal=False)
        shipped_terminal_metrics = full["accent_metrics"](
            lane_base, base.terminal_colors, foregrounds, terminal=True
        )
        shipped_sequential_metrics, _ = full["sequential_metrics"](
            lane_base, base.sequential_anchors
        )
        failures = full["dependent_failures"](
            lane_base,
            values,
            metrics,
            base.terminal_colors,
            shipped_terminal_metrics,
            shipped_sequential_metrics,
            shipped_sequential_metrics,
        )
        cat_trials[str(count)] = {
            "selected": list(values),
            "objective": best["objective"] if isinstance(best, dict) else None,
            "failures": failures,
        }
        if not failures and categorical is None:
            categorical = values
            categorical_metrics = metrics
            if count > categorical_shipped:
                adopted_reason = f"count {count} adopted: every categorical release gate passes"
        elif not failures and categorical is not None and count > len(categorical):
            categorical = values
            categorical_metrics = metrics
            adopted_reason = (
                f"count {count} adopted over {len(categorical)}: gates pass with margin"
            )
    if categorical is None:
        categorical = base.categorical_colors
        categorical_metrics = full["accent_metrics"](
            lane_base, categorical, foregrounds, terminal=False
        )
        adopted_reason = "no larger count passed all gates; shipped retained"

    term_runs = [
        full["bounded_exact_search"](
            base.terminal_colors,
            lambda values, lb=lane_base, fg=foregrounds: full["terminal_objective"](lb, fg, values),
            seed=TERMINAL_SEED_BASE + profile_index * 100 + seed_add,
            iterations=iterations["terminal"],
            radius=36 if slug_has_deep_transform(base.slug) else 16,
            initial_candidates=full["TERMINAL_INITIAL_PROPOSALS"].get(base.slug, ()),
        )
        for seed_add in (0, 1)
    ]
    terminal, _ = full["select_two_seed_runs"](term_runs)

    sequential_baseline, _ = full["sequential_metrics"](lane_base, base.sequential_anchors)
    seq_runs = [
        full["bounded_exact_search"](
            base.sequential_anchors,
            lambda values, lb=lane_base, baseline=sequential_baseline: full["sequential_objective"](
                lb, baseline, values
            ),
            seed=SEQUENTIAL_SEED_BASE + profile_index * 100 + seed_add,
            iterations=iterations["sequential"],
            radius=10,
        )
        for seed_add in (0, 1)
    ]
    sequential, _ = full["select_two_seed_runs"](seq_runs)
    sequential_record, sequence = full["sequential_metrics"](lane_base, sequential)
    dependency_payload = {
        "surfaces": list(surfaces),
        "gains": list(base.profile.gains),
        "baseline": sequential_baseline,
        "objective": "transformed-first-v1",
    }
    fingerprint = hashlib.sha256(
        json.dumps(dependency_payload, sort_keys=True).encode()
    ).hexdigest()
    return {
        "categorical": list(categorical),
        "categorical_trials": cat_trials,
        "categorical_adoption": adopted_reason,
        "categorical_metrics": categorical_metrics,
        "terminal": list(terminal),
        "terminal_runs": [{k: v for k, v in r.items() if k != "selected"} for r in term_runs],
        "sequential_anchors": list(sequential),
        "sequential_metrics": sequential_record,
        "sequential_dependency_fingerprint": fingerprint,
        "continuous_float_srgb": sequence.tolist(),
        "continuous_hex8": [srgb_to_hex(v) for v in sequence],
    }


def slug_has_deep_transform(slug: str) -> bool:
    return slug in TERMINAL_INITIAL_PROPOSALS


def expand_to_six(surfaces: tuple[str, ...]) -> tuple[str, ...]:
    """Resample N selected surfaces to the six-role ladder by Oklab interpolation."""

    if len(surfaces) == 6:
        return surfaces
    lab = srgb_to_oklab(hex_array(surfaces))
    anchors = np.linspace(0.0, 1.0, len(surfaces))
    positions = np.linspace(0.0, 1.0, 6)
    expanded = np.column_stack(
        [np.interp(positions, anchors, lab[:, channel]) for channel in range(3)]
    )
    rgb = oklab_to_srgb(expanded)
    return tuple(srgb_to_hex(v) for v in np.clip(rgb, 0.0, 1.0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    full = load_full_palette_module()
    iterations = {
        "system": 300 if args.quick else 2400,
        "categorical": 300 if args.quick else 900,
        "terminal": 600 if args.quick else (4000 if True else 900),
        "sequential": 60 if args.quick else 180,
    }
    output: dict[str, Any] = {
        "schema": 4,
        "method": (
            "transformed-first: even transformed distinctness gates bind before commanded "
            "warmth; variable surface count (>=3); dependent banks searched fresh per lane"
        ),
        "profiles": {},
    }
    for profile_index, slug in enumerate(PROFILES):
        base = family(slug)
        record: dict[str, Any] = {"name": base.name, "gains": list(base.profile.gains), "lanes": {}}
        shipped_surfaces = tuple(base.surfaces[f"bg_{i}"] for i in range(6))
        shipped_fg = tuple(base.surfaces[f"fg_{i}"] for i in range(3))
        for lane, weight in LANES.items():
            print(f"{slug} / {lane}", flush=True)
            if weight == 0.0:
                banks = search_dependent_banks(
                    full, base, shipped_surfaces, shipped_fg, profile_index, iterations
                )
                lane_record: dict[str, Any] = {
                    "weight": weight,
                    "bg_count": 6,
                    "surfaces": {f"bg_{i}": shipped_surfaces[i] for i in range(6)},
                    "foregrounds": list(shipped_fg),
                    **banks,
                    "search": {
                        "per_count": {},
                        "note": "current lane is the shipped palette scored verbatim; "
                        "no surface search applied",
                    },
                }
                record["lanes"][lane] = lane_record
                continue
            if slug == "1200k-dark":
                # User-directed shape: N=4 with shipped bg_0/bg_4 endpoints frozen;
                # only the two interior surfaces and the foregrounds are searched.
                pinned = pinned_endpoint_surfaces(base, 4)
                fg_runs = [
                    bounded_system_search(
                        base,
                        4,
                        weight,
                        seed=SYSTEM_SEED_BASE + profile_index * 100 + add,
                        iterations=iterations["system"],
                    )
                    for add in (0, 1)
                ]
                _, fg_pick = select_two_seed_runs(fg_runs)
                foregrounds = tuple(fg_pick["selected"]["foregrounds"])
                runs = [
                    refine_pinned_intermediates(
                        base,
                        pinned,
                        foregrounds,
                        seed=SYSTEM_SEED_BASE + profile_index * 100 + add,
                        iterations=iterations["system"],
                    )
                    for add in (0, 1)
                ]
                best, _ = select_two_seed_runs(runs)
                chosen_count = 4
                choice_rule = (
                    "user-directed: N=4, shipped bg_0/bg_4 endpoints frozen, "
                    "interiors refined for even CAM16-UCS steps"
                )
                lane_record = {
                    "weight": weight,
                    "bg_count": chosen_count,
                    "count_choice_rule": choice_rule,
                    "surfaces": {f"bg_{i}": v for i, v in enumerate(best["selected"]["surfaces"])},
                    "foregrounds": list(best["selected"]["foregrounds"]),
                    **search_dependent_banks(
                        full,
                        base,
                        tuple(best["selected"]["surfaces"]),
                        tuple(best["selected"]["foregrounds"]),
                        profile_index,
                        iterations,
                    ),
                    "search": {
                        "per_count": {"4": runs_summary(best)},
                        "count_choice_rule": choice_rule,
                    },
                }
                record["lanes"][lane] = lane_record
                continue
            counts = {}
            for count in range(MINIMUM_BG_COUNT, MAXIMUM_BG_COUNT + 1):
                runs = [
                    bounded_system_search(
                        base,
                        count,
                        weight,
                        seed=SYSTEM_SEED_BASE + profile_index * 100 + add,
                        iterations=iterations["system"],
                    )
                    for add in (0, 1)
                ]
                best, _ = select_two_seed_runs(runs)
                counts[count] = best
            feasible = [n for n in counts if counts[n]["objective"] < 1e13]
            if feasible:
                chosen_count = min(feasible, key=lambda n: (counts[n]["objective"], -n))
                choice_rule = "best feasible objective; larger N wins ties"
            else:
                chosen_count = min(counts, key=lambda n: (counts[n]["objective"], -n))
                choice_rule = "no feasible count; best penalty objective"
            lane_record = {
                "weight": weight,
                "bg_count": chosen_count,
                "count_choice_rule": choice_rule,
                "surfaces": {
                    f"bg_{i}": v for i, v in enumerate(counts[chosen_count]["selected"]["surfaces"])
                },
                "foregrounds": list(counts[chosen_count]["selected"]["foregrounds"]),
                **search_dependent_banks(
                    full,
                    base,
                    tuple(counts[chosen_count]["selected"]["surfaces"]),
                    tuple(counts[chosen_count]["selected"]["foregrounds"]),
                    profile_index,
                    iterations,
                ),
                "search": {
                    "per_count": {str(n): runs_summary(counts[n]) for n in counts},
                    "count_choice_rule": choice_rule,
                },
            }
            record["lanes"][lane] = lane_record
        output["profiles"][slug] = record
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
