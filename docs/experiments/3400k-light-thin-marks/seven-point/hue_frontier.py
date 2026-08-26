#!/usr/bin/env python3
"""De novo two-color hue frontier for fixed-fg0 Candidate A geometry."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
ROOT = EXPERIMENT.parents[2]
BASELINE_A = ("#7C140A", "#857D0B", "#0A6109", "#2B8CAD", "#5D53AE", "#B34B71")
FIXED_FOUR = ("#0A6109", "#2B8CAD", "#5D53AE", "#B34B71")
HUE_FAMILIES = (
    ("AMBER-ORANGE", "Amber / orange", "benchmark-c", 60.0, 78.0),
    ("GOLDEN-YELLOW", "Golden yellow", "a", 78.0, 90.0),
    ("YELLOW", "Yellow", "b", 90.0, 102.0),
    ("YELLOW-GREEN-EDGE", "Yellow-green edge", "c", 102.0, 113.0),
)
ROLE_ORDER = ("reference", "benchmark-c", "a", "b", "c")
EXPECTED_FILES = ("catalog-summary.json", "results.json")
WIDTHS = (1.5, 2.0, 3.0)
BACKGROUNDS = ("bg_0", "bg_1")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seven = _load("seven_optimizer_for_hue_frontier", "optimizer.py")
polish = _load("seven_polish_for_hue_frontier", "polish.py")
p3 = seven.p3
srgb_to_oklab = seven.srgb_to_oklab
contrast_ratio = seven.contrast_ratio


class HueFrontierError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HueFrontierError(message)


def source_binding(path: Path) -> dict[str, str]:
    relative = str(path.resolve().relative_to(ROOT))
    completed = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", relative],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    commit = completed.stdout.strip()
    require(completed.returncode == 0 and len(commit) == 40, f"source uncommitted: {relative}")
    return {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "commit": commit,
    }


def lch_from_lab(lab: Sequence[float]) -> tuple[float, float, float]:
    value = np.asarray(lab, dtype=float)
    return (
        float(value[0]),
        float(np.hypot(value[1], value[2])),
        float(np.degrees(np.arctan2(value[2], value[1])) % 360.0),
    )


def hue_delta(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.abs((left - right + 180.0) % 360.0 - 180.0)


def contexts(inputs: Any, width: float) -> tuple[tuple[Mapping[int, float], np.ndarray], ...]:
    surfaces = inputs.baseline["family"]["surfaces"]
    return tuple(
        (lanes, p3.parse_exact_hex8(surfaces[background]))
        for geometry, lanes in p3._mask_summaries(inputs).items()
        if float(geometry[0]) == width
        for background in BACKGROUNDS
    )


def raster_cross(
    left_rgb: np.ndarray,
    right_rgb: np.ndarray,
    width_contexts: Sequence[tuple[Mapping[int, float], np.ndarray]],
    gains: np.ndarray,
    margin: float,
) -> np.ndarray:
    result = np.full((len(left_rgb), len(right_rgb)), math.inf)
    for lanes, background in width_contexts:
        left_points = [
            srgb_to_oklab((lanes[index] * left_rgb + (1.0 - lanes[index]) * background) * gains)
            for index in (0, 1)
        ]
        right_points = [
            srgb_to_oklab((lanes[index] * right_rgb + (1.0 - lanes[index]) * background) * gains)
            for index in (0, 1)
        ]
        for left_lane, right_lane in ((0, 1), (1, 0)):
            distance = np.linalg.norm(
                left_points[left_lane][:, None, :] - right_points[right_lane][None, :, :],
                axis=2,
            )
            result = np.minimum(result, distance * 100.0 - margin)
    return result


def raster_to_fixed(
    catalog_rgb: np.ndarray,
    fixed_rgb: np.ndarray,
    fg_rgb: np.ndarray,
    width_contexts: Sequence[tuple[Mapping[int, float], np.ndarray]],
    gains: np.ndarray,
    margin: float,
) -> tuple[np.ndarray, float]:
    fixed_set = np.vstack((fg_rgb, fixed_rgb))
    candidate = raster_cross(catalog_rgb, fixed_set, width_contexts, gains, margin)
    fixed_pairs = raster_cross(fixed_set, fixed_set, width_contexts, gains, margin)
    upper = fixed_pairs[np.triu_indices(len(fixed_set), 1)]
    return np.min(candidate, axis=1), float(np.min(upper))


def hard_fixed_mask(
    commanded: np.ndarray,
    transformed: np.ndarray,
    hues: np.ndarray,
    fixed_commanded: np.ndarray,
    fixed_transformed: np.ndarray,
    fixed_hues: np.ndarray,
    contract: Mapping[str, Any],
) -> np.ndarray:
    gates = contract["hard_gates"]
    return (
        (
            np.min(
                np.linalg.norm(commanded[:, None] - fixed_commanded[None], axis=2) * 100.0,
                axis=1,
            )
            >= gates["commanded_category_pair_delta_e_ok"]
        )
        & (
            np.min(
                np.linalg.norm(transformed[:, None] - fixed_transformed[None], axis=2) * 100.0,
                axis=1,
            )
            >= gates["nominal_transformed_category_pair_delta_e_ok"]
        )
        & (
            np.min(hue_delta(hues[:, None], fixed_hues[None]), axis=1)
            >= gates["commanded_minimum_hue_gap_degrees"]
        )
    )


def support_intervals(hues: Sequence[float]) -> list[list[float]]:
    values = sorted({round(float(value), 6) for value in hues})
    if not values:
        return []
    groups = [[values[0]]]
    for value in values[1:]:
        if value - groups[-1][-1] > 10.0:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [[group[0], group[-1]] for group in groups]


def contrast_payload(bank: Sequence[str], inputs: Any) -> dict[str, Any]:
    surfaces = inputs.baseline["family"]["surfaces"]
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    rows = {}
    for name, value in (("free_1", bank[0]), ("free_2", bank[1])):
        rgb = p3.parse_exact_hex8(value)
        rows[name] = {
            state: {
                background: contrast_ratio(
                    rgb * state_gains,
                    p3.parse_exact_hex8(surfaces[background]) * state_gains,
                )
                for background in BACKGROUNDS
            }
            for state, state_gains in (("commanded", np.ones(3)), ("transformed", gains))
        }
    return rows


def lex_positions(valid: np.ndarray, components: Sequence[np.ndarray]) -> list[tuple[int, int]]:
    positions = list(zip(*np.where(valid), strict=True))
    require(bool(positions), "no feasible frontier pair")
    for component in components:
        best = max(float(component[left, right]) for left, right in positions)
        positions = [
            (left, right)
            for left, right in positions
            if abs(float(component[left, right]) - best) <= 1e-12
        ]
    return positions


def select_family(
    family: tuple[str, str, str, float, float],
    catalog: Sequence[Any],
    rgb: np.ndarray,
    commanded: np.ndarray,
    transformed: np.ndarray,
    hues: np.ndarray,
    feasible_indices: np.ndarray,
    fixed_indices: Sequence[int],
    raster_to_fixed_by_width: Mapping[float, tuple[np.ndarray, float]],
    width_contexts: Mapping[float, Sequence[tuple[Mapping[int, float], np.ndarray]]],
    inputs: Any,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    lane, display, browser_role, hue_low, hue_high = family
    second_indices = feasible_indices[
        (hues[feasible_indices] >= hue_low) & (hues[feasible_indices] < hue_high)
    ]
    first_indices = feasible_indices
    require(len(second_indices) > 0, f"empty feasible hue bin {lane}")
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    margin = float(contract["raster"]["calibrated_error_margin_delta_e_ok"])
    gates = contract["hard_gates"]
    pair_commanded = (
        np.linalg.norm(commanded[first_indices, None] - commanded[second_indices][None], axis=2)
        * 100.0
    )
    pair_transformed = (
        np.linalg.norm(transformed[first_indices, None] - transformed[second_indices][None], axis=2)
        * 100.0
    )
    pair_hue = hue_delta(hues[first_indices, None], hues[second_indices][None])
    valid = (
        (pair_commanded >= gates["commanded_category_pair_delta_e_ok"])
        & (pair_transformed >= gates["nominal_transformed_category_pair_delta_e_ok"])
        & (pair_hue >= gates["commanded_minimum_hue_gap_degrees"])
        & (first_indices[:, None] != second_indices[None, :])
    )
    raster_components = []
    for width in WIDTHS:
        cross = raster_cross(
            rgb[first_indices], rgb[second_indices], width_contexts[width], gains, margin
        )
        to_fixed, fixed_floor = raster_to_fixed_by_width[width]
        component = np.minimum(cross, fixed_floor)
        component = np.minimum(component, to_fixed[first_indices, None])
        component = np.minimum(component, to_fixed[second_indices][None, :])
        raster_components.append(component)
    fixed_set_indices = np.asarray(fixed_indices, dtype=int)
    fixed_rgb = rgb[fixed_set_indices]
    fg_rgb = p3.parse_exact_hex8("#342F2C")
    commanded_fixed = np.vstack((srgb_to_oklab(fg_rgb), commanded[fixed_set_indices]))
    transformed_fixed = np.vstack((srgb_to_oklab(fg_rgb * gains), transformed[fixed_set_indices]))
    commanded_to_fixed = np.min(
        np.linalg.norm(commanded[:, None] - commanded_fixed[None], axis=2) * 100.0,
        axis=1,
    )
    transformed_to_fixed = np.min(
        np.linalg.norm(transformed[:, None] - transformed_fixed[None], axis=2) * 100.0,
        axis=1,
    )
    commanded_fixed_floor = float(
        np.min(
            (np.linalg.norm(commanded_fixed[:, None] - commanded_fixed[None, :], axis=2) * 100.0)[
                np.triu_indices(len(commanded_fixed), 1)
            ]
        )
    )
    transformed_fixed_floor = float(
        np.min(
            (
                np.linalg.norm(transformed_fixed[:, None] - transformed_fixed[None, :], axis=2)
                * 100.0
            )[np.triu_indices(len(transformed_fixed), 1)]
        )
    )
    transformed_solid = np.minimum(pair_transformed, transformed_fixed_floor)
    transformed_solid = np.minimum(transformed_solid, transformed_to_fixed[first_indices, None])
    transformed_solid = np.minimum(transformed_solid, transformed_to_fixed[second_indices][None, :])
    commanded_solid = np.minimum(pair_commanded, commanded_fixed_floor)
    commanded_solid = np.minimum(commanded_solid, commanded_to_fixed[first_indices, None])
    commanded_solid = np.minimum(commanded_solid, commanded_to_fixed[second_indices][None, :])
    sensitivity = np.full_like(pair_commanded, math.inf)
    sensitivity_first = np.full(len(catalog), math.inf)
    sensitivity_second = np.full(len(catalog), math.inf)
    sensitivity_fixed_floor = math.inf
    fixed_all_rgb = np.vstack((fg_rgb, fixed_rgb))
    for gain in p3._gain_samples(inputs, nominal_only=False):
        sample = np.asarray([gain["red_gain"], gain["green_gain"], gain["blue_gain"]])
        points = srgb_to_oklab(rgb * sample)
        fixed_points = srgb_to_oklab(fixed_all_rgb * sample)
        sensitivity_first = np.minimum(
            sensitivity_first,
            np.min(np.linalg.norm(points[:, None] - fixed_points[None], axis=2) * 100.0, axis=1),
        )
        sensitivity_second = np.minimum(sensitivity_second, sensitivity_first)
        sensitivity_fixed_floor = min(
            sensitivity_fixed_floor,
            float(
                np.min(
                    (np.linalg.norm(fixed_points[:, None] - fixed_points[None, :], axis=2) * 100.0)[
                        np.triu_indices(len(fixed_points), 1)
                    ]
                )
            ),
        )
        sensitivity = np.minimum(
            sensitivity,
            np.linalg.norm(points[first_indices, None] - points[second_indices][None], axis=2)
            * 100.0,
        )
    sensitivity = np.minimum(sensitivity, sensitivity_fixed_floor)
    sensitivity = np.minimum(sensitivity, sensitivity_first[first_indices, None])
    sensitivity = np.minimum(sensitivity, sensitivity_second[second_indices][None, :])
    components = [
        raster_components[0],
        raster_components[1],
        raster_components[2],
        transformed_solid,
        commanded_solid,
        sensitivity,
    ]
    positions = lex_positions(valid, components)
    candidates = []
    for left, right in positions:
        bank = seven.canonical_categories(
            [
                catalog[int(first_indices[left])].hex8,
                catalog[int(second_indices[right])].hex8,
                *FIXED_FOUR,
            ]
        )
        evaluation = seven.evaluate(bank, inputs, contract)
        require(evaluation["hard_gate_failures"] == [], f"frontier gate failure {lane}")
        candidates.append((tuple(evaluation["objective"]), bank, evaluation, left, right))
    objective, bank, evaluation, left, right = max(candidates, key=lambda row: (row[0], row[1]))
    first = catalog[int(first_indices[left])]
    second = catalog[int(second_indices[right])]
    require(tuple(objective) == tuple(evaluation["objective"]), "frontier objective mismatch")
    return {
        "lane": lane,
        "display_name": display,
        "browser_role": browser_role,
        "hue_bin_degrees": [hue_low, hue_high],
        "categories": list(bank),
        "free_1": first.hex8,
        "free_2": second.hex8,
        "free_1_oklch": list(lch_from_lab(first.commanded_oklab)),
        "free_2_oklch": list(lch_from_lab(second.commanded_oklab)),
        "free_1_transformed_oklch": list(lch_from_lab(first.transformed_oklab)),
        "free_2_transformed_oklch": list(lch_from_lab(second.transformed_oklab)),
        "candidate_id": p3.sha256_json(
            {"lane": lane, "categories": list(bank), "contract": p3.sha256_json(contract)}
        ),
        "category_set_sha256": p3.bank_hash(bank),
        "metrics": evaluation["metrics"],
        "objective": evaluation["objective"],
        "hard_gate_failures": evaluation["hard_gate_failures"],
        "contrast": contrast_payload(bank, inputs),
        "search": {
            "first_pool_count": len(first_indices),
            "second_bin_pool_count": len(second_indices),
            "pair_evaluation_count": len(first_indices) * len(second_indices),
            "hard_feasible_pair_count": int(np.sum(valid)),
            "full_objective_tie_count": len(positions),
            "ranking": "six-component objective then maximum canonical category tuple",
        },
    }


def run() -> dict[str, Any]:
    inputs = seven.load_inputs(replay=False)
    contract = seven.load_contract()
    seven.validate_contract(contract, inputs)
    catalog, catalog_summary = seven.build_catalog(inputs, contract, smoke=False)
    rgb = np.asarray([p3.parse_exact_hex8(row.hex8) for row in catalog])
    commanded = np.asarray([row.commanded_oklab for row in catalog])
    transformed = np.asarray([row.transformed_oklab for row in catalog])
    hues = np.asarray([row.hue_degrees for row in catalog])
    by_hex = {row.hex8: index for index, row in enumerate(catalog)}
    fixed_indices = [by_hex[value] for value in FIXED_FOUR]
    fixed_commanded = commanded[np.asarray(fixed_indices)]
    fixed_transformed = transformed[np.asarray(fixed_indices)]
    fixed_hues = hues[np.asarray(fixed_indices)]
    feasible_mask = hard_fixed_mask(
        commanded,
        transformed,
        hues,
        fixed_commanded,
        fixed_transformed,
        fixed_hues,
        contract,
    )
    feasible_indices = np.flatnonzero(feasible_mask)
    # Report actual global hue support: a color is supported only if some second free
    # color completes every pair hard gate with the fixed four.
    pair_supported = np.zeros(len(feasible_indices), dtype=bool)
    gates = contract["hard_gates"]
    for start in range(0, len(feasible_indices), 256):
        stop = min(start + 256, len(feasible_indices))
        left = feasible_indices[start:stop]
        pair_cmd = (
            np.linalg.norm(commanded[left, None] - commanded[feasible_indices][None], axis=2)
            * 100.0
        )
        pair_transformed = (
            np.linalg.norm(transformed[left, None] - transformed[feasible_indices][None], axis=2)
            * 100.0
        )
        pair_hue = hue_delta(hues[left, None], hues[feasible_indices][None])
        valid = (
            (pair_cmd >= gates["commanded_category_pair_delta_e_ok"])
            & (pair_transformed >= gates["nominal_transformed_category_pair_delta_e_ok"])
            & (pair_hue >= gates["commanded_minimum_hue_gap_degrees"])
            & (left[:, None] != feasible_indices[None, :])
        )
        pair_supported[start:stop] = np.any(valid, axis=1)
    supported_indices = feasible_indices[pair_supported]
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    margin = float(contract["raster"]["calibrated_error_margin_delta_e_ok"])
    fg_rgb = p3.parse_exact_hex8("#342F2C")
    fixed_rgb = rgb[np.asarray(fixed_indices)]
    width_contexts = {width: contexts(inputs, width) for width in WIDTHS}
    raster_to_fixed_by_width = {
        width: raster_to_fixed(rgb, fixed_rgb, fg_rgb, width_contexts[width], gains, margin)
        for width in WIDTHS
    }
    lanes = [
        select_family(
            family,
            catalog,
            rgb,
            commanded,
            transformed,
            hues,
            supported_indices,
            fixed_indices,
            raster_to_fixed_by_width,
            width_contexts,
            inputs,
            contract,
        )
        for family in HUE_FAMILIES
    ]
    transformed_pairs = [
        np.concatenate(
            [
                np.asarray(row["free_1_transformed_oklch"]),
                np.asarray(row["free_2_transformed_oklch"]),
            ]
        )
        for row in lanes
    ]
    for left, right in itertools.combinations(range(len(lanes)), 2):
        require(
            bool(np.linalg.norm(transformed_pairs[left] - transformed_pairs[right]) >= 0.02),
            f"frontier transformed near-clones {lanes[left]['lane']} / {lanes[right]['lane']}",
        )
    baseline_eval = seven.evaluate(BASELINE_A, inputs, contract)
    baseline_bank = seven.canonical_categories(BASELINE_A)
    baseline = {
        "lane": "BASELINE-A",
        "display_name": "Candidate A baseline",
        "browser_role": "reference",
        "categories": list(baseline_bank),
        "free_1": BASELINE_A[0],
        "free_2": BASELINE_A[1],
        "candidate_id": p3.sha256_json({"lane": "BASELINE-A", "categories": list(baseline_bank)}),
        "category_set_sha256": p3.bank_hash(baseline_bank),
        "metrics": baseline_eval["metrics"],
        "objective": baseline_eval["objective"],
        "hard_gate_failures": baseline_eval["hard_gate_failures"],
        "contrast": contrast_payload(baseline_bank, inputs),
    }
    browser_roles = {"reference": baseline}
    browser_roles.update({row["browser_role"]: row for row in lanes})
    return {
        "schema_version": 1,
        "artifact_kind": "seven-point-hue-frontier",
        "input_chain_sha256": p3.input_chain_sha256(inputs),
        "search_contract_sha256": p3.sha256_json(contract),
        "fixed_fg0": "#342F2C",
        "fixed_four": list(FIXED_FOUR),
        "ranking_policy": "de novo six-component objective; canonical tuple only after exact equality",
        "proximity_or_named_gold_objective": False,
        "selection": None,
        "production": False,
        "feasible_hue_support": {
            "exact_color_count": len(supported_indices),
            "minimum_degrees": float(np.min(hues[supported_indices])),
            "maximum_degrees": float(np.max(hues[supported_indices])),
            "intervals_degrees": support_intervals(hues[supported_indices]),
            "occupied_12_degree_bins": sorted(
                {int(value // 12) for value in hues[supported_indices]}
            ),
        },
        "catalog_summary": catalog_summary,
        "baseline": baseline,
        "lanes": lanes,
        "browser_roles": browser_roles,
        "source": source_binding(Path(__file__)),
    }


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def payloads(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "catalog-summary.json": result["catalog_summary"],
        "results.json": {key: value for key, value in result.items() if key != "catalog_summary"},
    }


def build(output_dir: Path) -> None:
    inputs = seven.load_inputs(replay=False)
    output = p3.validate_external_output_path(Path(output_dir), inputs)
    if output.exists():
        require(not list(output.iterdir()), "hue frontier output directory must be empty")
    result = run()
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads(result).items():
        (output / name).write_bytes(json_bytes(payload))


def validate(artifact_dir: Path) -> None:
    directory = Path(artifact_dir)
    require(directory.is_dir(), "hue frontier artifact directory missing")
    require({path.name for path in directory.iterdir()} == set(EXPECTED_FILES), "hue files differ")
    actual = {name: json.loads((directory / name).read_text()) for name in EXPECTED_FILES}
    require(actual == payloads(run()), "hue frontier replay differs")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--output-dir", type=Path, required=True)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "build":
        build(args.output_dir)
    else:
        validate(args.artifact_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
