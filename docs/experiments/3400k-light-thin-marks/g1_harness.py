#!/usr/bin/env python3
"""Deterministic Phase 2A core for 3400K Light thin-mark reconnaissance.

The module reads only the frozen G0 baseline. It builds analytical/planned
artifacts; browser observations and human visibility results remain pending.
"""

from __future__ import annotations

import html
import inspect
import itertools
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
GAINS = np.array([1.0, 0.74, 0.53], dtype=float)
CATEGORY_NAMES = ("one", "two", "three", "four", "five", "six")
BACKGROUND_NAMES = ("bg_0", "bg_1", "bg_2")
FOREGROUND_NAMES = ("fg_0", "fg_1", "fg_2")
STATE_ORDER = ("commanded", "transformed")
STYLE_ORDER = ("solid", "dashed", "dotted")
PRIMARY_Y_B = {"bg_0": 56.18, "bg_1": 49.82, "bg_2": 44.32}
SENSITIVITY_Y_B = {"bg_0": 94.77, "bg_1": 84.05, "bg_2": 74.76}

Metric = Callable[..., float]


def load_baseline() -> dict[str, Any]:
    return json.loads((HERE / "baseline.json").read_text(encoding="utf-8"))


def specimen_contract() -> dict[str, Any]:
    return {
        "state_order": list(STATE_ORDER),
        "background_order": list(BACKGROUND_NAMES),
        "category_order": list(CATEGORY_NAMES),
        "style_order": list(STYLE_ORDER),
        "backgrounds": {"gate": ["bg_0", "bg_1"], "report_only": ["bg_2"]},
        "widths_css_px": [1.5, 2.0, 3.0],
        "device_pixel_ratios": [1, 2],
        "orientations": [
            "horizontal",
            "vertical",
            "diagonal_45",
            "shallow_1_2",
            "curved",
        ],
        "phases_css_px": [[0.0, 0.0], [0.0, 0.5], [0.5, 0.0], [0.5, 0.5]],
        "styles": {
            "solid": {"dasharray": None, "linecap": "butt", "dashoffset": 0.0},
            "dashed": {"dasharray": [8.0, 5.0], "linecap": "butt", "dashoffset": 0.0},
            "dotted": {"dasharray": [1.0, 5.0], "linecap": "round", "dashoffset": 0.0},
        },
        "viewports_css_px": {"desktop": [1280, 900], "phone": [390, 844]},
        "features": [
            "isolated_lines",
            "same_style_crossings",
            "short_legends",
            "endpoint_markers",
            "sparklines",
            "financial_cockpit",
            "thesis_baskets",
        ],
        "line_core": {
            "minimum_coverage": 0.5,
            "aggregation": "per-channel median",
            "definition": (
                "For each uninterrupted stroke segment, exclude endpoints, joins, markers, "
                "crossings, and dash transitions; at each normal slice choose the max-coverage "
                "pixel nearest the mathematical centerline, retain coverage >= 0.5, then take "
                "the per-channel median across retained pixels."
            ),
        },
        "data_policy": "deterministic fake data; no consumer imports; no private data",
    }


def _hex_to_rgb(value: str) -> np.ndarray:
    value = value.removeprefix("#")
    return np.array([int(value[index : index + 2], 16) for index in (0, 2, 4)]) / 255.0


def _rgb_to_hex(value: np.ndarray) -> str:
    rgb8 = np.clip(np.rint(np.asarray(value) * 255.0), 0, 255).astype(int)
    return "#" + "".join(f"{channel:02X}" for channel in rgb8)


def _transform(value: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(value, dtype=float) * GAINS, 0.0, 1.0)


def _srgb_to_linear(value: np.ndarray) -> np.ndarray:
    value = np.asarray(value, dtype=float)
    return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)


def _oklab(value: np.ndarray) -> np.ndarray:
    matrix_1 = np.array(
        [
            [0.4122214708, 0.5363325363, 0.0514459929],
            [0.2119034982, 0.6806995451, 0.1073969566],
            [0.0883024619, 0.2817188376, 0.6299787005],
        ]
    )
    matrix_2 = np.array(
        [
            [0.2104542553, 0.7936177850, -0.0040720468],
            [1.9779984951, -2.4285922050, 0.4505937099],
            [0.0259040371, 0.7827717662, -0.8086757660],
        ]
    )
    return np.tensordot(
        np.cbrt(np.tensordot(_srgb_to_linear(value), matrix_1.T, axes=1)), matrix_2.T, axes=1
    )


def _delta_e_ok(left: np.ndarray, right: np.ndarray, **_: Any) -> float:
    return float(np.linalg.norm(_oklab(left) - _oklab(right)) * 100.0)


def _cam16_ucs(value: np.ndarray, context: dict[str, Any]) -> np.ndarray:
    try:
        import colour
    except ModuleNotFoundError as error:  # pragma: no cover - exercised by environment setup
        raise RuntimeError("G1 CAM16-UCS requires the project 'experiment' extra") from error

    xyz = np.asarray(colour.sRGB_to_XYZ(np.asarray(value, dtype=float)))
    white_xyz = np.asarray(colour.sRGB_to_XYZ(np.ones(3, dtype=float)))
    flare_xyz = context["flare_fraction_of_Yw"] * white_xyz
    surround = colour.VIEWING_CONDITIONS_CAM16[context["surround"]]
    return np.asarray(
        colour.XYZ_to_CAM16UCS(
            xyz + flare_xyz,
            XYZ_w=white_xyz,
            L_A=context["L_A_cd_m2"],
            Y_b=context["Y_b"],
            surround=surround,
        )
    )


def _cam16_distance(
    left: np.ndarray, right: np.ndarray, *, context: dict[str, Any], **_: Any
) -> float:
    return float(np.linalg.norm(_cam16_ucs(left, context) - _cam16_ucs(right, context)))


def _metric_call(
    metric: Metric,
    left: np.ndarray,
    right: np.ndarray,
    *,
    context: dict[str, Any],
    background: str,
    coverage: float,
) -> float:
    signature = inspect.signature(metric)
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    available = {"context": context, "background": background, "coverage": coverage}
    kwargs = {
        name: value
        for name, value in available.items()
        if accepts_kwargs or name in signature.parameters
    }
    return float(metric(left, right, **kwargs))


