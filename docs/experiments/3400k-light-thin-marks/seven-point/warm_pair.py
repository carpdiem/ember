#!/usr/bin/env python3
"""Focused exact-Hex refinement of Candidate A's two warm categorical colors."""

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
CONTRACT_PATH = HERE / "search-contract.json"
BASELINE_A = ("#7C140A", "#857D0B", "#0A6109", "#2B8CAD", "#5D53AE", "#B34B71")
FIXED_FOUR = ("#0A6109", "#2B8CAD", "#5D53AE", "#B34B71")
ROLE_ORDER = ("reference", "benchmark-c", "a", "b", "c")
LANE_SPECS = (
    {
        "id": "LIFT-ONLY",
        "browser_role": "benchmark-c",
        "display": "Lift only",
        "compliance": "FULL_3_0",
        "red_band": {"L": [0.40, 0.43], "C": [0.10, 0.14], "H": [25.0, 38.0]},
        "gold_band": {"L": [0.575, 0.595], "C": [0.08, 0.135], "H": [100.0, 110.0]},
        "target": {"red": [0.415, 0.13, 30.13], "gold": [0.589, 0.105, 104.95]},
    },
    {
        "id": "CLEAN-GOLD",
        "browser_role": "a",
        "display": "Clean gold",
        "compliance": "FULL_3_0",
        "red_band": {"L": [0.41, 0.435], "C": [0.09, 0.13], "H": [35.0, 46.0]},
        "gold_band": {"L": [0.56, 0.59], "C": [0.075, 0.115], "H": [88.0, 100.0]},
        "target": {"red": [0.425, 0.11, 40.0], "gold": [0.581, 0.1025, 94.0]},
    },
    {
        "id": "BRIGHT-WARM",
        "browser_role": "b",
        "display": "Bright warm",
        "compliance": "FULL_3_0",
        "red_band": {"L": [0.43, 0.45], "C": [0.085, 0.12], "H": [44.0, 55.0]},
        "gold_band": {"L": [0.56, 0.59], "C": [0.07, 0.115], "H": [88.0, 100.0]},
        "target": {"red": [0.44, 0.10, 52.0], "gold": [0.581, 0.10, 94.0]},
    },
    {
        "id": "PHOTOPIC-2.7",
        "browser_role": "c",
        "display": "Photopic 2.7 challenge",
        "compliance": "TRANSFORMED_BG1_2_7_EXCEPTION",
        "red_band": {"L": [0.43, 0.45], "C": [0.085, 0.12], "H": [44.0, 55.0]},
        "gold_band": {"L": [0.595, 0.625], "C": [0.09, 0.11], "H": [90.0, 98.0]},
        "target": {"red": [0.44, 0.10, 52.0], "gold": [0.612, 0.1025, 94.0]},
    },
)
EXPECTED_FILES = ("catalog-summary.json", "results.json")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seven = _load("seven_point_optimizer_for_warm_pair", "optimizer.py")
polish = _load("seven_point_polish_for_warm_pair", "polish.py")
p3 = seven.p3
srgb_to_oklab = seven.srgb_to_oklab
contrast_ratio = seven.contrast_ratio


class WarmPairError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WarmPairError(message)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    require(completed.returncode == 0 and len(commit) == 40, f"source is not committed: {relative}")
    return {"file": path.name, "sha256": sha256_file(path), "commit": commit}


def lch(row: Any) -> tuple[float, float, float]:
    lab = np.asarray(row.commanded_oklab, dtype=float)
    return (
        float(lab[0]),
        float(np.hypot(lab[1], lab[2])),
        float(np.degrees(np.arctan2(lab[2], lab[1])) % 360.0),
    )


