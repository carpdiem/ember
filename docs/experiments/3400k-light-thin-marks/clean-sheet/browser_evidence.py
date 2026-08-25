#!/usr/bin/env python3
"""Build, capture, and verify clean-sheet Chromium evidence, including fg_0.

All persistent output is explicit and external to the repository. Screenshots and
HTML atlases exist only in a temporary directory and are deleted after capture.
"""

from __future__ import annotations

import argparse
import base64
import itertools
import json
import math
import subprocess
import sys
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
ROOT = EXPERIMENT.parents[2]
for directory in (HERE, EXPERIMENT):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import g1_browser_validate as g1
import g2_package as g2
import optimizer as clean
import phase3_optimizer as p3

SCHEMA_VERSION = 1
BASE_COUNT = 2_160
CATEGORY_OBSERVATION_COUNT = 25_920
FG0_OBSERVATION_COUNT = 4_320
OBSERVATION_COUNT = 30_240
CATEGORICAL_PAIR_COUNT = 32_400
CATEGORY_FG0_PAIR_COUNT = 25_920
PAIR_COUNT = 58_320
PAIR_FAMILY_ORDER = ("categorical", "category_fg_0")
EVIDENCE_LIMIT_BYTES = 50_000_000
SEARCH_FILES = ("catalog-summary.json", "candidates.json", "metrics.json")

_REQUEST_KEYS = {
    "schema_version",
    "artifact_kind",
    "request_role",
    "candidate_id",
    "lane",
    "serialized_bank",
    "serialized_bank_sha256",
    "binding",
    "mask_set",
    "counts",
    "pair_family_order",
    "requested_observations",
    "requested_pairs",
    "full_image_hash_used",
    "human_width_capacity",
    "production_promotion_authorized",
}
_BINDING_KEYS = {
    "input_chain_sha256",
    "search_contract_sha256",
    "search_artifacts",
    "optimizer_source",
}
_SOURCE_KEYS = {"file", "sha256", "commit"}
_ARTIFACT_KEYS = {"file", "sha256", "canonical_sha256"}
_COUNTS_KEYS = {
    "bases",
    "category_observations",
    "fg0_observations",
    "observations",
    "categorical_pairs",
    "category_fg0_pairs",
    "pairs",
}
_OBSERVATION_REQUEST_KEYS = {
    "id",
    "family",
    "mask_id",
    "state",
    "background",
    "role",
    "lane",
}
_PAIR_REQUEST_KEYS = {
    "id",
    "family",
    "state",
    "background",
    "width_css_px",
    "style",
    "orientation",
    "dpr",
    "phase_css_px",
    "roles",
    "left_observation_id",
    "right_observation_id",
}
_OBSERVATION_TOP_KEYS = {
    "schema_version",
    "artifact_kind",
    "request_sha256",
    "candidate_id",
    "binding",
    "observation_count",
    "observation_order_sha256",
    "records",
}
_OBSERVATION_RECORD_KEYS = {
    "request_observation_id",
    "sample_count",
    "observed_rgb8_median",
    "observed_rgb8_base64",
}
_PAIRS_TOP_KEYS = {
    "schema_version",
    "artifact_kind",
    "request_sha256",
    "candidate_id",
    "binding",
    "pair_count",
    "pair_order_sha256",
    "family_order",
    "family_counts",
    "rows",
    "metrics_by_family",
}
_PAIR_RECORD_KEYS = {
    "id",
    "family",
    "matched_station_count",
    "observed_delta_e_ok",
    "proxy_prediction_delta_e_ok",
    "actual_residual_delta_e_ok",
}
_RESULT_KEYS = {
    "schema_version",
    "artifact_kind",
    "status",
    "request_sha256",
    "candidate_id",
    "serialized_bank_sha256",
    "binding",
    "counts",
    "observation_residuals_by_family",
    "pair_metrics_by_family",
    "source_provenance",
    "full_image_hash_used",
    "human_width_capacity",
    "production_promotion_authorized",
}
_PROVENANCE_KEYS = {"browser", "browser_version", "browser_status"}


