"""Fixed-fg0 symmetric seven-point categorical optimizer.

The searched object is an unordered set: the frozen ``fg_0`` plus six free
categorical colors.  Categories have no semantic slots and are serialized only
by exact commanded Oklab hue (then Hex8).  Every score is recomputed after the
canonical Hex8 boundary.  This experiment-only CLI writes solely to an
explicit directory outside the Git repository.
"""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
SEVEN_DIR = Path(__file__).resolve().parent
CLEAN_DIR = EXPERIMENT_DIR / "clean-sheet"
if str(EXPERIMENT_DIR) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_DIR))

import phase3_optimizer as p3

from ember.color import contrast_ratio, srgb_to_oklab


def _load_clean_module():
    spec = importlib.util.spec_from_file_location(
        "seven_point_clean_sheet_optimizer", CLEAN_DIR / "optimizer.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the validated clean-sheet optimizer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


clean = _load_clean_module()
CONTRACT_PATH = SEVEN_DIR / "search-contract.json"
EVIDENCE_PATH = EXPERIMENT_DIR / "review/g2-clean-sheet/evidence/candidates.json"
CATEGORY_COUNT = 6
POINT_COUNT = 7
PAIR_COUNT = 21
WIDTHS = (1.5, 2.0, 3.0)
BACKGROUND_NAMES = ("bg_0", "bg_1")
EXPECTED_TOP_KEYS = {
    "artifact_policy",
    "authorization",
    "benchmark",
    "exploration",
    "fixed",
    "hard_gates",
    "lanes",
    "materiality",
    "objective",
    "raster",
    "schema_version",
    "selection",
    "set",
}


@dataclass(frozen=True)
class SearchColor:
    """One exact catalog color with metrics derived from reparsed bytes."""

    hex8: str
    commanded_oklab: tuple[float, float, float]
    transformed_oklab: tuple[float, float, float]
    hue_degrees: float


def _exact_keys(value: object, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise ValueError(f"{label} keys differ: {sorted(actual ^ expected)}")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _range(value: object, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must be a two-value array")
    low, high = (_finite(item, label) for item in value)
    if not low < high:
        raise ValueError(f"{label} must be strictly increasing")
    return low, high


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise TypeError("seven-point search contract must be an object")
    return value


def load_inputs(*, replay: bool = False) -> p3.Phase3Inputs:
    return clean.load_authorized_inputs(EXPERIMENT_DIR, replay=replay)


def validate_contract(contract: Mapping[str, Any], inputs: p3.Phase3Inputs) -> None:
    """Validate the closed contract using explicit exceptions under normal and ``-O``."""

    _exact_keys(contract, EXPECTED_TOP_KEYS, "search contract")
    if contract["schema_version"] != 1 or contract["selection"] is not None:
        raise ValueError("schema version must be 1 and selection must be null")

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
        raise ValueError("authorization does not bind the approved input chain")

    fixed = _exact_keys(
        contract["fixed"], {"fg_0", "frozen_non_categorical_sha256", "policy"}, "fixed"
    )
    frozen = p3.frozen_non_categorical(inputs.baseline)
    expected_fg0 = inputs.baseline["family"]["surfaces"]["fg_0"]
    if fixed["fg_0"] != expected_fg0 or expected_fg0 != "#342F2C":
        raise ValueError("fg0 is not frozen to exact #342F2C")
    if fixed["frozen_non_categorical_sha256"] != p3.sha256_json(frozen):
        raise ValueError("frozen non-categorical hash differs from committed inputs")
    if "byte-for-byte frozen" not in str(fixed["policy"]):
        raise ValueError("fixed policy must freeze every non-categorical byte")

    set_contract = _exact_keys(
        contract["set"],
        {
            "category_count",
            "fixed_color_count",
            "role_permutation",
            "semantics",
            "serialization",
            "unordered",
        },
        "set",
    )
    if dict(set_contract) != {
        "category_count": 6,
        "fixed_color_count": 1,
        "role_permutation": False,
        "semantics": None,
        "serialization": "ascending exact commanded Oklab hue, tie canonical Hex8",
        "unordered": True,
    }:
        raise ValueError("seven-point set must be unordered, role-neutral, and fixed-fg0")

    exploration = _exact_keys(
        contract["exploration"],
        {"chroma", "exact_catalog", "hue_degrees", "lightness"},
        "exploration",
    )
    if (
        _range(exploration["lightness"], "exploration lightness") != (0.3, 0.64)
        or _range(exploration["chroma"], "exploration chroma") != (0.04, 0.14)
        or _range(exploration["hue_degrees"], "exploration hue") != (0.0, 360.0)
        or exploration["exact_catalog"] != "canonical Hex8 reparsed before every gate and metric"
    ):
        raise ValueError("exploration support or exact-Hex boundary differs")

    expected_gates = {
        "commanded_category_foreground_delta_e_ok": 8.0,
        "commanded_category_pair_delta_e_ok": 16.0,
        "commanded_minimum_hue_gap_degrees": 30.0,
        "graphics_contrast_ratio": 3.0,
        "nominal_transformed_category_foreground_delta_e_ok": 5.0,
        "nominal_transformed_category_pair_delta_e_ok": 8.0,
    }
    gates = _exact_keys(contract["hard_gates"], set(expected_gates), "hard gates")
    if dict(gates) != expected_gates:
        raise ValueError("hard gates differ from the approved seven-point gates")

    expected_lanes = [
        {"id": "A", "lightness": [0.34, 0.60], "method": "single-mid-band"},
        {"id": "B", "lightness": [0.42, 0.64], "method": "bright-band"},
        {
            "id": "C",
            "lower_count": 3,
            "lower_lightness": [0.3, 0.45],
            "method": "two-tier-lattice",
            "upper_count": 3,
            "upper_lightness": [0.48, 0.64],
        },
    ]
    if contract["lanes"] != expected_lanes:
        raise ValueError("lanes differ from the three approved structural lanes")

    objective = _exact_keys(
        contract["objective"],
        {
            "pair_count",
            "primary",
            "secondary_after_exact_primary_equality",
            "symmetric_lane_directions",
        },
        "objective",
    )
    if objective["pair_count"] != PAIR_COUNT or objective["symmetric_lane_directions"] is not True:
        raise ValueError("objective must cover 21 pairs and both lane directions")
    if objective["primary"] != (
        "raw minimum calibrated nominal-transformed 1.5px raster-proxy separation over "
        "the unordered fixed-fg0-plus-six-category set"
    ):
        raise ValueError("primary objective is not the one raw symmetric all-21 scalar")
    if objective["secondary_after_exact_primary_equality"] != [
        "transformed_2px_all_21_minimum",
        "transformed_3px_all_21_minimum",
        "nominal_transformed_solid_all_21_minimum",
        "commanded_solid_all_21_minimum",
        "gain_sensitivity_all_21_minimum",
    ]:
        raise ValueError("secondary exact-equality tie-break order differs")

    materiality = _exact_keys(
        contract["materiality"], {"minimum_proxy_improvement_delta_e_ok", "policy"}, "materiality"
    )
    if (
        _finite(materiality["minimum_proxy_improvement_delta_e_ok"], "materiality target") != 1.0
        or materiality["policy"] != "deterministic shortlist target; NOT human floor"
    ):
        raise ValueError("materiality target differs or is mislabeled as a human floor")

    benchmark = _exact_keys(
        contract["benchmark"],
        {"browser_worst_all_21_1_5px_delta_e_ok", "recompute_from", "source_lane"},
        "benchmark",
    )
    if dict(benchmark) != {
        "browser_worst_all_21_1_5px_delta_e_ok": 7.30273837,
        "recompute_from": "review/g2-clean-sheet/evidence/candidates.json",
        "source_lane": "C",
    }:
        raise ValueError("benchmark must reference exact committed clean-sheet Candidate C")

    raster = _exact_keys(
        contract["raster"],
        {
            "backgrounds",
            "calibrated_error_margin_delta_e_ok",
            "mask_count",
            "mask_file",
            "widths_css_px",
        },
        "raster",
    )
    if dict(raster) != {
        "backgrounds": ["bg_0", "bg_1"],
        "calibrated_error_margin_delta_e_ok": 0.75,
        "mask_count": 720,
        "mask_file": "raster-masks.json",
        "widths_css_px": [1.5, 2.0, 3.0],
    }:
        raise ValueError("raster harness differs from the exact current harness")
    artifacts = _exact_keys(
        contract["artifact_policy"],
        {"closed_filenames", "explicit_external_directory_only", "production"},
        "artifact policy",
    )
    if dict(artifacts) != {
        "closed_filenames": ["catalog-summary.json", "results.json"],
        "explicit_external_directory_only": True,
        "production": False,
    }:
        raise ValueError("artifact policy must be closed, external, and non-production")

    serialized = json.dumps(contract, sort_keys=True).lower()
    forbidden = ("role similarity", "baseline permutation", "churn", "lexicographic category")
    if any(term in serialized for term in forbidden):
        raise ValueError(
            "role semantics, baseline permutation, churn, or class ordering is forbidden"
        )


def _hue(lab: Sequence[float]) -> float:
    return float(np.degrees(np.arctan2(lab[2], lab[1])) % 360.0)


def _hue_delta(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def canonical_categories(values: Iterable[str]) -> tuple[str, ...]:
    """Return six distinct canonical Hex8 colors ordered only for review."""

    bank = p3.canonical_bank(values)
    if len(bank) != CATEGORY_COUNT:
        raise ValueError("exactly six categorical colors are required")
    rows = [(_hue(srgb_to_oklab(p3.parse_exact_hex8(hex8))), hex8) for hex8 in bank]
    return tuple(hex8 for _, hex8 in sorted(rows))


def candidate_family(categories: Iterable[str], inputs: p3.Phase3Inputs) -> dict[str, Any]:
    """Construct a review family and prove that only categorical bytes changed."""

    ordered = canonical_categories(categories)
    value = deepcopy(inputs.baseline)
    value["family"]["categorical"] = dict(zip(p3.ROLE_NAMES, ordered, strict=True))
    p3.assert_only_categorical_changed(inputs.baseline, value)
    return value


def benchmark_categories(inputs: p3.Phase3Inputs, contract: Mapping[str, Any]) -> tuple[str, ...]:
    """Load Candidate C from committed evidence; no benchmark colors live in source."""

    evidence = json.loads(EVIDENCE_PATH.read_text())
    _exact_keys(
        evidence,
        {
            "candidates",
            "input_chain_sha256",
            "objective_policy",
            "schema_version",
            "search_contract_sha256",
            "selection",
        },
        "clean-sheet candidate evidence",
    )
    if evidence["input_chain_sha256"] != p3.input_chain_sha256(inputs):
        raise ValueError("clean-sheet Candidate C evidence belongs to another input chain")
    rows = [
        row
        for row in evidence["candidates"]
        if row.get("lane") == contract["benchmark"]["source_lane"]
    ]
    if len(rows) != 1:
        raise ValueError("committed evidence does not contain exactly one Candidate C")
    bank = canonical_categories(rows[0]["bank"])
    if set(bank) != set(rows[0]["discovered_bank"]):
        raise ValueError("Candidate C evidence bank and discovered set disagree")
    return bank


def build_catalog(
    inputs: p3.Phase3Inputs, contract: Mapping[str, Any], *, smoke: bool = False
) -> tuple[list[SearchColor], dict[str, Any]]:
    """Reuse the validated broad clean-sheet exact-Hex catalog construction."""

    validate_contract(contract, inputs)
    clean_contract = clean.load_contract(CLEAN_DIR / "search-contract.json")
    clean.validate_contract(clean_contract, inputs)
    source, source_summary = clean.build_catalog(inputs, clean_contract, reduced=smoke)
    rows = [
        SearchColor(
            hex8=row.hex8,
            commanded_oklab=row.commanded_oklab,
            transformed_oklab=row.transformed_oklab,
            hue_degrees=_hue(row.commanded_oklab),
        )
        for row in source
    ]
    rows.sort(key=lambda row: row.hex8)
    summary = {
        "schema_version": 1,
        "mode": "smoke" if smoke else "full",
        "exact_hex8_count": len(rows),
        "source": "validated clean-sheet exact-Hex catalog",
        "source_support": source_summary["support"],
        "canonical_hex8_reparsed_before_metrics": True,
        "lane_eligible_counts": {
            lane["id"]: sum(_lane_color_eligible(row, lane) for row in rows)
            for lane in contract["lanes"]
        },
    }
    minimum = 250 if smoke else 1_000
    if len(rows) < minimum or source_summary["support"]["hue_bins_occupied"] < 12:
        raise RuntimeError("exact catalog is not materially broad")
    return rows, summary


def _lane_color_eligible(
    color: SearchColor, lane: Mapping[str, Any], tier: str | None = None
) -> bool:
    lightness = color.commanded_oklab[0]
    if lane["id"] in ("A", "B"):
        low, high = lane["lightness"]
    elif tier == "lower":
        low, high = lane["lower_lightness"]
    elif tier == "upper":
        low, high = lane["upper_lightness"]
    else:
        return (
            lane["lower_lightness"][0] <= lightness <= lane["lower_lightness"][1]
            or lane["upper_lightness"][0] <= lightness <= lane["upper_lightness"][1]
        )
    return bool(low <= lightness <= high)


def _pair_minimum(points: np.ndarray, labels: Sequence[str]) -> dict[str, Any]:
    rows = [
        (float(np.linalg.norm(points[left] - points[right]) * 100.0), labels[left], labels[right])
        for left, right in itertools.combinations(range(POINT_COUNT), 2)
    ]
    if len(rows) != PAIR_COUNT:
        raise RuntimeError("seven-point solid metric did not enumerate 21 pairs")
    value, left, right = min(rows)
    return {"delta_e_ok": value, "binding": f"{left} vs {right}", "pair_count": len(rows)}


def _raster_metric(
    categories: tuple[str, ...],
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
    width: float,
) -> dict[str, Any]:
    category_rgb = p3.bank_rgb(categories)
    surfaces = inputs.baseline["family"]["surfaces"]
    fg0 = p3.parse_exact_hex8(surfaces["fg_0"])
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    labels = ("fg_0", *(f"category-{index}" for index in range(CATEGORY_COUNT)))
    margin = float(contract["raster"]["calibrated_error_margin_delta_e_ok"])
    rows: list[tuple[float, str, str, str]] = []
    geometry_count = 0
    direction_count = 0
    category_coverage: set[int] = set()
    pair_coverage: set[tuple[int, int]] = set()
    for geometry, lanes in sorted(p3._mask_summaries(inputs).items()):
        actual_width, style, orientation, dpr, phase = geometry
        if actual_width != width:
            continue
        geometry_count += 1
        for background_name in BACKGROUND_NAMES:
            background = p3.parse_exact_hex8(surfaces[background_name])
            points_by_lane = []
            for lane in (0, 1):
                coverage = lanes[lane]
                rgb = np.vstack((fg0, category_rgb))
                composite = coverage * rgb + (1.0 - coverage) * background
                points_by_lane.append(srgb_to_oklab(np.clip(composite * gains, 0.0, 1.0)))
            context = (
                f"{background_name}/{style}/{orientation}/dpr-{dpr}/phase-{phase[0]:g}-{phase[1]:g}"
            )
            for left, right in itertools.combinations(range(POINT_COUNT), 2):
                pair_coverage.add((left, right))
                if left > 0:
                    category_coverage.add(left - 1)
                if right > 0:
                    category_coverage.add(right - 1)
                for left_lane, right_lane in ((0, 1), (1, 0)):
                    direction_count += 1
                    value = float(
                        np.linalg.norm(
                            points_by_lane[left_lane][left] - points_by_lane[right_lane][right]
                        )
                        * 100.0
                        - margin
                    )
                    rows.append(
                        (
                            value,
                            f"{labels[left]} vs {labels[right]}",
                            f"lane-{left_lane}-to-{right_lane}",
                            context,
                        )
                    )
    if (
        geometry_count != 120
        or len(pair_coverage) != PAIR_COUNT
        or category_coverage != set(range(6))
    ):
        raise RuntimeError("raster objective lacks a geometry, pair, or category")
    value, binding, direction, context = min(rows)
    return {
        "calibrated_delta_e_ok": value,
        "binding": binding,
        "direction": direction,
        "context": context,
        "width_css_px": width,
        "pair_count": len(pair_coverage),
        "category_indices": sorted(category_coverage),
        "lane_direction_evaluations": direction_count,
        "geometry_count": geometry_count,
        "backgrounds": list(BACKGROUND_NAMES),
    }


def compute_metrics(
    values: Iterable[str], inputs: p3.Phase3Inputs, contract: Mapping[str, Any]
) -> dict[str, Any]:
    categories = canonical_categories(values)
    category_rgb = p3.bank_rgb(categories)
    fg0 = p3.parse_exact_hex8(inputs.baseline["family"]["surfaces"]["fg_0"])
    all_rgb = np.vstack((fg0, category_rgb))
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    labels = ("fg_0", *(f"category-{index}" for index in range(CATEGORY_COUNT)))
    raster = {f"{width:g}": _raster_metric(categories, inputs, contract, width) for width in WIDTHS}
    sensitivity_rows = []
    for gain in p3._gain_samples(inputs, nominal_only=False):
        sample = np.asarray([gain["red_gain"], gain["green_gain"], gain["blue_gain"]])
        minimum = _pair_minimum(srgb_to_oklab(all_rgb * sample), labels)
        sensitivity_rows.append((minimum["delta_e_ok"], gain["id"], minimum["binding"]))
    sensitivity, gain_id, sensitivity_binding = min(sensitivity_rows)
    return {
        "primary_raw_symmetric_scalar": raster["1.5"]["calibrated_delta_e_ok"],
        "raster_all_21": raster,
        "nominal_transformed_solid_all_21": _pair_minimum(srgb_to_oklab(all_rgb * gains), labels),
        "commanded_solid_all_21": _pair_minimum(srgb_to_oklab(all_rgb), labels),
        "gain_sensitivity_all_21": {
            "delta_e_ok": sensitivity,
            "gain_sample": gain_id,
            "binding": sensitivity_binding,
            "pair_count": PAIR_COUNT,
        },
    }


def objective(metrics: Mapping[str, Any]) -> tuple[float, ...]:
    """One primary scalar followed only by exact-primary-equality tie-breaks."""

    return (
        float(metrics["primary_raw_symmetric_scalar"]),
        float(metrics["raster_all_21"]["2"]["calibrated_delta_e_ok"]),
        float(metrics["raster_all_21"]["3"]["calibrated_delta_e_ok"]),
        float(metrics["nominal_transformed_solid_all_21"]["delta_e_ok"]),
        float(metrics["commanded_solid_all_21"]["delta_e_ok"]),
        float(metrics["gain_sensitivity_all_21"]["delta_e_ok"]),
    )


def hard_gate_failures(
    values: Iterable[str], inputs: p3.Phase3Inputs, contract: Mapping[str, Any]
) -> list[dict[str, Any]]:
    categories = canonical_categories(values)
    rgb = p3.bank_rgb(categories)
    commanded = srgb_to_oklab(rgb)
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    transformed = srgb_to_oklab(rgb * gains)
    surfaces = inputs.baseline["family"]["surfaces"]
    foreground_rgb = np.asarray(
        [p3.parse_exact_hex8(surfaces[name]) for name in ("fg_0", "fg_1", "fg_2")]
    )
    commanded_fg = srgb_to_oklab(foreground_rgb)
    transformed_fg = srgb_to_oklab(foreground_rgb * gains)
    gates = contract["hard_gates"]
    failures: list[dict[str, Any]] = []

    def floor(name: str, actual: float, threshold: float) -> None:
        if actual + 1e-12 < threshold:
            failures.append({"gate": name, "actual": actual, "threshold": threshold})

    category_pairs = [
        float(np.linalg.norm(commanded[left] - commanded[right]) * 100.0)
        for left, right in itertools.combinations(range(6), 2)
    ]
    transformed_pairs = [
        float(np.linalg.norm(transformed[left] - transformed[right]) * 100.0)
        for left, right in itertools.combinations(range(6), 2)
    ]
    hues = sorted(_hue(row) for row in commanded)
    hue_gaps = [(hues[(index + 1) % 6] - hue) % 360.0 for index, hue in enumerate(hues)]
    floor(
        "commanded-category-pair", min(category_pairs), gates["commanded_category_pair_delta_e_ok"]
    )
    floor("commanded-category-hue-gap", min(hue_gaps), gates["commanded_minimum_hue_gap_degrees"])
    floor(
        "commanded-category-foreground-safety",
        float(np.min(np.linalg.norm(commanded[:, None] - commanded_fg[None, :], axis=2)) * 100.0),
        gates["commanded_category_foreground_delta_e_ok"],
    )
    floor(
        "transformed-category-noncollapse",
        min(transformed_pairs),
        gates["nominal_transformed_category_pair_delta_e_ok"],
    )
    floor(
        "transformed-category-foreground-safety",
        float(
            np.min(np.linalg.norm(transformed[:, None] - transformed_fg[None, :], axis=2)) * 100.0
        ),
        gates["nominal_transformed_category_foreground_delta_e_ok"],
    )
    for state, state_gains in (("commanded", np.ones(3)), ("nominal-transformed", gains)):
        for background_name in BACKGROUND_NAMES:
            background = p3.parse_exact_hex8(surfaces[background_name]) * state_gains
            actual = min(contrast_ratio(color * state_gains, background) for color in rgb)
            floor(
                f"graphics-contrast/{state}/{background_name}",
                actual,
                gates["graphics_contrast_ratio"],
            )
    return failures


def evaluate(
    values: Iterable[str], inputs: p3.Phase3Inputs, contract: Mapping[str, Any]
) -> dict[str, Any]:
    categories = canonical_categories(values)
    metrics = compute_metrics(categories, inputs, contract)
    return {
        "categories": list(categories),
        "metrics": metrics,
        "objective": list(objective(metrics)),
        "hard_gate_failures": hard_gate_failures(categories, inputs, contract),
    }


def _quick_pair_proxy(
    left: SearchColor,
    right: SearchColor,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
    width: float = 1.5,
) -> float:
    surfaces = inputs.baseline["family"]["surfaces"]
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    left_rgb = p3.parse_exact_hex8(left.hex8)
    right_rgb = p3.parse_exact_hex8(right.hex8)
    margin = float(contract["raster"]["calibrated_error_margin_delta_e_ok"])
    result = math.inf
    for geometry, lanes in p3._mask_summaries(inputs).items():
        if geometry[0] != width:
            continue
        for background_name in BACKGROUND_NAMES:
            background = p3.parse_exact_hex8(surfaces[background_name])
            for left_lane, right_lane in ((0, 1), (1, 0)):
                left_point = srgb_to_oklab(
                    (lanes[left_lane] * left_rgb + (1.0 - lanes[left_lane]) * background) * gains
                )
                right_point = srgb_to_oklab(
                    (lanes[right_lane] * right_rgb + (1.0 - lanes[right_lane]) * background) * gains
                )
                result = min(
                    result, float(np.linalg.norm(left_point - right_point) * 100.0 - margin)
                )
    return result


def _search_lane(
    catalog: Sequence[SearchColor],
    lane: Mapping[str, Any],
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
    benchmark_primary: float,
    *,
    smoke: bool,
) -> tuple[tuple[str, ...], dict[str, Any]] | None:
    """Deterministic hue-skeleton multistart beam with role-neutral set states."""

    fg0_rgb = p3.parse_exact_hex8(inputs.baseline["family"]["surfaces"]["fg_0"])
    fg0_lab = tuple(float(value) for value in srgb_to_oklab(fg0_rgb))
    fg0 = SearchColor("#342F2C", fg0_lab, fg0_lab, _hue(fg0_lab))
    target = benchmark_primary + float(
        contract["materiality"]["minimum_proxy_improvement_delta_e_ok"]
    )
    pool_limit = 45 if smoke else 110
    beam_limit = 80 if smoke else 220
    rotations = (0.0, 20.0, 40.0) if smoke else tuple(float(value) for value in range(0, 60, 5))
    pair_cache: dict[tuple[str, str], float] = {}
    fg_cache: dict[str, float] = {}

    def pair_score(left: SearchColor, right: SearchColor) -> float:
        key = tuple(sorted((left.hex8, right.hex8)))
        if key not in pair_cache:
            pair_cache[key] = _quick_pair_proxy(left, right, inputs, contract)
        return pair_cache[key]

    def fg_score(color: SearchColor) -> float:
        if color.hex8 not in fg_cache:
            fg_cache[color.hex8] = pair_score(fg0, color)
        return fg_cache[color.hex8]

    by_hex = {row.hex8: row for row in catalog}
    best: tuple[tuple[float, ...], tuple[str, ...], dict[str, Any]] | None = None
    completed_set_count = 0
    for rotation in rotations:
        targets = [((rotation + 60.0 * index) % 360.0) for index in range(6)]
        tiers: list[str | None] = [None] * 6
        if lane["id"] == "C":
            tiers = ["lower" if index % 2 == 0 else "upper" for index in range(6)]
        slot_pools: list[list[SearchColor]] = []
        exhausted = False
        for target_hue, tier in zip(targets, tiers, strict=True):
            eligible = [
                row
                for row in catalog
                if _lane_color_eligible(row, lane, tier)
                and _hue_delta(row.hue_degrees, target_hue) <= 27.5
                and fg_score(row) + 1e-12 >= target
            ]
            eligible.sort(
                key=lambda row: (
                    -fg_score(row),
                    _hue_delta(row.hue_degrees, target_hue),
                    -row.commanded_oklab[0],
                    row.hex8,
                )
            )
            if not eligible:
                exhausted = True
                break
            slot_pools.append(eligible[:pool_limit])
        if exhausted:
            continue

        beam: list[tuple[tuple[str, ...], float, float]] = [((), math.inf, 0.0)]
        for slot_pool in slot_pools:
            proposals: dict[tuple[str, ...], tuple[float, float]] = {}
            for selected, selected_min, selected_sum in beam:
                selected_rows = [by_hex[hex8] for hex8 in selected]
                for row in slot_pool:
                    if row.hex8 in selected:
                        continue
                    commanded_distances = [
                        float(
                            np.linalg.norm(
                                np.asarray(row.commanded_oklab) - np.asarray(other.commanded_oklab)
                            )
                            * 100.0
                        )
                        for other in selected_rows
                    ]
                    transformed_distances = [
                        float(
                            np.linalg.norm(
                                np.asarray(row.transformed_oklab)
                                - np.asarray(other.transformed_oklab)
                            )
                            * 100.0
                        )
                        for other in selected_rows
                    ]
                    if commanded_distances and (
                        min(commanded_distances) + 1e-12
                        < contract["hard_gates"]["commanded_category_pair_delta_e_ok"]
                        or min(transformed_distances) + 1e-12
                        < contract["hard_gates"]["nominal_transformed_category_pair_delta_e_ok"]
                        or min(
                            _hue_delta(row.hue_degrees, other.hue_degrees)
                            for other in selected_rows
                        )
                        + 1e-12
                        < contract["hard_gates"]["commanded_minimum_hue_gap_degrees"]
                    ):
                        continue
                    distances = [pair_score(row, other) for other in selected_rows]
                    next_min = min(selected_min, fg_score(row), *distances)
                    next_sum = selected_sum + fg_score(row) + sum(distances)
                    key = tuple(sorted((*selected, row.hex8)))
                    current = proposals.get(key)
                    if current is None or (next_min, next_sum) > current:
                        proposals[key] = (next_min, next_sum)
            ranked = sorted(
                ((score, total, selected) for selected, (score, total) in proposals.items()),
                key=lambda item: (item[0], item[1], item[2]),
                reverse=True,
            )
            beam = [(selected, score, total) for score, total, selected in ranked[:beam_limit]]
            if not beam:
                break
        for selected, _, _ in beam[: min(len(beam), 30)]:
            completed_set_count += 1
            evaluation = evaluate(selected, inputs, contract)
            if evaluation["hard_gate_failures"]:
                continue
            primary = evaluation["metrics"]["primary_raw_symmetric_scalar"]
            if primary + 1e-12 < target:
                continue
            candidate = (
                tuple(evaluation["objective"]),
                tuple(evaluation["categories"]),
                evaluation,
            )
            if best is None or candidate[:2] > best[:2]:
                best = candidate

    if best is None:
        return None
    _, categories, evaluation = best
    metadata = {
        "hue_skeleton_multistart": True,
        "farthest_point_beam": True,
        "exact_catalog_local_swaps": False,
        "rotation_count": len(rotations),
        "beam_width": beam_limit,
        "slot_pool_limit": pool_limit,
        "completed_set_count": completed_set_count,
        "pair_cache_count": len(pair_cache),
    }
    return categories, {"evaluation": evaluation, "search": metadata}


def _search_lane_clique(
    catalog: Sequence[SearchColor],
    lane: Mapping[str, Any],
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
    benchmark_primary: float,
    *,
    smoke: bool,
) -> tuple[tuple[str, ...], dict[str, Any]] | None:
    """Solve exact target feasibility as a deterministic six-clique problem."""

    del smoke
    target = benchmark_primary + float(
        contract["materiality"]["minimum_proxy_improvement_delta_e_ok"]
    )
    eligible = [row for row in catalog if _lane_color_eligible(row, lane)]
    rgb = np.asarray([p3.parse_exact_hex8(row.hex8) for row in eligible])
    commanded = np.asarray([row.commanded_oklab for row in eligible])
    transformed = np.asarray([row.transformed_oklab for row in eligible])
    hues = np.asarray([row.hue_degrees for row in eligible])
    surfaces = inputs.baseline["family"]["surfaces"]
    fg0 = p3.parse_exact_hex8(surfaces["fg_0"])
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    margin = float(contract["raster"]["calibrated_error_margin_delta_e_ok"])
    pair_proxy = np.full((len(eligible), len(eligible)), math.inf)
    fg_proxy = np.full(len(eligible), math.inf)
    for geometry, lanes in p3._mask_summaries(inputs).items():
        if geometry[0] != 1.5:
            continue
        for background_name in BACKGROUND_NAMES:
            background = p3.parse_exact_hex8(surfaces[background_name])
            points = [
                srgb_to_oklab((lanes[index] * rgb + (1.0 - lanes[index]) * background) * gains)
                for index in (0, 1)
            ]
            fg_points = [
                srgb_to_oklab((lanes[index] * fg0 + (1.0 - lanes[index]) * background) * gains)
                for index in (0, 1)
            ]
            for left_lane, right_lane in ((0, 1), (1, 0)):
                distances = np.sqrt(
                    np.sum(
                        (points[left_lane][:, None, :] - points[right_lane][None, :, :]) ** 2,
                        axis=2,
                    )
                )
                pair_proxy = np.minimum(pair_proxy, distances * 100.0 - margin)
                fg_proxy = np.minimum(
                    fg_proxy,
                    np.linalg.norm(points[left_lane] - fg_points[right_lane], axis=1) * 100.0
                    - margin,
                )

    vertices = np.flatnonzero(fg_proxy + 1e-12 >= target)
    if not len(vertices):
        return None
    pair_proxy = pair_proxy[np.ix_(vertices, vertices)]
    commanded = commanded[vertices]
    transformed = transformed[vertices]
    hues = hues[vertices]
    commanded_distance = (
        np.linalg.norm(commanded[:, None, :] - commanded[None, :, :], axis=2) * 100.0
    )
    transformed_distance = (
        np.linalg.norm(transformed[:, None, :] - transformed[None, :, :], axis=2) * 100.0
    )
    hue_distance = np.abs((hues[:, None] - hues[None, :] + 180.0) % 360.0 - 180.0)
    gates = contract["hard_gates"]
    graph = (
        (pair_proxy + 1e-12 >= target)
        & (commanded_distance + 1e-12 >= gates["commanded_category_pair_delta_e_ok"])
        & (transformed_distance + 1e-12 >= gates["nominal_transformed_category_pair_delta_e_ok"])
        & (hue_distance + 1e-12 >= gates["commanded_minimum_hue_gap_degrees"])
    )
    np.fill_diagonal(graph, False)
    adjacency: list[int] = []
    for index in range(len(vertices)):
        bits = 0
        for neighbor in np.flatnonzero(graph[index]):
            bits |= 1 << int(neighbor)
        adjacency.append(bits)
    lower = [
        eligible[int(vertices[index])].commanded_oklab[0] <= 0.45 for index in range(len(vertices))
    ]
    calls = 0

    def search(chosen: list[int], candidates: int) -> list[int] | None:
        nonlocal calls
        calls += 1
        if len(chosen) == 6:
            if lane["id"] != "C" or sum(lower[index] for index in chosen) == 3:
                return chosen
            return None
        needed = 6 - len(chosen)
        if candidates.bit_count() < needed:
            return None
        if lane["id"] == "C":
            chosen_lower = sum(lower[index] for index in chosen)
            available = [index for index in range(len(vertices)) if (candidates >> index) & 1]
            available_lower = sum(lower[index] for index in available)
            available_upper = len(available) - available_lower
            if (
                chosen_lower > 3
                or chosen_lower + available_lower < 3
                or len(chosen) - chosen_lower + available_upper < 3
            ):
                return None
        while candidates:
            options = [index for index in range(len(vertices)) if (candidates >> index) & 1]
            vertex = max(
                options,
                key=lambda index: ((adjacency[index] & candidates).bit_count(), -index),
            )
            remaining = candidates & ~(1 << vertex)
            result = search([*chosen, vertex], remaining & adjacency[vertex])
            if result is not None:
                return result
            candidates = remaining
            if candidates.bit_count() < needed:
                return None
        return None

    clique = search([], (1 << len(vertices)) - 1)
    if clique is None:
        return None
    categories = canonical_categories(eligible[int(vertices[index])].hex8 for index in clique)
    evaluation = evaluate(categories, inputs, contract)
    if evaluation["hard_gate_failures"] or evaluation["objective"][0] + 1e-12 < target:
        raise RuntimeError("clique admission disagrees with exact recomputation")
    return categories, {
        "evaluation": evaluation,
        "search": {
            "algorithm": "deterministic-bitset-target-clique",
            "target_delta_e_ok": target,
            "vertex_count": len(vertices),
            "edge_count": int(np.sum(graph) // 2),
            "backtracking_calls": calls,
            "exact_catalog_local_swaps": False,
        },
    }


def run_optimizer(
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
    *,
    smoke: bool = False,
    require_all_lanes: bool = True,
) -> dict[str, Any]:
    validate_contract(contract, inputs)
    catalog, catalog_summary = build_catalog(inputs, contract, smoke=smoke)
    benchmark_bank = benchmark_categories(inputs, contract)
    benchmark = evaluate(benchmark_bank, inputs, contract)
    benchmark_primary = benchmark["metrics"]["primary_raw_symmetric_scalar"]
    rows = []
    infeasible = []
    for lane in contract["lanes"]:
        found = _search_lane_clique(catalog, lane, inputs, contract, benchmark_primary, smoke=smoke)
        if found is None:
            infeasible.append(
                {
                    "lane": lane["id"],
                    "method": lane["method"],
                    "reason": "no exact set cleared hard gates and the +1.0 proxy target",
                }
            )
            continue
        categories, details = found
        evaluation = details["evaluation"]
        family = candidate_family(categories, inputs)
        rows.append(
            {
                "candidate_id": p3.sha256_json(
                    {
                        "categories": list(categories),
                        "contract": p3.sha256_json(contract),
                        "lane": lane["id"],
                    }
                ),
                "lane": lane["id"],
                "method": lane["method"],
                "categories": list(categories),
                "category_set_sha256": p3.bank_hash(categories),
                "serialization": contract["set"]["serialization"],
                "objective": evaluation["objective"],
                "metrics": evaluation["metrics"],
                "hard_gate_failures": evaluation["hard_gate_failures"],
                "proxy_improvement_delta_e_ok": (
                    evaluation["metrics"]["primary_raw_symmetric_scalar"] - benchmark_primary
                ),
                "materiality_pass": True,
                "search": details["search"],
                "frozen_non_categorical_sha256": p3.sha256_json(p3.frozen_non_categorical(family)),
            }
        )
    if require_all_lanes and infeasible:
        lanes = ", ".join(row["lane"] for row in infeasible)
        raise RuntimeError(f"infeasible seven-point structural lane(s): {lanes}")
    return {
        "schema_version": 1,
        "input_chain_sha256": p3.input_chain_sha256(inputs),
        "search_contract_sha256": p3.sha256_json(contract),
        "production": False,
        "human_capacity": None,
        "selection": None,
        "objective_policy": {
            "kind": "single-raw-symmetric-minimum",
            "primary": contract["objective"]["primary"],
            "secondary_only_after_exact_primary_equality": contract["objective"][
                "secondary_after_exact_primary_equality"
            ],
            "class_normalization": False,
            "role_semantics": False,
            "churn": False,
        },
        "benchmark": {
            "source": "exact clean-sheet Candidate C recomputed from committed evidence",
            "categories": list(benchmark_bank),
            "browser_worst_all_21_1_5px_delta_e_ok": contract["benchmark"][
                "browser_worst_all_21_1_5px_delta_e_ok"
            ],
            "proxy": benchmark,
        },
        "catalog_summary": catalog_summary,
        "candidates": rows,
        "infeasible_lanes": infeasible,
    }


def _payloads(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "catalog-summary.json": result["catalog_summary"],
        "results.json": {key: value for key, value in result.items() if key != "catalog_summary"},
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def build_artifacts(
    output_dir: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
    *,
    smoke: bool = False,
) -> dict[str, Path]:
    output = p3.validate_external_output_path(Path(output_dir), inputs)
    expected = set(contract["artifact_policy"]["closed_filenames"])
    if output.exists():
        existing = {path.name for path in output.iterdir()}
        if existing - expected:
            raise ValueError(
                f"output directory contains unexpected entries: {sorted(existing - expected)}"
            )
    result = run_optimizer(inputs, contract, smoke=smoke)
    payloads = _payloads(result)
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
    smoke: bool = False,
) -> None:
    directory = Path(artifact_dir).resolve()
    expected_names = set(contract["artifact_policy"]["closed_filenames"])
    if not directory.is_dir():
        raise ValueError("artifact directory does not exist")
    entries = list(directory.iterdir())
    if (
        any(not path.is_file() for path in entries)
        or {path.name for path in entries} != expected_names
    ):
        raise ValueError("artifact directory violates the closed filename schema")
    actual = {name: json.loads((directory / name).read_text()) for name in sorted(expected_names)}
    expected = _payloads(run_optimizer(inputs, contract, smoke=smoke))
    if actual != expected:
        raise ValueError("artifact recomputation mismatch")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    contract_parser = sub.add_parser("validate-contract")
    contract_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument("--smoke", action="store_true")
    validate_parser = sub.add_parser("validate-artifacts")
    validate_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    validate_parser.add_argument("--artifact-dir", type=Path, required=True)
    validate_parser.add_argument("--smoke", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    inputs = load_inputs(replay=False)
    contract = load_contract(args.contract)
    validate_contract(contract, inputs)
    if args.command == "validate-contract":
        return 0
    clean.authorization_receipt(inputs, replay=True)
    if args.command == "build":
        build_artifacts(args.output_dir, inputs, contract, smoke=args.smoke)
        return 0
    if args.command == "validate-artifacts":
        validate_artifacts(args.artifact_dir, inputs, contract, smoke=args.smoke)
        return 0
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