def _scenarios() -> list[dict[str, Any]]:
    rows = []
    for background in BACKGROUND_NAMES:
        rows.append(
            {
                "id": f"primary-dim-{background}",
                "family": "primary",
                "background": background,
                "surround": "Dim",
                "flare_fraction_of_Yw": 0.0,
                "L_A_cd_m2": 14.2,
                "Y_b": PRIMARY_Y_B[background],
            }
        )
    for adapting_luminance in (9.5, 19.0):
        for background in BACKGROUND_NAMES:
            rows.append(
                {
                    "id": f"sensitivity-average-la-{adapting_luminance:g}-{background}",
                    "family": "sensitivity",
                    "background": background,
                    "surround": "Average",
                    "flare_fraction_of_Yw": 0.0075,
                    "L_A_cd_m2": adapting_luminance,
                    "Y_b": SENSITIVITY_Y_B[background],
                }
            )
    return rows


def _pairs(names: tuple[str, ...] = CATEGORY_NAMES) -> list[tuple[str, str]]:
    return list(itertools.combinations(names, 2))


def _round_tree(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 8)
    if isinstance(value, dict):
        return {key: _round_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_tree(item) for item in value]
    return value


def compute_proxy_frontier(
    baseline: dict[str, Any] | None = None,
    *,
    transformed_metric: Metric | None = None,
) -> dict[str, Any]:
    """Compute an analytical solid/coverage reconnaissance with one owned metric.

    The injected callable owns every transformed solid and proxy distance. No row
    is browser evidence and no returned distance is a calibrated human floor.
    """

    baseline = baseline or load_baseline()
    metric = transformed_metric or _cam16_distance
    categories = {
        name: _hex_to_rgb(value) for name, value in baseline["family"]["categorical"].items()
    }
    surfaces = {
        name: _hex_to_rgb(baseline["family"]["surfaces"][name]) for name in BACKGROUND_NAMES
    }
    pair_names = _pairs()
    commanded_rows = [
        {
            "roles": [f"cat.{left}", f"cat.{right}"],
            "delta_e_ok": _delta_e_ok(categories[left], categories[right]),
        }
        for left, right in pair_names
    ]

    solid_rows = []
    proxy_rows = []
    for scenario in _scenarios():
        background_name = scenario["background"]
        transformed_background = _transform(surfaces[background_name])
        for left_name, right_name in pair_names:
            left = _transform(categories[left_name])
            right = _transform(categories[right_name])
            solid_rows.append(
                {
                    "scenario": scenario["id"],
                    "scenario_family": scenario["family"],
                    "background": background_name,
                    "roles": [f"cat.{left_name}", f"cat.{right_name}"],
                    "distance": _metric_call(
                        metric,
                        left,
                        right,
                        context=scenario,
                        background=background_name,
                        coverage=1.0,
                    ),
                }
            )
            for coverage in (0.5, 0.75, 1.0):
                composite_left = coverage * left + (1.0 - coverage) * transformed_background
                composite_right = coverage * right + (1.0 - coverage) * transformed_background
                proxy_rows.append(
                    {
                        "scenario": scenario["id"],
                        "scenario_family": scenario["family"],
                        "background": background_name,
                        "coverage": coverage,
                        "roles": [f"cat.{left_name}", f"cat.{right_name}"],
                        "distance": _metric_call(
                            metric,
                            composite_left,
                            composite_right,
                            context=scenario,
                            background=background_name,
                            coverage=coverage,
                        ),
                    }
                )

    minimum = min(solid_rows, key=lambda row: (row["distance"], row["scenario"], row["roles"]))
    scenario_minima = []
    for scenario in _scenarios():
        candidates = [row for row in solid_rows if row["scenario"] == scenario["id"]]
        scenario_minima.append(min(candidates, key=lambda row: (row["distance"], row["roles"])))
    commanded_rows.sort(key=lambda row: (row["delta_e_ok"], row["roles"]))
    proxy_rows.sort(key=lambda row: (row["scenario"], row["coverage"], row["roles"]))
    return _round_tree(
        {
            "commanded_solid_oklab": {
                "domain": "encoded commanded sRGB converted to Oklab",
                "minimum_pair": commanded_rows[0],
                "pairs": commanded_rows,
            },
            "transformed_metric": {
                "backend": (
                    "CAM16-UCS engineering model"
                    if transformed_metric is None
                    else "injected callable"
                ),
                "ownership": (
                    "the same callable owns every transformed solid and composited-proxy distance"
                ),
                "callable_name": getattr(metric, "__name__", type(metric).__name__),
                "solid_minimum_pair": minimum,
                "scenario_minima": scenario_minima,
                "scenario_policy": "report separately; never average",
            },
            "proxy_model": {
                "operation_order": "encoded-sRGB composite, then channel-gain transform",
                "coverages": [0.5, 0.75, 1.0],
                "status": "analytical engineering proxy; browser calibration pending",
                "human_floor": None,
            },
            "proxy_matrix": proxy_rows,
        }
    )


def proxy_acceptance(comparison: dict[str, float]) -> str:
    return (
        "PASS"
        if comparison["correlation"] >= 0.95 and comparison["pair_background_mae_max"] <= 0.75
        else "FAIL"
    )


def _viewing_conditions() -> dict[str, Any]:
    return {
        "claim_scope": "engineering appearance-model assumptions; not device calibration",
        "signal_domain": {
            "input": "encoded sRGB in [0, 1]",
            "compositing": "coverage-weighted encoded sRGB",
            "transform": "diagonal gain multiplication in encoded sRGB, clipped to [0, 1]",
            "colour_science_XYZ_domain": "0 to 1 (reference scale)",
            "CAM16_UCS_units": "colour-science CAM16-UCS Euclidean distance",
        },
        "display_white": {"chromaticity": "D65", "Y_w_cd_m2": 100.0},
        "transform": {
            "gains": [1.0, 0.74, 0.53],
            "operation_order": "transform after rasterization/compositing",
        },
        "flare_implementation": {
            "formula": "XYZ_stimulus_for_CAM16 = sRGB_to_XYZ(transformed_rgb) + flare_fraction_of_Yw * XYZ_D65_white",
            "white_point": "XYZ_D65_white remains normalized to Y=1.0",
            "scope": "additive neutral engineering sensitivity term; not measured veiling glare",
        },
        "primary": {
            "surround": "Dim",
            "flare_fraction_of_Yw": 0.0,
            "L_A_cd_m2": 14.2,
            "Y_b": PRIMARY_Y_B,
        },
        "sensitivity": {
            "surround": "Average",
            "flare_fraction_of_Yw": 0.0075,
            "L_A_cd_m2": [9.5, 19.0],
            "transformed_white_adapted_Y_b": SENSITIVITY_Y_B,
        },
        "scenario_policy": "report separately; never average",
        "browser_pixels": "release oracle; no G1 browser observations committed in Phase 2A",
    }


