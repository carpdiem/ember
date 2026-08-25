"""Clean-sheet categorical palette discovery for the 3400K Light experiment.

The optimizer searches six free OKLCh colors over one global domain. Proposals
cross an immediate canonical Hex8 boundary and every gate and reported metric is
computed from the reparsed bytes. Bank discovery is role-neutral; a separate
permutation step binds the discovered set to the six categorical roles.

This module is experiment-only. Pure functions do not write files, and the CLI
requires an explicit output directory outside the repository.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
if str(EXPERIMENT_DIR) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_DIR))

import phase3_optimizer as p3

from ember.color import (
    contrast_ratio,
    oklab_to_srgb,
    srgb_to_hex,
    srgb_to_oklab,
    wcag_luminance,
)

CONTRACT_PATH = Path(__file__).with_name("search-contract.json")
ROLE_NAMES = p3.ROLES
FOREGROUNDS = ("fg_0", "fg_1", "fg_2")
GATE_BACKGROUNDS = ("bg_0", "bg_1")
EXPECTED_CONTRACT_KEYS = {
    "authorization",
    "bank",
    "exploration",
    "hard_gates",
    "lanes",
    "materiality",
    "objective",
    "raster",
    "report_only",
    "schema_version",
}
FORBIDDEN_SEARCH_TERMS = (
    "per_role_l",
    "hue_half_width",
    "mean_chroma",
    "baseline_relative",
    "baseline_ratio",
    "j_prime_envelope",
    "m_prime_envelope",
    "baseline_seed",
    "churn_objective",
    "retention_envelope",
    "l_max",
)


@dataclass(frozen=True)
class CatalogColor:
    """One exact-Hex8 color admitted to the global proposal catalog."""

    hex8: str
    commanded_oklab: tuple[float, float, float]
    transformed_oklab: tuple[float, float, float]
    proposal_lightness: float
    proposal_chroma: float
    proposal_hue_degrees: float


def _exact_keys(value: object, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise ValueError(f"{label} keys differ: {sorted(actual ^ expected)}")
    return value


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _ordered_range(value: object, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must contain two values")
    low = _finite_number(value[0], f"{label}[0]")
    high = _finite_number(value[1], f"{label}[1]")
    if not low < high:
        raise ValueError(f"{label} must be strictly increasing")
    return low, high


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise TypeError("clean-sheet search contract must be an object")
    return value


def validate_contract(contract: Mapping[str, Any], inputs: p3.Phase3Inputs) -> None:
    """Validate the closed clean-sheet schema without using ``assert``."""

    _exact_keys(contract, EXPECTED_CONTRACT_KEYS, "search contract")
    if contract["schema_version"] != 1:
        raise ValueError("search contract schema version must be 1")

    authorization = _exact_keys(
        contract["authorization"],
        {"approved_g1_head", "input_chain_sha256", "require_independent_replay"},
        "authorization",
    )
    expected_authorization = {
        "approved_g1_head": p3.APPROVED_G1_HEAD,
        "input_chain_sha256": p3.input_chain_sha256(inputs),
        "require_independent_replay": True,
    }
    if dict(authorization) != expected_authorization:
        raise ValueError("authorization does not bind the approved G1 input chain")

    bank = _exact_keys(
        contract["bank"],
        {"count", "discovery_then_role_permutation", "role_order"},
        "bank",
    )
    if dict(bank) != {
        "count": 6,
        "discovery_then_role_permutation": True,
        "role_order": list(ROLE_NAMES),
    }:
        raise ValueError("bank must specify six roles after role-neutral discovery")

    exploration = _exact_keys(
        contract["exploration"],
        {"lightness", "chroma", "hue_degrees", "exact_catalog"},
        "exploration",
    )
    lightness = _ordered_range(exploration["lightness"], "exploration lightness")
    chroma = _ordered_range(exploration["chroma"], "exploration chroma")
    hue = _ordered_range(exploration["hue_degrees"], "exploration hue")
    if lightness != (0.3, 0.64) or chroma != (0.04, 0.14) or hue != (0.0, 360.0):
        raise ValueError("exploration domain differs from the approved global support")
    if exploration["exact_catalog"] != (
        "quantize to canonical Hex8, reparse, then admit by exact gamut and hard single-color gates"
    ):
        raise ValueError("exact catalog boundary is weakened")

    expected_gates = {
        "commanded_category_foreground_delta_e_ok": 8.0,
        "commanded_category_pair_delta_e_ok": 16.0,
        "graphics_contrast_ratio": 3.0,
        "minimum_commanded_oklab_lightness": 0.3,
        "minimum_nominal_transformed_luminance": 0.003,
        "nominal_transformed_category_foreground_delta_e_ok": 5.0,
        "nominal_transformed_category_pair_delta_e_ok": 8.0,
    }
    gates = _exact_keys(contract["hard_gates"], set(expected_gates), "hard gates")
    for name, value in gates.items():
        _finite_number(value, f"hard gate {name}")
    if dict(gates) != expected_gates:
        raise ValueError("hard gates differ from the approved clean-sheet gates")

    lanes = contract["lanes"]
    expected_lanes = [
        {"broad_anchor_count": 0, "id": "A", "method": "constructive-cool-lighter-warm-darker"},
        {
            "broad_anchor_count": 0,
            "id": "B",
            "method": "transformed-native-targets-inverted-through-gains",
        },
        {
            "broad_anchor_count": 2,
            "broad_anchor_half_width_degrees": 30.0,
            "broad_anchor_hues_degrees": [176.2766872, 266.0687792],
            "id": "C",
            "method": "continuity-compromise-zero-to-two-broad-anchors",
        },
    ]
    if lanes != expected_lanes:
        raise ValueError("lanes differ from the approved three-lane design")

    materiality = _exact_keys(
        contract["materiality"],
        {
            "category_fg_0_distinctiveness_delta_e_ok",
            "comparison_reference",
            "full_bank_1_5px_thin_proxy_delta_e_ok",
            "policy",
            "selected_weakest_three_dark_cluster_analog_delta_e_ok",
        },
        "materiality",
    )
    expected_materiality = {
        "category_fg_0_distinctiveness_delta_e_ok": 0.25,
        "full_bank_1_5px_thin_proxy_delta_e_ok": 0.5,
        "selected_weakest_three_dark_cluster_analog_delta_e_ok": 0.5,
    }
    for name, expected in expected_materiality.items():
        if _finite_number(materiality[name], f"materiality {name}") != expected:
            raise ValueError(f"materiality {name} must be {expected}")
    if materiality["comparison_reference"] != "current approved categorical bank":
        raise ValueError("materiality comparison reference differs")
    if materiality["policy"] != "deterministic search targets; NOT human floors":
        raise ValueError("materiality policy differs")

    objective = _exact_keys(
        contract["objective"], {"lexicographic_worst_case", "selection"}, "objective"
    )
    expected_objective = [
        "nominal_transformed_1_5px_raster_category_pair",
        "nominal_transformed_1_5px_raster_category_fg_0",
        "nominal_transformed_j_prime_luminance_pair",
        "nominal_transformed_solid_category_pair",
        "commanded_solid_category_pair",
        "raster_2px_then_3px",
        "hue_breadth_topology_sensitivity",
    ]
    if (
        objective["lexicographic_worst_case"] != expected_objective
        or objective["selection"] is not None
    ):
        raise ValueError("objective or null human selection policy differs")

    raster = _exact_keys(
        contract["raster"],
        {
            "calibrated_error_margin_delta_e_ok",
            "mask_count",
            "mask_file",
            "states",
            "widths_css_px",
        },
        "raster",
    )
    if dict(raster) != {
        "calibrated_error_margin_delta_e_ok": 0.75,
        "mask_count": 720,
        "mask_file": "raster-masks.json",
        "states": ["commanded", "nominal-transformed"],
        "widths_css_px": [1.5, 2.0, 3.0],
    }:
        raise ValueError("raster contract differs")
    if contract["report_only"] != {
        "baseline_churn": True,
        "gain_and_viewing_sensitivity": True,
    }:
        raise ValueError("report-only policy differs")

    serialized = json.dumps(contract, sort_keys=True).lower()
    present = [term for term in FORBIDDEN_SEARCH_TERMS if term in serialized]
    if present:
        raise ValueError(f"forbidden fossilizing search constraints present: {present}")


def authorization_receipt(inputs: p3.Phase3Inputs, *, replay: bool = True) -> dict[str, Any]:
    return p3.authorize_search(inputs, replay=replay)


def load_authorized_inputs(
    experiment_dir: Path = EXPERIMENT_DIR, *, replay: bool = True
) -> p3.Phase3Inputs:
    inputs = p3.load_inputs(Path(experiment_dir))
    authorization_receipt(inputs, replay=replay)
    return inputs


def _hue_degrees(lab: np.ndarray) -> np.ndarray:
    return np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360.0


def _hue_delta(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def _single_color_admitted(
    rgb: np.ndarray,
    commanded_lab: np.ndarray,
    transformed_rgb: np.ndarray,
    transformed_lab: np.ndarray,
    backgrounds: np.ndarray,
    gains: np.ndarray,
    foreground_lab: np.ndarray,
    transformed_foreground_lab: np.ndarray,
    gates: Mapping[str, Any],
) -> bool:
    commanded_fg = float(np.min(np.linalg.norm(commanded_lab - foreground_lab, axis=1)) * 100.0)
    transformed_fg = float(
        np.min(np.linalg.norm(transformed_lab - transformed_foreground_lab, axis=1)) * 100.0
    )
    contrasts = [contrast_ratio(rgb, background) for background in backgrounds]
    contrasts.extend(
        contrast_ratio(transformed_rgb, transformed_background)
        for transformed_background in backgrounds * gains
    )
    return (
        commanded_lab[0] + 1e-12 >= gates["minimum_commanded_oklab_lightness"]
        and commanded_fg + 1e-12 >= gates["commanded_category_foreground_delta_e_ok"]
        and transformed_fg + 1e-12 >= gates["nominal_transformed_category_foreground_delta_e_ok"]
        and float(wcag_luminance(transformed_rgb)) + 1e-12
        >= gates["minimum_nominal_transformed_luminance"]
        and min(contrasts) + 1e-12 >= gates["graphics_contrast_ratio"]
    )


def build_catalog(
    inputs: p3.Phase3Inputs, contract: Mapping[str, Any], *, reduced: bool = False
) -> tuple[list[CatalogColor], dict[str, Any]]:
    """Construct a broad exact catalog from global OKLCh support."""

    validate_contract(contract, inputs)
    exploration = contract["exploration"]
    l_low, l_high = (float(value) for value in exploration["lightness"])
    c_low, c_high = (float(value) for value in exploration["chroma"])
    if reduced:
        lightness_axis = np.linspace(l_low, l_high, 18)
        chroma_axis = np.linspace(c_low, c_high, 6)
        hue_axis = np.arange(0.0, 360.0, 15.0)
    else:
        lightness_axis = np.linspace(l_low, l_high, 35)
        chroma_axis = np.linspace(c_low, c_high, 11)
        hue_axis = np.arange(0.0, 360.0, 7.5)

    surfaces = inputs.baseline["family"]["surfaces"]
    backgrounds = np.asarray([p3.parse_exact_hex8(surfaces[name]) for name in GATE_BACKGROUNDS])
    foregrounds = np.asarray([p3.parse_exact_hex8(surfaces[name]) for name in FOREGROUNDS])
    foreground_lab = srgb_to_oklab(foregrounds)
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    transformed_foreground_lab = srgb_to_oklab(foregrounds * gains)
    rows: dict[str, CatalogColor] = {}

    for lightness in lightness_axis:
        for chroma in chroma_axis:
            for hue in hue_axis:
                radians = np.radians(hue)
                proposal = np.asarray(
                    [lightness, chroma * np.cos(radians), chroma * np.sin(radians)], dtype=float
                )
                proposal_rgb = oklab_to_srgb(proposal)
                if np.any(proposal_rgb < -1e-6) or np.any(proposal_rgb > 1.0 + 1e-6):
                    continue
                hex8 = srgb_to_hex(proposal_rgb)
                rgb = p3.parse_exact_hex8(hex8)
                commanded_lab = srgb_to_oklab(rgb)
                transformed_rgb = rgb * gains
                transformed_lab = srgb_to_oklab(transformed_rgb)
                if not _single_color_admitted(
                    rgb,
                    commanded_lab,
                    transformed_rgb,
                    transformed_lab,
                    backgrounds,
                    gains,
                    foreground_lab,
                    transformed_foreground_lab,
                    contract["hard_gates"],
                ):
                    continue
                rows.setdefault(
                    hex8,
                    CatalogColor(
                        hex8=hex8,
                        commanded_oklab=tuple(float(value) for value in commanded_lab),
                        transformed_oklab=tuple(float(value) for value in transformed_lab),
                        proposal_lightness=float(lightness),
                        proposal_chroma=float(chroma),
                        proposal_hue_degrees=float(hue),
                    ),
                )

    catalog = [rows[key] for key in sorted(rows)]
    if len(catalog) < 6:
        raise RuntimeError("global exact catalog contains fewer than six admissible colors")

    baseline = set(_baseline_bank(inputs))
    exact_lab = np.asarray([row.commanded_oklab for row in catalog])
    exact_chroma = np.linalg.norm(exact_lab[:, 1:], axis=1)
    exact_hue = _hue_degrees(exact_lab)
    support = {
        "lightness_bins_occupied": len(
            np.unique(np.digitize(exact_lab[:, 0], np.linspace(l_low, l_high, 9)))
        ),
        "chroma_bins_occupied": len(
            np.unique(np.digitize(exact_chroma, np.linspace(c_low, c_high, 6)))
        ),
        "hue_bins_occupied": len(np.unique(np.floor(exact_hue / 15.0).astype(int))),
        "non_baseline_fraction": float(
            sum(row.hex8 not in baseline for row in catalog) / len(catalog)
        ),
    }
    summary = {
        "schema_version": 1,
        "catalog_mode": "reduced" if reduced else "full",
        "exact_hex8_count": len(catalog),
        "requested_domain": {
            "lightness": list(exploration["lightness"]),
            "chroma": list(exploration["chroma"]),
            "hue_degrees": list(exploration["hue_degrees"]),
        },
        "support": support,
        "admission": {
            "canonical_hex8_reparsed_before_metrics": True,
            "exact_srgb_gamut": True,
            "hard_single_color_gates": sorted(contract["hard_gates"]),
            "uniform_lightness_ceiling": None,
            "upper_lightness_derived_from_exact_background_contrast": True,
        },
    }
    return catalog, summary


def _baseline_bank(inputs: p3.Phase3Inputs) -> tuple[str, ...]:
    categorical = inputs.baseline["family"]["categorical"]
    return tuple(categorical[name] for name in p3.ROLE_NAMES)


def _lane_targets(lane: str, inputs: p3.Phase3Inputs) -> tuple[list[float], list[float]]:
    if lane == "A":
        return [20.0, 80.0, 140.0, 200.0, 260.0, 320.0], [0.42, 0.60, 0.40, 0.58, 0.42, 0.58]
    if lane == "C":
        return [15.0, 75.0, 135.0, 195.0, 255.0, 315.0], [0.45, 0.58, 0.42, 0.58, 0.42, 0.58]
    if lane != "B":
        raise ValueError(f"unknown search lane: {lane}")

    transformed_native_oklch = (
        (0.42, 0.10, 10.0),
        (0.28, 0.10, 35.0),
        (0.53, 0.11, 135.0),
        (0.36, 0.09, 155.0),
        (0.48, 0.10, 255.0),
        (0.27, 0.10, 285.0),
    )
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    hues: list[float] = []
    lightnesses: list[float] = []
    for lightness, chroma, hue in transformed_native_oklch:
        radians = np.radians(hue)
        transformed_lab = np.asarray(
            [lightness, chroma * np.cos(radians), chroma * np.sin(radians)], dtype=float
        )
        transformed_rgb = oklab_to_srgb(transformed_lab)
        commanded_lab = srgb_to_oklab(np.clip(transformed_rgb / gains, 0.0, 1.0))
        hues.append(float(_hue_degrees(commanded_lab)))
        lightnesses.append(float(commanded_lab[0]))
    return hues, lightnesses


def _discover_bank(
    catalog: Sequence[CatalogColor],
    lane: str,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> tuple[str, ...]:
    """Discover an unordered bank; no role or baseline values enter this search."""

    target_hues, target_lightnesses = _lane_targets(lane, inputs)
    hexes = [row.hex8 for row in catalog]
    commanded = np.asarray([row.commanded_oklab for row in catalog]) * 100.0
    transformed = np.asarray([row.transformed_oklab for row in catalog]) * 100.0
    hues = np.asarray([float(_hue_degrees(np.asarray(row.commanded_oklab))) for row in catalog])
    lane_contract = next(row for row in contract["lanes"] if row["id"] == lane)
    anchor_hues = lane_contract.get("broad_anchor_hues_degrees", [])
    anchor_half_width = lane_contract.get("broad_anchor_half_width_degrees")
    beam: list[tuple[tuple[int, ...], float, float]] = [((), math.inf, math.inf)]

    for target_hue, target_lightness in zip(target_hues, target_lightnesses, strict=True):
        pool = [
            index
            for index in range(len(catalog))
            if _hue_delta(float(hues[index]), target_hue) <= 35.0
        ]
        pool.sort(
            key=lambda index: (
                abs(catalog[index].commanded_oklab[0] - target_lightness),
                _hue_delta(float(hues[index]), target_hue),
                hexes[index],
            )
        )
        pool = pool[:150]
        if not pool:
            raise RuntimeError(f"lane {lane} target has no globally admissible colors")
        next_rows: list[
            tuple[tuple[float, float, float, float], tuple[int, ...], float, float]
        ] = []
        for selected, commanded_min, transformed_min in beam:
            for index in pool:
                if index in selected:
                    continue
                commanded_distance = min(
                    (
                        float(np.linalg.norm(commanded[index] - commanded[other]))
                        for other in selected
                    ),
                    default=math.inf,
                )
                transformed_distance = min(
                    (
                        float(np.linalg.norm(transformed[index] - transformed[other]))
                        for other in selected
                    ),
                    default=math.inf,
                )
                next_commanded = min(commanded_min, commanded_distance)
                next_transformed = min(transformed_min, transformed_distance)
                new_selected = (*selected, index)
                if len(new_selected) == 6 and anchor_hues:
                    if anchor_half_width is None:
                        raise RuntimeError(f"lane {lane} anchor width is missing")
                    anchor_assignments = itertools.permutations(new_selected, len(anchor_hues))
                    if not any(
                        all(
                            _hue_delta(float(hues[color_index]), float(anchor_hue))
                            <= float(anchor_half_width)
                            for color_index, anchor_hue in zip(assignment, anchor_hues, strict=True)
                        )
                        for assignment in anchor_assignments
                    ):
                        continue
                if len(new_selected) == 6 and (
                    next_commanded + 1e-12
                    < contract["hard_gates"]["commanded_category_pair_delta_e_ok"]
                    or next_transformed + 1e-12
                    < contract["hard_gates"]["nominal_transformed_category_pair_delta_e_ok"]
                ):
                    continue
                topology_error = sum(
                    _hue_delta(float(hues[color_index]), slot_hue)
                    for color_index, slot_hue in zip(new_selected, target_hues, strict=False)
                )
                score = (
                    min(next_commanded, next_transformed),
                    next_transformed,
                    next_commanded,
                    -topology_error,
                )
                next_rows.append((score, new_selected, next_commanded, next_transformed))
        next_rows.sort(
            key=lambda row: (row[0], tuple(hexes[index] for index in row[1])), reverse=True
        )
        beam = [
            (selected, commanded_min, transformed_min)
            for _, selected, commanded_min, transformed_min in next_rows[:300]
        ]
        if not beam:
            raise RuntimeError(f"lane {lane} search beam was exhausted")

    return tuple(sorted(hexes[index] for index in beam[0][0]))


def _permute_roles(
    discovered: Sequence[str], inputs: p3.Phase3Inputs
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    """Bind an already-discovered set to roles as an explicit second phase."""

    discovered_bank = p3.canonical_bank(discovered)
    discovered_lab = p3.bank_oklab(discovered_bank)
    role_reference = p3.bank_oklab(_baseline_bank(inputs))
    best: tuple[float, tuple[str, ...], tuple[int, ...]] | None = None
    for permutation in itertools.permutations(range(6)):
        cost = float(
            sum(
                np.linalg.norm(discovered_lab[color_index] - role_reference[role_index])
                for role_index, color_index in enumerate(permutation)
            )
        )
        ordered = tuple(discovered_bank[index] for index in permutation)
        candidate = (cost, ordered, permutation)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        raise RuntimeError("role permutation produced no assignment")
    ordered = best[1]
    mapping = [
        {
            "role": role,
            "discovered_index": int(best[2][role_index]),
            "hex8": ordered[role_index],
        }
        for role_index, role in enumerate(ROLE_NAMES)
    ]
    return ordered, mapping


def _continuity_anchor_matches(
    discovered: Sequence[str], lane_contract: Mapping[str, Any]
) -> list[dict[str, Any]]:
    anchor_hues = lane_contract.get("broad_anchor_hues_degrees", [])
    if not anchor_hues:
        return []
    half_width = float(lane_contract["broad_anchor_half_width_degrees"])
    bank = p3.canonical_bank(discovered)
    hues = [float(_hue_degrees(row)) for row in p3.bank_oklab(bank)]
    matches = []
    used: set[int] = set()
    for anchor_hue in anchor_hues:
        choices = sorted(
            (
                (_hue_delta(hue, float(anchor_hue)), bank[index], index, hue)
                for index, hue in enumerate(hues)
                if index not in used
            )
        )
        if not choices or choices[0][0] > half_width + 1e-12:
            raise RuntimeError("continuity lane does not cover every declared broad anchor")
        delta, hex8, index, hue = choices[0]
        used.add(index)
        matches.append(
            {
                "anchor_hue_degrees": float(anchor_hue),
                "matched_hex8": hex8,
                "matched_hue_degrees": hue,
                "hue_delta_degrees": delta,
                "half_width_degrees": half_width,
            }
        )
    return matches


def _minimum_pair(points: np.ndarray, labels: Sequence[str]) -> dict[str, Any]:
    rows = [
        (
            float(np.linalg.norm(points[left] - points[right]) * 100.0),
            f"{labels[left]} vs {labels[right]}",
        )
        for left, right in itertools.combinations(range(len(points)), 2)
    ]
    value, binding = min(rows)
    return {"delta_e_ok": value, "binding": binding}


def _minimum_foreground(
    category_points: np.ndarray,
    foreground_points: np.ndarray,
    foreground_labels: Sequence[str],
) -> dict[str, Any]:
    rows = [
        (
            float(
                np.linalg.norm(category_points[category] - foreground_points[foreground]) * 100.0
            ),
            f"{ROLE_NAMES[category]} vs {foreground_labels[foreground]}",
        )
        for category in range(6)
        for foreground in range(len(foreground_points))
    ]
    value, binding = min(rows)
    return {"delta_e_ok": value, "binding": binding}


def _raster_metrics(
    bank: tuple[str, ...], inputs: p3.Phase3Inputs, contract: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    rgb = p3.bank_rgb(bank)
    surfaces = inputs.baseline["family"]["surfaces"]
    fg0 = p3.parse_exact_hex8(surfaces["fg_0"])
    backgrounds = {name: p3.parse_exact_hex8(surfaces[name]) for name in GATE_BACKGROUNDS}
    gains_by_state = {
        "commanded": np.ones(3),
        "nominal-transformed": np.asarray(inputs.viewing["transform"]["gains"], dtype=float),
    }
    margin = float(contract["raster"]["calibrated_error_margin_delta_e_ok"])
    pair_rows: dict[str, tuple[float, str]] = {}
    fg0_rows: dict[str, tuple[float, str]] = {}

    for geometry, lanes in sorted(p3._mask_summaries(inputs).items()):
        width, style, orientation, dpr, phase = geometry
        for state, gains in gains_by_state.items():
            for background_name, background in backgrounds.items():
                key = f"{width:g}/{state}/{background_name}"
                category_points = []
                fg0_points = []
                for lane in (0, 1):
                    coverage = lanes[lane]
                    category_composite = coverage * rgb + (1.0 - coverage) * background
                    fg0_composite = coverage * fg0 + (1.0 - coverage) * background
                    category_points.append(
                        srgb_to_oklab(np.clip(category_composite * gains, 0.0, 1.0))
                    )
                    fg0_points.append(srgb_to_oklab(np.clip(fg0_composite * gains, 0.0, 1.0)))
                context = (
                    f"{state}/{background_name}/{style}/{orientation}/dpr-{dpr}/"
                    f"phase-{phase[0]:g}-{phase[1]:g}"
                )
                for left, right in itertools.combinations(range(6), 2):
                    for left_lane, right_lane in ((0, 1), (1, 0)):
                        value = float(
                            np.linalg.norm(
                                category_points[left_lane][left]
                                - category_points[right_lane][right]
                            )
                            * 100.0
                            - margin
                        )
                        binding = f"{context}/{ROLE_NAMES[left]} vs {ROLE_NAMES[right]}"
                        current = pair_rows.get(key)
                        if current is None or (value, binding) < current:
                            pair_rows[key] = (value, binding)
                for category in range(6):
                    for category_lane, foreground_lane in ((0, 1), (1, 0)):
                        value = float(
                            np.linalg.norm(
                                category_points[category_lane][category]
                                - fg0_points[foreground_lane]
                            )
                            * 100.0
                            - margin
                        )
                        binding = f"{context}/{ROLE_NAMES[category]} vs fg_0"
                        current = fg0_rows.get(key)
                        if current is None or (value, binding) < current:
                            fg0_rows[key] = (value, binding)

    def finish(rows: Mapping[str, tuple[float, str]]) -> dict[str, Any]:
        if not rows:
            raise RuntimeError("approved raster mask set produced no metric rows")
        value, binding = min(rows.values())
        return {
            "calibrated_delta_e_ok": value,
            "binding": binding,
            "mask_count": len(inputs.raster_masks["records"]),
            "exact_binding": True,
            "minimum_by_width_state_background": {
                key: {"calibrated_delta_e_ok": row[0], "binding": row[1]}
                for key, row in sorted(rows.items())
            },
        }

    return finish(pair_rows), finish(fg0_rows)


def _contrast_metrics(bank: tuple[str, ...], inputs: p3.Phase3Inputs) -> dict[str, Any]:
    rgb = p3.bank_rgb(bank)
    surfaces = inputs.baseline["family"]["surfaces"]
    gains_by_state = {
        "commanded": np.ones(3),
        "nominal-transformed": np.asarray(inputs.viewing["transform"]["gains"], dtype=float),
    }
    values: dict[str, dict[str, Any]] = {}
    for state, gains in gains_by_state.items():
        for background_name in GATE_BACKGROUNDS:
            background = p3.parse_exact_hex8(surfaces[background_name]) * gains
            rows = [
                (float(contrast_ratio(color * gains, background)), ROLE_NAMES[index])
                for index, color in enumerate(rgb)
            ]
            value, role = min(rows)
            values[f"{state}/{background_name}"] = {
                "contrast_ratio": value,
                "binding": f"{role} vs {background_name}",
            }
    return values


def _j_prime_pair(transformed_rgb: np.ndarray, inputs: p3.Phase3Inputs) -> dict[str, Any]:
    rows: list[tuple[float, str]] = []
    for scenario in p3._viewing_scenarios(inputs.viewing, primary_only=True):
        ucs = p3._cam16_ucs(transformed_rgb, scenario)
        for left, right in itertools.combinations(range(6), 2):
            rows.append(
                (
                    float(abs(ucs[left, 0] - ucs[right, 0])),
                    f"{scenario['id']}/{ROLE_NAMES[left]} vs {ROLE_NAMES[right]}",
                )
            )
    value, binding = min(rows)
    return {"delta_j_prime": value, "binding": binding}


def _luminance_pair(transformed_rgb: np.ndarray) -> dict[str, Any]:
    luminance = np.asarray(wcag_luminance(transformed_rgb), dtype=float)
    rows = [
        (
            float(abs(luminance[left] - luminance[right])),
            f"{ROLE_NAMES[left]} vs {ROLE_NAMES[right]}",
        )
        for left, right in itertools.combinations(range(6), 2)
    ]
    value, binding = min(rows)
    return {"absolute_luminance_difference": value, "binding": binding}


def _hue_topology(commanded_oklab: np.ndarray) -> dict[str, Any]:
    ordered = sorted(
        (float(_hue_degrees(row)), ROLE_NAMES[index]) for index, row in enumerate(commanded_oklab)
    )
    hues = [row[0] for row in ordered]
    circular_gaps = [
        (hues[(index + 1) % len(hues)] - hue) % 360.0 for index, hue in enumerate(hues)
    ]
    minimum = min(circular_gaps)
    maximum = max(circular_gaps)
    minimum_index = circular_gaps.index(minimum)
    return {
        "minimum_circular_gap_degrees": minimum,
        "binding": (
            f"{ordered[minimum_index][1]} vs {ordered[(minimum_index + 1) % len(ordered)][1]}"
        ),
        "maximum_to_minimum_gap_ratio": maximum / minimum,
        "sorted_hues_degrees": hues,
        "circular_gaps_degrees": circular_gaps,
    }


def _sensitivity_report(bank: tuple[str, ...], inputs: p3.Phase3Inputs) -> dict[str, Any]:
    rgb = p3.bank_rgb(bank)
    fg0 = p3.parse_exact_hex8(inputs.baseline["family"]["surfaces"]["fg_0"])
    rows = []
    for gain in p3._gain_samples(inputs, nominal_only=False):
        gains = np.asarray([gain["red_gain"], gain["green_gain"], gain["blue_gain"]], dtype=float)
        category = srgb_to_oklab(rgb * gains)
        foreground = srgb_to_oklab(fg0 * gains)
        pair = _minimum_pair(category, ROLE_NAMES)
        fg = _minimum_foreground(category, foreground[None, :], ("fg_0",))
        rows.append(
            {
                "gain_sample": gain["id"],
                "category_pair_delta_e_ok": pair["delta_e_ok"],
                "category_pair_binding": pair["binding"],
                "category_fg_0_delta_e_ok": fg["delta_e_ok"],
                "category_fg_0_binding": fg["binding"],
            }
        )
    pair_row = min(rows, key=lambda row: (row["category_pair_delta_e_ok"], row["gain_sample"]))
    fg0_row = min(rows, key=lambda row: (row["category_fg_0_delta_e_ok"], row["gain_sample"]))
    return {
        "policy": "report-only sampled gain sensitivity; never averaged into gates",
        "sample_count": len(rows),
        "category_pair_min": pair_row,
        "category_fg_0_min": fg0_row,
    }


def _churn_report(bank: tuple[str, ...], inputs: p3.Phase3Inputs) -> dict[str, Any]:
    distances = (
        np.linalg.norm(p3.bank_oklab(bank) - p3.bank_oklab(_baseline_bank(inputs)), axis=1) * 100.0
    )
    index = int(np.argmax(distances))
    return {
        "policy": "report-only; excluded from proposal generation, hard gates, and objective",
        "mean_role_delta_e_ok": float(np.mean(distances)),
        "maximum_role_delta_e_ok": float(distances[index]),
        "binding": ROLE_NAMES[index],
    }


def compute_metrics(
    bank_values: Iterable[str], inputs: p3.Phase3Inputs, contract: Mapping[str, Any]
) -> dict[str, Any]:
    bank = p3.canonical_bank(bank_values)
    rgb = p3.bank_rgb(bank)
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    transformed_rgb = rgb * gains
    commanded = srgb_to_oklab(rgb)
    transformed = srgb_to_oklab(transformed_rgb)
    surfaces = inputs.baseline["family"]["surfaces"]
    foreground_rgb = np.asarray([p3.parse_exact_hex8(surfaces[name]) for name in FOREGROUNDS])
    commanded_foreground = srgb_to_oklab(foreground_rgb)
    transformed_foreground = srgb_to_oklab(foreground_rgb * gains)
    raster_pair, raster_fg0 = _raster_metrics(bank, inputs, contract)
    return {
        "commanded_category_pair": _minimum_pair(commanded, ROLE_NAMES),
        "commanded_category_fg_0": _minimum_foreground(
            commanded, commanded_foreground[:1], ("fg_0",)
        ),
        "commanded_category_fg_1_fg_2": _minimum_foreground(
            commanded, commanded_foreground[1:], ("fg_1", "fg_2")
        ),
        "nominal_transformed_solid_category_pair": _minimum_pair(transformed, ROLE_NAMES),
        "nominal_transformed_category_fg_0": _minimum_foreground(
            transformed, transformed_foreground[:1], ("fg_0",)
        ),
        "nominal_transformed_category_fg_1_fg_2": _minimum_foreground(
            transformed, transformed_foreground[1:], ("fg_1", "fg_2")
        ),
        "graphics_contrast_by_background_state": _contrast_metrics(bank, inputs),
        "nominal_transformed_j_prime_pair": _j_prime_pair(transformed_rgb, inputs),
        "nominal_transformed_luminance_pair": _luminance_pair(transformed_rgb),
        "commanded_hue_topology": _hue_topology(commanded),
        "raster_category_pair": raster_pair,
        "raster_category_fg_0": raster_fg0,
        "sensitivity_report": _sensitivity_report(bank, inputs),
        "churn_report": _churn_report(bank, inputs),
    }


def _hard_gate_failures(
    bank: tuple[str, ...],
    metrics: Mapping[str, Any],
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    gates = contract["hard_gates"]
    failures: list[dict[str, Any]] = []

    def floor(gate: str, actual: float, threshold: float, binding: str) -> None:
        if actual + 1e-12 < threshold:
            failures.append(
                {
                    "gate": gate,
                    "actual": actual,
                    "relation": ">=",
                    "threshold": threshold,
                    "binding": binding,
                }
            )

    floor(
        "commanded-category-pair",
        metrics["commanded_category_pair"]["delta_e_ok"],
        gates["commanded_category_pair_delta_e_ok"],
        metrics["commanded_category_pair"]["binding"],
    )
    for name in ("commanded_category_fg_0", "commanded_category_fg_1_fg_2"):
        floor(
            "commanded-category-foreground",
            metrics[name]["delta_e_ok"],
            gates["commanded_category_foreground_delta_e_ok"],
            metrics[name]["binding"],
        )
    floor(
        "nominal-transformed-category-pair",
        metrics["nominal_transformed_solid_category_pair"]["delta_e_ok"],
        gates["nominal_transformed_category_pair_delta_e_ok"],
        metrics["nominal_transformed_solid_category_pair"]["binding"],
    )
    for name in (
        "nominal_transformed_category_fg_0",
        "nominal_transformed_category_fg_1_fg_2",
    ):
        floor(
            "nominal-transformed-category-foreground",
            metrics[name]["delta_e_ok"],
            gates["nominal_transformed_category_foreground_delta_e_ok"],
            metrics[name]["binding"],
        )
    for key, row in metrics["graphics_contrast_by_background_state"].items():
        floor(
            "graphics-contrast",
            row["contrast_ratio"],
            gates["graphics_contrast_ratio"],
            f"{key}/{row['binding']}",
        )
    commanded_lightness = p3.bank_oklab(bank)[:, 0]
    minimum_index = int(np.argmin(commanded_lightness))
    floor(
        "minimum-commanded-oklab-lightness",
        float(commanded_lightness[minimum_index]),
        gates["minimum_commanded_oklab_lightness"],
        ROLE_NAMES[minimum_index],
    )
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    transformed_luminance = np.asarray(wcag_luminance(p3.bank_rgb(bank) * gains), dtype=float)
    luminance_index = int(np.argmin(transformed_luminance))
    floor(
        "minimum-nominal-transformed-luminance",
        float(transformed_luminance[luminance_index]),
        gates["minimum_nominal_transformed_luminance"],
        ROLE_NAMES[luminance_index],
    )
    return failures


def evaluate_bank(
    bank_values: Iterable[str], inputs: p3.Phase3Inputs, contract: Mapping[str, Any]
) -> dict[str, Any]:
    validate_contract(contract, inputs)
    bank = p3.canonical_bank(bank_values)
    metrics = compute_metrics(bank, inputs, contract)
    return {
        "bank": list(bank),
        "metrics": metrics,
        "hard_gate_failures": _hard_gate_failures(bank, metrics, inputs, contract),
    }


def _weakest_three_pair_mean(bank: tuple[str, ...], inputs: p3.Phase3Inputs) -> float:
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    points = srgb_to_oklab(p3.bank_rgb(bank) * gains) * 100.0
    values = sorted(
        float(np.linalg.norm(points[left] - points[right]))
        for left, right in itertools.combinations(range(6), 2)
    )
    return float(np.mean(values[:3]))


def _raster_minimum(metric: Mapping[str, Any], *, width: str, state: str) -> float:
    values = [
        row["calibrated_delta_e_ok"]
        for key, row in metric["minimum_by_width_state_background"].items()
        if key.startswith(f"{width}/{state}/")
    ]
    if not values:
        raise RuntimeError(f"raster metric lacks {width}/{state} rows")
    return float(min(values))


def _materiality_admission(
    bank: tuple[str, ...],
    metrics: Mapping[str, Any],
    baseline_metrics: Mapping[str, Any],
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    baseline_bank = _baseline_bank(inputs)
    comparisons = {
        "selected_weakest_three_dark_cluster_analog": (
            _weakest_three_pair_mean(bank, inputs),
            _weakest_three_pair_mean(baseline_bank, inputs),
            contract["materiality"]["selected_weakest_three_dark_cluster_analog_delta_e_ok"],
        ),
        "full_bank_1_5px_thin_proxy": (
            _raster_minimum(
                metrics["raster_category_pair"], width="1.5", state="nominal-transformed"
            ),
            _raster_minimum(
                baseline_metrics["raster_category_pair"], width="1.5", state="nominal-transformed"
            ),
            contract["materiality"]["full_bank_1_5px_thin_proxy_delta_e_ok"],
        ),
        "category_fg_0_distinctiveness": (
            min(
                metrics["commanded_category_fg_0"]["delta_e_ok"],
                metrics["nominal_transformed_category_fg_0"]["delta_e_ok"],
                _raster_minimum(
                    metrics["raster_category_fg_0"], width="1.5", state="nominal-transformed"
                ),
            ),
            min(
                baseline_metrics["commanded_category_fg_0"]["delta_e_ok"],
                baseline_metrics["nominal_transformed_category_fg_0"]["delta_e_ok"],
                _raster_minimum(
                    baseline_metrics["raster_category_fg_0"],
                    width="1.5",
                    state="nominal-transformed",
                ),
            ),
            contract["materiality"]["category_fg_0_distinctiveness_delta_e_ok"],
        ),
    }
    result: dict[str, Any] = {
        "policy": contract["materiality"]["policy"],
        "comparison_reference": contract["materiality"]["comparison_reference"],
    }
    for name, (candidate, baseline, target) in comparisons.items():
        improvement = float(candidate - baseline)
        result[name] = {
            "candidate": float(candidate),
            "baseline": float(baseline),
            "improvement": improvement,
            "target": float(target),
            "pass": improvement + 1e-12 >= float(target),
        }
    return result


def _materiality_passes(admission: Mapping[str, Any]) -> bool:
    return all(
        bool(admission[name]["pass"])
        for name in (
            "selected_weakest_three_dark_cluster_analog",
            "full_bank_1_5px_thin_proxy",
            "category_fg_0_distinctiveness",
        )
    )


def _candidate_objective(metrics: Mapping[str, Any]) -> tuple[float, ...]:
    """Return the approved worst-case ordering used after bank discovery."""

    pair_raster = metrics["raster_category_pair"]
    fg0_raster = metrics["raster_category_fg_0"]
    return (
        _raster_minimum(pair_raster, width="1.5", state="nominal-transformed"),
        _raster_minimum(fg0_raster, width="1.5", state="nominal-transformed"),
        float(metrics["nominal_transformed_j_prime_pair"]["delta_j_prime"]),
        float(metrics["nominal_transformed_solid_category_pair"]["delta_e_ok"]),
        float(metrics["commanded_category_pair"]["delta_e_ok"]),
        _raster_minimum(pair_raster, width="2", state="nominal-transformed"),
        _raster_minimum(pair_raster, width="3", state="nominal-transformed"),
        float(metrics["commanded_hue_topology"]["minimum_circular_gap_degrees"]),
        -float(metrics["commanded_hue_topology"]["maximum_to_minimum_gap_ratio"]),
        float(metrics["sensitivity_report"]["category_pair_min"]["category_pair_delta_e_ok"]),
    )


def run_optimizer(
    inputs: p3.Phase3Inputs, contract: Mapping[str, Any], *, reduced: bool = False
) -> dict[str, Any]:
    validate_contract(contract, inputs)
    catalog, catalog_summary = build_catalog(inputs, contract, reduced=reduced)
    # A coarser exact lattice is independent constructive support, not a lower-
    # quality mode. Dense beams can settle in a different local basin, so full
    # runs admit the stronger result from both supports.
    support_catalogs = [catalog]
    if not reduced:
        coarse_catalog, _ = build_catalog(inputs, contract, reduced=True)
        support_catalogs.append(coarse_catalog)
    baseline_metrics = compute_metrics(_baseline_bank(inputs), inputs, contract)
    candidates = []
    for lane_contract in contract["lanes"]:
        lane = lane_contract["id"]
        admitted = []
        for support_catalog in support_catalogs:
            discovered = _discover_bank(support_catalog, lane, inputs, contract)
            bank, permutation = _permute_roles(discovered, inputs)
            evaluation = evaluate_bank(bank, inputs, contract)
            materiality = _materiality_admission(
                bank, evaluation["metrics"], baseline_metrics, inputs, contract
            )
            if not evaluation["hard_gate_failures"] and _materiality_passes(materiality):
                admitted.append(
                    (
                        _candidate_objective(evaluation["metrics"]),
                        tuple(bank),
                        tuple(discovered),
                        permutation,
                        evaluation,
                        materiality,
                    )
                )
        if not admitted:
            raise RuntimeError(
                f"lane {lane} produced no candidate clearing every hard and materiality gate"
            )
        _, bank, discovered, permutation, evaluation, materiality = max(
            admitted, key=lambda row: (row[0], row[1])
        )
        candidates.append(
            {
                "candidate_id": p3.sha256_json(
                    {
                        "lane": lane,
                        "bank": list(bank),
                        "contract": p3.sha256_json(contract),
                    }
                ),
                "lane": lane,
                "lane_method": lane_contract["method"],
                "broad_anchor_count": lane_contract["broad_anchor_count"],
                "continuity_anchor_matches": _continuity_anchor_matches(discovered, lane_contract),
                "discovered_bank": list(discovered),
                "bank": list(bank),
                "bank_sha256": p3.bank_hash(bank),
                "bank_discovery_precedes_role_permutation": True,
                "role_permutation": permutation,
                "metrics": evaluation["metrics"],
                "hard_gate_failures": evaluation["hard_gate_failures"],
                "materiality_admission": materiality,
            }
        )
    return {
        "schema_version": 1,
        "input_chain_sha256": p3.input_chain_sha256(inputs),
        "search_contract_sha256": p3.sha256_json(contract),
        "catalog_summary": catalog_summary,
        "objective_policy": {
            "kind": "lexicographic-worst-case",
            "dimensions": list(contract["objective"]["lexicographic_worst_case"]),
        },
        "selection": None,
        "candidates": candidates,
    }


def _artifact_payloads(result: Mapping[str, Any]) -> dict[str, Any]:
    candidates = {
        "schema_version": result["schema_version"],
        "input_chain_sha256": result["input_chain_sha256"],
        "search_contract_sha256": result["search_contract_sha256"],
        "objective_policy": result["objective_policy"],
        "selection": result["selection"],
        "candidates": [
            {key: value for key, value in row.items() if key != "metrics"}
            for row in result["candidates"]
        ],
    }
    metrics = {
        "schema_version": 1,
        "candidate_ids": [row["candidate_id"] for row in result["candidates"]],
        "metrics_by_candidate": {
            row["candidate_id"]: row["metrics"] for row in result["candidates"]
        },
    }
    return {
        "catalog-summary.json": result["catalog_summary"],
        "candidates.json": candidates,
        "metrics.json": metrics,
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def build_artifacts(
    output_dir: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
    *,
    reduced: bool = False,
) -> dict[str, Path]:
    output = p3.validate_external_output_path(Path(output_dir), inputs)
    existing = {path.name for path in output.iterdir()} if output.exists() else set()
    unexpected = existing - {"catalog-summary.json", "candidates.json", "metrics.json"}
    if unexpected:
        raise ValueError(f"output directory contains unexpected files: {sorted(unexpected)}")
    result = run_optimizer(inputs, contract, reduced=reduced)
    payloads = _artifact_payloads(result)
    output.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, payload in payloads.items():
        path = output / name
        path.write_bytes(_json_bytes(payload))
        paths[name] = path
    return paths


def validate_artifacts(
    artifact_dir: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
    *,
    reduced: bool = False,
) -> None:
    directory = Path(artifact_dir).resolve()
    expected_names = {"catalog-summary.json", "candidates.json", "metrics.json"}
    if not directory.is_dir():
        raise ValueError("artifact directory does not exist")
    entries = list(directory.iterdir())
    if any(not path.is_file() for path in entries):
        raise ValueError("artifact directory contains a non-file entry")
    actual_names = {path.name for path in entries}
    if actual_names != expected_names:
        raise ValueError(f"artifact filenames differ: {sorted(actual_names ^ expected_names)}")
    actual = {}
    for name in sorted(expected_names):
        value = json.loads((directory / name).read_text())
        if not isinstance(value, dict):
            raise TypeError(f"{name} must contain an object")
        actual[name] = value
    expected = _artifact_payloads(run_optimizer(inputs, contract, reduced=reduced))
    for name in sorted(expected_names):
        if actual[name] != expected[name]:
            raise ValueError(f"artifact recomputation mismatch: {name}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_contract_parser = subparsers.add_parser("validate-contract")
    validate_contract_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument("--reduced", action="store_true")

    validate_parser = subparsers.add_parser("validate-artifacts")
    validate_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    validate_parser.add_argument("--artifact-dir", type=Path, required=True)
    validate_parser.add_argument("--reduced", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    inputs = p3.load_inputs(EXPERIMENT_DIR)
    contract = load_contract(args.contract)
    validate_contract(contract, inputs)
    if args.command == "validate-contract":
        return 0
    authorization_receipt(inputs, replay=True)
    if args.command == "build":
        build_artifacts(args.output_dir, inputs, contract, reduced=args.reduced)
        return 0
    if args.command == "validate-artifacts":
        validate_artifacts(args.artifact_dir, inputs, contract, reduced=args.reduced)
        return 0
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
