#!/usr/bin/env python3
"""Bounded clean-sheet 3400K Light terminal-accent search.

Commanded colors are evaluated under a normal/daytime CAM16 condition.
Transformed colors are evaluated under a low-light CAM16 condition. The
browser-raster proxy is only a search accelerator; real Chromium evidence is
required before a finalist can be shown for human selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import colour
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import ember  # noqa: E402
from ember.color import (  # noqa: E402
    contrast_ratio,
    hex_to_srgb,
    oklab_to_srgb,
    srgb_to_hex,
    srgb_to_oklab,
    warm_transform,
)
from ember.definitions import FAMILIES  # noqa: E402

if Path(ember.__file__).resolve().parents[1] != SRC.resolve():
    raise RuntimeError(
        f"wrong Ember import source: {Path(ember.__file__).resolve()} (expected under {SRC})"
    )

SCHEMA_VERSION = 1
SOURCE_COMMIT = "016c6b37b283baf44711af3330d2872305b9398c"
SOURCE_MANIFEST_SHA256 = "e7044ae9e629975df2db19ef0c472c74b99efb0ce0e56a46f862387a863f9f4c"
ROLE_ORDER = ("red", "green", "yellow", "blue", "magenta", "cyan")
ROLE_HUE_CENTERS = dict(zip(ROLE_ORDER, (20.0, 140.0, 82.0, 275.0, 335.0, 185.0), strict=True))
ROLE_HUE_RADIUS = 25.0
NORMAL_VIEW = {"L_A": 64.0, "Y_b": 20.0, "flare": 0.0075, "label": "normal-daytime"}
LOW_LIGHT_VIEW = {"L_A": 8.0, "Y_b": 3.0, "flare": 0.0075, "label": "low-light"}
COVERAGES = np.asarray((0.05, 0.08, 0.12, 0.18, 0.25, 0.35, 0.50, 0.65, 0.80, 1.0))
CONTRAST_FLOOR = 4.5
CONTRAST_SOFT_TARGET = 7.0
COMMAND_L_RANGE = (0.22, 0.58)
COMMAND_C_RANGE = (0.065, 0.18)
TRANSFORMED_L_CHALLENGE = 0.30
TRANSFORMED_L_FLOOR = 0.18
TRANSFORMED_C_FLOOR = 0.055
COMMAND_OKLAB_FG0_FLOOR = 9.0
TRANSFORMED_OKLAB_FG0_FLOOR = 6.0
COMMAND_PAIR_OKLAB_FLOOR = 14.0
TRANSFORMED_PAIR_OKLAB_FLOOR = 7.5
NORMAL_CAM_PAIR_FLOOR_RATIO = 0.90
LOW_CAM_PAIR_FLOOR_RATIO = 0.90
NORMAL_CAM_FG_FLOOR = 15.0
LOW_CAM_FG_FLOOR = 10.0
CATALOG_KEEP = 420
RANDOM_COMBINATIONS = 180_000
GAIN_SAMPLES = (
    (1.0, 0.74, 0.53),
    (1.0, 0.703, 0.5035),
    (1.0, 0.703, 0.5565),
    (1.0, 0.777, 0.5035),
    (1.0, 0.777, 0.5565),
)


class SearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    role: str
    hex: str
    command_l: float
    command_c: float
    command_h: float
    transformed_l: float
    transformed_c: float
    transformed_h: float
    command_fg0_oklab: float
    transformed_fg0_oklab: float
    normal_cam_fg_min: float
    low_cam_fg_min: float
    commanded_contrast_min: float
    transformed_contrast_min: float
    sampled_contrast_min: float
    sampled_fg0_oklab_min: float
    sampled_low_cam_fg_min: float
    raster_proxy_p10: float
    raster_proxy_median: float
    raster_proxy_near_fraction: float
    contrast_excess: float


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def hue(values: np.ndarray) -> np.ndarray:
    return np.degrees(np.arctan2(values[..., 2], values[..., 1])) % 360.0


def hue_error(values: np.ndarray, center: float) -> np.ndarray:
    return np.abs((values - center + 180.0) % 360.0 - 180.0)


def cam16_ucs(values: np.ndarray, gains: tuple[float, float, float], view: dict[str, Any]) -> np.ndarray:
    transformed = np.clip(np.asarray(values) * np.asarray(gains), 0.0, 1.0)
    xyz = colour.sRGB_to_XYZ(transformed)
    flare = float(view["flare"]) * colour.sRGB_to_XYZ(np.ones_like(transformed))
    return np.asarray(
        colour.XYZ_to_CAM16UCS(
            xyz + flare,
            L_A=float(view["L_A"]),
            Y_b=float(view["Y_b"]),
        ),
        dtype=float,
    )


def hex_array(values: tuple[str, ...]) -> np.ndarray:
    return np.asarray([hex_to_srgb(value) for value in values])


def pair_min(values: np.ndarray) -> float:
    distances = np.linalg.norm(values[:, None] - values[None, :], axis=2)
    return float(distances[np.triu_indices(len(values), k=1)].min())


def contrast_rows(values: np.ndarray, backgrounds: np.ndarray) -> np.ndarray:
    result = np.empty((len(values), len(backgrounds)))
    for i, value in enumerate(values):
        for j, background in enumerate(backgrounds):
            result[i, j] = contrast_ratio(value, background)
    return result


def raster_proxy(
    values: np.ndarray,
    fg0: np.ndarray,
    backgrounds: np.ndarray,
    gains: tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return per-candidate p10, median, and near-tail fraction.

    This uses a declared coverage station set and RGB8 quantization. It is not
    a browser oracle; finalists must be measured from Chromium pixels.
    """

    rows = []
    for state_gains in ((1.0, 1.0, 1.0), gains):
        g = np.asarray(state_gains)
        for background in backgrounds:
            for alpha in COVERAGES:
                candidate_pixel = np.rint(
                    np.clip((alpha * values + (1.0 - alpha) * background) * g, 0.0, 1.0)
                    * 255.0
                ) / 255.0
                fg_pixel = np.rint(
                    np.clip((alpha * fg0 + (1.0 - alpha) * background) * g, 0.0, 1.0)
                    * 255.0
                ) / 255.0
                distance = np.linalg.norm(
                    srgb_to_oklab(candidate_pixel) - srgb_to_oklab(fg_pixel), axis=1
                ) * 100.0
                rows.append(distance)
    matrix = np.asarray(rows).T
    return (
        np.quantile(matrix, 0.10, axis=1),
        np.quantile(matrix, 0.50, axis=1),
        np.mean(matrix < 0.5, axis=1),
    )