def _raster_baseline(baseline: dict[str, Any]) -> dict[str, Any]:
    contract = specimen_contract()
    rows = []
    for case_number, (state, background, width, style, orientation, dpr, phase, pair) in enumerate(
        itertools.product(
            contract["state_order"],
            contract["background_order"],
            contract["widths_css_px"],
            contract["style_order"],
            contract["orientations"],
            contract["device_pixel_ratios"],
            contract["phases_css_px"],
            _pairs(tuple(contract["category_order"])),
        ),
        start=1,
    ):
        rows.append(
            {
                "id": f"planned-{case_number:05d}",
                "state": state,
                "background": background,
                "background_policy": "gate" if background in ("bg_0", "bg_1") else "report-only",
                "width_css_px": width,
                "style": style,
                "orientation": orientation,
                "dpr": dpr,
                "phase_css_px": phase,
                "roles": [f"cat.{pair[0]}", f"cat.{pair[1]}"],
                "status": "PENDING_BROWSER_CALIBRATION",
                "observed_line_core_rgb8": None,
                "observed_distance": None,
            }
        )
    return {
        "baseline_source_commit": baseline["baseline_source_commit"],
        "source_bank": "CURRENT frozen 3400K Light categorical",
        "browser_release_oracle": True,
        "matrix_kind": "complete deterministic planned-case matrix; not observed measurements",
        "matrix_status": "PENDING_BROWSER_CALIBRATION",
        "planned_case_count": len(rows),
        "specimen_contract": contract,
        "matrix": rows,
        "width_capacity": {
            f"{width:.1f}": {
                "human_capacity_status": "UNKNOWN/UNPROVEN",
                "capacity": None,
                "pass_fail": None,
            }
            for width in contract["widths_css_px"]
        },
        "bounded_single_bank_reconnaissance": {
            "bank": "CURRENT frozen 3400K Light categorical only",
            "candidate_optimization_performed": False,
            "categorical_line_created": False,
            "candidate_colors": None,
        },
        "analytical_proxy_frontier": compute_proxy_frontier(baseline),
    }


def _neutral_confusability(baseline: dict[str, Any]) -> dict[str, Any]:
    family = baseline["family"]
    categories = {
        f"cat.{name}": _hex_to_rgb(value) for name, value in family["categorical"].items()
    }
    comparisons: list[tuple[str, str, str, np.ndarray]] = []
    for name in FOREGROUND_NAMES:
        comparisons.append(
            ("foreground", name, family["surfaces"][name], _hex_to_rgb(family["surfaces"][name]))
        )
    comparisons.append(
        (
            "benchmark_reference",
            "benchmark.reference.neutral",
            family["surfaces"]["fg_2"],
            _hex_to_rgb(family["surfaces"]["fg_2"]),
        )
    )
    for name in ("red", "green", "yellow", "blue", "magenta", "cyan"):
        comparisons.append(
            (
                "terminal_report_only",
                f"terminal.{name}",
                family["terminal"][name],
                _hex_to_rgb(family["terminal"][name]),
            )
        )

    rows = []
    for category_name, category in categories.items():
        for comparison_family, reference_name, reference_hex, reference in comparisons:
            rows.append(
                {
                    "category": category_name,
                    "comparison_family": comparison_family,
                    "reference": reference_name,
                    "reference_hex": reference_hex,
                    "state": "commanded",
                    "scenario": "commanded-solid-oklab",
                    "background": None,
                    "metric": "Oklab Euclidean x 100",
                    "analytical_distance": _delta_e_ok(category, reference),
                    "human_floor": None,
                }
            )
            for scenario in _scenarios():
                rows.append(
                    {
                        "category": category_name,
                        "comparison_family": comparison_family,
                        "reference": reference_name,
                        "reference_hex": reference_hex,
                        "state": "transformed",
                        "scenario": scenario["id"],
                        "scenario_family": scenario["family"],
                        "background": scenario["background"],
                        "metric": "CAM16-UCS engineering assumption",
                        "analytical_distance": _cam16_distance(
                            _transform(category), _transform(reference), context=scenario
                        ),
                        "human_floor": None,
                    }
                )
    return _round_tree(
        {
            "baseline_source_commit": baseline["baseline_source_commit"],
            "matrix_kind": "complete analytical solid-color reconnaissance; not browser pixels",
            "benchmark_reference": {
                "role": "benchmark.reference.neutral",
                "source": "frozen fg_2 alias; no new candidate color",
                "hex": family["surfaces"]["fg_2"],
            },
            "terminal_policy": "report-only defense-in-depth",
            "scenario_policy": "report separately; never average",
            "final_human_floor": None,
            "matrix": rows,
        }
    )


def _gain_grid() -> dict[str, Any]:
    green_offsets = (-0.05, -0.025, 0.0, 0.025, 0.05)
    blue_offsets = (-0.05, -0.0375, -0.025, -0.0125, 0.0, 0.0125, 0.025, 0.0375, 0.05)
    samples = []
    for green_offset, blue_offset in itertools.product(green_offsets, blue_offsets):
        samples.append(
            {
                "name": f"g{green_offset:+.4f}_b{blue_offset:+.4f}",
                "red_gain": 1.0,
                "green_gain": round(0.74 * (1.0 + green_offset), 8),
                "blue_gain": round(0.53 * (1.0 + blue_offset), 8),
                "green_relative_offset": green_offset,
                "blue_relative_offset": blue_offset,
                "status": "PLANNED_ANALYTICAL_SAMPLE",
            }
        )
    return {
        "claim": "sampled grid and local refinement; not a continuous worst case",
        "grid": {
            "red_axis": {"fixed": 1.0},
            "green_axis": {"center": 0.74, "relative_offsets": list(green_offsets)},
            "blue_axis": {"center": 0.53, "relative_offsets": list(blue_offsets)},
            "sample_count": len(samples),
            "samples": samples,
        },
        "local_refinement_protocol": {
            "status": "specified-not-run",
            "trigger": "after the sampled-grid minimum is identified for a named pair/scenario",
            "bounds": "stay inside the adjacent green/blue grid cell",
            "design": "deterministic 5 x 5 subgrid including cell boundaries",
            "ownership": "same transformed CAM16-UCS engineering metric and named scenario",
            "continuous_worst_case_claim": False,
        },
        "brightness_uncertainty": {
            "separate_from_channel_gain_grid": True,
            "Y_w_cd_m2_samples": [80.0, 100.0, 120.0],
            "status": "planned sensitivity; never pooled with channel-gain samples",
        },
    }


