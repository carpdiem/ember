#!/usr/bin/env python3
"""True-superset warm-pair-plus-pink coordinate diagnosis."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
FIXED_THREE = ("#0A6109", "#2B8CAD", "#5D53AE")
ORIGINAL_A = ("#7C140A", "#857D0B", *FIXED_THREE, "#B34B71")
FIXED_FOUR_YELLOW = ("#7F180E", "#867412", *FIXED_THREE, "#B34B71")
BOUNDED_GOLDEN = ("#790C1A", "#91772A", *FIXED_THREE, "#AC507C")
SEEDS = (
    ("ORIGINAL-A", ORIGINAL_A),
    ("FIXED-FOUR-YELLOW", FIXED_FOUR_YELLOW),
    ("BOUNDED-GOLDEN-CHALLENGE", BOUNDED_GOLDEN),
)
MAX_PASSES = 6
MAX_EXACT_PRIMARY_TIES_PER_SWEEP = 24
OBJECTIVE_EQUALITY_TOLERANCE = 0.001
EXPECTED_FILES = ("catalog-summary.json", "results.json")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seven = _load("seven_for_true_superset", "optimizer.py")
polish = _load("polish_for_true_superset", "polish.py")
p3 = seven.p3


class SupersetError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SupersetError(message)


def objective_better(left: Sequence[float], right: Sequence[float]) -> bool:
    for left_value, right_value in zip(left, right, strict=True):
        if abs(float(left_value) - float(right_value)) <= OBJECTIVE_EQUALITY_TOLERANCE:
            continue
        return float(left_value) > float(right_value)
    return False


def select_objective_row(rows: Sequence[tuple[Any, ...]]) -> tuple[Any, ...]:
    require(bool(rows), "cannot select from empty objective rows")
    best = rows[0]
    for row in rows[1:]:
        if objective_better(row[0], best[0]) or (
            not objective_better(best[0], row[0]) and row[1] > best[1]
        ):
            best = row
    return best


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


def unaffected_primary(
    tables: Any,
    pair_proxy: np.ndarray,
    bank_indices: Sequence[int],
    slot: int,
) -> float:
    others = [index for index in range(6) if index != slot]
    values = [float(tables.fg_proxy[bank_indices[index]]) for index in others]
    for left in range(len(others)):
        for right in range(left + 1, len(others)):
            values.append(float(pair_proxy[bank_indices[others[left]], others[right]]))
    return min(values)


def slot_proposals(
    tables: Any,
    contract: Mapping[str, Any],
    bank: Sequence[str],
    free_value: str,
    pair_proxy: np.ndarray,
) -> tuple[list[tuple[float, tuple[str, ...], str]], int]:
    bank = seven.canonical_categories(bank)
    slot = bank.index(free_value)
    bank_indices = [tables.by_hex[value] for value in bank]
    others = [index for index in range(6) if index != slot]
    other_indices = np.asarray([bank_indices[index] for index in others], dtype=int)
    gates = contract["hard_gates"]
    valid = (
        np.min(
            np.linalg.norm(
                tables.commanded[:, None] - tables.commanded[other_indices][None],
                axis=2,
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
                (tables.hues[:, None] - tables.hues[other_indices][None] + 180.0) % 360.0 - 180.0
            ),
            axis=1,
        )
        >= gates["commanded_minimum_hue_gap_degrees"]
    )
    valid[other_indices] = False
    floor = unaffected_primary(tables, pair_proxy, bank_indices, slot)
    scores = np.minimum(tables.fg_proxy, np.min(pair_proxy[:, others], axis=1))
    scores = np.minimum(scores, floor)
    scores[~valid] = -math.inf
    best_primary = float(np.max(scores))
    require(math.isfinite(best_primary), f"no exact replacement for {free_value}")
    rows = {}
    for catalog_index in np.flatnonzero(np.abs(scores - best_primary) <= 1e-12):
        candidate = list(bank)
        candidate[slot] = tables.catalog[int(catalog_index)].hex8
        canonical = seven.canonical_categories(candidate)
        rows[canonical] = tables.catalog[int(catalog_index)].hex8
    return (
        [(best_primary, canonical, rows[canonical]) for canonical in sorted(rows, reverse=True)],
        len(tables.catalog),
    )


def search_seed(
    seed_name: str,
    seed_values: Sequence[str],
    tables: Any,
    inputs: Any,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    bank = seven.canonical_categories(seed_values)
    fixed = set(FIXED_THREE)
    free_values = [value for value in bank if value not in fixed]
    require(len(free_values) == 3, f"seed {seed_name} does not have three free roles")
    seed_evaluation = seven.evaluate(bank, inputs, contract)
    require(seed_evaluation["hard_gate_failures"] == [], f"seed {seed_name} fails gates")
    current = seed_evaluation
    ledger = []
    proxy_evaluations = 0
    exact_evaluations = 1
    stop_reason = "pass_cap"
    for pass_index in range(1, MAX_PASSES + 1):
        bank_indices = [tables.by_hex[value] for value in bank]
        pair_proxy = polish.catalog_to_bank_proxy(tables, bank_indices)
        proposals = []
        for free_value in free_values:
            rows, scanned = slot_proposals(tables, contract, bank, free_value, pair_proxy)
            proposals.extend(
                (primary, candidate, free_value, replacement)
                for primary, candidate, replacement in rows
            )
            proxy_evaluations += scanned
        best_primary = max(row[0] for row in proposals)
        primary_ties = {}
        for proposal in proposals:
            if abs(proposal[0] - best_primary) <= 1e-12:
                primary_ties[proposal[1]] = proposal
        selected_proposals = [
            primary_ties[key]
            for key in sorted(primary_ties, reverse=True)[:MAX_EXACT_PRIMARY_TIES_PER_SWEEP]
        ]
        exact_rows = []
        for primary, candidate, free_value, replacement in selected_proposals:
            evaluation = seven.evaluate(candidate, inputs, contract)
            exact_evaluations += 1
            if evaluation["hard_gate_failures"]:
                continue
            exact_rows.append(
                (
                    tuple(evaluation["objective"]),
                    candidate,
                    evaluation,
                    primary,
                    free_value,
                    replacement,
                )
            )
        require(bool(exact_rows), f"seed {seed_name} has no exact sweep finalist")
        best = select_objective_row(exact_rows)
        objective, candidate, evaluation, primary, removed, replacement = best
        current_objective = tuple(current["objective"])
        if not objective_better(objective, current_objective):
            stop_reason = "coordinate_local_optimum"
            break
        old_bank = bank
        bank = candidate
        free_values[free_values.index(removed)] = replacement
        current = evaluation
        ledger.append(
            {
                "pass": pass_index,
                "removed_hex8": removed,
                "added_hex8": replacement,
                "before_categories": list(old_bank),
                "after_categories": list(bank),
                "before_objective": list(current_objective),
                "after_objective": list(objective),
                "proxy_primary": primary,
            }
        )
        print(
            f"[true-superset] seed={seed_name} pass={pass_index} primary={objective[0]:.9f}",
            file=sys.stderr,
            flush=True,
        )
    require(
        not objective_better(seed_evaluation["objective"], current["objective"]),
        "seed regressed",
    )
    return {
        "seed": seed_name,
        "seed_categories": list(seven.canonical_categories(seed_values)),
        "seed_objective": seed_evaluation["objective"],
        "final_categories": list(bank),
        "final_objective": current["objective"],
        "hard_gate_failures": current["hard_gate_failures"],
        "passes_accepted": len(ledger),
        "stop_reason": stop_reason,
        "proxy_evaluation_count": proxy_evaluations,
        "exact_evaluation_count": exact_evaluations,
        "ledger": ledger,
    }


def browser_candidate(
    lane: str,
    categories: Sequence[str],
    inputs: Any,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    bank = seven.canonical_categories(categories)
    evaluation = seven.evaluate(bank, inputs, contract)
    require(evaluation["hard_gate_failures"] == [], f"browser candidate {lane} fails")
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
    tables, catalog_summary = polish.build_catalog_tables(inputs, contract, progress=True)
    seed_rows = [
        {
            "name": name,
            "categories": list(seven.canonical_categories(values)),
            "evaluation": seven.evaluate(values, inputs, contract),
        }
        for name, values in SEEDS
    ]
    for row in seed_rows:
        require(row["evaluation"]["hard_gate_failures"] == [], f"seed {row['name']} fails")
    searches = [search_seed(name, values, tables, inputs, contract) for name, values in SEEDS]
    best_seed = select_objective_row(
        [
            (tuple(row["evaluation"]["objective"]), tuple(row["categories"]), row)
            for row in seed_rows
        ]
    )[2]
    best_search = select_objective_row(
        [(tuple(row["final_objective"]), tuple(row["final_categories"]), row) for row in searches]
    )[2]
    improved = objective_better(
        best_search["final_objective"], best_seed["evaluation"]["objective"]
    )
    genuinely_new = best_search["final_categories"] not in [row["categories"] for row in seed_rows]
    baseline_browser = browser_candidate("BASELINE-A", ORIGINAL_A, inputs, contract)
    fixed_browser = browser_candidate("FIXED-FOUR-YELLOW", FIXED_FOUR_YELLOW, inputs, contract)
    new_browser = browser_candidate(
        "TRUE-SUPERSET", best_search["final_categories"], inputs, contract
    )
    browser_roles = {
        "reference": baseline_browser,
        "benchmark-c": fixed_browser,
        "a": new_browser,
        "b": new_browser,
        "c": new_browser,
    }
    return {
        "schema_version": 1,
        "artifact_kind": "seven-point-true-superset-diagnosis",
        "input_chain_sha256": p3.input_chain_sha256(inputs),
        "search_contract_sha256": p3.sha256_json(contract),
        "fixed_fg0": "#342F2C",
        "fixed_three": list(FIXED_THREE),
        "free_role_count": 3,
        "hue_family_restriction": None,
        "proximity_or_churn_objective": False,
        "boundedness": {
            "method": "multi-seed monotonic full-catalog coordinate search",
            "pass_cap_per_seed": MAX_PASSES,
            "exact_primary_tie_cap_per_sweep": MAX_EXACT_PRIMARY_TIES_PER_SWEEP,
            "objective_equality_tolerance": OBJECTIVE_EQUALITY_TOLERANCE,
            "global_optimum_claim": False,
        },
        "seeds": [
            {
                "name": row["name"],
                "categories": row["categories"],
                "objective": row["evaluation"]["objective"],
                "hard_gate_failures": row["evaluation"]["hard_gate_failures"],
            }
            for row in seed_rows
        ],
        "searches": searches,
        "best_included_seed": {
            "name": best_seed["name"],
            "categories": best_seed["categories"],
            "objective": best_seed["evaluation"]["objective"],
        },
        "best_result": best_search,
        "proxy_nondominated_improvement": improved,
        "genuinely_new_candidate": genuinely_new,
        "new_chromium_authorized_by_result": improved and genuinely_new,
        "browser_non_regression_claim": False,
        "browser_roles": browser_roles,
        "production": False,
        "selection": None,
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
        require(not list(output.iterdir()), "true-superset output directory must be empty")
    result = run()
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads(result).items():
        (output / name).write_bytes(json_bytes(payload))


def validate(artifact_dir: Path) -> None:
    directory = Path(artifact_dir)
    require(directory.is_dir(), "true-superset artifact directory missing")
    require({path.name for path in directory.iterdir()} == set(EXPECTED_FILES), "files differ")
    actual = {name: json.loads((directory / name).read_text()) for name in EXPECTED_FILES}
    require(actual == payloads(run()), "true-superset replay differs")


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
