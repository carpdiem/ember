#!/usr/bin/env python3
"""Independently replay every G1 pair row from compact factored browser evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import itertools
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
APPROVED_HEAD = "922ba7faa45ccdb56e95356750d353c7602da78a"
CAPTURE_SOURCE_HEAD = "98d7ff9183fa91112583fd6fe8a1ed16fa90e157"
EXPERIMENT_RELATIVE = "docs/experiments/3400k-light-thin-marks"
GAINS = np.array([1.0, 0.74, 0.53])
BASE_FIELDS = (
    "state",
    "background",
    "width_css_px",
    "style",
    "orientation",
    "dpr",
    "phase_css_px",
)


class EvidenceIntegrityError(RuntimeError):
    """Raised when tracked evidence fails an explicit replay integrity check."""


def require(condition: object, message: str) -> None:
    """Raise an optimization-proof, actionable evidence-integrity error."""

    if not condition:
        raise EvidenceIntegrityError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rgb(value: str) -> np.ndarray:
    value = value.removeprefix("#")
    return np.array([int(value[index : index + 2], 16) for index in (0, 2, 4)]) / 255.0


def _oklab(values: np.ndarray) -> np.ndarray:
    encoded = np.asarray(values, dtype=float)
    linear = np.where(
        encoded <= 0.04045,
        encoded / 12.92,
        ((encoded + 0.055) / 1.055) ** 2.4,
    )
    first = np.array(
        [
            [0.4122214708, 0.5363325363, 0.0514459929],
            [0.2119034982, 0.6806995451, 0.1073969566],
            [0.0883024619, 0.2817188376, 0.6299787005],
        ]
    )
    second = np.array(
        [
            [0.2104542553, 0.7936177850, -0.0040720468],
            [1.9779984951, -2.428592205, 0.4505937099],
            [0.0259040371, 0.7827717662, -0.808675766],
        ]
    )
    return np.cbrt(linear @ first.T) @ second.T


def _git_blob_hash(revision: str, relative_path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=HERE,
        capture_output=True,
        check=True,
    )
    return hashlib.sha256(completed.stdout).hexdigest()


def _expected_dimensions(contract: dict[str, Any]):
    pairs = itertools.combinations(contract["category_order"], 2)
    return itertools.product(
        contract["state_order"],
        contract["background_order"],
        contract["widths_css_px"],
        contract["style_order"],
        contract["orientations"],
        contract["device_pixel_ratios"],
        contract["phases_css_px"],
        pairs,
    )


def _correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 2 or statistics.pstdev(left) == 0 or statistics.pstdev(right) == 0:
        return 1.0 if left == right else 0.0
    return float(np.corrcoef(np.asarray(left), np.asarray(right))[0, 1])


def _replay_acceptance(replayed_rows: list[dict[str, Any]]) -> dict[str, Any]:
    observed: list[float] = []
    predicted: list[float] = []
    residual: list[float] = []
    grouped: dict[tuple[str, tuple[str, str]], list[float]] = defaultdict(list)
    diagnostics: dict[tuple[str, str, int, tuple[str, str]], dict[str, list[float]]] = defaultdict(
        lambda: {"observed": [], "predicted": []}
    )
    for replayed in replayed_rows:
        row = replayed["row"]
        observed_values = replayed["observed"]
        predicted_values = replayed["predicted"]
        errors = replayed["residual"]
        observed.extend(observed_values)
        predicted.extend(predicted_values)
        residual.extend(errors)
        roles = tuple(row["roles"])
        grouped[(row["background"], roles)].extend(errors)
        key = (row["state"], row["background"], row["dpr"], roles)
        diagnostics[key]["observed"].extend(observed_values)
        diagnostics[key]["predicted"].extend(predicted_values)

    require(observed, "acceptance replay found no observed pair-distance samples")
    local_gates = []
    for (background, roles), errors in sorted(grouped.items()):
        mae = float(np.mean(errors))
        local_gates.append(
            {
                "background": background,
                "background_policy": "gate" if background in ("bg_0", "bg_1") else "report-only",
                "roles": list(roles),
                "mae_delta_e_ok": round(mae, 8),
                "status": "PASS" if background == "bg_2" or mae <= 0.75 else "FAIL",
            }
        )
    local_diagnostics = []
    for (state, background, dpr, roles), values in sorted(diagnostics.items()):
        local_diagnostics.append(
            {
                "state": state,
                "background": background,
                "dpr": dpr,
                "roles": list(roles),
                "correlation": round(_correlation(values["observed"], values["predicted"]), 8),
                "mae_delta_e_ok": round(
                    float(
                        np.mean(
                            np.abs(
                                np.asarray(values["observed"], dtype=float)
                                - np.asarray(values["predicted"], dtype=float)
                            )
                        )
                    ),
                    8,
                ),
            }
        )
    global_correlation = _correlation(observed, predicted)
    residual_values = np.asarray(residual)
    maximum_gate_mae = max(
        row["mae_delta_e_ok"] for row in local_gates if row["background_policy"] == "gate"
    )
    passed = (
        global_correlation >= 0.95
        and float(np.mean(residual_values)) <= 0.75
        and maximum_gate_mae <= 0.75
        and all(row["status"] == "PASS" for row in local_gates)
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "engineering_metric": "Oklab Euclidean distance x100 (Delta E OK)",
        "minimum_global_pooled_correlation": 0.95,
        "maximum_global_pooled_mae_delta_e_ok": 0.75,
        "maximum_gate_pair_background_mae_delta_e_ok": 0.75,
        "global_pooled_correlation": round(global_correlation, 8),
        "global_pooled_mae_delta_e_ok": round(float(np.mean(residual_values)), 8),
        "global_pooled_p95_delta_e_ok": round(float(np.quantile(residual_values, 0.95)), 8),
        "global_pooled_max_delta_e_ok": round(float(np.max(residual_values)), 8),
        "observed_gate_pair_background_mae_max_delta_e_ok": round(maximum_gate_mae, 8),
        "pair_background": local_gates,
        "local_correlations_diagnostic_only": local_diagnostics,
    }


def _records_by_id(records: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    mapped = {record["id"]: record for record in records}
    require(
        len(mapped) == len(records),
        f"{label} contains duplicate IDs: {len(records)} records but {len(mapped)} unique IDs",
    )
    return mapped


def verify_evidence(
    output_path: Path | None = None, *, evidence_dir: Path = HERE
) -> dict[str, Any]:
    evidence_dir = Path(evidence_dir)
    raster_path = evidence_dir / "raster-baseline.json"
    masks_path = evidence_dir / "raster-masks.json"
    observations_path = evidence_dir / "raster-observations.json"
    proxy_path = evidence_dir / "proxy-calibration.json"
    receipt_path = evidence_dir / "raster-verification.json"
    raster = json.loads(raster_path.read_text())
    masks_payload = json.loads(masks_path.read_text())
    observations_payload = json.loads(observations_path.read_text())
    proxy = json.loads(proxy_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    baseline_payload = json.loads((evidence_dir / "baseline.json").read_text())["family"]
    baseline = {
        "categorical": baseline_payload["categorical"],
        "surfaces": baseline_payload["surfaces"],
    }

    masks_hash = _sha256(masks_path)
    observations_hash = _sha256(observations_path)
    raster_hash = _sha256(raster_path)
    verifier_hash = _sha256(Path(__file__))
    replay_provenance = proxy["evidence"]["independent_replay"]
    require(
        replay_provenance["file"] == receipt_path.name,
        "independent replay receipt file must be raster-verification.json",
    )
    require(
        replay_provenance["verifier_file"] == Path(__file__).name,
        "independent replay verifier_file must be g1_evidence_verify.py",
    )
    require(
        replay_provenance["verifier_sha256"] == verifier_hash,
        "independent replay verifier hash is stale; regenerate the receipt provenance",
    )
    require(
        replay_provenance["sha256"] == _sha256(receipt_path),
        "independent replay receipt SHA-256 does not match raster-verification.json",
    )
    require(
        proxy["evidence"]["raster_masks"]["sha256"] == masks_hash,
        "proxy raster_masks SHA-256 does not match raster-masks.json",
    )
    require(
        proxy["evidence"]["raster_observations"]["sha256"] == observations_hash,
        "proxy raster_observations SHA-256 does not match raster-observations.json",
    )
    require(
        proxy["evidence"]["raster_ledger"]["sha256"] == raster_hash,
        "proxy raster_ledger SHA-256 does not match raster-baseline.json",
    )
    require(
        raster["evidence"]["raster_masks_sha256"] == masks_hash,
        "raster ledger mask SHA-256 does not match raster-masks.json",
    )
    require(
        raster["evidence"]["raster_observations_sha256"] == observations_hash,
        "raster ledger observation SHA-256 does not match raster-observations.json",
    )
    require(
        proxy["provenance"]["probe_sha256"]
        == _sha256(evidence_dir / "review/g1-browser-probe.html"),
        "capture probe SHA-256 does not match review/g1-browser-probe.html",
    )
    require(
        proxy["provenance"]["validator_source_commit"] == CAPTURE_SOURCE_HEAD,
        f"capture validator source commit must remain {CAPTURE_SOURCE_HEAD}",
    )
    capture_validator_path = f"{EXPERIMENT_RELATIVE}/g1_browser_validate.py"
    require(
        proxy["provenance"]["validator_sha256"]
        == _git_blob_hash(CAPTURE_SOURCE_HEAD, capture_validator_path),
        "capture validator SHA-256 does not match its recorded source commit",
    )
    approved_relative = f"{EXPERIMENT_RELATIVE}/raster-baseline.json"
    require(
        proxy["provenance"]["approved_ledger_sha256"]
        == _git_blob_hash(APPROVED_HEAD, approved_relative),
        "approved ledger SHA-256 does not match the approved implementation input",
    )

    mask_records = masks_payload["records"]
    base_records = observations_payload["bases"]
    observation_records = observations_payload["observations"]
    masks = _records_by_id(mask_records, "raster masks")
    bases = _records_by_id(base_records, "observation bases")
    observations = _records_by_id(observation_records, "role observations")
    require(
        len(mask_records) == len(masks) == masks_payload["record_count"] == 720,
        "mask evidence must contain exactly 720 unique records",
    )
    require(
        len(base_records) == len(bases) == observations_payload["base_count"] == 2_160,
        "observation evidence must contain exactly 2,160 unique bases",
    )
    require(
        len(observation_records)
        == len(observations)
        == observations_payload["observation_count"]
        == 21_600,
        "observation evidence must contain exactly 21,600 unique role observations",
    )

    prepared: dict[str, tuple[np.ndarray, np.ndarray, list[float]]] = {}
    for identifier, observation in observations.items():
        require(observation["status"] == "PASS", f"observation {identifier} is not PASS")
        require(
            observation["mask_id"] in masks,
            f"observation {identifier} references unknown mask {observation['mask_id']}",
        )
        require(
            observation["base_id"] in bases,
            f"observation {identifier} references unknown base {observation['base_id']}",
        )
        mask = masks[observation["mask_id"]]
        require(
            mask["status"] == "PASS", f"mask {mask['id']} referenced by {identifier} is not PASS"
        )
        count = observation["sample_count"]
        require(
            isinstance(count, int) and not isinstance(count, bool) and count > 0,
            f"observation {identifier} sample_count must be a positive integer",
        )
        try:
            observed_bytes = base64.b64decode(observation["observed_rgb8_base64"], validate=True)
        except ValueError as error:
            raise EvidenceIntegrityError(
                f"observation {identifier} contains invalid base64 RGB8 evidence"
            ) from error
        require(
            len(observed_bytes) == count * 3,
            f"observation {identifier} RGB8 byte count does not match sample_count {count}",
        )
        observed = np.frombuffer(observed_bytes, dtype=np.uint8).reshape(count, 3)
        require(
            count == mask["sample_count"] == len(mask["samples"]),
            f"observation {identifier} sample count does not match mask {mask['id']}",
        )
        base = bases[observation["base_id"]]
        coverage = np.array([sample[5] for sample in mask["samples"]])[:, None]
        foreground = _rgb(baseline["categorical"][observation["role"].split(".", 1)[1]])
        background = _rgb(baseline["surfaces"][base["background"]])
        gain = GAINS if base["state"] == "transformed" else np.ones(3)
        predicted = np.rint(
            np.clip(gain * (coverage * foreground + (1 - coverage) * background), 0, 1) * 255
        ).astype(np.uint8)
        residual = observed.astype(int) - predicted.astype(int)
        require(
            np.median(observed, axis=0).tolist() == observation["observed_rgb8_median"],
            f"observation {identifier} observed median does not match encoded RGB8 evidence",
        )
        require(
            np.median(predicted, axis=0).tolist() == observation["predicted_rgb8_median"],
            f"observation {identifier} predicted median does not replay",
        )
        require(
            np.median(residual, axis=0).tolist() == observation["residual_rgb8_median"],
            f"observation {identifier} residual median does not replay",
        )
        require(
            np.mean(np.abs(residual), axis=0).tolist() == observation["channel_mae_rgb8"],
            f"observation {identifier} channel MAE does not replay",
        )
        stations = [sample[0] for sample in mask["samples"]]
        require(
            len(stations) == len(set(stations)),
            f"mask {mask['id']} contains duplicate line-core station coordinates",
        )
        prepared[identifier] = (observed, predicted, stations)

    replayed = 0
    station_samples = 0
    maximum_metric_difference = 0.0
    dimensions = list(_expected_dimensions(raster["specimen_contract"]))
    require(
        len(raster["matrix"]) == len(dimensions) == 32_400,
        "raster ledger and specimen contract must both contain exactly 32,400 pair rows",
    )
    acceptance_rows: list[dict[str, Any]] = []
    for index, (row, expected) in enumerate(
        zip(raster["matrix"], dimensions, strict=True), start=1
    ):
        state, background, width, style, orientation, dpr, phase, pair = expected
        expected_projection = {
            "id": f"planned-{index:05d}",
            "state": state,
            "background": background,
            "background_policy": "gate" if background in ("bg_0", "bg_1") else "report-only",
            "width_css_px": width,
            "style": style,
            "orientation": orientation,
            "dpr": dpr,
            "phase_css_px": list(phase),
            "roles": [f"cat.{pair[0]}", f"cat.{pair[1]}"],
        }
        require(
            expected_projection == {key: row[key] for key in expected_projection},
            f"pair row planned-{index:05d} does not match the specimen-contract dimension order",
        )
        require(row["status"] == "PASS", f"pair row {row['id']} is not PASS")
        left_id = row["evidence"]["left_observation_id"]
        right_id = row["evidence"]["right_observation_id"]
        require(left_id in observations, f"pair row {row['id']} references unknown left {left_id}")
        require(
            right_id in observations, f"pair row {row['id']} references unknown right {right_id}"
        )
        left = observations[left_id]
        right = observations[right_id]
        expected_base = {field: row[field] for field in BASE_FIELDS}
        for side, observation, role, lane in (
            ("left", left, row["roles"][0], 0),
            ("right", right, row["roles"][1], 1),
        ):
            actual_base = bases[observation["base_id"]]
            require(
                {field: actual_base[field] for field in BASE_FIELDS} == expected_base,
                f"pair row {row['id']} {side} observation uses the wrong base dimensions",
            )
            require(
                observation["role"] == role and observation["lane"] == lane,
                f"pair row {row['id']} {side} observation role/lane mapping is incorrect",
            )
            mask_key = masks[observation["mask_id"]]["key"]
            expected_mask_key = {
                "width_css_px": width,
                "style": style,
                "orientation": orientation,
                "dpr": dpr,
                "phase_css_px": list(phase),
                "lane": lane,
            }
            require(
                mask_key == expected_mask_key,
                f"pair row {row['id']} {side} observation uses the wrong mask dimensions",
            )
        left_observed, left_predicted, left_stations = prepared[left["id"]]
        right_observed, right_predicted, right_stations = prepared[right["id"]]
        left_index = {station: position for position, station in enumerate(left_stations)}
        right_index = {station: position for position, station in enumerate(right_stations)}
        common = sorted(set(left_index) & set(right_index))
        require(common, f"pair row {row['id']} has no matched line-core stations")
        li = [left_index[station] for station in common]
        ri = [right_index[station] for station in common]
        observed_distance = (
            np.linalg.norm(
                _oklab(left_observed[li] / 255.0) - _oklab(right_observed[ri] / 255.0), axis=1
            )
            * 100
        )
        predicted_distance = (
            np.linalg.norm(
                _oklab(left_predicted[li] / 255.0) - _oklab(right_predicted[ri] / 255.0),
                axis=1,
            )
            * 100
        )
        values = (
            float(np.median(observed_distance)),
            float(np.median(predicted_distance)),
            float(np.mean(np.abs(observed_distance - predicted_distance))),
        )
        recorded = (row["observed_distance"], row["proxy_prediction"], row["proxy_error"])
        differences = [abs(value - saved) for value, saved in zip(values, recorded, strict=True)]
        maximum_metric_difference = max(maximum_metric_difference, *differences)
        require(
            all(difference <= 5e-9 for difference in differences),
            f"pair row {row['id']} metric replay differs by {max(differences):.12g}; limit is 5e-9",
        )
        require(
            row["evidence"]["matched_station_count"] == len(common),
            f"pair row {row['id']} matched-station count does not replay",
        )
        require(
            row["observed_line_core_rgb8"]
            == [left["observed_rgb8_median"], right["observed_rgb8_median"]],
            f"pair row {row['id']} observed RGB8 summary does not match its observations",
        )
        acceptance_rows.append(
            {
                "row": row,
                "observed": observed_distance.tolist(),
                "predicted": predicted_distance.tolist(),
                "residual": np.abs(observed_distance - predicted_distance).tolist(),
            }
        )
        replayed += 1
        station_samples += len(common)

    replayed_acceptance = _replay_acceptance(acceptance_rows)
    require(
        replayed_acceptance == proxy["acceptance"],
        "proxy acceptance aggregate does not match the independently replayed station metrics",
    )

    result = {
        "status": "PASS",
        "approved_head": APPROVED_HEAD,
        "planned_id_mapping_rows_verified": replayed,
        "pair_rows_replayed": replayed,
        "matched_pair_station_samples_replayed": station_samples,
        "role_observations_verified": len(observations),
        "mask_records_verified": len(masks),
        "maximum_rounded_metric_difference": maximum_metric_difference,
        "provenance": {
            "verifier_sha256": verifier_hash,
            "raster_masks_sha256": masks_hash,
            "raster_observations_sha256": observations_hash,
            "raster_ledger_sha256": raster_hash,
        },
    }
    require(
        receipt == result,
        "independent replay receipt content does not match the current deterministic replay",
    )
    if output_path is not None:
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, default=HERE)
    parser.add_argument(
        "--output",
        type=Path,
        help="verification result path (default: <evidence-dir>/raster-verification.json)",
    )
    arguments = parser.parse_args()
    output_path = arguments.output or arguments.evidence_dir / "raster-verification.json"
    try:
        result = verify_evidence(output_path, evidence_dir=arguments.evidence_dir)
    except (
        EvidenceIntegrityError,
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