def _visibility_protocol() -> dict[str, Any]:
    pairs = [[f"cat.{left}", f"cat.{right}"] for left, right in _pairs()]
    base_cell_count = len(pairs) * 2 * 2 * 3
    repeats_per_base_cell = 2
    noncatch_trials = base_cell_count * repeats_per_base_cell
    catch_trials = 40
    return {
        "study": "preregistered line-to-legend 2AFC",
        "design": "balanced incomplete fractional-block design",
        "pair_count": len(pairs),
        "pairs": pairs,
        "results": None,
        "final_visibility_threshold": None,
        "final_width_capacity": None,
        "human_status": "not run",
        "states": ["commanded", "transformed"],
        "backgrounds": ["bg_0", "bg_1"],
        "base_cells": {
            "dimensions": ["pair", "state", "background", "width_css_px"],
            "count_per_observer": base_cell_count,
            "coverage": "every observer completes every base cell",
            "widths_css_px": [1.5, 2.0, 3.0],
            "repeats_per_observer": repeats_per_base_cell,
            "noncatch_trials_per_observer": noncatch_trials,
        },
        "fractional_factors": {
            "styles": ["solid", "dashed", "dotted"],
            "orientations": [
                "horizontal",
                "vertical",
                "diagonal_45",
                "shallow_1_2",
                "curved",
            ],
            "not_full_factorial_per_observer": True,
            "base_cell_order": (
                "canonical Cartesian order: pair, then state, background, and width_css_px"
            ),
            "assignment_formula": {
                "observer_index": "zero-based integer",
                "repeat_index": "zero or one",
                "base_cell_index": "zero-based canonical base-cell ordinal",
                "style_index": "(observer_index + repeat_index + base_cell_index) mod 3",
                "orientation_index": (
                    "(observer_index + 2 * repeat_index + base_cell_index) mod 5"
                ),
                "correct_answer_side": (
                    "left when (observer_index + repeat_index + base_cell_index) mod 2 = 0; "
                    "right otherwise"
                ),
            },
            "balance_at_15_observers": (
                "for each base cell and repeat, the 15 observers cover every one of the "
                "3 style x 5 orientation combinations exactly once; repeat two covers each "
                "combination once again, and answer side swaps across repeats"
            ),
        },
        "task": (
            "A target line segment is shown in a chart and two labeled legend samples are "
            "offered; choose which legend identity matches the target."
        ),
        "catch_trials": {
            "count_per_observer": catch_trials,
            "fraction_of_total": catch_trials / (noncatch_trials + catch_trials),
            "design": "large commanded solid separations at 3 CSS px",
            "placement": "10 deterministic catches in each 100-trial block",
            "exclusion_rule": "preregister before data collection",
        },
        "session_plan": {
            "blocks_per_observer": 4,
            "trials_per_block_including_catches": 100,
            "rest_between_blocks_minutes": 3,
            "target_total_duration_minutes_max": 55,
            "timing_basis": (
                "400 total trials budgeted at no more than 5 seconds average each, plus "
                "adaptation and three required rests"
            ),
        },
        "adaptation": {
            "warm_state_minutes": 5,
            "neutral_reset_minutes": 2,
            "order": "counterbalanced across observers",
        },
        "screening": [
            "normal or corrected-to-normal acuity self-report",
            "Ishihara-style colour-vision screen",
            "viewing-distance and ambient-light compliance",
        ],
        "observers": {
            "minimum": 15,
            "multiple_observers_required": True,
            "balance_basis": "least common multiple of 3 styles and 5 orientations",
            "analyze_individual_and_group": True,
        },
        "aggregate_coverage_at_minimum": {
            "observers": 15,
            "noncatch_trials": noncatch_trials * 15,
            "observations_per_base_cell": repeats_per_base_cell * 15,
            "observations_per_style_orientation_per_base_cell": repeats_per_base_cell,
        },
        "power_analysis_before_run": {
            "required": True,
            "timing": "after protocol lock and before recruitment or response collection",
            "method": (
                "simulation-based power and interval-width analysis for the preregistered "
                "hierarchical 2AFC model using design-only effect-size scenarios"
            ),
            "decision_rule": (
                "increase observer count in multiples of 15 if the target power or precision "
                "is not met; never reduce below 15"
            ),
            "observed_results_used": False,
        },
        "floor_calibration": {
            "held_out": True,
            "allocation": "sealed before the run and excluded from proxy/model tuning",
            "method": "fit threshold only on held-out trial responses after protocol lock",
            "no_proxy_tuning_on_held_out": True,
        },
        "capacity_rule": (
            "No width receives PASS/FAIL or a capacity until observer-level uncertainty, catch "
            "criteria, and held-out floor calibration are complete."
        ),
    }


def _proxy_calibration_pending(baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "PENDING_BROWSER_CALIBRATION",
        "baseline_source_commit": baseline["baseline_source_commit"],
        "full_image_hash_used": False,
        "evidence_kind": "schema and acceptance API only; no browser observations",
        "acceptance": {
            "minimum_global_pooled_correlation": 0.95,
            "maximum_pair_background_mae": 0.75,
            "observed_global_pooled_correlation": None,
            "observed_pair_background_mae_max": None,
            "status": "NOT_EVALUATED",
        },
        "provenance": {
            "browser": None,
            "chromium_version": None,
            "chromium_version_status": "pending-browser-calibration",
            "probe_sha256": None,
            "validator_sha256": None,
        },
        "samples": [],
        "coordinates": None,
        "reason": "Phase 2B must collect real line-core pixels from the deterministic probe.",
    }


def _path_for_orientation(orientation: str, x: float, y: float) -> str:
    if orientation == "horizontal":
        return f"M{x:g},{y + 24:g} L{x + 116:g},{y + 24:g}"
    if orientation == "vertical":
        return f"M{x + 58:g},{y:g} L{x + 58:g},{y + 48:g}"
    if orientation == "diagonal_45":
        return f"M{x:g},{y + 48:g} L{x + 48:g},{y:g}"
    if orientation == "shallow_1_2":
        return f"M{x:g},{y + 40:g} L{x + 116:g},{y + 8:g}"
    return f"M{x:g},{y + 38:g} C{x + 30:g},{y:g} {x + 78:g},{y + 52:g} {x + 116:g},{y + 10:g}"