def baseline_metrics(base: Any, foregrounds: np.ndarray) -> dict[str, Any]:
    values = hex_array(base.terminal_colors)
    transformed = warm_transform(values, base.profile.gains)
    command_lab = srgb_to_oklab(values)
    transformed_lab = srgb_to_oklab(transformed)
    normal_cam = cam16_ucs(values, (1.0, 1.0, 1.0), NORMAL_VIEW)
    low_cam = cam16_ucs(values, base.profile.gains, LOW_LIGHT_VIEW)
    foreground_normal_cam = cam16_ucs(foregrounds, (1.0, 1.0, 1.0), NORMAL_VIEW)
    foreground_low_cam = cam16_ucs(foregrounds, base.profile.gains, LOW_LIGHT_VIEW)
    return {
        "values": list(base.terminal_colors),
        "command_pair_oklab": pair_min(command_lab) * 100.0,
        "transformed_pair_oklab": pair_min(transformed_lab) * 100.0,
        "normal_cam_pair": pair_min(normal_cam),
        "low_cam_pair": pair_min(low_cam),
        "normal_cam_fg_by_role": np.linalg.norm(
            normal_cam[:, None] - foreground_normal_cam[None, :], axis=2
        ).min(axis=1).tolist(),
        "low_cam_fg_by_role": np.linalg.norm(
            low_cam[:, None] - foreground_low_cam[None, :], axis=2
        ).min(axis=1).tolist(),
    }


