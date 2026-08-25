#!/usr/bin/env python3
"""Bounded full-catalog coordinate polish for fixed-fg0 seven-point finalists."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
ROOT = EXPERIMENT.parents[2]
SEED_PATH = HERE / "smoke-seeds.json"
CONTRACT_PATH = HERE / "search-contract.json"
EXPECTED_FILES = ("catalog-summary.json", "results.json")
MAX_PASSES = 6
MAX_TOTAL_RUNTIME_SECONDS = 240.0
MAX_LANE_RUNTIME_SECONDS = 90.0
MAX_EXACT_FINALISTS_PER_SWEEP = 24
MAX_EXACT_EVALUATIONS_PER_LANE = 1 + MAX_PASSES * MAX_EXACT_FINALISTS_PER_SWEEP
MIN_PRIMARY_IMPROVEMENT = 1e-9
BACKGROUND_NAMES = ("bg_0", "bg_1")


def _load_seven():
    spec = importlib.util.spec_from_file_location(
        "seven_point_optimizer_for_polish", HERE / "optimizer.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load seven-point optimizer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seven = _load_seven()
p3 = seven.p3
srgb_to_oklab = seven.srgb_to_oklab


class PolishError(RuntimeError):
    """Raised when bounded-polish evidence is malformed or inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PolishError(message)