def _fake_series() -> list[list[float]]:
    return [
        [
            50 + category * 3 + point * 1.4 + 5 * math.sin((point + category) * 0.7)
            for point in range(9)
        ]
        for category in range(6)
    ]


def _polyline(values: list[float], x: float, y: float, width: float, height: float) -> str:
    low, high = min(values), max(values)
    span = high - low or 1.0
    points = [
        (
            x + index * width / (len(values) - 1),
            y + height - (value - low) * height / span,
        )
        for index, value in enumerate(values)
    ]
    return "M" + " L".join(f"{px:.2f},{py:.2f}" for px, py in points)


def _shown_palettes(state: str, baseline: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    family = baseline["family"]

    def shown(value: str) -> str:
        rgb = _hex_to_rgb(value)
        return _rgb_to_hex(_transform(rgb) if state == "transformed" else rgb)

    surfaces = {name: shown(value) for name, value in family["surfaces"].items()}
    categories = {
        name: shown(family["categorical"][name]) for name in specimen_contract()["category_order"]
    }
    return surfaces, categories


def _feature_evidence(
    *,
    background_name: str,
    x: float,
    y: float,
    surfaces: dict[str, str],
    categories: dict[str, str],
    compact: bool,
) -> list[str]:
    fg_0, fg_2, rule = surfaces["fg_0"], surfaces["fg_2"], surfaces["bg_4"]
    names = specimen_contract()["category_order"]
    lines = [
        f'<g data-background="{background_name}" data-layout="{"phone" if compact else "desktop"}">'
    ]

    legend_y = y + (36 if compact else 50)
    lines.append(
        f'<g data-feature="short-category-legends"><text x="{x}" y="{legend_y - 9}" fill="{fg_0}" font-family="ui-monospace,monospace" font-size="10">short category legend</text>'
    )
    columns = 3 if compact else 6
    column_width = 112 if compact else 86
    for index, name in enumerate(names):
        column, row = index % columns, index // columns
        sample_x = x + column * column_width
        sample_y = legend_y + row * 22
        lines.append(
            f'<line data-feature="short-category-legend" data-role="cat.{name}" x1="{sample_x}" y1="{sample_y}" x2="{sample_x + 26}" y2="{sample_y}" stroke="{categories[name]}" stroke-width="2"/>'
        )
        lines.append(
            f'<text x="{sample_x + 32}" y="{sample_y + 4}" fill="{fg_2}" font-family="ui-monospace,monospace" font-size="9">{name}</text>'
        )
    lines.append("</g>")

    crossing_x = x
    crossing_y = y + (104 if compact else 105)
    lines.append(
        f'<g data-feature="same-style-color-only-crossing" data-style="solid" data-geometry="g1-crossing-geometry" transform="translate({crossing_x} {crossing_y})">'
    )
    for name, transform in (("five", ""), ("six", ' transform="translate(0 30) scale(1 -1)"')):
        lines.append(
            f'<use href="#g1-crossing-geometry" data-role="cat.{name}" fill="none" stroke="{categories[name]}" stroke-width="2" stroke-linecap="butt" stroke-dashoffset="0"{transform}/>'
        )
    lines.append("</g>")
    lines.append(
        f'<text x="{crossing_x}" y="{crossing_y + 45}" fill="{fg_2}" font-family="ui-monospace,monospace" font-size="9">equal geometry + solid style; colour only</text>'
    )

    marker_x = x + (184 if compact else 232)
    marker_y = crossing_y + 14
    lines.append('<g data-feature="endpoint-markers" data-style="solid">')
    lines.append(
        f'<line x1="{marker_x}" y1="{marker_y}" x2="{marker_x + 76}" y2="{marker_y}" stroke="{categories["one"]}" stroke-width="2"/>'
    )
    for endpoint_x in (marker_x, marker_x + 76):
        lines.append(
            f'<circle data-feature="endpoint-marker" data-role="cat.one" cx="{endpoint_x}" cy="{marker_y}" r="4" fill="{surfaces[background_name]}" stroke="{categories["one"]}" stroke-width="2"/>'
        )
    lines.append("</g>")

    spark_y = y + (169 if compact else 180)
    spark_width = 150 if compact else 250
    lines.append(
        f'<g data-feature="sparklines"><text x="{x}" y="{spark_y - 8}" fill="{fg_0}" font-family="ui-monospace,monospace" font-size="10">sparklines · fake deterministic data</text>'
    )
    for index, name in enumerate(("one", "three", "six")):
        lines.append(
            f'<path data-feature="sparkline" data-role="cat.{name}" d="{_polyline(_fake_series()[index * 2], x, spark_y + index * 19, spark_width, 13)}" fill="none" stroke="{categories[name]}" stroke-width="1.5"/>'
        )
    lines.append("</g>")

    composition_y = y + (232 if compact else 245)
    cockpit_x = x
    cockpit_width = 164 if compact else 270
    cockpit_height = 106 if compact else 92
    lines.append(
        f'<g data-feature="financial-cockpit" data-data-policy="fake-deterministic"><rect x="{cockpit_x}" y="{composition_y}" width="{cockpit_width}" height="{cockpit_height}" rx="5" fill="none" stroke="{rule}"/><text x="{cockpit_x + 9}" y="{composition_y + 17}" fill="{fg_0}" font-family="ui-monospace,monospace" font-size="10">fake Financial Cockpit</text>'
    )
    for index, name in enumerate(("one", "two", "four")):
        lines.append(
            f'<path data-role="cat.{name}" d="{_polyline(_fake_series()[index], cockpit_x + 9, composition_y + 27 + index * 20, cockpit_width - 18, 13)}" fill="none" stroke="{categories[name]}" stroke-width="1.5"/>'
        )
    lines.append("</g>")

    baskets_x = x + (174 if compact else 286)
    baskets_width = 166 if compact else 276
    lines.append(
        f'<g data-feature="thesis-baskets" data-data-policy="fake-deterministic"><rect x="{baskets_x}" y="{composition_y}" width="{baskets_width}" height="{cockpit_height}" rx="5" fill="none" stroke="{rule}"/><text x="{baskets_x + 9}" y="{composition_y + 17}" fill="{fg_0}" font-family="ui-monospace,monospace" font-size="10">fake Thesis Baskets</text>'
    )
    for index, name in enumerate(("three", "five", "six")):
        row_y = composition_y + 33 + index * 22
        lines.append(
            f'<line data-role="cat.{name}" x1="{baskets_x + 10}" y1="{row_y}" x2="{baskets_x + 38}" y2="{row_y}" stroke="{categories[name]}" stroke-width="2"/>'
        )
        lines.append(
            f'<rect x="{baskets_x + 48}" y="{row_y - 4}" width="{(index + 1) * (24 if compact else 42)}" height="8" fill="{categories[name]}" opacity="0.82"/>'
        )
    lines.extend(["</g>", "</g>"])
    return lines


def _svg(state: str, baseline: dict[str, Any]) -> str:
    surfaces, categories = _shown_palettes(state, baseline)
    title = "transformed gain [1, .74, .53]" if state == "transformed" else "commanded sRGB"
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="900" viewBox="0 0 1280 900">',
        '<defs><path id="g1-crossing-geometry" d="M0,30 L44,0 L88,30"/></defs>',
        f'<rect width="1280" height="900" fill="{surfaces["bg_0"]}"/>',
        f'<text x="32" y="38" fill="{surfaces["fg_0"]}" font-family="ui-monospace,monospace" font-size="22" font-weight="700">G1 current-bank evidence · {html.escape(title)}</text>',
        f'<text x="32" y="62" fill="{surfaces["fg_1"]}" font-family="ui-monospace,monospace" font-size="13">real tagged specimens · fake deterministic compositions · browser and human calibration pending</text>',
    ]
    for background_index, background_name in enumerate(("bg_0", "bg_1")):
        y0 = 82 + background_index * 390
        lines.extend(
            [
                f'<rect x="24" y="{y0}" width="1232" height="370" rx="10" fill="{surfaces[background_name]}" stroke="{surfaces["bg_4"]}"/>',
                f'<text x="42" y="{y0 + 25}" fill="{surfaces["fg_0"]}" font-family="ui-monospace,monospace" font-size="14" font-weight="700">{background_name} · gate surface</text>',
            ]
        )
        lines.extend(
            _feature_evidence(
                background_name=background_name,
                x=42,
                y=y0 + 5,
                surfaces=surfaces,
                categories=categories,
                compact=False,
            )
        )
        lines.append(
            f'<g data-feature="isolated-lines" data-background="{background_name}"><text x="650" y="{y0 + 49}" fill="{surfaces["fg_0"]}" font-family="ui-monospace,monospace" font-size="10">isolated geometry + style/width samples</text>'
        )
        for index, orientation in enumerate(specimen_contract()["orientations"]):
            x = 650 + index * 112
            path = _path_for_orientation(orientation, x, y0 + 58)
            lines.append(
                f'<path data-orientation="{orientation}" d="{path}" fill="none" stroke="{categories[CATEGORY_NAMES[index]]}" stroke-width="1.5"/>'
            )
        for row, style_name in enumerate(STYLE_ORDER):
            spec = specimen_contract()["styles"][style_name]
            dash = (
                ""
                if spec["dasharray"] is None
                else f' stroke-dasharray="{" ".join(str(value) for value in spec["dasharray"])}"'
            )
            sample_y = y0 + 150 + row * 27
            lines.append(
                f'<line data-style="{style_name}" x1="650" y1="{sample_y}" x2="770" y2="{sample_y}" stroke="{categories[CATEGORY_NAMES[row]]}" stroke-width="2" stroke-linecap="{spec["linecap"]}"{dash}/>'
            )
        for row, width in enumerate(specimen_contract()["widths_css_px"]):
            sample_y = y0 + 150 + row * 27
            lines.append(
                f'<line data-width="{width:g}" x1="800" y1="{sample_y}" x2="920" y2="{sample_y}" stroke="{categories[CATEGORY_NAMES[row + 3]]}" stroke-width="{width:g}"/>'
            )
        lines.append("</g>")
    lines.append(
        f'<text x="32" y="874" fill="{surfaces["fg_2"]}" font-family="ui-monospace,monospace" font-size="12">bg_2 report-only · no candidate colors · no browser samples · no human width PASS/FAIL</text>'
    )
    lines.append("</svg>\n")
    return "\n".join(lines)