class CleanSheetEvidenceError(RuntimeError):
    """Raised for stale, incomplete, reordered, or tampered clean-sheet evidence."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CleanSheetEvidenceError(message)


def exact_keys(value: object, expected: set[str], label: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{label} must be an object")
    require(set(value) == expected, f"{label} keys are not closed")
    return value


def canonical_json(value: Any) -> bytes:
    return g2.canonical_json(value)


def sha256_json(value: Any) -> str:
    return p3.sha256_json(value)


def sha256_file(path: Path) -> str:
    return g2.sha256_file(path)


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CleanSheetEvidenceError(f"{label} cannot be read: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def _write_json(path: Path, value: Any) -> None:
    payload = canonical_json(value) + b"\n"
    require(len(payload) < EVIDENCE_LIMIT_BYTES, f"{path.name} would exceed 50 MB")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _optimizer_source() -> dict[str, str]:
    relative = str((HERE / "optimizer.py").relative_to(ROOT))
    completed = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", relative],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    require(completed.returncode == 0, "optimizer source commit cannot be resolved")
    commit = completed.stdout.strip()
    require(len(commit) == 40, "optimizer source commit is invalid")
    return {"file": "optimizer.py", "sha256": sha256_file(HERE / "optimizer.py"), "commit": commit}


def _artifact_binding(
    search_artifacts: Path, inputs: p3.Phase3Inputs, contract: Mapping[str, Any]
) -> dict[str, Any]:
    directory = Path(search_artifacts)
    artifacts = []
    for name in SEARCH_FILES:
        path = directory / name
        payload = _load_object(path, f"search artifact {name}")
        artifacts.append(
            {"file": name, "sha256": sha256_file(path), "canonical_sha256": sha256_json(payload)}
        )
    return {
        "input_chain_sha256": p3.input_chain_sha256(inputs),
        "search_contract_sha256": sha256_json(contract),
        "search_artifacts": artifacts,
        "optimizer_source": _optimizer_source(),
    }


def _validate_binding(
    binding: object,
    search_artifacts: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> None:
    row = exact_keys(binding, _BINDING_KEYS, "evidence binding")
    exact_keys(row["optimizer_source"], _SOURCE_KEYS, "optimizer source")
    artifacts = row["search_artifacts"]
    require(
        isinstance(artifacts, list) and len(artifacts) == 3, "search artifact binding is incomplete"
    )
    for index, artifact in enumerate(artifacts):
        exact_keys(artifact, _ARTIFACT_KEYS, f"search artifact binding {index}")
    require(
        row == _artifact_binding(search_artifacts, inputs, contract), "evidence binding is stale"
    )


def _base_rows(inputs: p3.Phase3Inputs) -> list[dict[str, Any]]:
    planned = g1._validate_ledger(inputs.raster_ledger)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in planned:
        key = g1._base_key(item)
        if key not in seen:
            seen.add(key)
            values = dict(zip(g1.BASE_FIELDS, key, strict=True))
            values["phase_css_px"] = list(values["phase_css_px"])
            rows.append({"id": f"base-{len(rows) + 1:04d}", **values})
    require(len(rows) == BASE_COUNT, "base factorization is not exactly 2,160")
    return rows


def build_observation_plan(inputs: p3.Phase3Inputs) -> list[dict[str, Any]]:
    """Return category observations followed by the independent fg_0 extension."""

    masks = sorted(inputs.raster_masks["records"], key=lambda row: row["id"])
    rows: list[dict[str, Any]] = []
    for family, roles in (("categorical", p3.ROLES), ("category_fg_0", ("fg_0",))):
        for mask in masks:
            lane = mask["key"]["lane"]
            for state in ("commanded", "transformed"):
                for background in (*p3.GATE_BACKGROUNDS, p3.REPORT_BACKGROUND):
                    for role in roles:
                        rows.append(
                            {
                                "id": f"{mask['id']}/{state}/{background}/{role}",
                                "family": family,
                                "mask_id": mask["id"],
                                "state": state,
                                "background": background,
                                "role": role,
                                "lane": lane,
                            }
                        )
    require(
        sum(row["family"] == "categorical" for row in rows) == CATEGORY_OBSERVATION_COUNT,
        "category observation count is not 25,920",
    )
    require(
        sum(row["family"] == "category_fg_0" for row in rows) == FG0_OBSERVATION_COUNT,
        "fg0 observation count is not 4,320",
    )
    require(len(rows) == OBSERVATION_COUNT, "total observation count is not 30,240")
    return rows


def build_pair_plan(inputs: p3.Phase3Inputs) -> list[dict[str, Any]]:
    """Return the closed categorical then category/fg_0 pair-family ordering."""

    masks = {
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
    bases = _base_rows(inputs)
    rows: list[dict[str, Any]] = []

    def observation_id(mask: Mapping[str, Any], base: Mapping[str, Any], role: str) -> str:
        return f"{mask['id']}/{base['state']}/{base['background']}/{role}"

    for base in bases:
        base_key = tuple(
            tuple(base[field]) if field == "phase_css_px" else base[field]
            for field in g1.BASE_FIELDS
        )
        left_mask = masks[g1._mask_key(base_key, 0)]
        right_mask = masks[g1._mask_key(base_key, 1)]
        common = {field: base[field] for field in g1.BASE_FIELDS}
        for left, right in itertools.combinations(p3.ROLES, 2):
            rows.append(
                {
                    "id": f"categorical-{len(rows) + 1:05d}",
                    "family": "categorical",
                    **common,
                    "roles": [left, right],
                    "left_observation_id": observation_id(left_mask, base, left),
                    "right_observation_id": observation_id(right_mask, base, right),
                }
            )
    require(len(rows) == CATEGORICAL_PAIR_COUNT, "categorical pair count is not 32,400")
    fg_index = 0
    for base in bases:
        base_key = tuple(
            tuple(base[field]) if field == "phase_css_px" else base[field]
            for field in g1.BASE_FIELDS
        )
        lane_masks = [masks[g1._mask_key(base_key, lane)] for lane in (0, 1)]
        common = {field: base[field] for field in g1.BASE_FIELDS}
        for category in p3.ROLES:
            for category_lane, fg_lane in ((0, 1), (1, 0)):
                fg_index += 1
                rows.append(
                    {
                        "id": f"category-fg0-{fg_index:05d}",
                        "family": "category_fg_0",
                        **common,
                        "roles": [category, "fg_0"],
                        "left_observation_id": observation_id(
                            lane_masks[category_lane], base, category
                        ),
                        "right_observation_id": observation_id(lane_masks[fg_lane], base, "fg_0"),
                    }
                )
    require(fg_index == CATEGORY_FG0_PAIR_COUNT, "category-fg0 pair count is not 25,920")
    require(len(rows) == PAIR_COUNT, "total pair count is not 58,320")
    require(
        [family for family, _ in itertools.groupby(row["family"] for row in rows)]
        == list(PAIR_FAMILY_ORDER),
        "pair family order differs",
    )
    return rows


def _counts() -> dict[str, int]:
    return {
        "bases": BASE_COUNT,
        "category_observations": CATEGORY_OBSERVATION_COUNT,
        "fg0_observations": FG0_OBSERVATION_COUNT,
        "observations": OBSERVATION_COUNT,
        "categorical_pairs": CATEGORICAL_PAIR_COUNT,
        "category_fg0_pairs": CATEGORY_FG0_PAIR_COUNT,
        "pairs": PAIR_COUNT,
    }


def _search_rows(search_artifacts: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = _load_object(Path(search_artifacts) / "candidates.json", "candidate artifact")
    metrics = _load_object(Path(search_artifacts) / "metrics.json", "metrics artifact")
    return candidates, metrics


def _request_for(
    role: str,
    candidate: Mapping[str, Any],
    binding: Mapping[str, Any],
    observations: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    inputs: p3.Phase3Inputs,
) -> dict[str, Any]:
    bank = p3.canonical_bank(candidate["bank"])
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "clean-sheet-chromium-request-with-fg0",
        "request_role": role,
        "candidate_id": candidate["candidate_id"],
        "lane": candidate["lane"],
        "serialized_bank": list(bank),
        "serialized_bank_sha256": p3.bank_hash(bank),
        "binding": dict(binding),
        "mask_set": {
            "file": p3.INPUT_FILENAMES["raster_masks"],
            "sha256": inputs.source_sha256["raster_masks"],
            "count": 720,
            "rerasterize": False,
        },
        "counts": _counts(),
        "pair_family_order": list(PAIR_FAMILY_ORDER),
        "requested_observations": observations,
        "requested_pairs": pairs,
        "full_image_hash_used": False,
        "human_width_capacity": None,
        "production_promotion_authorized": False,
    }


def build_requests(
    search_artifacts: Path,
    output_dir: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Recompute the clean-sheet search and write reference/A/B/C requests."""

    clean.validate_artifacts(search_artifacts, inputs, contract, reduced=False)
    candidates_payload, _ = _search_rows(search_artifacts)
    candidates = candidates_payload["candidates"]
    require([row["lane"] for row in candidates] == ["A", "B", "C"], "candidate lanes differ")
    binding = _artifact_binding(search_artifacts, inputs, contract)
    observations = build_observation_plan(inputs)
    pairs = build_pair_plan(inputs)
    baseline = clean._baseline_bank(inputs)
    reference = {
        "lane": "REFERENCE",
        "bank": list(baseline),
        "candidate_id": sha256_json(
            {"lane": "REFERENCE", "bank": list(baseline), "contract": sha256_json(contract)}
        ),
    }
    output = p3.validate_external_output_path(Path(output_dir), inputs)
    output.mkdir(parents=True, exist_ok=True)
    requests = {}
    for role, candidate in (
        ("REFERENCE", reference),
        *zip(("A", "B", "C"), candidates, strict=True),
    ):
        request = _request_for(role, candidate, binding, observations, pairs, inputs)
        validate_request(request, search_artifacts, inputs, contract, validate_search=False)
        _write_json(output / f"browser-request-{role.lower()}.json", request)
        requests[role] = request
    return requests


