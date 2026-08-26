#!/usr/bin/env python3
"""De novo six-color rebuild excluding commanded Oklch hue 92° through 118°."""

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
FORBIDDEN_HUE_ARC = (92.0, 118.0)
DISCOVERY_THRESHOLD_ITERATIONS = 16
DISCOVERY_FINALIST_LIMIT = 24
OBJECTIVE_EQUALITY_TOLERANCE = 0.001
POLISH_PASS_CAP = 6
EXPECTED_FILES = ("catalog-summary.json", "results.json")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seven = _load("seven_for_forbidden_arc", "optimizer.py")
polish = _load("polish_for_forbidden_arc", "polish.py")
p3 = seven.p3
srgb_to_oklab = seven.srgb_to_oklab


class ForbiddenArcError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ForbiddenArcError(message)


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


def hue_allowed(hue: float) -> bool:
    return not (FORBIDDEN_HUE_ARC[0] <= float(hue) <= FORBIDDEN_HUE_ARC[1])


def filter_catalog(catalog: Sequence[Any]) -> list[Any]:
    return [row for row in catalog if hue_allowed(row.hue_degrees)]


def objective_better(left: Sequence[float], right: Sequence[float]) -> bool:
    for left_value, right_value in zip(left, right, strict=True):
        if abs(float(left_value) - float(right_value)) <= OBJECTIVE_EQUALITY_TOLERANCE:
            continue
        return float(left_value) > float(right_value)
    return False


def select_objective_row(rows: Sequence[tuple[Any, ...]]) -> tuple[Any, ...]:
    require(bool(rows), "cannot select empty objective rows")
    best = rows[0]
    for row in rows[1:]:
        if objective_better(row[0], best[0]) or (
            not objective_better(best[0], row[0]) and row[1] > best[1]
        ):
            best = row
    return best