def _phone_svg(state: str, baseline: dict[str, Any]) -> str:
    surfaces, categories = _shown_palettes(state, baseline)
    title = "transformed" if state == "transformed" else "commanded"
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="390" height="844" viewBox="0 0 390 844">',
        '<defs><path id="g1-crossing-geometry" d="M0,30 L44,0 L88,30"/></defs>',
        f'<rect width="390" height="844" fill="{surfaces["bg_0"]}"/>',
        f'<text x="16" y="25" fill="{surfaces["fg_0"]}" font-family="ui-monospace,monospace" font-size="16" font-weight="700">G1 phone · {title}</text>',
        f'<text x="16" y="43" fill="{surfaces["fg_1"]}" font-family="ui-monospace,monospace" font-size="9">390×844 · compact real evidence · fake compositions</text>',
    ]
    for background_index, background_name in enumerate(("bg_0", "bg_1")):
        y0 = 54 + background_index * 382
        lines.extend(
            [
                f'<rect x="10" y="{y0}" width="370" height="372" rx="8" fill="{surfaces[background_name]}" stroke="{surfaces["bg_4"]}"/>',
                f'<text x="20" y="{y0 + 20}" fill="{surfaces["fg_0"]}" font-family="ui-monospace,monospace" font-size="11" font-weight="700">{background_name} · gate surface</text>',
            ]
        )
        lines.extend(
            _feature_evidence(
                background_name=background_name,
                x=20,
                y=y0 + 3,
                surfaces=surfaces,
                categories=categories,
                compact=True,
            )
        )
    lines.append(
        f'<text x="16" y="829" fill="{surfaces["fg_2"]}" font-family="ui-monospace,monospace" font-size="9">structural aid only · browser/human evidence pending</text>'
    )
    lines.append("</svg>\n")
    return "\n".join(lines)