def hue_delta(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.abs((left - right + 180.0) % 360.0 - 180.0)


def in_band(rows: Sequence[Any], band: Mapping[str, Sequence[float]]) -> np.ndarray:
    values = np.asarray([lch(row) for row in rows])
    return (
        (values[:, 0] >= band["L"][0])
        & (values[:, 0] <= band["L"][1])
        & (values[:, 1] >= band["C"][0])
        & (values[:, 1] <= band["C"][1])
        & (values[:, 2] >= band["H"][0])
        & (values[:, 2] <= band["H"][1])
    )


def custom_gold_rows(inputs: Any) -> list[Any]:
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    by_hex = {}
    for lightness in np.arange(0.595, 0.6251, 0.005):
        for chroma in np.arange(0.09, 0.1101, 0.005):
            for hue in np.arange(90.0, 98.01, 2.0):
                radians = np.radians(hue)
                proposal = np.asarray(
                    [lightness, chroma * np.cos(radians), chroma * np.sin(radians)]
                )
                rgb = seven.clean.oklab_to_srgb(proposal)
                if np.any(rgb < -1e-6) or np.any(rgb > 1.0 + 1e-6):
                    continue
                hex8 = p3.srgb_to_hex(rgb)
                exact_rgb = p3.parse_exact_hex8(hex8)
                commanded = srgb_to_oklab(exact_rgb)
                transformed = srgb_to_oklab(exact_rgb * gains)
                by_hex[hex8] = seven.SearchColor(
                    hex8=hex8,
                    commanded_oklab=tuple(float(value) for value in commanded),
                    transformed_oklab=tuple(float(value) for value in transformed),
                    hue_degrees=seven._hue(commanded),
                )
    return [by_hex[key] for key in sorted(by_hex)]


def proxy_between(left_rgb: np.ndarray, right_rgb: np.ndarray, tables: Any) -> np.ndarray:
    result = np.full((len(left_rgb), len(right_rgb)), math.inf)
    for lanes, background in tables.contexts:
        left_points = [
            srgb_to_oklab(
                (lanes[index] * left_rgb + (1.0 - lanes[index]) * background) * tables.gains
            )
            for index in (0, 1)
        ]
        right_points = [
            srgb_to_oklab(
                (lanes[index] * right_rgb + (1.0 - lanes[index]) * background) * tables.gains
            )
            for index in (0, 1)
        ]
        for left_lane, right_lane in ((0, 1), (1, 0)):
            distance = np.linalg.norm(
                left_points[left_lane][:, None, :] - right_points[right_lane][None, :, :],
                axis=2,
            )
            result = np.minimum(result, distance * 100.0 - tables.margin)
    return result


def target_distance(row: Any, target: Sequence[float]) -> float:
    lightness, chroma, hue = lch(row)
    return (
        ((lightness - target[0]) / 0.04) ** 2
        + ((chroma - target[1]) / 0.025) ** 2
        + (((hue - target[2] + 180.0) % 360.0 - 180.0) / 12.0) ** 2
    )


def contrast_payload(bank: Sequence[str], inputs: Any) -> dict[str, Any]:
    surfaces = inputs.baseline["family"]["surfaces"]
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    rows = {}
    for role, value in (("warm_red", bank[0]), ("warm_gold", bank[1])):
        rgb = p3.parse_exact_hex8(value)
        rows[role] = {}
        for state, state_gains in (("commanded", np.ones(3)), ("transformed", gains)):
            rows[role][state] = {
                background: contrast_ratio(
                    rgb * state_gains,
                    p3.parse_exact_hex8(surfaces[background]) * state_gains,
                )
                for background in ("bg_0", "bg_1")
            }
    return rows


def select_lane(
    spec: Mapping[str, Any],
    rows: Sequence[Any],
    tables: Any,
    inputs: Any,
    contract: Mapping[str, Any],
    benchmark_primary: float,
) -> dict[str, Any]:
    red_indices = np.flatnonzero(in_band(rows, spec["red_band"]))
    gold_indices = np.flatnonzero(in_band(rows, spec["gold_band"]))
    require(len(red_indices) > 0 and len(gold_indices) > 0, f"empty target pool for {spec['id']}")
    fixed_indices = [tables.by_hex[value] for value in FIXED_FOUR]
    fixed_rgb = tables.rgb[np.asarray(fixed_indices)]
    all_rgb = np.asarray([p3.parse_exact_hex8(row.hex8) for row in rows])
    to_fixed = proxy_between(all_rgb, fixed_rgb, tables)
    cross = proxy_between(all_rgb[red_indices], all_rgb[gold_indices], tables)
    fixed_floor = min(float(tables.fg_proxy[index]) for index in fixed_indices)
    baseline_pair = polish.catalog_to_bank_proxy(
        tables, fixed_indices + [tables.by_hex[BASELINE_A[0]], tables.by_hex[BASELINE_A[1]]]
    )
    for left, right in itertools.combinations(range(4), 2):
        fixed_floor = min(fixed_floor, float(baseline_pair[fixed_indices[left], right]))
    cmd = np.asarray([row.commanded_oklab for row in rows])
    transformed = np.asarray([row.transformed_oklab for row in rows])
    hues = np.asarray([row.hue_degrees for row in rows])
    fixed_cmd = np.asarray([srgb_to_oklab(p3.parse_exact_hex8(value)) for value in FIXED_FOUR])
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    fixed_transformed = np.asarray(
        [srgb_to_oklab(p3.parse_exact_hex8(value) * gains) for value in FIXED_FOUR]
    )
    fixed_hues = np.asarray([seven._hue(value) for value in fixed_cmd])
    gates = contract["hard_gates"]
    red_valid = (
        np.min(np.linalg.norm(cmd[red_indices, None] - fixed_cmd[None], axis=2) * 100.0, axis=1)
        >= gates["commanded_category_pair_delta_e_ok"]
    )
    red_valid &= (
        np.min(
            np.linalg.norm(transformed[red_indices, None] - fixed_transformed[None], axis=2)
            * 100.0,
            axis=1,
        )
        >= gates["nominal_transformed_category_pair_delta_e_ok"]
    )
    red_valid &= (
        np.min(hue_delta(hues[red_indices, None], fixed_hues[None]), axis=1)
        >= gates["commanded_minimum_hue_gap_degrees"]
    )
    gold_valid = (
        np.min(np.linalg.norm(cmd[gold_indices, None] - fixed_cmd[None], axis=2) * 100.0, axis=1)
        >= gates["commanded_category_pair_delta_e_ok"]
    )
    gold_valid &= (
        np.min(
            np.linalg.norm(transformed[gold_indices, None] - fixed_transformed[None], axis=2)
            * 100.0,
            axis=1,
        )
        >= gates["nominal_transformed_category_pair_delta_e_ok"]
    )
    gold_valid &= (
        np.min(hue_delta(hues[gold_indices, None], fixed_hues[None]), axis=1)
        >= gates["commanded_minimum_hue_gap_degrees"]
    )
    pair_cmd = np.linalg.norm(cmd[red_indices, None] - cmd[gold_indices][None], axis=2) * 100.0
    pair_transformed = (
        np.linalg.norm(transformed[red_indices, None] - transformed[gold_indices][None], axis=2)
        * 100.0
    )
    pair_hue = hue_delta(hues[red_indices, None], hues[gold_indices][None])
    valid = red_valid[:, None] & gold_valid[None, :]
    valid &= pair_cmd >= gates["commanded_category_pair_delta_e_ok"]
    valid &= pair_transformed >= gates["nominal_transformed_category_pair_delta_e_ok"]
    valid &= pair_hue >= gates["commanded_minimum_hue_gap_degrees"]
    score = np.minimum(cross, fixed_floor)
    score = np.minimum(score, tables.fg_proxy[red_indices, None])
    score = np.minimum(score, tables.fg_proxy[gold_indices][None, :])
    score = np.minimum(score, np.min(to_fixed[red_indices], axis=1)[:, None])
    score = np.minimum(score, np.min(to_fixed[gold_indices], axis=1)[None, :])
    valid &= score + 1e-12 >= benchmark_primary
    candidates = []
    for red_position, gold_position in zip(*np.where(valid), strict=True):
        red_index = int(red_indices[red_position])
        gold_index = int(gold_indices[gold_position])
        bank = seven.canonical_categories(
            [rows[red_index].hex8, rows[gold_index].hex8, *FIXED_FOUR]
        )
        fit = target_distance(rows[red_index], spec["target"]["red"]) + target_distance(
            rows[gold_index], spec["target"]["gold"]
        )
        candidates.append(
            (
                -fit,
                float(score[red_position, gold_position]),
                bank,
                red_index,
                gold_index,
            )
        )
    require(bool(candidates), f"no admissible exact pair for {spec['id']}")
    candidates.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    selected = None
    exact_evaluation_count = 0
    for _, _, bank, red_index, gold_index in candidates[:256]:
        evaluation = seven.evaluate(bank, inputs, contract)
        exact_evaluation_count += 1
        failures = evaluation["hard_gate_failures"]
        if spec["compliance"] == "FULL_3_0":
            if failures:
                continue
        else:
            if len(failures) != 1:
                continue
            failure = failures[0]
            if (
                failure["gate"] != "graphics-contrast/nominal-transformed/bg_1"
                or failure["actual"] + 1e-12 < 2.7
            ):
                continue
        selected = (bank, evaluation, failures, red_index, gold_index)
        break
    if selected is None:
        raise WarmPairError(f"no exact finalist survived for {spec['id']}")
    bank, evaluation, failures, red_index, gold_index = selected
    contrasts = contrast_payload(bank, inputs)
    if spec["compliance"] == "FULL_3_0":
        require(
            min(
                contrasts[role][state][background]
                for role in contrasts
                for state in contrasts[role]
                for background in contrasts[role][state]
            )
            >= 3.0,
            f"{spec['id']} violates the 3.0 graphics floor",
        )
    else:
        require(
            contrasts["warm_gold"]["transformed"]["bg_1"] >= 2.7,
            "photopic lane misses 2.7 transformed bg1 floor",
        )
    return {
        "lane": spec["id"],
        "display_name": spec["display"],
        "browser_role": spec["browser_role"],
        "compliance": spec["compliance"],
        "categories": list(bank),
        "warm_red": rows[red_index].hex8,
        "warm_gold": rows[gold_index].hex8,
        "warm_red_oklch": list(lch(rows[red_index])),
        "warm_gold_oklch": list(lch(rows[gold_index])),
        "candidate_id": p3.sha256_json(
            {"lane": spec["id"], "categories": list(bank), "contract": p3.sha256_json(contract)}
        ),
        "category_set_sha256": p3.bank_hash(bank),
        "metrics": evaluation["metrics"],
        "objective": evaluation["objective"],
        "hard_gate_failures": failures,
        "contrast": contrasts,
        "search": {
            "red_pool_count": len(red_indices),
            "gold_pool_count": len(gold_indices),
            "pair_evaluation_count": len(red_indices) * len(gold_indices),
            "admissible_pair_count": len(candidates),
            "exact_evaluation_count": exact_evaluation_count,
            "exact_evaluation_cap": 256,
            "target_band": {"red": spec["red_band"], "gold": spec["gold_band"]},
            "target": spec["target"],
        },
    }


def run() -> dict[str, Any]:
    inputs = seven.load_inputs(replay=False)
    contract = seven.load_contract(CONTRACT_PATH)
    seven.validate_contract(contract, inputs)
    tables, catalog_summary = polish.build_catalog_tables(inputs, contract, progress=True)
    custom = custom_gold_rows(inputs)
    union = {row.hex8: row for row in tables.catalog}
    union.update({row.hex8: row for row in custom})
    rows = [union[key] for key in sorted(union)]
    # Rebuild table arrays for the exact union while preserving the calibrated contexts.
    rgb = np.asarray([p3.parse_exact_hex8(row.hex8) for row in rows])
    commanded = np.asarray([row.commanded_oklab for row in rows])
    transformed = np.asarray([row.transformed_oklab for row in rows])
    hues = np.asarray([row.hue_degrees for row in rows])
    fg0 = p3.parse_exact_hex8("#342F2C")
    fg_proxy = np.full(len(rows), math.inf)
    for lanes, background in tables.contexts:
        points = [
            srgb_to_oklab((lanes[index] * rgb + (1.0 - lanes[index]) * background) * tables.gains)
            for index in (0, 1)
        ]
        fg_points = [
            srgb_to_oklab((lanes[index] * fg0 + (1.0 - lanes[index]) * background) * tables.gains)
            for index in (0, 1)
        ]
        for left_lane, right_lane in ((0, 1), (1, 0)):
            fg_proxy = np.minimum(
                fg_proxy,
                np.linalg.norm(points[left_lane] - fg_points[right_lane], axis=1) * 100.0
                - tables.margin,
            )
    union_tables = polish.CatalogTables(
        catalog=tuple(rows),
        rgb=rgb,
        commanded=commanded,
        transformed=transformed,
        hues=hues,
        fg_proxy=fg_proxy,
        contexts=tables.contexts,
        gains=tables.gains,
        margin=tables.margin,
        by_hex={row.hex8: index for index, row in enumerate(rows)},
    )
    benchmark = seven.evaluate(seven.benchmark_categories(inputs, contract), inputs, contract)
    benchmark_primary = float(benchmark["metrics"]["primary_raw_symmetric_scalar"])
    lanes = [
        select_lane(spec, rows, union_tables, inputs, contract, benchmark_primary)
        for spec in LANE_SPECS
    ]
    # The exact target bands must remain materially different after transformation.
    warm_points = [
        np.concatenate(
            [
                np.asarray(
                    row["metrics"]["nominal_transformed_solid_all_21"]["delta_e_ok"]
                ).reshape(1),
                srgb_to_oklab(p3.parse_exact_hex8(row["warm_red"]) * union_tables.gains),
                srgb_to_oklab(p3.parse_exact_hex8(row["warm_gold"]) * union_tables.gains),
            ]
        )
        for row in lanes
    ]
    for left, right in itertools.combinations(range(len(lanes)), 2):
        require(
            bool(np.linalg.norm(warm_points[left][1:] - warm_points[right][1:]) * 100.0 >= 2.0),
            f"warm lanes are transformed near-clones: {lanes[left]['lane']} / {lanes[right]['lane']}",
        )
    baseline = seven.evaluate(BASELINE_A, inputs, contract)
    baseline_row = {
        "lane": "BASELINE-A",
        "display_name": "Candidate A baseline",
        "browser_role": "reference",
        "compliance": "FULL_3_0",
        "categories": list(seven.canonical_categories(BASELINE_A)),
        "candidate_id": p3.sha256_json({"lane": "BASELINE-A", "categories": list(BASELINE_A)}),
        "category_set_sha256": p3.bank_hash(seven.canonical_categories(BASELINE_A)),
        "metrics": baseline["metrics"],
        "objective": baseline["objective"],
        "hard_gate_failures": baseline["hard_gate_failures"],
        "contrast": contrast_payload(seven.canonical_categories(BASELINE_A), inputs),
    }
    browser_roles = {"reference": baseline_row}
    browser_roles.update({row["browser_role"]: row for row in lanes})
    require(tuple(browser_roles) == ROLE_ORDER, "warm browser role order differs")
    return {
        "schema_version": 1,
        "artifact_kind": "seven-point-warm-pair-refinement",
        "input_chain_sha256": p3.input_chain_sha256(inputs),
        "search_contract_sha256": p3.sha256_json(contract),
        "fixed_fg0": "#342F2C",
        "fixed_four": list(FIXED_FOUR),
        "motivation": "Michael found Candidate A category-2 #857D0B ugly; this is a human aesthetic correction, not scalar-optimizer churn.",
        "benchmark_prior_c_proxy": benchmark_primary,
        "selection": None,
        "production": False,
        "catalog_summary": {
            **catalog_summary,
            "custom_photopic_gold_count": len(custom),
            "union_exact_hex8_count": len(rows),
        },
        "baseline": baseline_row,
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
        require(not list(output.iterdir()), "warm output directory must be empty")
    result = run()
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads(result).items():
        (output / name).write_bytes(json_bytes(payload))


def validate(artifact_dir: Path) -> None:
    directory = Path(artifact_dir)
    require(directory.is_dir(), "warm artifact directory is missing")
    require(
        {path.name for path in directory.iterdir()} == set(EXPECTED_FILES),
        "warm artifact filenames differ",
    )
    actual = {name: json.loads((directory / name).read_text()) for name in EXPECTED_FILES}
    require(actual == payloads(run()), "warm artifact deterministic replay differs")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--output-dir", type=Path, required=True)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        build(args.output_dir)
        return 0
    if args.command == "validate":
        validate(args.artifact_dir)
        return 0
    raise WarmPairError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