def hue_support(catalog: Sequence[Any]) -> dict[str, Any]:
    hues = sorted(float(row.hue_degrees) for row in catalog)
    bins = sorted({int(value // 12) for value in hues})
    return {
        "minimum_degrees": min(hues),
        "maximum_degrees": max(hues),
        "occupied_12_degree_bins": bins,
        "forbidden_arc_degrees": list(FORBIDDEN_HUE_ARC),
        "forbidden_arc_color_count": sum(
            FORBIDDEN_HUE_ARC[0] <= value <= FORBIDDEN_HUE_ARC[1] for value in hues
        ),
    }


def catalog_tables(catalog: Sequence[Any], inputs: Any, contract: Mapping[str, Any]) -> Any:
    rgb = np.asarray([p3.parse_exact_hex8(row.hex8) for row in catalog])
    commanded = np.asarray([row.commanded_oklab for row in catalog])
    transformed = np.asarray([row.transformed_oklab for row in catalog])
    hues = np.asarray([row.hue_degrees for row in catalog])
    surfaces = inputs.baseline["family"]["surfaces"]
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    margin = float(contract["raster"]["calibrated_error_margin_delta_e_ok"])
    contexts = tuple(
        (lanes, p3.parse_exact_hex8(surfaces[background]))
        for geometry, lanes in p3._mask_summaries(inputs).items()
        if float(geometry[0]) == 1.5
        for background in ("bg_0", "bg_1")
    )
    fg0 = p3.parse_exact_hex8("#342F2C")
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
    return polish.CatalogTables(
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


def discover(
    catalog: Sequence[Any],
    inputs: Any,
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    # The existing clique implementation adds contract materiality (+1) to the
    # supplied benchmark. -1 therefore yields an objective-independent zero floor.
    zero_floor_benchmark = -1.0
    shared = seven._shared_proxy_tables(
        catalog,
        inputs,
        contract,
        target=0.0,
        progress=True,
    )
    rows = []
    for lane in contract["lanes"]:
        found = seven._search_lane_clique(
            catalog,
            lane,
            inputs,
            contract,
            zero_floor_benchmark,
            shared,
            smoke=True,
            progress=True,
        )
        require(found is not None, f"filtered discovery lane infeasible: {lane['id']}")
        categories, details = found
        evaluation = details["evaluation"]
        require(evaluation["hard_gate_failures"] == [], f"discovery gate failure {lane['id']}")
        rows.append(
            {
                "lane": lane["id"],
                "method": lane["method"],
                "categories": list(categories),
                "objective": evaluation["objective"],
                "metrics": evaluation["metrics"],
                "search": details["search"],
            }
        )
    require(
        all(
            row["search"]["threshold_iterations"] == DISCOVERY_THRESHOLD_ITERATIONS for row in rows
        ),
        "discovery threshold iterations weakened",
    )
    require(
        all(row["search"]["finalist_clique_count"] <= DISCOVERY_FINALIST_LIMIT for row in rows),
        "discovery finalist limit differs",
    )
    return rows


def unaffected_primary(
    tables: Any,
    pair_proxy: np.ndarray,
    bank_indices: Sequence[int],
    slot: int,
) -> float:
    others = [index for index in range(6) if index != slot]
    values = [float(tables.fg_proxy[bank_indices[index]]) for index in others]
    for left, right in itertools.combinations(others, 2):
        values.append(float(pair_proxy[bank_indices[left], right]))
    return min(values)


def lane_mask(
    tables: Any,
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


def polish_lane(
    seed: Mapping[str, Any],
    lane: Mapping[str, Any],
    tables: Any,
    inputs: Any,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    bank = seven.canonical_categories(seed["categories"])
    current = seven.evaluate(bank, inputs, contract)
    ledger = []
    proxy_evaluations = 0
    exact_evaluations = 1
    stop_reason = "pass_cap"
    for pass_index in range(1, POLISH_PASS_CAP + 1):
        bank_indices = [tables.by_hex[value] for value in bank]
        pair_proxy = polish.catalog_to_bank_proxy(tables, bank_indices)
        proposals = []
        for slot in range(6):
            others = [index for index in range(6) if index != slot]
            other_indices = np.asarray([bank_indices[index] for index in others], dtype=int)
            valid = lane_mask(tables, lane, bank_indices, slot)
            valid[other_indices] = False
            gates = contract["hard_gates"]
            valid &= (
                np.min(
                    np.linalg.norm(
                        tables.commanded[:, None] - tables.commanded[other_indices][None], axis=2
                    )
                    * 100.0,
                    axis=1,
                )
                >= gates["commanded_category_pair_delta_e_ok"]
            )
            valid &= (
                np.min(
                    np.linalg.norm(
                        tables.transformed[:, None] - tables.transformed[other_indices][None],
                        axis=2,
                    )
                    * 100.0,
                    axis=1,
                )
                >= gates["nominal_transformed_category_pair_delta_e_ok"]
            )
            valid &= (
                np.min(
                    np.abs(
                        (tables.hues[:, None] - tables.hues[other_indices][None] + 180.0) % 360.0
                        - 180.0
                    ),
                    axis=1,
                )
                >= gates["commanded_minimum_hue_gap_degrees"]
            )
            floor = unaffected_primary(tables, pair_proxy, bank_indices, slot)
            scores = np.minimum(tables.fg_proxy, np.min(pair_proxy[:, others], axis=1))
            scores = np.minimum(scores, floor)
            scores[~valid] = -math.inf
            best_primary = float(np.max(scores))
            for catalog_index in np.flatnonzero(np.abs(scores - best_primary) <= 1e-12):
                candidate = list(bank)
                candidate[slot] = tables.catalog[int(catalog_index)].hex8
                canonical = seven.canonical_categories(candidate)
                proposals.append((best_primary, canonical))
            proxy_evaluations += len(tables.catalog)
        best_primary = max(row[0] for row in proposals)
        unique = {
            candidate: primary
            for primary, candidate in proposals
            if abs(primary - best_primary) <= 1e-12
        }
        exact_rows = []
        for candidate in sorted(unique, reverse=True)[:DISCOVERY_FINALIST_LIMIT]:
            evaluation = seven.evaluate(candidate, inputs, contract)
            exact_evaluations += 1
            if evaluation["hard_gate_failures"]:
                continue
            exact_rows.append((tuple(evaluation["objective"]), candidate, evaluation))
        require(bool(exact_rows), f"no exact polish finalist {lane['id']}")
        best = select_objective_row(exact_rows)
        objective, candidate, evaluation = best
        if not objective_better(objective, current["objective"]):
            stop_reason = "coordinate_local_optimum"
            break
        ledger.append(
            {
                "pass": pass_index,
                "before_categories": list(bank),
                "after_categories": list(candidate),
                "before_objective": current["objective"],
                "after_objective": list(objective),
            }
        )
        bank = candidate
        current = evaluation
        print(
            f"[forbidden-arc] lane={lane['id']} pass={pass_index} primary={objective[0]:.9f}",
            file=sys.stderr,
            flush=True,
        )
    require(current["hard_gate_failures"] == [], f"polished gate failure {lane['id']}")
    require(
        all(hue_allowed(seven._hue(srgb_to_oklab(p3.parse_exact_hex8(value)))) for value in bank),
        f"forbidden hue survived {lane['id']}",
    )
    return {
        "lane": lane["id"],
        "method": lane["method"],
        "categories": list(bank),
        "candidate_id": p3.sha256_json(
            {"lane": lane["id"], "categories": list(bank), "forbidden_arc": list(FORBIDDEN_HUE_ARC)}
        ),
        "category_set_sha256": p3.bank_hash(bank),
        "objective": current["objective"],
        "metrics": current["metrics"],
        "hard_gate_failures": current["hard_gate_failures"],
        "polish": {
            "pass_cap": POLISH_PASS_CAP,
            "passes_accepted": len(ledger),
            "stop_reason": stop_reason,
            "proxy_evaluation_count": proxy_evaluations,
            "exact_evaluation_count": exact_evaluations,
            "exact_primary_tie_cap": DISCOVERY_FINALIST_LIMIT,
            "ledger": ledger,
        },
    }


def benchmark_candidate(
    lane: str,
    categories: Sequence[str],
    inputs: Any,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    bank = seven.canonical_categories(categories)
    evaluation = seven.evaluate(bank, inputs, contract)
    require(evaluation["hard_gate_failures"] == [], f"benchmark {lane} fails gates")
    return {
        "lane": lane,
        "categories": list(bank),
        "candidate_id": p3.sha256_json(
            {"lane": lane, "categories": list(bank), "contract": p3.sha256_json(contract)}
        ),
        "category_set_sha256": p3.bank_hash(bank),
        "objective": evaluation["objective"],
        "metrics": evaluation["metrics"],
        "hard_gate_failures": evaluation["hard_gate_failures"],
    }


def run() -> dict[str, Any]:
    inputs = seven.load_inputs(replay=False)
    contract = seven.load_contract()
    seven.validate_contract(contract, inputs)
    smoke_all, smoke_summary = seven.build_catalog(inputs, contract, smoke=True)
    full_all, full_summary = seven.build_catalog(inputs, contract, smoke=False)
    smoke = filter_catalog(smoke_all)
    full = filter_catalog(full_all)
    require(
        len(smoke) < len(smoke_all) and len(full) < len(full_all), "forbidden arc removed no colors"
    )
    require(hue_support(smoke)["forbidden_arc_color_count"] == 0, "smoke arc leak")
    require(hue_support(full)["forbidden_arc_color_count"] == 0, "full arc leak")
    discoveries = discover(smoke, inputs, contract)
    tables = catalog_tables(full, inputs, contract)
    lanes = {lane["id"]: lane for lane in contract["lanes"]}
    finalists = [
        polish_lane(row, lanes[row["lane"]], tables, inputs, contract) for row in discoveries
    ]
    require(len({tuple(row["categories"]) for row in finalists}) == 3, "frontier collapsed")
    transformed = [
        np.concatenate(
            [
                srgb_to_oklab(p3.parse_exact_hex8(value) * tables.gains)
                for value in row["categories"]
            ]
        )
        for row in finalists
    ]
    for left, right in itertools.combinations(range(3), 2):
        require(
            bool(np.linalg.norm(transformed[left] - transformed[right]) >= 0.02),
            "finalists are transformed near-clones",
        )
    full_polish = json.loads((HERE / "full-polish/results.json").read_text())
    candidate_a_categories = next(
        row["categories"] for row in full_polish["candidates"] if row["lane"] == "A"
    )
    candidate_a = benchmark_candidate("CANDIDATE-A", candidate_a_categories, inputs, contract)
    prior_c = benchmark_candidate(
        "PRIOR-C", seven.benchmark_categories(inputs, contract), inputs, contract
    )
    browser_roles = {
        "reference": candidate_a,
        "benchmark-c": prior_c,
        "a": finalists[0],
        "b": finalists[1],
        "c": finalists[2],
    }
    return {
        "schema_version": 1,
        "artifact_kind": "seven-point-forbidden-hue-arc-rebuild",
        "input_chain_sha256": p3.input_chain_sha256(inputs),
        "search_contract_sha256": p3.sha256_json(contract),
        "fixed_fg0": "#342F2C",
        "pair_accounting": {
            "role_count": 7,
            "total_unordered_pairs": 21,
            "category_category_pairs": 15,
            "fg0_category_pairs": 6,
            "lane_directions": 2,
        },
        "forbidden_arc": {
            "coordinate": "commanded Oklch hue degrees",
            "closed_interval_degrees": list(FORBIDDEN_HUE_ARC),
            "role_neutral": True,
        },
        "catalog": {
            "smoke_before": len(smoke_all),
            "smoke_after": len(smoke),
            "smoke_rejected": len(smoke_all) - len(smoke),
            "full_before": len(full_all),
            "full_after": len(full),
            "full_rejected": len(full_all) - len(full),
            "smoke_support": hue_support(smoke),
            "full_support": hue_support(full),
            "source_summary_smoke": smoke_summary,
            "source_summary_full": full_summary,
        },
        "bounded_search": {
            "discovery": "broad 940-color exact catalog after role-neutral arc filter",
            "full_catalog_polish": "monotonic exact one-color coordinate search",
            "reason": "prior full-catalog clique materialized O(n^2) graphs and exceeded bounded runtime",
            "threshold_iterations": DISCOVERY_THRESHOLD_ITERATIONS,
            "discovery_finalist_limit": DISCOVERY_FINALIST_LIMIT,
            "objective_equality_tolerance": OBJECTIVE_EQUALITY_TOLERANCE,
            "global_optimum_claim": False,
        },
        "eligibility_uses_a_or_prior_c": False,
        "benchmarks": {
            "candidate_a_actual_1_5": 9.48364502,
            "prior_c_actual_1_5": 7.30273837,
            "policy": "evidence only; not search eligibility",
        },
        "browser_roles": browser_roles,
        "discoveries": discoveries,
        "candidates": finalists,
        "selection": None,
        "production": False,
        "catalog_summary": {
            "schema_version": 1,
            "mode": "forbidden-arc-full",
            "exact_hex8_count": len(full),
            "forbidden_arc": list(FORBIDDEN_HUE_ARC),
            "canonical_hex8_reparsed_before_metrics": True,
        },
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
        require(not list(output.iterdir()), "forbidden-arc output must be empty")
    result = run()
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads(result).items():
        (output / name).write_bytes(json_bytes(payload))


def validate(artifact_dir: Path) -> None:
    directory = Path(artifact_dir)
    require(directory.is_dir(), "forbidden-arc artifacts missing")
    require({path.name for path in directory.iterdir()} == set(EXPECTED_FILES), "files differ")
    actual = {name: json.loads((directory / name).read_text()) for name in EXPECTED_FILES}
    require(actual == payloads(run()), "forbidden-arc replay differs")


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