def _exact_keys(value: object, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PolishError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise PolishError(f"{label} keys differ: {sorted(actual ^ expected)}")
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_commit(path: Path) -> str:
    relative = str(path.resolve().relative_to(ROOT))
    completed = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", relative],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    commit = completed.stdout.strip()
    if completed.returncode != 0 or len(commit) != 40:
        raise PolishError(f"source file is not committed: {relative}")
    return commit


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise PolishError(f"{label} must be an object")
    return value


def _hue_delta(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.abs((left - right + 180.0) % 360.0 - 180.0)


@dataclass(frozen=True)
class CatalogTables:
    catalog: tuple[Any, ...]
    rgb: np.ndarray
    commanded: np.ndarray
    transformed: np.ndarray
    hues: np.ndarray
    fg_proxy: np.ndarray
    contexts: tuple[tuple[Mapping[int, float], np.ndarray], ...]
    gains: np.ndarray
    margin: float
    by_hex: Mapping[str, int]


def validate_seeds(
    seeds: Mapping[str, Any], inputs: Any, contract: Mapping[str, Any]
) -> list[dict[str, Any]]:
    row = _exact_keys(
        seeds,
        {
            "artifact_kind",
            "candidates",
            "finalist_limit",
            "fixed_fg_0",
            "input_chain_sha256",
            "objective_tolerance",
            "production",
            "schema_version",
            "search_contract_sha256",
            "selection",
            "source_command",
            "source_exact_catalog_count",
            "source_results_sha256",
            "threshold_iterations",
        },
        "smoke seeds",
    )
    _require(row["schema_version"] == 1, "smoke seed schema differs")
    _require(row["artifact_kind"] == "seven-point-940-color-smoke-seeds", "seed kind differs")
    _require(row["input_chain_sha256"] == p3.input_chain_sha256(inputs), "seed input chain differs")
    _require(row["search_contract_sha256"] == p3.sha256_json(contract), "seed contract differs")
    _require(row["fixed_fg_0"] == contract["fixed"]["fg_0"] == "#342F2C", "seed fg0 differs")
    _require(row["threshold_iterations"] == 16, "seed threshold iterations weakened")
    _require(row["finalist_limit"] == 24, "seed finalist limit weakened")
    _require(row["objective_tolerance"] == 0.001, "seed objective tolerance weakened")
    _require(row["source_exact_catalog_count"] == 940, "seed catalog count differs")
    _require(row["selection"] is None and row["production"] is False, "seed makes promotion claim")
    candidates = row["candidates"]
    _require(isinstance(candidates, list) and len(candidates) == 3, "seed candidates differ")
    expected_lanes = [(lane["id"], lane["method"]) for lane in contract["lanes"]]
    _require(
        [(candidate.get("lane"), candidate.get("method")) for candidate in candidates]
        == expected_lanes,
        "seed lane order differs",
    )
    validated = []
    for candidate in candidates:
        item = _exact_keys(
            candidate,
            {
                "categories",
                "category_set_sha256",
                "lane",
                "method",
                "primary_raw_symmetric_scalar",
            },
            f"seed lane {candidate.get('lane')}",
        )
        bank = seven.canonical_categories(item["categories"])
        _require(p3.bank_hash(bank) == item["category_set_sha256"], "seed bank hash differs")
        evaluation = seven.evaluate(bank, inputs, contract)
        _require(evaluation["hard_gate_failures"] == [], "seed fails a hard gate")
        _require(
            evaluation["metrics"]["primary_raw_symmetric_scalar"]
            == item["primary_raw_symmetric_scalar"],
            "seed primary differs from exact recomputation",
        )
        validated.append(dict(item))
    return validated


def build_catalog_tables(
    inputs: Any, contract: Mapping[str, Any], *, progress: bool
) -> tuple[CatalogTables, dict[str, Any]]:
    started = time.perf_counter()
    catalog, summary = seven.build_catalog(inputs, contract, smoke=False)
    rgb = np.asarray([p3.parse_exact_hex8(row.hex8) for row in catalog])
    commanded = np.asarray([row.commanded_oklab for row in catalog])
    transformed = np.asarray([row.transformed_oklab for row in catalog])
    hues = np.asarray([row.hue_degrees for row in catalog])
    surfaces = inputs.baseline["family"]["surfaces"]
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    margin = float(contract["raster"]["calibrated_error_margin_delta_e_ok"])
    contexts = tuple(
        (lanes, p3.parse_exact_hex8(surfaces[background_name]))
        for geometry, lanes in p3._mask_summaries(inputs).items()
        if geometry[0] == 1.5
        for background_name in BACKGROUND_NAMES
    )
    fg0 = p3.parse_exact_hex8(surfaces["fg_0"])
    fg_proxy = np.full(len(catalog), math.inf)
    for lanes, background in contexts:
        points = [
            srgb_to_oklab((lanes[index] * rgb + (1.0 - lanes[index]) * background) * gains)
            for index in (0, 1)
        ]
        fg_points = [
            srgb_to_oklab((lanes[index] * fg0 + (1.0 - lanes[index]) * background) * gains)
            for index in (0, 1)
        ]
        for left_lane, right_lane in ((0, 1), (1, 0)):
            fg_proxy = np.minimum(
                fg_proxy,
                np.linalg.norm(points[left_lane] - fg_points[right_lane], axis=1) * 100.0 - margin,
            )
    tables = CatalogTables(
        catalog=tuple(catalog),
        rgb=rgb,
        commanded=commanded,
        transformed=transformed,
        hues=hues,
        fg_proxy=fg_proxy,
        contexts=contexts,
        gains=gains,
        margin=margin,
        by_hex={row.hex8: index for index, row in enumerate(catalog)},
    )
    if progress:
        print(
            f"[seven-polish] catalog-ready colors={len(catalog)} contexts={len(contexts)} "
            f"seconds={time.perf_counter() - started:.3f}",
            file=sys.stderr,
            flush=True,
        )
    return tables, summary


def catalog_to_bank_proxy(tables: CatalogTables, bank_indices: Sequence[int]) -> np.ndarray:
    bank_rgb = tables.rgb[np.asarray(bank_indices, dtype=int)]
    result = np.full((len(tables.catalog), 6), math.inf)
    for lanes, background in tables.contexts:
        catalog_points = [
            srgb_to_oklab(
                (lanes[index] * tables.rgb + (1.0 - lanes[index]) * background) * tables.gains
            )
            for index in (0, 1)
        ]
        bank_points = [
            srgb_to_oklab(
                (lanes[index] * bank_rgb + (1.0 - lanes[index]) * background) * tables.gains
            )
            for index in (0, 1)
        ]
        for left_lane, right_lane in ((0, 1), (1, 0)):
            distance = np.linalg.norm(
                catalog_points[left_lane][:, None, :] - bank_points[right_lane][None, :, :],
                axis=2,
            )
            result = np.minimum(result, distance * 100.0 - tables.margin)
    return result


def _lane_candidate_mask(
    tables: CatalogTables,
    lane: Mapping[str, Any],
    bank_indices: Sequence[int],
    slot: int,
) -> np.ndarray:
    mask = np.asarray([seven._lane_color_eligible(row, lane) for row in tables.catalog])
    if lane["id"] != "C":
        return mask
    lightness = tables.commanded[:, 0]
    lower = lightness <= lane["lower_lightness"][1]
    upper = lightness >= lane["upper_lightness"][0]
    current_lower = tables.commanded[np.asarray(bank_indices), 0] <= lane["lower_lightness"][1]
    lower_without = int(np.sum(current_lower)) - int(current_lower[slot])
    upper_without = 5 - lower_without
    return mask & (((lower_without + lower) == 3) & ((upper_without + upper) == 3))


def _unaffected_primary(
    tables: CatalogTables,
    pair_proxy: np.ndarray,
    bank_indices: Sequence[int],
    slot: int,
) -> float:
    others = [index for index in range(6) if index != slot]
    values = [float(tables.fg_proxy[bank_indices[index]]) for index in others]
    for left, right in itertools.combinations(others, 2):
        values.append(float(pair_proxy[bank_indices[left], right]))
    return min(values)


def best_swap_per_slot(
    tables: CatalogTables,
    contract: Mapping[str, Any],
    lane: Mapping[str, Any],
    bank: Sequence[str],
    pair_proxy: np.ndarray,
) -> tuple[list[tuple[float, int, int, tuple[str, ...]]], int]:
    bank_indices = [tables.by_hex[hex8] for hex8 in bank]
    gates = contract["hard_gates"]
    proposals = []
    evaluations = 0
    for slot in range(6):
        others = [index for index in range(6) if index != slot]
        other_indices = np.asarray([bank_indices[index] for index in others], dtype=int)
        valid = _lane_candidate_mask(tables, lane, bank_indices, slot)
        for other_index in other_indices:
            valid[other_index] = False
        commanded_distance = (
            np.linalg.norm(
                tables.commanded[:, None, :] - tables.commanded[other_indices][None, :, :],
                axis=2,
            )
            * 100.0
        )
        transformed_distance = (
            np.linalg.norm(
                tables.transformed[:, None, :] - tables.transformed[other_indices][None, :, :],
                axis=2,
            )
            * 100.0
        )
        hue_distance = _hue_delta(tables.hues[:, None], tables.hues[other_indices][None, :])
        valid &= (
            np.min(commanded_distance, axis=1) + 1e-12
            >= gates["commanded_category_pair_delta_e_ok"]
        )
        valid &= (
            np.min(transformed_distance, axis=1) + 1e-12
            >= gates["nominal_transformed_category_pair_delta_e_ok"]
        )
        valid &= np.min(hue_distance, axis=1) + 1e-12 >= gates["commanded_minimum_hue_gap_degrees"]
        unaffected = _unaffected_primary(tables, pair_proxy, bank_indices, slot)
        scores = np.minimum(
            np.minimum(tables.fg_proxy, np.min(pair_proxy[:, others], axis=1)),
            unaffected,
        )
        scores[~valid] = -math.inf
        best_score = float(np.max(scores))
        if not math.isfinite(best_score):
            continue
        best_indices = np.flatnonzero(np.abs(scores - best_score) <= 1e-12)
        candidate_rows = []
        for catalog_index in best_indices:
            candidate = list(bank)
            candidate[slot] = tables.catalog[int(catalog_index)].hex8
            canonical = seven.canonical_categories(candidate)
            candidate_rows.append((canonical, int(catalog_index)))
        for canonical, catalog_index in sorted(candidate_rows, reverse=True):
            proposals.append((best_score, slot, catalog_index, canonical))
        evaluations += len(tables.catalog)
    return proposals, evaluations


def select_exact_best(rows: Sequence[tuple[Any, ...]]) -> tuple[Any, ...]:
    """Match optimizer.py: maximize objective, then canonical category tuple."""

    if not rows:
        raise PolishError("cannot select from an empty exact finalist set")
    return max(rows, key=lambda row: (row[0], row[1]))


def bounded_primary_ties(
    proposals: Sequence[tuple[float, int, int, tuple[str, ...]]], remaining: int
) -> list[tuple[float, int, int, tuple[str, ...]]]:
    """Dedupe exact-primary ties, prefer canonical maxima, and cap the sweep."""

    if remaining <= 0 or not proposals:
        return []
    best_primary = max(row[0] for row in proposals)
    unique = {
        proposal[3]: proposal for proposal in proposals if abs(proposal[0] - best_primary) <= 1e-12
    }
    ordered = [unique[key] for key in sorted(unique, reverse=True)]
    return ordered[: min(MAX_EXACT_FINALISTS_PER_SWEEP, remaining)]


def polish_lane(
    seed: Mapping[str, Any],
    tables: CatalogTables,
    inputs: Any,
    contract: Mapping[str, Any],
    lane: Mapping[str, Any],
    *,
    total_started: float,
    progress: bool,
) -> dict[str, Any]:
    lane_started = time.perf_counter()
    bank = seven.canonical_categories(seed["categories"])
    current = seven.evaluate(bank, inputs, contract)
    seed_primary = float(current["metrics"]["primary_raw_symmetric_scalar"])
    ledger = []
    proxy_evaluations = 0
    exact_evaluations = 1
    stop_reason = "pass_cap"
    for pass_index in range(1, MAX_PASSES + 1):
        elapsed_lane = time.perf_counter() - lane_started
        elapsed_total = time.perf_counter() - total_started
        if elapsed_lane >= MAX_LANE_RUNTIME_SECONDS:
            stop_reason = "lane_runtime_cap"
            break
        if elapsed_total >= MAX_TOTAL_RUNTIME_SECONDS:
            stop_reason = "total_runtime_cap"
            break
        pass_started = time.perf_counter()
        bank_indices = [tables.by_hex[hex8] for hex8 in bank]
        pair_proxy = catalog_to_bank_proxy(tables, bank_indices)
        proposals, scanned = best_swap_per_slot(tables, contract, lane, bank, pair_proxy)
        proxy_evaluations += scanned
        remaining_exact = MAX_EXACT_EVALUATIONS_PER_LANE - exact_evaluations
        if remaining_exact <= 0:
            stop_reason = "exact_evaluation_cap"
            break
        proposals = bounded_primary_ties(proposals, remaining_exact)
        exact_rows = []
        for proxy_primary, slot, catalog_index, candidate_bank in proposals:
            evaluation = seven.evaluate(candidate_bank, inputs, contract)
            exact_evaluations += 1
            if evaluation["hard_gate_failures"]:
                continue
            exact_rows.append(
                (
                    tuple(evaluation["objective"]),
                    candidate_bank,
                    evaluation,
                    proxy_primary,
                    slot,
                    catalog_index,
                )
            )
        if not exact_rows:
            stop_reason = "no_admissible_swap"
            break
        best = select_exact_best(exact_rows)
        _objective, candidate_bank, evaluation, proxy_primary, slot, catalog_index = best
        current_primary = float(current["metrics"]["primary_raw_symmetric_scalar"])
        candidate_primary = float(evaluation["metrics"]["primary_raw_symmetric_scalar"])
        if candidate_primary <= current_primary + MIN_PRIMARY_IMPROVEMENT:
            stop_reason = "coordinate_local_optimum"
            if progress:
                print(
                    f"[seven-polish] lane={lane['id']} pass={pass_index} "
                    f"current={current_primary:.9f} best={candidate_primary:.9f} "
                    f"stop={stop_reason} seconds={time.perf_counter() - pass_started:.3f}",
                    file=sys.stderr,
                    flush=True,
                )
            break
        old_bank = bank
        bank = candidate_bank
        current = evaluation
        ledger.append(
            {
                "pass": pass_index,
                "slot": slot,
                "removed_hex8": old_bank[slot],
                "added_hex8": tables.catalog[catalog_index].hex8,
                "proxy_primary": proxy_primary,
                "before_primary": current_primary,
                "after_primary": candidate_primary,
                "category_set_sha256": p3.bank_hash(bank),
            }
        )
        if progress:
            print(
                f"[seven-polish] lane={lane['id']} pass={pass_index} slot={slot} "
                f"before={current_primary:.9f} after={candidate_primary:.9f} "
                f"scans={scanned} exact={len(exact_rows)} "
                f"seconds={time.perf_counter() - pass_started:.3f}",
                file=sys.stderr,
                flush=True,
            )
    final_primary = float(current["metrics"]["primary_raw_symmetric_scalar"])
    _require(final_primary + 1e-12 >= seed_primary, f"lane {lane['id']} regressed from seed")
    _require(current["hard_gate_failures"] == [], f"lane {lane['id']} final bank fails gates")
    return {
        "candidate_id": p3.sha256_json(
            {
                "categories": list(bank),
                "contract": p3.sha256_json(contract),
                "lane": lane["id"],
                "method": "bounded-full-catalog-coordinate-polish",
            }
        ),
        "lane": lane["id"],
        "method": lane["method"],
        "polish_method": "bounded-full-catalog-coordinate-polish",
        "categories": list(bank),
        "category_set_sha256": p3.bank_hash(bank),
        "seed_categories": list(seven.canonical_categories(seed["categories"])),
        "seed_category_set_sha256": seed["category_set_sha256"],
        "seed_primary_raw_symmetric_scalar": seed_primary,
        "metrics": current["metrics"],
        "objective": current["objective"],
        "hard_gate_failures": current["hard_gate_failures"],
        "primary_improvement_over_seed": final_primary - seed_primary,
        "changed_from_seed": tuple(bank) != tuple(seven.canonical_categories(seed["categories"])),
        "polish": {
            "pass_cap": MAX_PASSES,
            "passes_accepted": len(ledger),
            "proxy_evaluation_count": proxy_evaluations,
            "exact_evaluation_count": exact_evaluations,
            "lane_runtime_cap_seconds": MAX_LANE_RUNTIME_SECONDS,
            "stop_reason": stop_reason,
            "ledger": ledger,
        },
    }


def run_polish(*, progress: bool = False) -> dict[str, Any]:
    total_started = time.perf_counter()
    inputs = seven.load_inputs(replay=False)
    contract = seven.load_contract(CONTRACT_PATH)
    seven.validate_contract(contract, inputs)
    seeds_payload = _load_json(SEED_PATH, "smoke seeds")
    seeds = validate_seeds(seeds_payload, inputs, contract)
    tables, catalog_summary = build_catalog_tables(inputs, contract, progress=progress)
    lanes = {lane["id"]: lane for lane in contract["lanes"]}
    candidates = []
    for seed in seeds:
        candidates.append(
            polish_lane(
                seed,
                tables,
                inputs,
                contract,
                lanes[seed["lane"]],
                total_started=total_started,
                progress=progress,
            )
        )
    total_runtime = time.perf_counter() - total_started
    _require(total_runtime <= MAX_TOTAL_RUNTIME_SECONDS + 5.0, "total runtime cap exceeded")
    return {
        "schema_version": 1,
        "artifact_kind": "seven-point-bounded-full-catalog-polish",
        "input_chain_sha256": p3.input_chain_sha256(inputs),
        "search_contract_sha256": p3.sha256_json(contract),
        "fixed_fg0": contract["fixed"]["fg_0"],
        "production": False,
        "selection": None,
        "human_capacity": None,
        "objective_policy": {
            "kind": "single-raw-symmetric-minimum",
            "pair_count": 21,
            "lane_directions": 2,
            "class_normalization": False,
            "role_semantics": False,
            "churn": False,
            "exact_tie_break": "maximum canonical category tuple after six-component objective",
        },
        "bounds": {
            "pass_cap": MAX_PASSES,
            "lane_runtime_cap_seconds": MAX_LANE_RUNTIME_SECONDS,
            "total_runtime_cap_seconds": MAX_TOTAL_RUNTIME_SECONDS,
            "exact_evaluation_cap_per_lane": MAX_EXACT_EVALUATIONS_PER_LANE,
            "exact_finalist_cap_per_sweep": MAX_EXACT_FINALISTS_PER_SWEEP,
            "minimum_primary_improvement": MIN_PRIMARY_IMPROVEMENT,
        },
        "seed_source": {
            "file": SEED_PATH.name,
            "sha256": _sha256_file(SEED_PATH),
            "source_results_sha256": seeds_payload["source_results_sha256"],
            "exact_catalog_count": seeds_payload["source_exact_catalog_count"],
            "threshold_iterations": seeds_payload["threshold_iterations"],
            "finalist_limit": seeds_payload["finalist_limit"],
            "objective_tolerance": seeds_payload["objective_tolerance"],
        },
        "polish_source": {
            "file": Path(__file__).name,
            "sha256": _sha256_file(Path(__file__)),
            "commit": _source_commit(Path(__file__)),
        },
        "optimizer_source": {
            "file": "optimizer.py",
            "sha256": _sha256_file(HERE / "optimizer.py"),
            "commit": _source_commit(HERE / "optimizer.py"),
        },
        "catalog_summary": catalog_summary,
        "candidates": candidates,
    }


def _payloads(result: Mapping[str, Any]) -> dict[str, Any]:
    summary = dict(result["catalog_summary"])
    summary["polish_seed_file"] = SEED_PATH.name
    summary["polish_seed_sha256"] = result["seed_source"]["sha256"]
    return {
        "catalog-summary.json": summary,
        "results.json": {key: value for key, value in result.items() if key != "catalog_summary"},
    }


def build(output_dir: Path, *, progress: bool) -> dict[str, Path]:
    inputs = seven.load_inputs(replay=False)
    output = p3.validate_external_output_path(Path(output_dir), inputs)
    if output.exists():
        entries = list(output.iterdir())
        if entries:
            raise PolishError("polish output directory must be empty")
    result = run_polish(progress=progress)
    output.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, payload in _payloads(result).items():
        path = output / name
        path.write_bytes(_json_bytes(payload))
        paths[name] = path
    return paths


def validate(artifact_dir: Path, *, progress: bool) -> None:
    directory = Path(artifact_dir).resolve()
    _require(directory.is_dir(), "polish artifact directory does not exist")
    entries = list(directory.iterdir())
    _require(
        all(path.is_file() for path in entries)
        and {path.name for path in entries} == set(EXPECTED_FILES),
        "polish artifact directory violates closed filenames",
    )
    actual = {name: json.loads((directory / name).read_text()) for name in EXPECTED_FILES}
    expected = _payloads(run_polish(progress=progress))
    _require(actual == expected, "polish artifact deterministic replay differs")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--output-dir", type=Path, required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        build(args.output_dir, progress=True)
        return 0
    if args.command == "validate":
        validate(args.artifact_dir, progress=True)
        return 0
    raise PolishError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