def _expected_candidates(
    search_artifacts: Path, inputs: p3.Phase3Inputs, contract: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    candidates, _ = _search_rows(search_artifacts)
    rows = {row["lane"]: row for row in candidates["candidates"]}
    baseline = clean._baseline_bank(inputs)
    rows["REFERENCE"] = {
        "lane": "REFERENCE",
        "bank": list(baseline),
        "candidate_id": sha256_json(
            {"lane": "REFERENCE", "bank": list(baseline), "contract": sha256_json(contract)}
        ),
    }
    return rows


def validate_request(
    request: object,
    search_artifacts: Path | None,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
    *,
    validate_search: bool = True,
) -> None:
    row = exact_keys(request, _REQUEST_KEYS, "browser request")
    require(row["schema_version"] == 1, "browser request schema is invalid")
    require(
        row["artifact_kind"] == "clean-sheet-chromium-request-with-fg0", "request kind is invalid"
    )
    role = row["request_role"]
    require(role in {"REFERENCE", "A", "B", "C"} and row["lane"] == role, "request role is invalid")
    exact_keys(row["counts"], _COUNTS_KEYS, "request counts")
    require(row["counts"] == _counts(), "request counts differ")
    require(row["pair_family_order"] == list(PAIR_FAMILY_ORDER), "pair family order differs")
    require(
        row["mask_set"]
        == {
            "file": p3.INPUT_FILENAMES["raster_masks"],
            "sha256": inputs.source_sha256["raster_masks"],
            "count": 720,
            "rerasterize": False,
        },
        "request mask set is stale",
    )
    require(
        row["full_image_hash_used"] is False
        and row["human_width_capacity"] is None
        and row["production_promotion_authorized"] is False,
        "request makes a forbidden image, human, or promotion claim",
    )
    if validate_search and search_artifacts is not None:
        clean.validate_artifacts(search_artifacts, inputs, contract, reduced=False)
    if search_artifacts is None:
        binding = exact_keys(row["binding"], _BINDING_KEYS, "evidence binding")
        exact_keys(binding["optimizer_source"], _SOURCE_KEYS, "optimizer source")
        require(binding["optimizer_source"] == _optimizer_source(), "optimizer source is stale")
        require(
            binding["input_chain_sha256"] == p3.input_chain_sha256(inputs)
            and binding["search_contract_sha256"] == sha256_json(contract),
            "request input or contract binding is stale",
        )
        artifacts = binding["search_artifacts"]
        require(
            isinstance(artifacts, list)
            and [artifact.get("file") for artifact in artifacts] == list(SEARCH_FILES),
            "search artifact binding is incomplete or reordered",
        )
        for index, artifact in enumerate(artifacts):
            exact_keys(artifact, _ARTIFACT_KEYS, f"search artifact binding {index}")
            for key in ("sha256", "canonical_sha256"):
                value = artifact[key]
                require(
                    isinstance(value, str)
                    and len(value) == 64
                    and all(character in "0123456789abcdef" for character in value),
                    f"search artifact {key} is invalid",
                )
        expected = {
            "lane": role,
            "bank": list(p3.canonical_bank(row["serialized_bank"])),
            "candidate_id": sha256_json(
                {
                    "lane": role,
                    "bank": list(p3.canonical_bank(row["serialized_bank"])),
                    "contract": sha256_json(contract),
                }
            ),
        }
    else:
        require(search_artifacts is not None, "search artifacts are required for full validation")
        _validate_binding(row["binding"], search_artifacts, inputs, contract)
        expected = _expected_candidates(search_artifacts, inputs, contract)[role]
    bank = p3.canonical_bank(row["serialized_bank"])
    require(list(bank) == expected["bank"], "request bank differs from recomputed candidate")
    require(row["serialized_bank_sha256"] == p3.bank_hash(bank), "request bank hash is stale")
    require(row["candidate_id"] == expected["candidate_id"], "request candidate ID is stale")
    observations = row["requested_observations"]
    pairs = row["requested_pairs"]
    require(isinstance(observations, list), "request observations must be an array")
    require(isinstance(pairs, list), "request pairs must be an array")
    for index, item in enumerate(observations):
        exact_keys(item, _OBSERVATION_REQUEST_KEYS, f"request observation {index}")
    for index, item in enumerate(pairs):
        exact_keys(item, _PAIR_REQUEST_KEYS, f"request pair {index}")
    require(
        observations == build_observation_plan(inputs),
        "request observations are incomplete or reordered",
    )
    require(pairs == build_pair_plan(inputs), "request pairs are incomplete or reordered")


def _render_context(request: Mapping[str, Any], inputs: p3.Phase3Inputs) -> dict[str, Any]:
    categorical = dict(zip(p3.ROLE_NAMES, request["serialized_bank"], strict=True))
    categorical["fg_0"] = inputs.baseline["family"]["surfaces"]["fg_0"]
    return {
        "contract": inputs.raster_ledger["specimen_contract"],
        "categorical": categorical,
        "surfaces": {
            name: inputs.baseline["family"]["surfaces"][name]
            for name in (*p3.GATE_BACKGROUNDS, p3.REPORT_BACKGROUND)
        },
    }


def _g1_role(role: str) -> str:
    return role if role.startswith("cat.") else f"cat.{role}"


def _capture(
    browse: Path,
    request: Mapping[str, Any],
    inputs: p3.Phase3Inputs,
    workspace: Path,
) -> list[dict[str, Any]]:
    masks = {row["id"]: row for row in inputs.raster_masks["records"]}
    context = _render_context(request, inputs)
    evidence: dict[str, dict[str, Any]] = {}
    for dpr in (1, 2):
        tiles = []
        for item in request["requested_observations"]:
            mask = masks[item["mask_id"]]
            key = mask["key"]
            if key["dpr"] != dpr:
                continue
            tiles.append(
                {
                    "id": item["id"],
                    "kind": "color",
                    "base": [
                        item["state"],
                        item["background"],
                        key["width_css_px"],
                        key["style"],
                        key["orientation"],
                        key["dpr"],
                        key["phase_css_px"],
                    ],
                    "role": _g1_role(item["role"]),
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
            stem = f"clean-{request['request_role'].lower()}-dpr{dpr}-{start // g1.CHUNK_TILES:03d}"
            html_path, png_path = workspace / f"{stem}.html", workspace / f"{stem}.png"
            g1._write_atlas(html_path, chunk, context)
            commands = json.dumps(
                [
                    ["goto", html_path.as_uri()],
                    ["screenshot", str(png_path), "--selector", "#atlas"],
                ]
            )
            g1._run([str(browse), "chain"], cwd=workspace, stdin=commands)
            with Image.open(png_path) as opened:
                image = np.asarray(opened.convert("RGB"), dtype=np.uint8)
            expected_shape = (
                math.ceil(len(chunk) / g1.ATLAS_COLUMNS) * g1.TILE_HEIGHT * dpr,
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
                evidence[tile["id"]] = {
                    "request_observation_id": tile["id"],
                    "sample_count": len(observed),
                    "observed_rgb8_median": np.median(observed, axis=0).tolist(),
                    "observed_rgb8_base64": base64.b64encode(observed.tobytes()).decode("ascii"),
                }
            html_path.unlink(missing_ok=True)
            png_path.unlink(missing_ok=True)
    rows = [evidence[item["id"]] for item in request["requested_observations"]]
    require(len(rows) == OBSERVATION_COUNT, "capture observation count is not 30,240")
    return rows


def _decode_observation(record: Mapping[str, Any], mask: Mapping[str, Any]) -> np.ndarray:
    count = record["sample_count"]
    require(
        isinstance(count, int) and not isinstance(count, bool) and count > 0,
        "sample count is invalid",
    )
    require(count == mask["sample_count"], "sample count differs from exact mask")
    try:
        decoded = base64.b64decode(record["observed_rgb8_base64"], validate=True)
    except (ValueError, TypeError) as error:
        raise CleanSheetEvidenceError("observation RGB8 payload is invalid") from error
    values = np.frombuffer(decoded, dtype=np.uint8)
    require(values.size == count * 3, "observation RGB8 cardinality differs")
    values = values.reshape(count, 3)
    median = np.median(values, axis=0).tolist()
    require(record["observed_rgb8_median"] == median, "observation median differs from raw RGB8")
    return values


def _pair_evidence(
    records: Sequence[Mapping[str, Any]],
    request: Mapping[str, Any],
    inputs: p3.Phase3Inputs,
) -> dict[str, Any]:
    masks = {row["id"]: row for row in inputs.raster_masks["records"]}
    requested_observations = {row["id"]: row for row in request["requested_observations"]}
    evidence = {row["request_observation_id"]: row for row in records}
    context = _render_context(request, inputs)
    rows = []
    acceptance: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for item in request["requested_pairs"]:
        left_request = requested_observations[item["left_observation_id"]]
        right_request = requested_observations[item["right_observation_id"]]
        left_mask, right_mask = masks[left_request["mask_id"]], masks[right_request["mask_id"]]
        left = {**evidence[left_request["id"]], "role": _g1_role(left_request["role"])}
        right = {**evidence[right_request["id"]], "role": _g1_role(right_request["role"])}
        base = {field: item[field] for field in g1.BASE_FIELDS}
        metrics = g1.reconstruct_pair_metrics(left, right, left_mask, right_mask, base, context)
        require(metrics["status"] == "PASS", f"pair reconstruction failed for {item['id']}")
        compact = {
            "id": item["id"],
            "family": item["family"],
            "matched_station_count": metrics["matched_station_count"],
            "observed_delta_e_ok": round(metrics["observed_distance"], 8),
            "proxy_prediction_delta_e_ok": round(metrics["proxy_prediction"], 8),
            "actual_residual_delta_e_ok": round(metrics["proxy_error"], 8),
        }
        rows.append(compact)
        acceptance[item["family"]].append(
            {
                **item,
                "status": "PASS",
                "observed_distance": compact["observed_delta_e_ok"],
                "proxy_prediction": compact["proxy_prediction_delta_e_ok"],
                "proxy_error": compact["actual_residual_delta_e_ok"],
                "_observed_by_station": metrics["observed_by_station"].tolist(),
                "_predicted_by_station": metrics["predicted_by_station"].tolist(),
                "_absolute_residual_by_station": metrics["absolute_residual_by_station"].tolist(),
            }
        )
        key = f"{item['width_css_px']:g}/{item['state']}/{item['background']}"
        grouped[item["family"]][key].append(compact["observed_delta_e_ok"])
        grouped[item["family"]][f"residual/{key}"].append(compact["actual_residual_delta_e_ok"])
    metrics_by_family = {}
    for family in PAIR_FAMILY_ORDER:
        family_rows = acceptance[family]
        family_acceptance = g1.evaluate_acceptance(family_rows)
        actual = {}
        for width in (1.5, 2.0, 3.0):
            width_key = f"{width:g}"
            actual[width_key] = {}
            for state in ("commanded", "transformed"):
                actual[width_key][state] = {}
                for background in (*p3.GATE_BACKGROUNDS, p3.REPORT_BACKGROUND):
                    key = f"{width_key}/{state}/{background}"
                    values = grouped[family][key]
                    residuals = grouped[family][f"residual/{key}"]
                    actual[width_key][state][background] = {
                        "minimum_observed_delta_e_ok": min(values),
                        "actual_residual_mae_delta_e_ok": float(np.mean(residuals)),
                        "actual_residual_max_delta_e_ok": max(residuals),
                    }
        metrics_by_family[family] = {
            "pair_count": len(family_rows),
            "actual_by_width_state_background": actual,
            "actual_residual_acceptance": family_acceptance,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "clean-sheet-complete-browser-pairs-with-fg0",
        "request_sha256": sha256_json(request),
        "candidate_id": request["candidate_id"],
        "binding": request["binding"],
        "pair_count": len(rows),
        "pair_order_sha256": sha256_json([row["id"] for row in rows]),
        "family_order": list(PAIR_FAMILY_ORDER),
        "family_counts": {
            "categorical": sum(row["family"] == "categorical" for row in rows),
            "category_fg_0": sum(row["family"] == "category_fg_0" for row in rows),
        },
        "rows": rows,
        "metrics_by_family": metrics_by_family,
    }


def _observation_residuals(
    records: Sequence[Mapping[str, Any]],
    request: Mapping[str, Any],
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    masks = {row["id"]: row for row in inputs.raster_masks["records"]}
    context = _render_context(request, inputs)
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    margin = float(contract["raster"]["calibrated_error_margin_delta_e_ok"])
    for record, item in zip(records, request["requested_observations"], strict=True):
        mask = masks[item["mask_id"]]
        actual = np.asarray(record["observed_rgb8_median"], dtype=float) / 255.0
        base = {
            "state": item["state"],
            "background": item["background"],
        }
        predicted = g1._predict_rgb8(mask, _g1_role(item["role"]), base, context)
        expected = np.median(predicted, axis=0) / 255.0
        delta = float(np.linalg.norm(g1._oklab(actual) - g1._oklab(expected)) * 100.0)
        width = mask["key"]["width_css_px"]
        key = f"{width:g}/{item['state']}/{item['background']}"
        grouped[item["family"]][key].append(delta)
    result = {}
    for family in PAIR_FAMILY_ORDER:
        actual = {}
        all_values = []
        for width in (1.5, 2.0, 3.0):
            width_key = f"{width:g}"
            actual[width_key] = {}
            for state in ("commanded", "transformed"):
                actual[width_key][state] = {}
                for background in (*p3.GATE_BACKGROUNDS, p3.REPORT_BACKGROUND):
                    values = grouped[family][f"{width_key}/{state}/{background}"]
                    all_values.extend(values)
                    actual[width_key][state][background] = {
                        "actual_residual_mean_delta_e_ok": float(np.mean(values)),
                        "actual_residual_max_delta_e_ok": max(values),
                    }
        result[family] = {
            "status": "PASS" if max(all_values) <= margin else "FAIL",
            "maximum_delta_e_ok": max(all_values),
            "margin_delta_e_ok": margin,
            "actual_by_width_state_background": actual,
        }
    return result


def _result(
    request: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    pairs: Mapping[str, Any],
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    residuals = _observation_residuals(records, request, inputs, contract)
    pair_metrics = pairs["metrics_by_family"]
    status = "PASS"
    if any(residuals[family]["status"] != "PASS" for family in PAIR_FAMILY_ORDER):
        status = "FAIL"
    if any(
        pair_metrics[family]["actual_residual_acceptance"]["status"] != "PASS"
        for family in PAIR_FAMILY_ORDER
    ):
        status = "FAIL"
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "clean-sheet-browser-result-with-independent-fg0",
        "status": status,
        "request_sha256": sha256_json(request),
        "candidate_id": request["candidate_id"],
        "serialized_bank_sha256": request["serialized_bank_sha256"],
        "binding": request["binding"],
        "counts": request["counts"],
        "observation_residuals_by_family": residuals,
        "pair_metrics_by_family": pair_metrics,
        "source_provenance": dict(provenance),
        "full_image_hash_used": False,
        "human_width_capacity": None,
        "production_promotion_authorized": False,
    }


def run_browser(
    request_path: Path,
    output_dir: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    request = _load_object(request_path, "browser request")
    validate_request(request, None, inputs, contract, validate_search=False)
    browse = g1._browse_binary()
    require(browse is not None, "gstack Chromium browser is unavailable")
    output = p3.validate_external_output_path(Path(output_dir), inputs)
    output.mkdir(parents=True, exist_ok=True)
    browser_status = g1._sanitize_status(g1._browse(browse, output, "status", timeout=60))
    browser_version = g1._browse(browse, output, "js", "navigator.userAgent", timeout=60)
    with tempfile.TemporaryDirectory(
        prefix=f"clean-sheet-{request['request_role'].lower()}-"
    ) as temp:
        records = _capture(browse, request, inputs, Path(temp))
    observations = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "clean-sheet-full-ordered-browser-observations-with-fg0",
        "request_sha256": sha256_json(request),
        "candidate_id": request["candidate_id"],
        "binding": request["binding"],
        "observation_count": len(records),
        "observation_order_sha256": sha256_json([row["request_observation_id"] for row in records]),
        "records": records,
    }
    pairs = _pair_evidence(records, request, inputs)
    provenance = {
        "browser": "Chromium via gstack browse",
        "browser_version": browser_version,
        "browser_status": browser_status,
    }
    result = _result(request, records, pairs, inputs, contract, provenance)
    label = request["request_role"].lower()
    _write_json(output / f"browser-observations-{label}.json", observations)
    _write_json(output / f"browser-pairs-{label}.json", pairs)
    _write_json(output / f"browser-result-{label}.json", result)
    return result


def _validate_observations(
    payload: object, request: Mapping[str, Any], inputs: p3.Phase3Inputs
) -> list[dict[str, Any]]:
    row = exact_keys(payload, _OBSERVATION_TOP_KEYS, "browser observations")
    require(
        row["schema_version"] == 1
        and row["artifact_kind"] == "clean-sheet-full-ordered-browser-observations-with-fg0",
        "browser observation schema is invalid",
    )
    require(row["request_sha256"] == sha256_json(request), "observation request hash is stale")
    require(row["candidate_id"] == request["candidate_id"], "observation candidate is stale")
    require(row["binding"] == request["binding"], "observation binding is stale")
    records = row["records"]
    require(
        isinstance(records, list) and len(records) == OBSERVATION_COUNT,
        "observation count is invalid",
    )
    require(row["observation_count"] == len(records), "observation count is contradictory")
    masks = {mask["id"]: mask for mask in inputs.raster_masks["records"]}
    for index, (record, requested) in enumerate(
        zip(records, request["requested_observations"], strict=True)
    ):
        exact_keys(record, _OBSERVATION_RECORD_KEYS, f"browser observation record {index}")
        require(
            record["request_observation_id"] == requested["id"],
            "observations are incomplete or reordered",
        )
        _decode_observation(record, masks[requested["mask_id"]])
    order = [record["request_observation_id"] for record in records]
    require(
        row["observation_order_sha256"] == sha256_json(order), "observation order hash is stale"
    )
    return records


def _validate_pair_payload(payload: object) -> Mapping[str, Any]:
    row = exact_keys(payload, _PAIRS_TOP_KEYS, "browser pairs")
    records = row["rows"]
    require(isinstance(records, list), "pair rows must be an array")
    for index, record in enumerate(records):
        exact_keys(record, _PAIR_RECORD_KEYS, f"browser pair record {index}")
        require(record["family"] in PAIR_FAMILY_ORDER, "pair family is invalid")
    return row


def _validate_result_payload(payload: object) -> Mapping[str, Any]:
    row = exact_keys(payload, _RESULT_KEYS, "browser result")
    exact_keys(row["counts"], _COUNTS_KEYS, "result counts")
    exact_keys(row["source_provenance"], _PROVENANCE_KEYS, "result provenance")
    require(
        row["full_image_hash_used"] is False
        and row["human_width_capacity"] is None
        and row["production_promotion_authorized"] is False,
        "result makes a forbidden image, human, or promotion claim",
    )
    return row


def verify(
    request_path: Path,
    result_path: Path,
    observation_path: Path,
    pair_path: Path,
    search_artifacts: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
    *,
    validate_search: bool = True,
) -> dict[str, Any]:
    request = _load_object(request_path, "browser request")
    result = _load_object(result_path, "browser result")
    observations = _load_object(observation_path, "browser observations")
    pairs = _load_object(pair_path, "browser pairs")
    validate_request(
        request,
        search_artifacts,
        inputs,
        contract,
        validate_search=validate_search,
    )
    records = _validate_observations(observations, request, inputs)
    pair_row = _validate_pair_payload(pairs)
    result_row = _validate_result_payload(result)
    expected_pairs = _pair_evidence(records, request, inputs)
    require(
        canonical_json(pair_row) == canonical_json(expected_pairs),
        "pair evidence differs from raw evidence",
    )
    require(pair_row["pair_count"] == PAIR_COUNT, "pair count is not 58,320")
    require(pair_row["family_order"] == list(PAIR_FAMILY_ORDER), "pair family order differs")
    require(
        pair_row["family_counts"]
        == {"categorical": CATEGORICAL_PAIR_COUNT, "category_fg_0": CATEGORY_FG0_PAIR_COUNT},
        "pair family counts differ",
    )
    expected_result = _result(
        request,
        records,
        expected_pairs,
        inputs,
        contract,
        result_row["source_provenance"],
    )
    require(
        canonical_json(result_row) == canonical_json(expected_result),
        "result differs from raw evidence",
    )
    require(result_row["status"] == "PASS", "browser result failed")
    return {
        "status": "PASS",
        "candidate_id": request["candidate_id"],
        "request_role": request["request_role"],
        "observation_count": len(records),
        "pair_count": pair_row["pair_count"],
        "family_counts": pair_row["family_counts"],
        "request_sha256": sha256_json(request),
        "result_sha256": sha256_json(result),
        "observations_sha256": sha256_json(observations),
        "pairs_sha256": sha256_json(pairs),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    requests = subparsers.add_parser("requests")
    requests.add_argument("--search-artifacts", type=Path, required=True)
    requests.add_argument("--output-dir", type=Path, required=True)
    browser = subparsers.add_parser("browser")
    browser.add_argument("--request", type=Path, required=True)
    browser.add_argument("--output-dir", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--request", type=Path, required=True)
    verify_parser.add_argument("--result", type=Path, required=True)
    verify_parser.add_argument("--observations", type=Path, required=True)
    verify_parser.add_argument("--pairs", type=Path, required=True)
    verify_parser.add_argument("--search-artifacts", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    inputs = clean.load_authorized_inputs(EXPERIMENT, replay=True)
    contract = clean.load_contract(HERE / "search-contract.json")
    clean.validate_contract(contract, inputs)
    if args.command == "requests":
        value = {
            role: sha256_json(request)
            for role, request in build_requests(
                args.search_artifacts, args.output_dir, inputs, contract
            ).items()
        }
    elif args.command == "browser":
        value = run_browser(args.request, args.output_dir, inputs, contract)
    else:
        value = verify(
            args.request,
            args.result,
            args.observations,
            args.pairs,
            args.search_artifacts,
            inputs,
            contract,
        )
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
