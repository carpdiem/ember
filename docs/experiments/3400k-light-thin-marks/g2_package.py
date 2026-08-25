#!/usr/bin/env python3
"""Build and verify the Phase 3 G2 frontier, Chromium evidence, and review package.

The trusted search is never replayed wholesale. Frontier derivation reads only the
source shards named by the compact receipt. Every retained exact-Hex8 bank is then
fully recomputed, classified with standard Pareto dominance against the baseline,
and shortlisted by the deterministic G2 policy.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import g1_browser_validate as g1
import phase3_optimizer as p3

RECEIPT_SCHEMA_VERSION = 1
PAIR_EVIDENCE_SCHEMA_VERSION = 1
OBSERVATION_EVIDENCE_SCHEMA_VERSION = 1
BROWSER_EVIDENCE_LIMIT_BYTES = 50_000_000

_RECEIPT_KEYS = {
    "schema_version",
    "artifact_kind",
    "source_engine_commit",
    "source_engine_file_sha256",
    "frontier_policy_version",
    "input_chain_sha256",
    "search_contract_sha256",
    "parent",
    "refine",
    "baseline",
    "candidates",
    "pareto_dimensions",
    "frontier_eligibility_policy",
    "strict_pareto_improvement_informative",
    "g2_shortlist_policy",
    "g2_shortlist",
    "frontier_rows_sha256",
    "browser_oracle_status",
    "human_width_capacity",
    "production_promotion_authorized",
}
_SUMMARY_KEYS = {
    "candidate_id",
    "row_kind",
    "serialized_bank",
    "serialized_bank_sha256",
    "pareto",
    "failure_count",
    "hard_floor_status",
    "strict_pareto_improvement",
    "pareto_frontier_eligible",
    "source",
    "lineage",
}
_SOURCE_KEYS = {"shard_descriptor", "row_position", "job_index", "source_row_sha256"}
_LINEAGE_KEYS = {
    "run_seed",
    "job_seed",
    "proposal_mode",
    "parent_artifact_sha256",
    "parent_candidate_ids",
}


class G2IntegrityError(RuntimeError):
    """Raised when G2 evidence is incomplete, stale, or internally contradictory."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise G2IntegrityError(message)


def canonical_json(value: Any) -> bytes:
    return p3.canonical_json(value)


