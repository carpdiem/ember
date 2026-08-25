"""Measure the corrected Phase 3 engine without retaining candidate banks."""

from __future__ import annotations

import json
import multiprocessing
import platform
import shutil
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import phase3_optimizer as p3


def timed(function, repeats: int = 1) -> tuple[dict[str, float | int], object]:
    durations = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = function()
        durations.append(time.perf_counter() - started)
    median = statistics.median(durations)
    return (
        {
            "repeats": repeats,
            "median_seconds": median,
            "minimum_seconds": min(durations),
            "maximum_seconds": max(durations),
        },
        result,
    )


def full_worker_measurement(tasks, inputs, contract, workers: int) -> dict[str, float | int]:
    started = time.perf_counter()
    if workers == 1:
        p3._initialize_full_worker(inputs, contract)
        rows = [p3._evaluate_full_worker(task) for task in tasks]
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=p3._initialize_full_worker,
            initargs=(inputs, contract),
        ) as executor:
            rows = list(executor.map(p3._evaluate_full_worker, tasks))
    elapsed = time.perf_counter() - started
    if any(row["evaluation_stage"] != "full" for row in rows):
        raise RuntimeError("worker benchmark did not execute full evaluations")
    return {
        "workers": workers,
        "banks": len(rows),
        "seconds": elapsed,
        "banks_per_second": len(rows) / elapsed,
    }


def main() -> None:
    inputs = p3.load_inputs(HERE)
    contract = p3.load_contract(HERE / "phase3-search-contract.json")
    p3.validate_search_contract(contract, inputs)

    probe_jobs = p3.make_search_jobs(seed=3400, count=100_000, chunk_size=100_000)
    proposal_timing, proposal_result = timed(
        lambda: p3._coarse_chunk(probe_jobs, inputs, contract, 3400)
    )
    proposal_rows, _, proposal_count = proposal_result
    cheap_survivors = sum(
        1 for row in proposal_rows if row["cheap_pass"] and not row["baseline_reference"]
    )
    deduped = len(p3.select_diverse_survivors(proposal_rows, limit=100_000))
    proposal_timing.update(
        {
            "proposals": proposal_count,
            "proposals_per_second": proposal_count / proposal_timing["median_seconds"],
            "cheap_survivors": cheap_survivors,
            "cheap_survivor_rate": cheap_survivors / proposal_count,
            "deduped_cheap_survivors": deduped,
            "baseline_included": True,
        }
    )

    scratch = Path("/tmp/phase3-benchmark-10k")
    shutil.rmtree(scratch, ignore_errors=True)
    search_timing, manifest = timed(
        lambda: p3.run_search(
            inputs,
            contract,
            output_dir=scratch,
            stage="coarse",
            seed=3400,
            budget=10_000,
            chunk_size=1_000,
            max_seconds=600,
            workers=1,
            final_selection=False,
        )
    )
    search_timing.update(
        {
            "proposals": manifest["completed_jobs"],
            "proposals_per_second": manifest["completed_jobs"] / search_timing["median_seconds"],
            "chunk_size": 1_000,
            "shard_count": len(manifest["shards"]),
            "immutable_shard_bytes_written": manifest["shard_bytes_written"],
            "final_shard_bytes_on_disk": sum(
                (scratch / descriptor["file"]).stat().st_size for descriptor in manifest["shards"]
            ),
            "manifest_bytes": (scratch / "search-manifest.json").stat().st_size,
            "checkpoint_model": "immutable write-once shards plus small ordered hash manifest",
        }
    )

    survivors = [
        row for row in proposal_rows if row["cheap_pass"] and not row["baseline_reference"]
    ][:12]
    tasks = [
        {
            "run_seed": 4400,
            "job_index": index,
            "job_seed": index,
            "proposal_mode": "exact-coarse-survivor",
            "serialized_bank": row["serialized_bank"],
            "parent_artifact_sha256": "0" * 64,
            "parent_candidate_ids": [row["candidate_id"]],
        }
        for index, row in enumerate(survivors)
    ]
    worker_one = full_worker_measurement(tasks, inputs, contract, 1)
    worker_four = full_worker_measurement(tasks, inputs, contract, 4)
    worker_speedup = worker_one["seconds"] / worker_four["seconds"]

    coarse_banks = 100_000
    full_banks = 500
    numerical_seconds = coarse_banks / proposal_timing["proposals_per_second"]
    numerical_seconds += full_banks / worker_four["banks_per_second"]
    result = {
        "schema_version": 2,
        "artifact_policy": {
            "environment_bound": True,
            "gating": False,
            "timings_deterministic": False,
            "wall_clock_timestamp_included": False,
        },
        "scope": "corrected engine throughput and counts only; no candidate banks or final search output",
        "bank_payload_included": False,
        "host": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "baseline_anchored_100k_proposal_probe": proposal_timing,
        "coarse_10k_immutable_shard_search": search_timing,
        "full_worker_execution": {
            "workers_1": worker_one,
            "workers_4": worker_four,
            "measured_speedup_4_over_1": worker_speedup,
            "completion_order_affects_bytes": False,
        },
        "phase3b_estimate": {
            "coarse_banks": coarse_banks,
            "full_survivors": full_banks,
            "coarse_workers_assumed": 1,
            "full_workers": 4,
            "numerical_wall_minutes": numerical_seconds / 60.0,
            "browser_finalists": 12,
            "browser_and_replay_budget_minutes": [10, 30],
            "total_wall_minutes_range": [
                max(15, numerical_seconds / 60.0 + 10),
                numerical_seconds / 60.0 + 30,
            ],
            "claim": "engineering estimate using measured coarse throughput and measured four-worker full throughput; no unmeasured worker division",
        },
    }
    output = HERE / "phase3-benchmark.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    shutil.rmtree(scratch, ignore_errors=True)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