def _review_index() -> str:
    return """<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>3400K Light G1 Phase 2A review</title>
<style>*{box-sizing:border-box}html,body{margin:0;max-width:100%;overflow-x:hidden;background:#171312;color:#ecdcbf;font:14px ui-monospace,monospace}header{position:sticky;top:0;max-width:100%;padding:12px 16px;background:#171312;border-bottom:1px solid #4d4540;overflow-wrap:anywhere}main{display:grid;gap:18px;width:100%;min-width:0;padding:12px}section{min-width:0}.frame{max-width:100%;padding:8px;background:#050404;border:1px solid #4d4540}.desktop-frame{overflow-x:auto;overflow-y:hidden}.phone-frame{overflow:hidden}.desktop-sheet{display:block;width:1280px;max-width:none}.phone-sheet{display:block;width:390px;max-width:100%;height:auto;margin:0 auto}.truth{max-width:1000px;color:#b4aa8e;line-height:1.5}b{color:#f490ac}a{color:#ecdcbf}@media(min-width:820px){main{padding:18px}.phone-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}</style>
<header><b>G1 CORE_READY_BROWSER_PENDING</b> · frozen current bank · <a href="../G1-REPORT.md">report</a> · <a href="../raster-baseline.json">planned raster matrix</a></header>
<main><p class="truth">Phase 2A fixes geometry and appearance-model assumptions. These SVGs are deterministic structural review aids, not browser-raster evidence. There are no candidate colours and no claimed human width capacity.</p>
<section><h2>Desktop commanded</h2><div class="frame desktop-frame"><img class="desktop-sheet" src="g1-commanded.svg" alt="G1 commanded desktop thin-mark evidence"></div></section>
<section><h2>Desktop transformed engineering view</h2><div class="frame desktop-frame"><img class="desktop-sheet" src="g1-transformed.svg" alt="G1 transformed desktop thin-mark evidence"></div></section>
<div class="phone-grid"><section><h2>Phone commanded · 390×844</h2><div class="frame phone-frame"><img class="phone-sheet" src="g1-phone-commanded.svg" alt="G1 commanded 390 by 844 phone evidence"></div></section>
<section><h2>Phone transformed · 390×844</h2><div class="frame phone-frame"><img class="phone-sheet" src="g1-phone-transformed.svg" alt="G1 transformed 390 by 844 phone evidence"></div></section></div></main>
"""


def _browser_probe_html(baseline: dict[str, Any]) -> str:
    family = baseline["family"]
    payload = {
        "contract": specimen_contract(),
        "categorical": family["categorical"],
        "surfaces": {name: family["surfaces"][name] for name in BACKGROUND_NAMES},
        "gains": [1.0, 0.74, 0.53],
        "status": "PENDING_BROWSER_CALIBRATION",
    }
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"""<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>G1 deterministic browser probe</title>
<style>*{{box-sizing:border-box}}html,body{{margin:0;background:#fff}}#status{{font:12px monospace;padding:8px}}svg{{display:block}}</style>
<div id="status">PENDING_BROWSER_CALIBRATION · case selected by ?case=0..32399</div><div id="probe"></div>
<script id="g1-contract" type="application/json">{data}</script>
<script>
const spec=JSON.parse(document.getElementById('g1-contract').textContent);
const pairs=[]; const names=spec.contract.category_order;
for(let i=0;i<names.length;i++)for(let j=i+1;j<names.length;j++)pairs.push([names[i],names[j]]);
const product=[];
for(const state of spec.contract.state_order)for(const background of spec.contract.background_order)for(const width_css_px of spec.contract.widths_css_px)for(const style of spec.contract.style_order)for(const orientation of spec.contract.orientations)for(const dpr of spec.contract.device_pixel_ratios)for(const phase_css_px of spec.contract.phases_css_px)for(const pair of pairs)product.push({{id:`planned-${{String(product.length+1).padStart(5,'0')}}`,state,background,background_policy:['bg_0','bg_1'].includes(background)?'gate':'report-only',width_css_px,style,orientation,dpr,phase_css_px,roles:pair.map(name=>`cat.${{name}}`),status:'PENDING_BROWSER_CALIBRATION',observed_line_core_rgb8:null,observed_distance:null}});
const index=Math.max(0,Math.min(product.length-1,Number(new URLSearchParams(location.search).get('case')||0)));
const row=product[index]; const style=spec.contract.styles[row.style];
const paths={{horizontal:'M16 64 L144 64',vertical:'M80 16 L80 112',diagonal_45:'M24 104 L120 8',shallow_1_2:'M16 88 L144 40',curved:'M16 96 C48 18 108 116 144 28'}};
const dash=style.dasharray?`stroke-dasharray="${{style.dasharray.join(' ')}}"`:'';
const warm='<defs><filter id="g1-warm" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" values="1 0 0 0 0 0 .74 0 0 0 0 0 .53 0 0 0 0 0 1 0"/></filter></defs>';
const filter=row.state==='transformed'?' filter="url(#g1-warm)"':'';
const roleNames=row.roles.map(role=>role.slice(4));
document.getElementById('probe').innerHTML=`<svg data-case="${{index}}" data-planned-id="${{row.id}}" data-status="PENDING_BROWSER_CALIBRATION" width="160" height="128" viewBox="0 0 160 128">${{warm}}<g${{filter}}><rect width="160" height="128" fill="${{spec.surfaces[row.background]}}"/><g transform="translate(${{row.phase_css_px[0]}} ${{row.phase_css_px[1]}})"><path d="${{paths[row.orientation]}}" fill="none" stroke="${{spec.categorical[roleNames[0]]}}" stroke-width="${{row.width_css_px}}" stroke-linecap="${{style.linecap}}" stroke-dashoffset="${{style.dashoffset}}" ${{dash}}/><path d="${{paths[row.orientation]}}" transform="translate(0 8)" fill="none" stroke="${{spec.categorical[roleNames[1]]}}" stroke-width="${{row.width_css_px}}" stroke-linecap="${{style.linecap}}" stroke-dashoffset="${{style.dashoffset}}" ${{dash}}/></g></g></svg>`;
document.getElementById('status').textContent+=` · ${{row.id}} · ${{JSON.stringify(row)}}`;
</script>
"""