def sha256_json(value: Any) -> str:
    return p3.sha256_json(value)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    require(isinstance(value, Mapping), f"{label} must be an object")
    require(set(value) == expected, f"{label} keys are not closed")


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise G2IntegrityError(f"{label} cannot be read: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def _atomic_json(path: Path, value: Any, *, compact: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        canonical_json(value) + b"\n"
        if compact
        else (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _git_blob_sha256(commit: str, relative_path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    require(completed.returncode == 0, "trusted source engine commit/blob is unavailable")
    return hashlib.sha256(completed.stdout).hexdigest()


def _row_summary(row: Mapping[str, Any], source: Mapping[str, Any] | None) -> dict[str, Any]:
    lineage = None
    if source is not None:
        lineage = {key: row[key] for key in _LINEAGE_KEYS}
    return {
        "candidate_id": row["candidate_id"],
        "row_kind": row["row_kind"],
        "serialized_bank": row["serialized_bank"],
        "serialized_bank_sha256": row["serialized_bank_sha256"],
        "pareto": row["pareto"],
        "failure_count": len(row["failures"]),
        "hard_floor_status": "REFERENCE_NOT_CANDIDATE" if source is None else "PASS",
        "strict_pareto_improvement": row["strict_pareto_improvement"],
        "pareto_frontier_eligible": row["pareto_frontier_eligible"],
        "source": dict(source) if source is not None else None,
        "lineage": lineage,
    }


def _binding_rows(bindings: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for binding in bindings:
        exact_keys(binding, {"shard_file", "row_position", "job_index"}, "frontier binding")
        row_position = binding["row_position"]
        job_index = binding["job_index"]
        require(
            isinstance(row_position, int)
            and not isinstance(row_position, bool)
            and row_position >= 0,
            "frontier binding row position is invalid",
        )
        require(
            isinstance(job_index, int) and not isinstance(job_index, bool) and job_index >= 0,
            "frontier binding job index is invalid",
        )
        rows.append(dict(binding))
    return rows


def _derive_frontier_receipt(
    search_root: Path,
    bindings: Sequence[Mapping[str, Any]],
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    search_root = Path(search_root)
    parent_path = search_root / "combined-survivors.json"
    refine_dir = search_root / "refined-5000"
    manifest_path = refine_dir / "search-manifest.json"
    parent = _load_object(parent_path, "combined survivor parent")
    manifest = _load_object(manifest_path, "refine search manifest")
    parent_hash = sha256_json(parent)

    require(parent.get("artifact_kind") == "coarse-survivors", "combined parent kind is invalid")
    require(
        parent.get("algorithm_version") == p3.SEARCH_ALGORITHM_VERSION, "parent algorithm is stale"
    )
    require(
        parent.get("input_chain_sha256") == p3.input_chain_sha256(inputs), "parent input is stale"
    )
    require(
        parent.get("search_contract_sha256") == sha256_json(contract), "parent contract is stale"
    )
    require(parent.get("deduped_survivor_count") == 5_000, "combined parent count is not 5,000")
    require(parent.get("seed_runs") == [44001, 44002, 44003, 44004], "parent seed lineage is stale")

    binding = manifest.get("run_binding", {})
    require(
        manifest.get("artifact_kind") == "phase3-search-shard-manifest",
        "refine manifest kind is invalid",
    )
    require(
        manifest.get("schema_version") == p3.SEARCH_MANIFEST_SCHEMA_VERSION,
        "refine schema is stale",
    )
    require(
        binding.get("algorithm_version") == p3.SEARCH_ALGORITHM_VERSION, "refine algorithm is stale"
    )
    require(binding.get("stage") == "refine", "trusted manifest is not a refine run")
    require(binding.get("budget") == 5_000, "trusted refine budget is not 5,000")
    require(manifest.get("completed_jobs") == 5_000, "trusted refine run is incomplete")
    require(binding.get("parent_artifact_sha256") == parent_hash, "refine parent hash is stale")
    require(
        binding.get("input_chain_sha256") == p3.input_chain_sha256(inputs), "refine input is stale"
    )
    require(
        binding.get("search_contract_sha256") == sha256_json(contract), "refine contract is stale"
    )
    require(
        manifest.get("run_binding_sha256") == sha256_json(binding), "refine binding hash is stale"
    )
    require(manifest.get("selected_candidate_id") is None, "search manifest selected a candidate")
    require(manifest.get("final_selection_performed") is False, "search crossed selection boundary")
    require(manifest.get("browser_oracle_run") is False, "search crossed browser boundary")

    descriptors = manifest.get("shards")
    require(
        isinstance(descriptors, list) and len(descriptors) == 100,
        "refine shard descriptors are incomplete",
    )
    descriptor_by_file = {row["file"]: row for row in descriptors}
    require(len(descriptor_by_file) == len(descriptors), "refine shard descriptors are duplicated")

    source_by_id: dict[str, dict[str, Any]] = {}
    raw_candidates: list[dict[str, Any]] = []
    shard_cache: dict[str, dict[str, Any]] = {}
    baseline_exact = p3.evaluate_candidate(
        p3._baseline_bank(inputs), inputs, contract, stage="full"
    )
    for requested in _binding_rows(bindings):
        file_name = requested["shard_file"]
        descriptor = descriptor_by_file.get(file_name)
        require(descriptor is not None, f"frontier source shard {file_name} is not in the manifest")
        if file_name not in shard_cache:
            path = refine_dir / file_name
            require(path.is_file(), f"frontier source shard {file_name} is missing")
            require(
                sha256_file(path) == descriptor["sha256"],
                f"frontier source shard {file_name} hash is stale",
            )
            shard_cache[file_name] = _load_object(path, f"frontier source shard {file_name}")
        records = shard_cache[file_name].get("records")
        require(isinstance(records, list), f"frontier source shard {file_name} records are invalid")
        position = requested["row_position"]
        require(position < len(records), f"frontier source row {file_name}:{position} is missing")
        row = records[position]
        require(
            row.get("job_index") == requested["job_index"], "frontier source job index is stale"
        )
        require(
            row.get("parent_artifact_sha256") == parent_hash, "frontier row parent lineage is stale"
        )
        require(row.get("evaluation_stage") == "full", "frontier source row is not fully evaluated")
        require(not row.get("failures"), "frontier source row does not pass hard floors")
        source = {
            "shard_descriptor": descriptor,
            "row_position": position,
            "job_index": requested["job_index"],
            "source_row_sha256": sha256_json(row),
        }
        candidate_id = row["candidate_id"]
        require(candidate_id not in source_by_id, "frontier candidate is duplicated")
        recomputed = p3.evaluate_candidate(row["serialized_bank"], inputs, contract, stage="full")
        recomputed["strict_pareto_improvement"] = p3._protected_hard_gates_nonregressed(
            recomputed, baseline_exact
        ) and p3.is_strict_pareto_improvement(recomputed["pareto"], baseline_exact["pareto"])
        for key in p3._CANDIDATE_LINEAGE_KEYS:
            recomputed[key] = row[key]
        source_expected = dict(recomputed)
        source_expected.pop("pareto_frontier_eligible")
        require(
            canonical_json(row) == canonical_json(source_expected),
            f"frontier source row {file_name}:{position} differs from full recomputation",
        )
        source_by_id[candidate_id] = source
        raw_candidates.append(recomputed)

    frontier_rows = p3.pareto_front(raw_candidates, baseline_exact)
    require(len(frontier_rows) == 15, "trusted compact frontier is not baseline plus 14 rows")
    require(
        {row["candidate_id"] for row in frontier_rows[1:]} == set(source_by_id),
        "trusted compact bindings do not equal the exact Pareto frontier",
    )
    shortlist = p3.deterministic_g2_shortlist(frontier_rows)
    baseline_summary = _row_summary(frontier_rows[0], None)
    candidate_summaries = [
        _row_summary(row, source_by_id[row["candidate_id"]]) for row in frontier_rows[1:]
    ]
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "artifact_kind": "compact-trusted-frontier-receipt",
        "source_engine_commit": p3.TRUSTED_PHASE3_SEARCH_HEAD,
        "source_engine_file_sha256": _git_blob_sha256(
            p3.TRUSTED_PHASE3_SEARCH_HEAD,
            "docs/experiments/3400k-light-thin-marks/phase3_optimizer.py",
        ),
        "frontier_policy_version": p3.FRONTIER_POLICY_VERSION,
        "input_chain_sha256": p3.input_chain_sha256(inputs),
        "search_contract_sha256": sha256_json(contract),
        "parent": {
            "file": parent_path.name,
            "file_sha256": sha256_file(parent_path),
            "canonical_sha256": parent_hash,
            "source_manifest_hashes": parent["source_manifest_hashes"],
            "seed_runs": parent["seed_runs"],
            "deduped_survivor_count": parent["deduped_survivor_count"],
        },
        "refine": {
            "directory": refine_dir.name,
            "manifest_file": manifest_path.name,
            "manifest_file_sha256": sha256_file(manifest_path),
            "manifest_canonical_sha256": sha256_json(manifest),
            "run_binding_sha256": manifest["run_binding_sha256"],
            "root_run_seed": binding["root_run_seed"],
            "completed_jobs": manifest["completed_jobs"],
            "shard_descriptor_count": len(descriptors),
            "shard_descriptors_sha256": sha256_json(descriptors),
        },
        "baseline": baseline_summary,
        "candidates": candidate_summaries,
        "pareto_dimensions": list(p3.PARETO_DIMENSIONS),
        "frontier_eligibility_policy": (
            "failure-free full recomputation; protected hard floors pass; nondominated with baseline"
        ),
        "strict_pareto_improvement_informative": True,
        "g2_shortlist_policy": {
            "target_metric": "raster_1_5_min",
            "operator": ">",
            "deterministic_delta_e_ok": p3.G2_SHORTLIST_DELTA_E_OK,
            "human_visibility_floor": None,
            "roles": [
                "maximum-1.5px-improvement",
                "lowest-commanded-deviation",
                "strongest-transformed-pair-minimum",
            ],
        },
        "g2_shortlist": shortlist,
        "frontier_rows_sha256": sha256_json([baseline_summary, *candidate_summaries]),
        "browser_oracle_status": "NOT_RUN",
        "human_width_capacity": None,
        "production_promotion_authorized": False,
    }
    return receipt, frontier_rows


def build_frontier_receipt(
    search_root: Path,
    bindings: Sequence[Mapping[str, Any]],
    output_path: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    receipt, _ = _derive_frontier_receipt(search_root, bindings, inputs, contract)
    _atomic_json(output_path, receipt)
    return receipt


def validate_frontier_receipt(
    receipt: Mapping[str, Any] | Path,
    search_root: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    payload = (
        _load_object(receipt, "frontier receipt") if isinstance(receipt, Path) else dict(receipt)
    )
    exact_keys(payload, _RECEIPT_KEYS, "frontier receipt")
    exact_keys(payload["baseline"], _SUMMARY_KEYS, "frontier baseline summary")
    require(payload["baseline"]["source"] is None, "baseline may not claim search-row lineage")
    require(payload["baseline"]["lineage"] is None, "baseline may not claim candidate lineage")
    candidates = payload["candidates"]
    require(
        isinstance(candidates, list) and len(candidates) == 14,
        "frontier receipt must contain 14 candidates",
    )
    bindings = []
    for candidate in candidates:
        exact_keys(candidate, _SUMMARY_KEYS, "frontier candidate summary")
        exact_keys(candidate["source"], _SOURCE_KEYS, "frontier source binding")
        exact_keys(candidate["lineage"], _LINEAGE_KEYS, "frontier candidate lineage")
        descriptor = candidate["source"]["shard_descriptor"]
        bindings.append(
            {
                "shard_file": descriptor["file"],
                "row_position": candidate["source"]["row_position"],
                "job_index": candidate["source"]["job_index"],
            }
        )
    expected, rows = _derive_frontier_receipt(search_root, bindings, inputs, contract)
    require(
        canonical_json(payload) == canonical_json(expected),
        "frontier receipt differs from exact source replay",
    )
    return rows


def build_browser_requests(
    receipt: Mapping[str, Any] | Path,
    search_root: Path,
    output_dir: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    payload = (
        _load_object(receipt, "frontier receipt") if isinstance(receipt, Path) else dict(receipt)
    )
    rows = validate_frontier_receipt(payload, search_root, inputs, contract)
    row_by_id = {row["candidate_id"]: row for row in rows}
    shortlist = payload["g2_shortlist"]
    selections = [
        ("REFERENCE", rows[0]),
        *[(item["role"], row_by_id[item["candidate_id"]]) for item in shortlist],
    ]
    observations = p3._browser_observations(inputs)
    receipt_hash = sha256_json(payload)
    requests: dict[str, dict[str, Any]] = {}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for role, row in selections:
        reference = role == "REFERENCE"
        rank = (
            0
            if reference
            else next(
                index
                for index, item in enumerate(rows[1:], 1)
                if item["candidate_id"] == row["candidate_id"]
            )
        )
        request = {
            "schema_version": p3.BROWSER_SCHEMA_VERSION,
            "request_kind": "baseline-reference" if reference else "frontier-candidate",
            "candidate_id": row["candidate_id"],
            "bank_kind": "categorical",
            "serialized_bank": row["serialized_bank"],
            "serialized_bank_sha256": row["serialized_bank_sha256"],
            "input_chain_sha256": p3.input_chain_sha256(inputs),
            "search_contract_sha256": sha256_json(contract),
            "frontier_manifest_sha256": receipt_hash,
            "frontier_rows_sha256": payload["frontier_rows_sha256"],
            "parent_artifact_sha256": payload["parent"]["canonical_sha256"],
            "frontier_rank": rank,
            "shortlist_role": role,
            "deterministic_shortlist_delta_e_ok": p3.G2_SHORTLIST_DELTA_E_OK,
            "human_visibility_floor": None,
            "mask_set": {
                "file": p3.INPUT_FILENAMES["raster_masks"],
                "sha256": inputs.source_sha256["raster_masks"],
                "count": 720,
                "rerasterize": False,
            },
            "requested_roles": list(p3.ROLES),
            "requested_role_observations": observations,
            "full_image_hash_used": False,
            "cvd_policy": "report-only",
            "human_width_capacity": None,
        }
        p3.validate_browser_oracle_request(request, inputs, contract)
        name = role.lower()
        _atomic_json(output_dir / f"browser-request-{name}.json", request, compact=True)
        requests[role] = request
    return requests


def _candidate_render_context(
    request: Mapping[str, Any], inputs: p3.Phase3Inputs
) -> dict[str, Any]:
    return {
        "contract": inputs.raster_ledger["specimen_contract"],
        "categorical": dict(zip(p3.ROLE_NAMES, request["serialized_bank"], strict=True)),
        "surfaces": {
            name: inputs.baseline["family"]["surfaces"][name]
            for name in (*p3.GATE_BACKGROUNDS, p3.REPORT_BACKGROUND)
        },
    }


def _capture_observations(
    browse: Path,
    request: Mapping[str, Any],
    inputs: p3.Phase3Inputs,
    workspace: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    masks = {row["id"]: row for row in inputs.raster_masks["records"]}
    render_context = _candidate_render_context(request, inputs)
    requested = request["requested_role_observations"]
    evidence_by_id: dict[str, dict[str, Any]] = {}
    performance = defaultdict(float)
    for dpr in (1, 2):
        tiles = []
        for item in requested:
            mask = masks[item["mask_id"]]
            key = mask["key"]
            if key["dpr"] != dpr:
                continue
            base = [
                item["state"],
                item["background"],
                key["width_css_px"],
                key["style"],
                key["orientation"],
                key["dpr"],
                key["phase_css_px"],
            ]
            tiles.append(
                {
                    "id": item["id"],
                    "kind": "color",
                    "base": base,
                    "role": item["role"],
                    "lane": key["lane"],
                    "mask_id": item["mask_id"],
                }
            )
        g1._browse(
            browse,
            workspace,
            "viewport",
            f"{g1.ATLAS_COLUMNS * g1.TILE_WIDTH}x720",
            "--scale",
            str(dpr),
        )
        for start in range(0, len(tiles), g1.CHUNK_TILES):
            chunk = tiles[start : start + g1.CHUNK_TILES]
            stem = f"g2-{request['shortlist_role'].lower()}-dpr{dpr}-{start // g1.CHUNK_TILES:03d}"
            html_path = workspace / f"{stem}.html"
            png_path = workspace / f"{stem}.png"
            g1._write_atlas(html_path, chunk, render_context)
            commands = json.dumps(
                [
                    ["goto", html_path.as_uri()],
                    ["screenshot", str(png_path), "--selector", "#atlas"],
                ]
            )
            began = time.perf_counter()
            g1._run([str(browse), "chain"], cwd=workspace, stdin=commands)
            performance["browser_seconds"] += time.perf_counter() - began
            with Image.open(png_path) as opened:
                image = np.asarray(opened.convert("RGB"), dtype=np.uint8)
            expected_rows = math.ceil(len(chunk) / g1.ATLAS_COLUMNS)
            expected_shape = (
                expected_rows * g1.TILE_HEIGHT * dpr,
                g1.ATLAS_COLUMNS * g1.TILE_WIDTH * dpr,
                3,
            )
            require(image.shape == expected_shape, f"browser chunk {stem} has wrong dimensions")
            for index, tile in enumerate(chunk):
                row_index, column = divmod(index, g1.ATLAS_COLUMNS)
                tile_image = image[
                    row_index * g1.TILE_HEIGHT * dpr : (row_index + 1) * g1.TILE_HEIGHT * dpr,
                    column * g1.TILE_WIDTH * dpr : (column + 1) * g1.TILE_WIDTH * dpr,
                ]
                mask = masks[tile["mask_id"]]
                observed = np.asarray(
                    [tile_image[int(sample[4]), int(sample[3])] for sample in mask["samples"]],
                    dtype=np.uint8,
                )
                require(len(observed) == mask["sample_count"] > 0, "browser observation is empty")
                evidence_by_id[tile["id"]] = {
                    "request_observation_id": tile["id"],
                    "sample_count": len(observed),
                    "observed_rgb8_base64": base64.b64encode(observed.tobytes()).decode("ascii"),
                    "observed_rgb8_median": np.median(observed, axis=0).tolist(),
                }
            performance["tiles"] += len(chunk)
            performance["chunks"] += 1
            html_path.unlink(missing_ok=True)
            png_path.unlink(missing_ok=True)
    ordered = [evidence_by_id[item["id"]] for item in requested]
    require(len(ordered) == 25_920, "browser observation capture is not exactly 25,920 rows")
    return ordered, dict(performance)


def _browser_result_observations(
    evidence: Sequence[Mapping[str, Any]],
    request: Mapping[str, Any],
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    requested = request["requested_role_observations"]
    masks = {row["id"]: row for row in inputs.raster_masks["records"]}
    margin = float(contract["raster_proxy"]["calibrated_error_margin_delta_e_ok"])
    rows = []
    for observed, item in zip(evidence, requested, strict=True):
        expected = (
            np.asarray(p3._expected_browser_rgb8(item, request, inputs, mask_lookup=masks)) / 255.0
        )
        actual = np.asarray(observed["observed_rgb8_median"], dtype=float) / 255.0
        delta = float(np.linalg.norm(p3.srgb_to_oklab(actual) - p3.srgb_to_oklab(expected)) * 100.0)
        rows.append(
            {
                "request_observation_id": item["id"],
                "status": "PASS" if observed["sample_count"] > 0 and delta <= margin else "FAIL",
                "sample_count": observed["sample_count"],
                "observed_rgb8_median": observed["observed_rgb8_median"],
                "delta_e_ok": delta,
            }
        )
    return rows


def _pair_evidence(
    observation_evidence: Sequence[Mapping[str, Any]],
    request: Mapping[str, Any],
    inputs: p3.Phase3Inputs,
) -> dict[str, Any]:
    planned = g1._validate_ledger(inputs.raster_ledger)
    mask_by_key = {
        (
            row["key"]["width_css_px"],
            row["key"]["style"],
            row["key"]["orientation"],
            row["key"]["dpr"],
            tuple(row["key"]["phase_css_px"]),
            row["key"]["lane"],
        ): row
        for row in inputs.raster_masks["records"]
    }
    evidence_by_id = {row["request_observation_id"]: row for row in observation_evidence}
    requested_by_key = {
        (row["mask_id"], row["state"], row["background"], row["role"]): row["id"]
        for row in request["requested_role_observations"]
    }
    render_context = _candidate_render_context(request, inputs)
    compact_rows = []
    acceptance_rows = []
    for item in planned:
        base = g1._base_key(item)
        left_mask = mask_by_key[g1._mask_key(base, 0)]
        right_mask = mask_by_key[g1._mask_key(base, 1)]
        left_id = requested_by_key[
            (left_mask["id"], item["state"], item["background"], item["roles"][0])
        ]
        right_id = requested_by_key[
            (right_mask["id"], item["state"], item["background"], item["roles"][1])
        ]
        left = {**evidence_by_id[left_id], "role": item["roles"][0]}
        right = {**evidence_by_id[right_id], "role": item["roles"][1]}
        base_record = dict(zip(g1.BASE_FIELDS, base, strict=True))
        metrics = g1.reconstruct_pair_metrics(
            left,
            right,
            left_mask,
            right_mask,
            base_record,
            render_context,
        )
        require(metrics["status"] == "PASS", f"pair reconstruction failed for {item['id']}")
        compact_rows.append(
            {
                "id": item["id"],
                "matched_station_count": metrics["matched_station_count"],
                "observed_distance": round(metrics["observed_distance"], 8),
                "proxy_prediction": round(metrics["proxy_prediction"], 8),
                "proxy_error": round(metrics["proxy_error"], 8),
            }
        )
        acceptance_rows.append(
            {
                **item,
                "status": "PASS",
                "observed_distance": round(metrics["observed_distance"], 8),
                "proxy_prediction": round(metrics["proxy_prediction"], 8),
                "proxy_error": round(metrics["proxy_error"], 8),
                "_observed_by_station": metrics["observed_by_station"].tolist(),
                "_predicted_by_station": metrics["predicted_by_station"].tolist(),
                "_absolute_residual_by_station": metrics["absolute_residual_by_station"].tolist(),
            }
        )
    acceptance = g1.evaluate_acceptance(acceptance_rows)
    minima = {}
    for width in (1.5, 2.0, 3.0):
        rows = [
            (item, compact)
            for item, compact in zip(planned, compact_rows, strict=True)
            if item["width_css_px"] == width and item["background_policy"] == "gate"
        ]
        item, compact = min(rows, key=lambda pair: (pair[1]["observed_distance"], pair[0]["id"]))
        minima[f"{width:g}"] = {
            "observed_delta_e_ok": compact["observed_distance"],
            "case_id": item["id"],
            "roles": item["roles"],
            "state": item["state"],
            "background": item["background"],
        }
    return {
        "schema_version": PAIR_EVIDENCE_SCHEMA_VERSION,
        "artifact_kind": "g2-complete-browser-pair-reconstruction",
        "request_sha256": sha256_json(request),
        "candidate_id": request["candidate_id"],
        "pair_count": len(compact_rows),
        "pair_order_sha256": sha256_json([row["id"] for row in compact_rows]),
        "rows": compact_rows,
        "browser_residual_acceptance": acceptance,
        "minimum_pair_by_width": minima,
        "human_visibility_floor": None,
        "human_width_capacity": None,
    }


def run_browser_validation(
    request_path: Path,
    output_dir: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    request = _load_object(request_path, "browser request")
    p3.validate_browser_oracle_request(request, inputs, contract)
    browse = g1._browse_binary()
    require(browse is not None, "gstack Chromium browser is unavailable")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    status_text = g1._browse(browse, output_dir, "status", timeout=60)
    user_agent = g1._browse(browse, output_dir, "js", "navigator.userAgent", timeout=60)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(
        prefix=f"ember-g2-{request['shortlist_role'].lower()}-"
    ) as temporary:
        evidence_rows, performance = _capture_observations(browse, request, inputs, Path(temporary))
    observation_payload = {
        "schema_version": OBSERVATION_EVIDENCE_SCHEMA_VERSION,
        "artifact_kind": "g2-full-ordered-browser-observations",
        "request_sha256": sha256_json(request),
        "candidate_id": request["candidate_id"],
        "observation_count": len(evidence_rows),
        "observation_order_sha256": sha256_json(
            [row["request_observation_id"] for row in evidence_rows]
        ),
        "records": evidence_rows,
    }
    role = request["shortlist_role"].lower()
    observation_path = output_dir / f"browser-observations-{role}.json"
    _atomic_json(observation_path, observation_payload, compact=True)
    require(
        observation_path.stat().st_size < BROWSER_EVIDENCE_LIMIT_BYTES,
        "observation evidence exceeds 50 MB",
    )

    pair_payload = _pair_evidence(evidence_rows, request, inputs)
    pair_path = output_dir / f"browser-pairs-{role}.json"
    _atomic_json(pair_path, pair_payload, compact=True)
    require(pair_path.stat().st_size < BROWSER_EVIDENCE_LIMIT_BYTES, "pair evidence exceeds 50 MB")

    result_rows = _browser_result_observations(evidence_rows, request, inputs, contract)
    aggregate = "FAIL" if any(row["status"] == "FAIL" for row in result_rows) else "PASS"
    if pair_payload["browser_residual_acceptance"]["status"] != "PASS":
        aggregate = "FAIL"
    deltas = [row["delta_e_ok"] for row in result_rows]
    replay = {
        "schema_version": 1,
        "status": aggregate,
        "request_sha256": sha256_json(request),
        "candidate_id": request["candidate_id"],
        "input_chain_sha256": request["input_chain_sha256"],
        "observation_count": len(result_rows),
        "pass_count": sum(row["status"] == "PASS" for row in result_rows),
        "fail_count": sum(row["status"] == "FAIL" for row in result_rows),
        "error_count": 0,
        "maximum_delta_e_ok": max(deltas),
    }
    result = {
        "schema_version": p3.BROWSER_SCHEMA_VERSION,
        "request_sha256": sha256_json(request),
        "candidate_id": request["candidate_id"],
        "serialized_bank_sha256": request["serialized_bank_sha256"],
        "input_chain_sha256": request["input_chain_sha256"],
        "status": aggregate,
        "observations": result_rows,
        "source_provenance": {
            "browser": "Chromium via gstack browse",
            "browser_version": user_agent,
            "probe_sha256": inputs.source_sha256["browser_probe"],
        },
        "replay_receipt": replay,
        "replay_sha256": sha256_json(replay),
        "full_image_hash_used": False,
        "human_width_capacity": None,
    }
    p3.validate_browser_oracle_result(result, request, inputs, contract)
    result_path = output_dir / f"browser-result-{role}.json"
    _atomic_json(result_path, result, compact=True)
    summary = {
        "schema_version": 1,
        "artifact_kind": "g2-browser-evidence-summary",
        "shortlist_role": request["shortlist_role"],
        "candidate_id": request["candidate_id"],
        "request": {"file": request_path.name, "sha256": sha256_file(request_path)},
        "result": {"file": result_path.name, "sha256": sha256_file(result_path)},
        "observations": {
            "file": observation_path.name,
            "sha256": sha256_file(observation_path),
            "bytes": observation_path.stat().st_size,
            "count": len(evidence_rows),
        },
        "pairs": {
            "file": pair_path.name,
            "sha256": sha256_file(pair_path),
            "bytes": pair_path.stat().st_size,
            "count": pair_payload["pair_count"],
        },
        "status": aggregate,
        "browser_residual_acceptance": pair_payload["browser_residual_acceptance"],
        "minimum_pair_by_width": pair_payload["minimum_pair_by_width"],
        "capture": {
            "tiles": int(performance["tiles"]),
            "chunks": int(performance["chunks"]),
            "browser_seconds": round(performance["browser_seconds"], 3),
            "total_seconds": round(time.perf_counter() - started, 3),
            "browser_status": g1._sanitize_status(status_text),
        },
        "human_width_capacity": None,
        "production_promotion_authorized": False,
    }
    _atomic_json(output_dir / f"browser-summary-{role}.json", summary)
    return summary


def verify_browser_evidence(
    request_path: Path,
    result_path: Path,
    observation_path: Path,
    pair_path: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    request = _load_object(request_path, "browser request")
    result = _load_object(result_path, "browser result")
    observations = _load_object(observation_path, "browser observations")
    pairs = _load_object(pair_path, "browser pairs")
    p3.validate_browser_oracle_result(result, request, inputs, contract)
    require(
        observations.get("request_sha256") == sha256_json(request),
        "observation request hash is stale",
    )
    require(
        observations.get("candidate_id") == request["candidate_id"],
        "observation candidate is stale",
    )
    records = observations.get("records")
    require(
        isinstance(records, list) and len(records) == 25_920,
        "observation evidence count is invalid",
    )
    require(
        [row["request_observation_id"] for row in records]
        == [row["id"] for row in request["requested_role_observations"]],
        "observation evidence is incomplete or reordered",
    )
    require(
        observations.get("observation_order_sha256")
        == sha256_json([row["request_observation_id"] for row in records]),
        "observation order hash is stale",
    )
    expected_pairs = _pair_evidence(records, request, inputs)
    require(
        canonical_json(pairs) == canonical_json(expected_pairs),
        "pair evidence differs from independent reconstruction",
    )
    require(pairs["pair_count"] == 32_400, "pair evidence count is not 32,400")
    require(
        pairs["browser_residual_acceptance"]["status"] == "PASS", "browser residual gates failed"
    )
    require(result["status"] == "PASS", "browser result failed")
    return {
        "status": "PASS",
        "candidate_id": request["candidate_id"],
        "shortlist_role": request["shortlist_role"],
        "observation_count": len(records),
        "pair_count": pairs["pair_count"],
        "request_sha256": sha256_json(request),
        "result_sha256": sha256_json(result),
        "observations_sha256": sha256_json(observations),
        "pairs_sha256": sha256_json(pairs),
    }


def _load_bindings(path: Path) -> list[dict[str, Any]]:
    value = json.loads(Path(path).read_text())
    require(isinstance(value, list), "binding file must contain an array")
    return [dict(row) for row in value]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and verify the G2 palette review package")
    parser.add_argument("--experiment", type=Path, default=HERE)
    subparsers = parser.add_subparsers(dest="command", required=True)
    frontier = subparsers.add_parser("frontier")
    frontier.add_argument("--search-root", type=Path, required=True)
    frontier.add_argument("--bindings", type=Path, required=True)
    frontier.add_argument("--output", type=Path, required=True)
    requests = subparsers.add_parser("requests")
    requests.add_argument("--search-root", type=Path, required=True)
    requests.add_argument("--receipt", type=Path, required=True)
    requests.add_argument("--output-dir", type=Path, required=True)
    browser = subparsers.add_parser("browser")
    browser.add_argument("--request", type=Path, required=True)
    browser.add_argument("--output-dir", type=Path, required=True)
    verify = subparsers.add_parser("verify-browser")
    verify.add_argument("--request", type=Path, required=True)
    verify.add_argument("--result", type=Path, required=True)
    verify.add_argument("--observations", type=Path, required=True)
    verify.add_argument("--pairs", type=Path, required=True)
    arguments = parser.parse_args()
    inputs = p3.load_inputs(arguments.experiment)
    contract = p3.load_contract(arguments.experiment / "phase3-search-contract.json")
    if arguments.command == "frontier":
        value = build_frontier_receipt(
            arguments.search_root,
            _load_bindings(arguments.bindings),
            arguments.output,
            inputs,
            contract,
        )
    elif arguments.command == "requests":
        value = build_browser_requests(
            arguments.receipt,
            arguments.search_root,
            arguments.output_dir,
            inputs,
            contract,
        )
        value = {key: sha256_json(item) for key, item in value.items()}
    elif arguments.command == "browser":
        value = run_browser_validation(arguments.request, arguments.output_dir, inputs, contract)
    else:
        value = verify_browser_evidence(
            arguments.request,
            arguments.result,
            arguments.observations,
            arguments.pairs,
            inputs,
            contract,
        )
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