def generate_role_catalog(
    role: str,
    base: Any,
    foregrounds: np.ndarray,
    backgrounds: np.ndarray,
    baseline: dict[str, Any],
) -> list[Candidate]:
    center = ROLE_HUE_CENTERS[role]
    labs = []
    for lightness in np.linspace(COMMAND_L_RANGE[0], COMMAND_L_RANGE[1], 43):
        for chroma in np.linspace(COMMAND_C_RANGE[0], COMMAND_C_RANGE[1], 27):
            for role_hue in np.linspace(center - ROLE_HUE_RADIUS, center + ROLE_HUE_RADIUS, 41):
                radians = math.radians(role_hue)
                labs.append((lightness, chroma * math.cos(radians), chroma * math.sin(radians)))
    lab = np.asarray(labs)
    raw_rgb = oklab_to_srgb(lab)
    in_gamut = np.all((raw_rgb >= 0.0) & (raw_rgb <= 1.0), axis=1)
    raw_rgb = raw_rgb[in_gamut]
    quantized_hex = sorted(
        {srgb_to_hex(value) for value in raw_rgb}
        | {base.terminal_colors[ROLE_ORDER.index(role)]}
    )
    values = hex_array(tuple(quantized_hex))
    command_lab = srgb_to_oklab(values)
    transformed = warm_transform(values, base.profile.gains)
    transformed_lab = srgb_to_oklab(transformed)
    command_hue = hue(command_lab)
    transformed_hue = hue(transformed_lab)
    current_transformed_hue = float(
        hue(srgb_to_oklab(warm_transform(hex_to_srgb(base.terminal_colors[ROLE_ORDER.index(role)]), base.profile.gains))[None, :])[0]
    )
    fg_command_lab = srgb_to_oklab(foregrounds)
    fg_transformed_lab = srgb_to_oklab(warm_transform(foregrounds, base.profile.gains))
    command_fg0 = np.linalg.norm(command_lab - fg_command_lab[0], axis=1) * 100.0
    transformed_fg0 = np.linalg.norm(transformed_lab - fg_transformed_lab[0], axis=1) * 100.0
    normal_cam = cam16_ucs(values, (1.0, 1.0, 1.0), NORMAL_VIEW)
    low_cam = cam16_ucs(values, base.profile.gains, LOW_LIGHT_VIEW)
    fg_normal_cam = cam16_ucs(foregrounds, (1.0, 1.0, 1.0), NORMAL_VIEW)
    fg_low_cam = cam16_ucs(foregrounds, base.profile.gains, LOW_LIGHT_VIEW)
    normal_cam_fg = np.linalg.norm(normal_cam[:, None] - fg_normal_cam[None, :], axis=2).min(axis=1)
    low_cam_fg = np.linalg.norm(low_cam[:, None] - fg_low_cam[None, :], axis=2).min(axis=1)
    # Terminal themes render on bg_0. bg_1 remains a reported raster stress
    # surface, not a text-contrast veto for the authored ANSI bank.
    command_contrast = contrast_rows(values, backgrounds[:1]).min(axis=1)
    transformed_contrast = contrast_rows(
        transformed, warm_transform(backgrounds[:1], base.profile.gains)
    ).min(axis=1)
    sampled_contrast = np.full(len(values), np.inf)
    sampled_fg0 = np.full(len(values), np.inf)
    sampled_low_cam_fg = np.full(len(values), np.inf)
    for gains in GAIN_SAMPLES:
        sampled_values = warm_transform(values, gains)
        sampled_foregrounds = warm_transform(foregrounds, gains)
        sampled_backgrounds = warm_transform(backgrounds[:1], gains)
        sampled_contrast = np.minimum(
            sampled_contrast,
            contrast_rows(sampled_values, sampled_backgrounds).min(axis=1),
        )
        sampled_fg0 = np.minimum(
            sampled_fg0,
            np.linalg.norm(
                srgb_to_oklab(sampled_values) - srgb_to_oklab(sampled_foregrounds)[0],
                axis=1,
            )
            * 100.0,
        )
        sampled_cam = cam16_ucs(values, gains, LOW_LIGHT_VIEW)
        sampled_fg_cam = cam16_ucs(foregrounds, gains, LOW_LIGHT_VIEW)
        sampled_low_cam_fg = np.minimum(
            sampled_low_cam_fg,
            np.linalg.norm(
                sampled_cam[:, None] - sampled_fg_cam[None, :], axis=2
            ).min(axis=1),
        )
    proxy_p10, proxy_median, proxy_near = raster_proxy(
        values, foregrounds[0], backgrounds, base.profile.gains
    )
    command_c = np.linalg.norm(command_lab[:, 1:], axis=1)
    transformed_c = np.linalg.norm(transformed_lab[:, 1:], axis=1)
    failures = (
        (hue_error(command_hue, center) > ROLE_HUE_RADIUS + 0.2)
        | (hue_error(transformed_hue, current_transformed_hue) > 32.0)
        | (command_fg0 < COMMAND_OKLAB_FG0_FLOOR)
        | (transformed_fg0 < TRANSFORMED_OKLAB_FG0_FLOOR)
        | (normal_cam_fg < NORMAL_CAM_FG_FLOOR)
        | (low_cam_fg < LOW_CAM_FG_FLOOR)
        | (command_contrast < CONTRAST_FLOOR)
        | (transformed_contrast < CONTRAST_FLOOR)
        | (sampled_contrast < CONTRAST_FLOOR)
        | (sampled_fg0 < TRANSFORMED_OKLAB_FG0_FLOOR)
        | (sampled_low_cam_fg < LOW_CAM_FG_FLOOR)
        | (transformed_lab[:, 0] < TRANSFORMED_L_FLOOR)
        | (transformed_c < TRANSFORMED_C_FLOOR)
    )
    candidates: list[Candidate] = []
    for index in np.flatnonzero(~failures):
        candidates.append(
            Candidate(
                role=role,
                hex=quantized_hex[index],
                command_l=float(command_lab[index, 0]),
                command_c=float(command_c[index]),
                command_h=float(command_hue[index]),
                transformed_l=float(transformed_lab[index, 0]),
                transformed_c=float(transformed_c[index]),
                transformed_h=float(transformed_hue[index]),
                command_fg0_oklab=float(command_fg0[index]),
                transformed_fg0_oklab=float(transformed_fg0[index]),
                normal_cam_fg_min=float(normal_cam_fg[index]),
                low_cam_fg_min=float(low_cam_fg[index]),
                commanded_contrast_min=float(command_contrast[index]),
                transformed_contrast_min=float(transformed_contrast[index]),
                sampled_contrast_min=float(sampled_contrast[index]),
                sampled_fg0_oklab_min=float(sampled_fg0[index]),
                sampled_low_cam_fg_min=float(sampled_low_cam_fg[index]),
                raster_proxy_p10=float(proxy_p10[index]),
                raster_proxy_median=float(proxy_median[index]),
                raster_proxy_near_fraction=float(proxy_near[index]),
                contrast_excess=float(
                    max(0.0, command_contrast[index] - CONTRAST_SOFT_TARGET)
                    + max(0.0, transformed_contrast[index] - CONTRAST_SOFT_TARGET)
                ),
            )
        )
    candidates.sort(
        key=lambda item: (
            item.raster_proxy_near_fraction,
            -item.raster_proxy_p10,
            -item.transformed_l,
            item.contrast_excess,
            item.hex,
        )
    )
    if not candidates:
        raise SearchError(f"no individually feasible {role} colors")
    # Keep broad objective diversity rather than only one scalar ranking.
    selected: dict[str, Candidate] = {
        item.hex: item for item in candidates[: CATALOG_KEEP // 3]
    }
    for key in (
        lambda item: (-item.transformed_l, -item.raster_proxy_p10, item.hex),
        lambda item: (-item.low_cam_fg_min, -item.raster_proxy_p10, item.hex),
        lambda item: (item.contrast_excess, -item.raster_proxy_p10, item.hex),
    ):
        for item in sorted(candidates, key=key)[: CATALOG_KEEP // 4]:
            selected[item.hex] = item
    baseline_hex = base.terminal_colors[ROLE_ORDER.index(role)]
    baseline_candidate = next(
        (item for item in candidates if item.hex == baseline_hex), None
    )
    if baseline_candidate is not None:
        selected[baseline_hex] = baseline_candidate
    result = list(selected.values())
    result.sort(
        key=lambda item: (
            item.raster_proxy_near_fraction,
            -item.raster_proxy_p10,
            -item.transformed_l,
            item.contrast_excess,
            item.hex,
        )
    )
    return result[:CATALOG_KEEP]


def bank_metrics(values: tuple[str, ...], base: Any) -> dict[str, float]:
    rgb = hex_array(values)
    transformed = warm_transform(rgb, base.profile.gains)
    metrics = {
        "command_pair_oklab": pair_min(srgb_to_oklab(rgb)) * 100.0,
        "transformed_pair_oklab": pair_min(srgb_to_oklab(transformed)) * 100.0,
        "normal_cam_pair": pair_min(cam16_ucs(rgb, (1.0, 1.0, 1.0), NORMAL_VIEW)),
        "low_cam_pair": pair_min(cam16_ucs(rgb, base.profile.gains, LOW_LIGHT_VIEW)),
    }
    metrics["sampled_pair_oklab"] = min(
        pair_min(srgb_to_oklab(warm_transform(rgb, gains))) * 100.0
        for gains in GAIN_SAMPLES
    )
    metrics["sampled_low_cam_pair"] = min(
        pair_min(cam16_ucs(rgb, gains, LOW_LIGHT_VIEW)) for gains in GAIN_SAMPLES
    )
    return metrics


def feasible_bank(metrics: dict[str, float], baseline: dict[str, Any]) -> bool:
    return (
        metrics["command_pair_oklab"] >= COMMAND_PAIR_OKLAB_FLOOR
        and metrics["transformed_pair_oklab"] >= TRANSFORMED_PAIR_OKLAB_FLOOR
        and metrics["sampled_pair_oklab"] >= TRANSFORMED_PAIR_OKLAB_FLOOR
        and metrics["normal_cam_pair"] >= NORMAL_CAM_PAIR_FLOOR_RATIO * baseline["normal_cam_pair"]
        and metrics["low_cam_pair"] >= LOW_CAM_PAIR_FLOOR_RATIO * baseline["low_cam_pair"]
        and metrics["sampled_low_cam_pair"]
        >= LOW_CAM_PAIR_FLOOR_RATIO * baseline["low_cam_pair"]
    )


def select_finalists(
    catalogs: dict[str, list[Candidate]],
    base: Any,
    baseline: dict[str, Any],
    seed: int,
) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    feasible: dict[tuple[str, ...], dict[str, Any]] = {}
    features = {}
    for role in ROLE_ORDER:
        rgb = hex_array(tuple(item.hex for item in catalogs[role]))
        features[role] = {
            "command_lab": srgb_to_oklab(rgb),
            "transformed_lab": srgb_to_oklab(warm_transform(rgb, base.profile.gains)),
            "normal_cam": cam16_ucs(rgb, (1.0, 1.0, 1.0), NORMAL_VIEW),
            "low_cam": cam16_ucs(rgb, base.profile.gains, LOW_LIGHT_VIEW),
        }
    compatibility: dict[tuple[int, int], np.ndarray] = {}
    normal_cam_floor = NORMAL_CAM_PAIR_FLOOR_RATIO * baseline["normal_cam_pair"]
    low_cam_floor = LOW_CAM_PAIR_FLOOR_RATIO * baseline["low_cam_pair"]
    for left_index, right_index in combinations(range(len(ROLE_ORDER)), 2):
        left_role = ROLE_ORDER[left_index]
        right_role = ROLE_ORDER[right_index]
        left = features[left_role]
        right = features[right_role]
        command_distance = np.linalg.norm(
            left["command_lab"][:, None] - right["command_lab"][None, :], axis=2
        ) * 100.0
        transformed_distance = np.linalg.norm(
            left["transformed_lab"][:, None] - right["transformed_lab"][None, :], axis=2
        ) * 100.0
        normal_cam_distance = np.linalg.norm(
            left["normal_cam"][:, None] - right["normal_cam"][None, :], axis=2
        )
        low_cam_distance = np.linalg.norm(
            left["low_cam"][:, None] - right["low_cam"][None, :], axis=2
        )
        sampled_transformed_distance = np.full_like(transformed_distance, np.inf)
        sampled_low_cam_distance = np.full_like(low_cam_distance, np.inf)
        left_rgb = hex_array(tuple(item.hex for item in catalogs[left_role]))
        right_rgb = hex_array(tuple(item.hex for item in catalogs[right_role]))
        for gains in GAIN_SAMPLES:
            sampled_left_lab = srgb_to_oklab(warm_transform(left_rgb, gains))
            sampled_right_lab = srgb_to_oklab(warm_transform(right_rgb, gains))
            sampled_transformed_distance = np.minimum(
                sampled_transformed_distance,
                np.linalg.norm(
                    sampled_left_lab[:, None] - sampled_right_lab[None, :], axis=2
                )
                * 100.0,
            )
            sampled_left_cam = cam16_ucs(left_rgb, gains, LOW_LIGHT_VIEW)
            sampled_right_cam = cam16_ucs(right_rgb, gains, LOW_LIGHT_VIEW)
            sampled_low_cam_distance = np.minimum(
                sampled_low_cam_distance,
                np.linalg.norm(
                    sampled_left_cam[:, None] - sampled_right_cam[None, :], axis=2
                ),
            )
        compatibility[(left_index, right_index)] = (
            (command_distance >= COMMAND_PAIR_OKLAB_FLOOR)
            & (transformed_distance >= TRANSFORMED_PAIR_OKLAB_FLOOR)
            & (sampled_transformed_distance >= TRANSFORMED_PAIR_OKLAB_FLOOR)
            & (normal_cam_distance >= normal_cam_floor)
            & (low_cam_distance >= low_cam_floor)
            & (sampled_low_cam_distance >= low_cam_floor)
        )
    # Deterministic role-wise leaders seed the pool.
    leader_sets = []
    for mode in ("raster", "photopic", "clearance", "low_contrast"):
        chosen = []
        for role in ROLE_ORDER:
            rows = catalogs[role]
            if mode == "raster":
                chosen.append(max(rows, key=lambda x: (x.raster_proxy_p10, x.transformed_l, x.hex)))
            elif mode == "photopic":
                chosen.append(max(rows, key=lambda x: (x.transformed_l, x.raster_proxy_p10, x.hex)))
            elif mode == "clearance":
                chosen.append(max(rows, key=lambda x: (x.low_cam_fg_min, x.raster_proxy_p10, x.hex)))
            else:
                chosen.append(min(rows, key=lambda x: (x.contrast_excess, -x.raster_proxy_p10, x.hex)))
        leader_sets.append(tuple(item.hex for item in chosen))
    candidates = list(leader_sets)
    baseline_values = tuple(base.terminal_colors)
    if all(
        baseline_values[index] in {item.hex for item in catalogs[role]}
        for index, role in enumerate(ROLE_ORDER)
    ):
        candidates.append(baseline_values)
    for _ in range(RANDOM_COMBINATIONS):
        selected_indices: list[int] = []
        complete = True
        for role_index, role in enumerate(ROLE_ORDER):
            allowed = np.ones(len(catalogs[role]), dtype=bool)
            for previous_index, previous_choice in enumerate(selected_indices):
                allowed &= compatibility[(previous_index, role_index)][previous_choice]
            options = np.flatnonzero(allowed)
            if not len(options):
                complete = False
                break
            option_index = min(
                len(options) - 1,
                int((rng.random() ** 1.8) * len(options)),
            )
            selected_indices.append(int(options[option_index]))
        if complete:
            candidates.append(
                tuple(
                    catalogs[role][index].hex
                    for role, index in zip(ROLE_ORDER, selected_indices, strict=True)
                )
            )
    lookup = {role: {item.hex: item for item in rows} for role, rows in catalogs.items()}


    def evaluate_values(values: tuple[str, ...]) -> dict[str, Any] | None:
        metrics = bank_metrics(values, base)
        if not feasible_bank(metrics, baseline):
            return None
        items = [
            lookup[role][value]
            for role, value in zip(ROLE_ORDER, values, strict=True)
        ]

        return {
            "values": list(values),
            "metrics": metrics,
            "individual": [asdict(item) for item in items],
            "objectives": {
                "minimum_raster_proxy_p10": min(
                    item.raster_proxy_p10 for item in items
                ),
                "maximum_raster_proxy_near_fraction": max(
                    item.raster_proxy_near_fraction for item in items
                ),
                "minimum_transformed_l": min(item.transformed_l for item in items),
                "minimum_low_cam_fg": min(item.low_cam_fg_min for item in items),
                "contrast_excess_sum": sum(item.contrast_excess for item in items),

            },
        }

    for values in candidates:
        if values in feasible:
            continue
        evaluated = evaluate_values(values)
        if evaluated is not None:
            feasible[values] = evaluated
    if not feasible:
        raise SearchError("no feasible six-role banks from bounded combination search")
    rows = list(feasible.values())
    modes = (
        (
            "A-raster-maximum",
            lambda row: (
                row["objectives"]["maximum_raster_proxy_near_fraction"],
                -row["objectives"]["minimum_raster_proxy_p10"],
                -row["objectives"]["minimum_transformed_l"],
                row["values"],
            ),
        ),
        (
            "B-photopic-balance",
            lambda row: (
                -row["objectives"]["minimum_transformed_l"],
                row["objectives"]["maximum_raster_proxy_near_fraction"],
                -row["objectives"]["minimum_raster_proxy_p10"],
                row["values"],
            ),
        ),
        (
            "C-low-churn-contrast",
            lambda row: (
                row["objectives"]["contrast_excess_sum"],
                row["objectives"]["maximum_raster_proxy_near_fraction"],
                -row["objectives"]["minimum_raster_proxy_p10"],
                row["values"],
            ),
        ),
    )
    selected = []
    used = set()
    for label, key in modes:
        for row in sorted(rows, key=key):
            key_values = tuple(row["values"])
            if key_values not in used:
                best = row
                for _ in range(2):
                    changed = False
                    for role_index, role in enumerate(ROLE_ORDER):
                        for item in catalogs[role]:
                            proposal = list(best["values"])
                            proposal[role_index] = item.hex
                            proposal_row = evaluate_values(tuple(proposal))
                            if proposal_row is not None and key(proposal_row) < key(best):
                                best = proposal_row
                                changed = True
                    if not changed:
                        break
                selected.append({"id": label, **best})
                used.add(tuple(best["values"]))
                break
    return selected


def run(seed: int) -> dict[str, Any]:
    base = next(family for family in FAMILIES if family.slug == "3400k-light")
    foregrounds = hex_array(tuple(base.surfaces[f"fg_{index}"] for index in range(3)))
    backgrounds = hex_array((base.surfaces["bg_0"], base.surfaces["bg_1"]))
    baseline = baseline_metrics(base, foregrounds)
    catalogs = {
        role: generate_role_catalog(role, base, foregrounds, backgrounds, baseline)
        for role in ROLE_ORDER
    }
    finalists = select_finalists(catalogs, base, baseline, seed)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "3400k-light-terminal-raster-search",
        "source": {
            "commit": SOURCE_COMMIT,
            "manifest_sha256": SOURCE_MANIFEST_SHA256,
        },
        "frozen": {
            "surfaces": dict(base.surfaces),
            "profile_gains": list(base.profile.gains),
            "categorical": list(base.categorical_colors),
            "sequential_anchors": list(base.sequential_anchors),
        },
        "viewing_conditions": {"commanded": NORMAL_VIEW, "transformed": LOW_LIGHT_VIEW},
        "contract": {
            "role_order": list(ROLE_ORDER),
            "role_hue_centers": ROLE_HUE_CENTERS,
            "role_hue_radius": ROLE_HUE_RADIUS,
            "contrast_floor": CONTRAST_FLOOR,
            "contrast_gate_backgrounds": ["bg_0"],
            "contrast_report_only_backgrounds": ["bg_1"],
            "contrast_soft_target": CONTRAST_SOFT_TARGET,
            "transformed_l_challenge": TRANSFORMED_L_CHALLENGE,
            "transformed_c_floor": TRANSFORMED_C_FLOOR,
            "command_pair_oklab_floor": COMMAND_PAIR_OKLAB_FLOOR,
            "transformed_pair_oklab_floor": TRANSFORMED_PAIR_OKLAB_FLOOR,
            "browser_evidence_required": True,
            "human_visibility_floor": None,
            "production_promotion_authorized": False,
        },
        "baseline": baseline,
        "catalog_counts": {role: len(rows) for role, rows in catalogs.items()},
        "seed": seed,
        "combination_budget": RANDOM_COMBINATIONS,
        "finalists": finalists,
    }
    payload["payload_sha256"] = sha256_json(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=340012)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    payload = run(args.seed)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(args.output)
    for finalist in payload["finalists"]:
        print(finalist["id"], finalist["values"], finalist["objectives"])


if __name__ == "__main__":
    main()
