"""Benchmark Phase 3A engine throughput on the frozen baseline only."""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import phase3_optimizer as p3


def timed(function, repeats: int) -> dict[str, float | int]:
    durations = []
    for _ in range(repeats):
        started = time.perf_counter()
        function()
        durations.append(time.perf_counter() - started)
    median = statistics.median(durations)
    return {
        "repeats": repeats,
        "median_seconds": median,
        "minimum_seconds": min(durations),
        "maximum_seconds": max(durations),
    }


def main() -> None:
    inputs = p3.load_inputs(HERE)
    contract = p3.load_contract(HERE / "phase3-search-contract.json")
    p3.validate_search_contract(contract, inputs)
    bank = tuple(inputs.baseline["family"]["categorical"][name] for name in p3.ROLE_NAMES)
    batch_size = 2_000
    coarse = timed(lambda: p3.evaluate_commanded_batch([bank] * batch_size, inputs), 5)
    coarse["banks_per_batch"] = batch_size
    coarse["banks_per_second"] = batch_size / coarse["median_seconds"]

    full = timed(lambda: p3.evaluate_candidate(bank, inputs, contract, stage="full"), 2)
    full["banks_per_second"] = 1.0 / full["median_seconds"]
    full["cam16_rows_per_bank"] = 9 * 45
    full["g1_masks_reused_per_bank"] = 720

    workers = 4
    coarse_banks = 100_000
    full_banks = 500
    numerical_seconds = coarse_banks / coarse["banks_per_second"] / workers
    numerical_seconds += full_banks / full["banks_per_second"] / workers
    result = {
        "schema_version": 1,
        "artifact_policy": {
            "environment_bound": True,
            "gating": False,
            "timings_deterministic": False,
            "wall_clock_timestamp_included": False,
        },
        "scope": "frozen baseline repeated for throughput only; no candidate search or replacement colors",
        "bank_payload_included": False,
        "host": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "vectorized_exact_hex8_coarse": coarse,
        "full_45_gain_all_viewing_plus_720_mask_proxy": full,
        "phase3b_estimate": {
            "coarse_banks": coarse_banks,
            "full_survivors": full_banks,
            "workers": workers,
            "numerical_wall_minutes": numerical_seconds / 60.0,
            "browser_finalists": 12,
            "browser_and_replay_budget_minutes": [10, 30],
            "total_wall_minutes_range": [
                max(15, numerical_seconds / 60.0 + 10),
                numerical_seconds / 60.0 + 30,
            ],
            "claim": "engineering estimate from baseline throughput; not a search result",
        },
    }
    output = HERE / "phase3-benchmark.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