def _report(baseline: dict[str, Any], raster: dict[str, Any], neutral: dict[str, Any]) -> str:
    frontier = raster["analytical_proxy_frontier"]
    commanded = frontier["commanded_solid_oklab"]["minimum_pair"]
    primary = [
        row
        for row in frontier["transformed_metric"]["scenario_minima"]
        if row["scenario_family"] == "primary"
    ]
    primary_rows = "\n".join(
        f"| {row['background']} | {' vs '.join(row['roles'])} | {row['distance']:.4f} |"
        for row in primary
    )
    return f"""# G1 Phase 2A: deterministic core checkpoint

**Verdict: `CORE_READY_BROWSER_PENDING`. Phase 3 candidate search remains blocked only until the Phase 2B browser machinery gates pass.**

The current 3400K Light categorical bank remains byte-frozen at `{baseline["baseline_source_commit"]}`. No candidate search, candidate colours, `categorical_line` bank, production palette edit, or export edit is present.

## What is ready

- A complete **planned** raster matrix of {raster["planned_case_count"]:,} cases covering state × background × width × style × orientation × DPR × phase × all 15 categorical pairs.
- Explicit line-core selection: coverage ≥ 0.5, max-coverage pixel nearest the centreline, exclusions for endpoints/joins/markers/crossings/dash transitions, then per-channel median.
- Commanded solid identity in Oklab and transformed solid/composited-proxy reconnaissance in CAM16-UCS under pinned light-viewing engineering assumptions.
- Complete analytical category-vs-foreground, benchmark-neutral, and report-only terminal matrices ({len(neutral["matrix"]):,} scenario rows).
- A named 45-sample asymmetric gain grid, a separate local-refinement protocol, and separate brightness uncertainty.
- A preregistered 15-pair 2AFC visibility protocol with no results.

## Metric ownership and viewing assumptions

Commanded solid minimum: **{" vs ".join(commanded["roles"])} = {commanded["delta_e_ok"]:.4f} ΔE_OK**.

Primary transformed solid CAM16-UCS minima are reported separately, never averaged:

| Surface | Pair | CAM16-UCS distance |
|---|---|---:|
{primary_rows}

The input is encoded sRGB in [0,1]. Coverage compositing occurs in encoded sRGB; gains `[1, .74, .53]` are applied **after** rasterization/compositing. `colour-science` receives XYZ on its 0–1 reference scale, D65 white normalized to Y=1 (mapped to Yw=100 cd/m²), and explicit CAM16 `L_A`, `Y_b`, and surround values. Primary conditions are Dim, flare 0, `L_A=14.2`, with per-surface `Y_b` 56.18/49.82/44.32. Sensitivity conditions are Average, flare 0.0075, `L_A` 9.5 and 19, with transformed-white-adapted `Y_b` 94.77/84.05/74.76. Flare is implemented as additive `flare_fraction × XYZ_D65_white` on the transformed stimulus before CAM16; it is an engineering sensitivity term, not measured device glare. Every scenario is reported separately and never averaged.

`compute_proxy_frontier(..., transformed_metric=callable)` routes every transformed solid and proxy distance through that callable. `proxy_acceptance` requires correlation ≥0.95 **and** maximum pair/background MAE ≤0.75; either bad polarity fails.

## Browser and human truth boundaries

`raster-baseline.json` is a planned-case ledger, **not observed browser measurements**. Every row is `PENDING_BROWSER_CALIBRATION`, with observed RGB and distances null. `proxy-calibration.json` contains the Phase 2B schema and acceptance thresholds but no samples, coordinates, observed RGB, correlation, MAE, or PASS. The browser release oracle remains mandatory.

Every width capacity is `UNKNOWN/UNPROVEN`. The 2AFC study has not run, so there is no visibility floor and no width PASS/FAIL. Analytical distances must not be relabelled as human capacity.

## Review

- [Commanded/transformed index](review/g1-index.html)
- [Commanded structural specimen](review/g1-commanded.svg)
- [Transformed engineering specimen](review/g1-transformed.svg)
- [Commanded 390×844 phone specimen](review/g1-phone-commanded.svg)
- [Transformed 390×844 phone specimen](review/g1-phone-transformed.svg)
- [Deterministic browser probe](review/g1-browser-probe.html)

The SVGs are structural review aids, not browser pixels. `bg_0` and `bg_1` are gate surfaces; `bg_2` remains report-only.

## Phase 2B sequencing

1. Run the deterministic probe in real Chromium at the pinned DPRs/viewports and record renderer provenance.
2. Derive coverage and line-core coordinates from actual raster pixels; do not invent them.
3. Store predicted/observed RGB8 samples and evaluate pooled correlation plus every pair/background MAE gate.
4. Treat a missing browser binary as SKIP and every launch/probe/runtime failure as ERROR.
5. When the browser machinery gates pass, the autonomous process may begin Phase 3 candidate search without inventing human results.
6. Run the preregistered multi-observer 2AFC study and held-out floor calibration before declaring a final visibility floor, assigning width capacity, or promoting any palette to production. The human study may follow or overlap candidate search; it is not a prerequisite for starting that search.
"""


def _compact_matrix_json(payload: dict[str, Any]) -> str:
    """Keep a complete planned matrix reviewable without 20 lines per case."""

    metadata = [(key, payload[key]) for key in sorted(payload) if key != "matrix"]
    lines = ["{"]
    for key, value in metadata:
        lines.append(
            f"  {json.dumps(key)}: {json.dumps(value, sort_keys=True, separators=(',', ':'))},"
        )
    lines.append('  "matrix": [')
    for index, row in enumerate(payload["matrix"]):
        comma = "," if index + 1 < len(payload["matrix"]) else ""
        lines.append(f"    {json.dumps(row, sort_keys=True, separators=(',', ':'))}{comma}")
    lines.extend(["  ]", "}"])
    return "\n".join(lines) + "\n"


def build_core_outputs(output_dir: Path = HERE) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    review = output_dir / "review"
    review.mkdir(parents=True, exist_ok=True)
    baseline = load_baseline()
    viewing = _viewing_conditions()
    raster = _raster_baseline(baseline)
    neutral = _neutral_confusability(baseline)
    artifacts = {
        "viewing-conditions.json": viewing,
        "raster-baseline.json": raster,
        "neutral-confusability.json": neutral,
        "gain-grid.json": _gain_grid(),
        "visibility-trial-protocol.json": _visibility_protocol(),
        "proxy-calibration.json": _proxy_calibration_pending(baseline),
    }
    for filename, payload in artifacts.items():
        text = (
            _compact_matrix_json(payload)
            if filename == "raster-baseline.json"
            else json.dumps(payload, indent=2, sort_keys=True) + "\n"
        )
        (output_dir / filename).write_text(text, encoding="utf-8")
    (output_dir / "G1-REPORT.md").write_text(_report(baseline, raster, neutral), encoding="utf-8")
    (review / "g1-index.html").write_text(_review_index(), encoding="utf-8")
    (review / "g1-commanded.svg").write_text(_svg("commanded", baseline), encoding="utf-8")
    (review / "g1-transformed.svg").write_text(_svg("transformed", baseline), encoding="utf-8")
    (review / "g1-phone-commanded.svg").write_text(
        _phone_svg("commanded", baseline), encoding="utf-8"
    )
    (review / "g1-phone-transformed.svg").write_text(
        _phone_svg("transformed", baseline), encoding="utf-8"
    )
    (review / "g1-browser-probe.html").write_text(_browser_probe_html(baseline), encoding="utf-8")


if __name__ == "__main__":
    build_core_outputs()
