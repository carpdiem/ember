#!/usr/bin/env python3
"""Constraint influence and one-slot minimal relaxation for the hue frontier."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
ROOT = EXPERIMENT.parents[2]
FIXED_FOUR = ("#0A6109", "#2B8CAD", "#5D53AE", "#B34B71")
FIXED_THREE_AFTER_RELAXATION = ("#0A6109", "#2B8CAD", "#5D53AE")
BASELINE_A = ("#7C140A", "#857D0B", *FIXED_FOUR)
BINS = (
    ("AMBER-ORANGE", 60.0, 78.0),
    ("GOLDEN-YELLOW", 78.0, 90.0),
    ("YELLOW", 90.0, 102.0),
    ("YELLOW-GREEN-EDGE", 102.0, 113.0),
)
EXPECTED_FILES = ("catalog-summary.json", "results.json")
PAIR_BEAM_CAP = 64
THIRD_TIE_CAP = 4


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seven = _load("seven_for_minimal_relaxation", "optimizer.py")
hue = _load("hue_for_minimal_relaxation", "hue_frontier.py")
p3 = seven.p3
srgb_to_oklab = seven.srgb_to_oklab


class RelaxationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RelaxationError(message)


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


def fixed_state(
    fixed_values: Sequence[str],
    catalog: Sequence[Any],
    rgb: np.ndarray,
    commanded: np.ndarray,
    transformed: np.ndarray,
    hues: np.ndarray,
    inputs: Any,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    by_hex = {row.hex8: index for index, row in enumerate(catalog)}
    fixed_indices = np.asarray([by_hex[value] for value in fixed_values], dtype=int)
    feasible_mask = hue.hard_fixed_mask(
        commanded,
        transformed,
        hues,
        commanded[fixed_indices],
        transformed[fixed_indices],
        hues[fixed_indices],
        contract,
    )
    feasible_indices = np.flatnonzero(feasible_mask)
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    margin = float(contract["raster"]["calibrated_error_margin_delta_e_ok"])
    fg_rgb = p3.parse_exact_hex8("#342F2C")
    width_contexts = {width: hue.contexts(inputs, width) for width in hue.WIDTHS}
    raster_fixed = {
        width: hue.raster_to_fixed(
            rgb,
            rgb[fixed_indices],
            fg_rgb,
            width_contexts[width],
            gains,
            margin,
        )
        for width in hue.WIDTHS
    }
    return {
        "fixed_values": tuple(fixed_values),
        "fixed_indices": fixed_indices,
        "feasible_indices": feasible_indices,
        "gains": gains,
        "margin": margin,
        "fg_rgb": fg_rgb,
        "width_contexts": width_contexts,
        "raster_fixed": raster_fixed,
    }


def relaxed_bin(
    state: Mapping[str, Any],
    bin_spec: tuple[str, float, float],
    catalog: Sequence[Any],
    rgb: np.ndarray,
    commanded: np.ndarray,
    transformed: np.ndarray,
    hues: np.ndarray,
    inputs: Any,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    name, low, high = bin_spec
    feasible = np.asarray(state["feasible_indices"], dtype=int)
    second = feasible[(hues[feasible] >= low) & (hues[feasible] < high)]
    require(len(second) > 0, f"empty relaxed bin {name}")
    gates = contract["hard_gates"]
    pair_commanded = (
        np.linalg.norm(commanded[feasible, None] - commanded[second][None], axis=2) * 100.0
    )
    pair_transformed = (
        np.linalg.norm(transformed[feasible, None] - transformed[second][None], axis=2) * 100.0
    )
    pair_hue = hue.hue_delta(hues[feasible, None], hues[second][None])
    valid = (
        (pair_commanded >= gates["commanded_category_pair_delta_e_ok"])
        & (pair_transformed >= gates["nominal_transformed_category_pair_delta_e_ok"])
        & (pair_hue >= gates["commanded_minimum_hue_gap_degrees"])
        & (feasible[:, None] != second[None, :])
    )
    raster_components = []
    for width in hue.WIDTHS:
        cross = hue.raster_cross(
            rgb[feasible],
            rgb[second],
            state["width_contexts"][width],
            state["gains"],
            state["margin"],
        )
        to_fixed, fixed_floor = state["raster_fixed"][width]
        component = np.minimum(cross, fixed_floor)
        component = np.minimum(component, to_fixed[feasible, None])
        component = np.minimum(component, to_fixed[second][None, :])
        raster_components.append(component)
    fixed_indices = np.asarray(state["fixed_indices"], dtype=int)
    fixed_rgb = rgb[fixed_indices]
    fg_rgb = state["fg_rgb"]
    commanded_fixed = np.vstack((srgb_to_oklab(fg_rgb), commanded[fixed_indices]))
    transformed_fixed = np.vstack(
        (srgb_to_oklab(fg_rgb * state["gains"]), transformed[fixed_indices])
    )
    commanded_to_fixed = np.min(
        np.linalg.norm(commanded[:, None] - commanded_fixed[None], axis=2) * 100.0,
        axis=1,
    )
    transformed_to_fixed = np.min(
        np.linalg.norm(transformed[:, None] - transformed_fixed[None], axis=2) * 100.0,
        axis=1,
    )
    cmd_floor = float(
        np.min(
            (np.linalg.norm(commanded_fixed[:, None] - commanded_fixed[None, :], axis=2) * 100.0)[
                np.triu_indices(len(commanded_fixed), 1)
            ]
        )
    )
    tr_floor = float(
        np.min(
            (
                np.linalg.norm(transformed_fixed[:, None] - transformed_fixed[None, :], axis=2)
                * 100.0
            )[np.triu_indices(len(transformed_fixed), 1)]
        )
    )
    tr_component = np.minimum(pair_transformed, tr_floor)
    tr_component = np.minimum(tr_component, transformed_to_fixed[feasible, None])
    tr_component = np.minimum(tr_component, transformed_to_fixed[second][None, :])
    cmd_component = np.minimum(pair_commanded, cmd_floor)
    cmd_component = np.minimum(cmd_component, commanded_to_fixed[feasible, None])
    cmd_component = np.minimum(cmd_component, commanded_to_fixed[second][None, :])
    sensitivity = np.full_like(pair_commanded, math.inf)
    sens_to_fixed = np.full(len(catalog), math.inf)
    sens_floor = math.inf
    fixed_all_rgb = np.vstack((fg_rgb, fixed_rgb))
    for gain in p3._gain_samples(inputs, nominal_only=False):
        sample = np.asarray([gain["red_gain"], gain["green_gain"], gain["blue_gain"]])
        points = srgb_to_oklab(rgb * sample)
        fixed_points = srgb_to_oklab(fixed_all_rgb * sample)
        sens_to_fixed = np.minimum(
            sens_to_fixed,
            np.min(np.linalg.norm(points[:, None] - fixed_points[None], axis=2) * 100.0, axis=1),
        )
        sens_floor = min(
            sens_floor,
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
            np.linalg.norm(points[feasible, None] - points[second][None], axis=2) * 100.0,
        )
    sensitivity = np.minimum(sensitivity, sens_floor)
    sensitivity = np.minimum(sensitivity, sens_to_fixed[feasible, None])
    sensitivity = np.minimum(sensitivity, sens_to_fixed[second][None, :])
    components = [
        raster_components[0],
        raster_components[1],
        raster_components[2],
        tr_component,
        cmd_component,
        sensitivity,
    ]
    positions = hue.lex_positions(valid, components)
    rows = []
    for left, right in positions:
        pair = tuple(sorted((catalog[int(feasible[left])].hex8, catalog[int(second[right])].hex8)))
        objective = [float(component[left, right]) for component in components]
        rows.append((tuple(objective), pair))
    objective, pair = max(rows, key=lambda row: (row[0], row[1]))
    return {
        "bin": name,
        "degrees": [low, high],
        "second_color_count": len(second),
        "hard_feasible_pair_count": int(np.sum(valid)),
        "best_pair": list(pair),
        "best_reduced_objective": list(objective),
        "exact_objective_tie_count": len(positions),
    }


def influence_analysis(
    catalog: Sequence[Any],
    rgb: np.ndarray,
    commanded: np.ndarray,
    transformed: np.ndarray,
    hues: np.ndarray,
    inputs: Any,
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    scenarios = [("NONE", FIXED_FOUR)] + [
        (removed, tuple(value for value in FIXED_FOUR if value != removed))
        for removed in FIXED_FOUR
    ]
    rows = []
    for removed, fixed_values in scenarios:
        started = time.perf_counter()
        print(
            f"[constraint-influence] scenario-start removed={removed}",
            file=sys.stderr,
            flush=True,
        )
        state = fixed_state(
            fixed_values,
            catalog,
            rgb,
            commanded,
            transformed,
            hues,
            inputs,
            contract,
        )
        bins = [
            relaxed_bin(
                state,
                bin_spec,
                catalog,
                rgb,
                commanded,
                transformed,
                hues,
                inputs,
                contract,
            )
            for bin_spec in BINS
        ]
        rows.append(
            {
                "removed_fixed_color": removed,
                "remaining_fixed_colors": list(fixed_values),
                "feasible_vertex_count": len(state["feasible_indices"]),
                "bins": bins,
            }
        )
        print(
            f"[constraint-influence] scenario-complete removed={removed} "
            f"seconds={time.perf_counter() - started:.3f}",
            file=sys.stderr,
            flush=True,
        )
    return rows


def pair_primary_candidates(
    state: Mapping[str, Any],
    catalog: Sequence[Any],
    rgb: np.ndarray,
    commanded: np.ndarray,
    transformed: np.ndarray,
    hues: np.ndarray,
    contract: Mapping[str, Any],
) -> list[tuple[float, tuple[str, str]]]:
    feasible = np.asarray(state["feasible_indices"], dtype=int)
    second = feasible[(hues[feasible] >= 60.0) & (hues[feasible] < 90.0)]
    gates = contract["hard_gates"]
    pair_cmd = np.linalg.norm(commanded[feasible, None] - commanded[second][None], axis=2) * 100.0
    pair_tr = (
        np.linalg.norm(transformed[feasible, None] - transformed[second][None], axis=2) * 100.0
    )
    pair_hue = hue.hue_delta(hues[feasible, None], hues[second][None])
    valid = (
        (pair_cmd >= gates["commanded_category_pair_delta_e_ok"])
        & (pair_tr >= gates["nominal_transformed_category_pair_delta_e_ok"])
        & (pair_hue >= gates["commanded_minimum_hue_gap_degrees"])
        & (feasible[:, None] != second[None, :])
    )
    cross = hue.raster_cross(
        rgb[feasible],
        rgb[second],
        state["width_contexts"][1.5],
        state["gains"],
        state["margin"],
    )
    to_fixed, fixed_floor = state["raster_fixed"][1.5]
    score = np.minimum(cross, fixed_floor)
    score = np.minimum(score, to_fixed[feasible, None])
    score = np.minimum(score, to_fixed[second][None, :])
    score[~valid] = -math.inf
    rows = {}
    for left, right in zip(*np.where(valid), strict=True):
        pair = tuple(sorted((catalog[int(feasible[left])].hex8, catalog[int(second[right])].hex8)))
        rows[pair] = max(rows.get(pair, -math.inf), float(score[left, right]))
    return sorted(((value, pair) for pair, value in rows.items()), reverse=True)


def best_third_for_pair(
    pair: tuple[str, str],
    catalog: Sequence[Any],
    rgb: np.ndarray,
    commanded: np.ndarray,
    transformed: np.ndarray,
    hues: np.ndarray,
    by_hex: Mapping[str, int],
    inputs: Any,
    contract: Mapping[str, Any],
) -> list[tuple[tuple[float, ...], tuple[str, ...], dict[str, Any]]]:
    existing_values = [*FIXED_THREE_AFTER_RELAXATION, *pair]
    existing_indices = np.asarray([by_hex[value] for value in existing_values], dtype=int)
    gates = contract["hard_gates"]
    valid = (
        np.min(
            np.linalg.norm(commanded[:, None] - commanded[existing_indices][None], axis=2) * 100.0,
            axis=1,
        )
        >= gates["commanded_category_pair_delta_e_ok"]
    )
    valid &= (
        np.min(
            np.linalg.norm(transformed[:, None] - transformed[existing_indices][None], axis=2)
            * 100.0,
            axis=1,
        )
        >= gates["nominal_transformed_category_pair_delta_e_ok"]
    )
    valid &= (
        np.min(hue.hue_delta(hues[:, None], hues[existing_indices][None]), axis=1)
        >= gates["commanded_minimum_hue_gap_degrees"]
    )
    valid[existing_indices] = False
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    margin = float(contract["raster"]["calibrated_error_margin_delta_e_ok"])
    fg_rgb = p3.parse_exact_hex8("#342F2C")
    to_existing, existing_floor = hue.raster_to_fixed(
        rgb,
        rgb[existing_indices],
        fg_rgb,
        hue.contexts(inputs, 1.5),
        gains,
        margin,
    )
    score = np.minimum(to_existing, existing_floor)
    score[~valid] = -math.inf
    best = float(np.max(score))
    candidates = np.flatnonzero(np.abs(score - best) <= 1e-12)
    candidates = sorted(candidates, key=lambda index: catalog[int(index)].hex8, reverse=True)[
        :THIRD_TIE_CAP
    ]
    rows = []
    for index in candidates:
        bank = seven.canonical_categories(
            [*FIXED_THREE_AFTER_RELAXATION, *pair, catalog[int(index)].hex8]
        )
        evaluation = seven.evaluate(bank, inputs, contract)
        if evaluation["hard_gate_failures"]:
            continue
        rows.append((tuple(evaluation["objective"]), bank, evaluation))
    return rows


def minimal_relaxation_search(
    catalog: Sequence[Any],
    rgb: np.ndarray,
    commanded: np.ndarray,
    transformed: np.ndarray,
    hues: np.ndarray,
    inputs: Any,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    state = fixed_state(
        FIXED_THREE_AFTER_RELAXATION,
        catalog,
        rgb,
        commanded,
        transformed,
        hues,
        inputs,
        contract,
    )
    pair_rows = pair_primary_candidates(state, catalog, rgb, commanded, transformed, hues, contract)
    require(bool(pair_rows), "no amber/golden pair after one-slot relaxation")
    by_hex = {row.hex8: index for index, row in enumerate(catalog)}
    finalists = []
    beam_count = min(PAIR_BEAM_CAP, len(pair_rows))
    for pair_index, (pair_primary, pair) in enumerate(pair_rows[:PAIR_BEAM_CAP], start=1):
        for objective, bank, evaluation in best_third_for_pair(
            pair,
            catalog,
            rgb,
            commanded,
            transformed,
            hues,
            by_hex,
            inputs,
            contract,
        ):
            finalists.append((objective, bank, evaluation, pair_primary, pair))
        if pair_index % 16 == 0 or pair_index == beam_count:
            print(
                f"[minimal-relaxation] pair-beam={pair_index}/{beam_count} "
                f"finalists={len(finalists)}",
                file=sys.stderr,
                flush=True,
            )
    require(bool(finalists), "no full bank after one-slot relaxation")
    objective, bank, evaluation, pair_primary, pair = max(
        finalists, key=lambda row: (row[0], row[1])
    )
    free_values = [value for value in bank if value not in FIXED_THREE_AFTER_RELAXATION]
    hue_family = next(
        value
        for value in free_values
        if 60.0 <= hue.lch_from_lab(catalog[by_hex[value]].commanded_oklab)[2] < 90.0
    )
    return {
        "lane": "PINK-SLOT-RELAXED",
        "display_name": "Minimal relaxation: free pink slot",
        "removed_fixed_color": "#B34B71",
        "remaining_fixed_colors": list(FIXED_THREE_AFTER_RELAXATION),
        "categories": list(bank),
        "free_colors": free_values,
        "hue_family_color": hue_family,
        "hue_family_oklch": list(hue.lch_from_lab(catalog[by_hex[hue_family]].commanded_oklab)),
        "candidate_id": p3.sha256_json(
            {
                "lane": "PINK-SLOT-RELAXED",
                "categories": list(bank),
                "contract": p3.sha256_json(contract),
            }
        ),
        "category_set_sha256": p3.bank_hash(bank),
        "objective": evaluation["objective"],
        "metrics": evaluation["metrics"],
        "hard_gate_failures": evaluation["hard_gate_failures"],
        "contrast": hue.contrast_payload(bank, inputs),
        "search": {
            "pair_beam_cap": PAIR_BEAM_CAP,
            "pair_beam_evaluated": min(PAIR_BEAM_CAP, len(pair_rows)),
            "third_tie_cap": THIRD_TIE_CAP,
            "exact_full_bank_count": len(finalists),
            "seed_pair_primary": pair_primary,
            "seed_pair": list(pair),
            "ranking": "full six-component objective then maximum canonical category tuple",
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
    influence = influence_analysis(catalog, rgb, commanded, transformed, hues, inputs, contract)
    amber_counts = {
        row["removed_fixed_color"]: row["bins"][0]["second_color_count"] for row in influence
    }
    binding = max((key for key in amber_counts if key != "NONE"), key=lambda key: amber_counts[key])
    require(binding == "#B34B71", "single-slot amber binding is not pink")
    minimal = minimal_relaxation_search(
        catalog, rgb, commanded, transformed, hues, inputs, contract
    )
    baseline_eval = seven.evaluate(BASELINE_A, inputs, contract)
    baseline_bank = seven.canonical_categories(BASELINE_A)
    fixed_frontier = json.loads((HERE / "hue-frontier/results.json").read_text())["browser_roles"][
        "b"
    ]
    baseline = {
        "lane": "BASELINE-A",
        "display_name": "Candidate A baseline",
        "categories": list(baseline_bank),
        "candidate_id": p3.sha256_json({"lane": "BASELINE-A", "categories": list(baseline_bank)}),
        "category_set_sha256": p3.bank_hash(baseline_bank),
        "objective": baseline_eval["objective"],
        "metrics": baseline_eval["metrics"],
        "hard_gate_failures": baseline_eval["hard_gate_failures"],
        "contrast": hue.contrast_payload(baseline_bank, inputs),
    }
    browser_roles = {
        "reference": baseline,
        "benchmark-c": fixed_frontier,
        "a": minimal,
        "b": minimal,
        "c": minimal,
    }
    return {
        "schema_version": 1,
        "artifact_kind": "seven-point-minimal-relaxation-frontier",
        "input_chain_sha256": p3.input_chain_sha256(inputs),
        "search_contract_sha256": p3.sha256_json(contract),
        "fixed_fg0": "#342F2C",
        "production": False,
        "selection": None,
        "constraint_influence": influence,
        "binding_fixed_slot": binding,
        "binding_mechanism": "removing #B34B71 expands exact amber second-color support from 2 to 85",
        "minimal_relaxation": minimal,
        "baseline": baseline,
        "fixed_four_frontier": fixed_frontier,
        "browser_roles": browser_roles,
        "catalog_summary": catalog_summary,
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
        require(not list(output.iterdir()), "minimal relaxation output must be empty")
    result = run()
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads(result).items():
        (output / name).write_bytes(json_bytes(payload))


def validate(artifact_dir: Path) -> None:
    directory = Path(artifact_dir)
    require(directory.is_dir(), "minimal relaxation artifacts missing")
    require(
        {path.name for path in directory.iterdir()} == set(EXPECTED_FILES), "artifact names differ"
    )
    actual = {name: json.loads((directory / name).read_text()) for name in EXPECTED_FILES}
    require(actual == payloads(run()), "minimal relaxation replay differs")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--output-dir", type=Path, required=True)
    v = sub.add_parser("validate")
    v.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "build":
        build(args.output_dir)
    else:
        validate(args.artifact_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
