#!/usr/bin/env python3
"""Independently replay every G1 pair row from compact factored browser evidence."""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
APPROVED_HEAD = "922ba7faa45ccdb56e95356750d353c7602da78a"
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


def _approved_blob_hash(relative_path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{APPROVED_HEAD}:{relative_path}"],
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


def verify_evidence(output_path: Path | None = None) -> dict[str, Any]:
    raster_path = HERE / "raster-baseline.json"
    masks_path = HERE / "raster-masks.json"
    observations_path = HERE / "raster-observations.json"
    proxy_path = HERE / "proxy-calibration.json"
    raster = json.loads(raster_path.read_text())
    masks_payload = json.loads(masks_path.read_text())
    observations_payload = json.loads(observations_path.read_text())
    proxy = json.loads(proxy_path.read_text())
    baseline_payload = json.loads((HERE / "baseline.json").read_text())["family"]
    baseline = {
        "categorical": baseline_payload["categorical"],
        "surfaces": baseline_payload["surfaces"],
    }

    assert proxy["evidence"]["raster_masks"]["sha256"] == _sha256(masks_path)
    assert proxy["evidence"]["raster_observations"]["sha256"] == _sha256(observations_path)
    assert proxy["evidence"]["raster_ledger"]["sha256"] == _sha256(raster_path)
    assert raster["evidence"]["raster_masks_sha256"] == _sha256(masks_path)
    assert raster["evidence"]["raster_observations_sha256"] == _sha256(observations_path)
    assert proxy["provenance"]["probe_sha256"] == _sha256(HERE / "review/g1-browser-probe.html")
    assert proxy["provenance"]["validator_sha256"] == _sha256(HERE / "g1_browser_validate.py")
    approved_relative = "docs/experiments/3400k-light-thin-marks/raster-baseline.json"
    assert proxy["provenance"]["approved_ledger_sha256"] == _approved_blob_hash(approved_relative)

    masks = {record["id"]: record for record in masks_payload["records"]}
    bases = {record["id"]: record for record in observations_payload["bases"]}
    observations = {record["id"]: record for record in observations_payload["observations"]}
    assert len(masks) == masks_payload["record_count"] == 720
    assert len(bases) == observations_payload["base_count"] == 2_160
    assert len(observations) == observations_payload["observation_count"] == 21_600

    prepared: dict[str, tuple[np.ndarray, np.ndarray, list[float]]] = {}
    for identifier, observation in observations.items():
        assert observation["status"] == "PASS"
        mask = masks[observation["mask_id"]]
        assert mask["status"] == "PASS"
        count = observation["sample_count"]
        observed = np.frombuffer(
            base64.b64decode(observation["observed_rgb8_base64"]), dtype=np.uint8
        ).reshape(count, 3)
        assert count == mask["sample_count"] == len(mask["samples"])
        base = bases[observation["base_id"]]
        coverage = np.array([sample[5] for sample in mask["samples"]])[:, None]
        foreground = _rgb(baseline["categorical"][observation["role"].split(".", 1)[1]])
        background = _rgb(baseline["surfaces"][base["background"]])
        gain = GAINS if base["state"] == "transformed" else np.ones(3)
        predicted = np.rint(
            np.clip(gain * (coverage * foreground + (1 - coverage) * background), 0, 1) * 255
        ).astype(np.uint8)
        assert np.median(observed, axis=0).tolist() == observation["observed_rgb8_median"]
        assert np.median(predicted, axis=0).tolist() == observation["predicted_rgb8_median"]
        prepared[identifier] = (observed, predicted, [sample[0] for sample in mask["samples"]])

    replayed = 0
    station_samples = 0
    maximum_metric_difference = 0.0
    dimensions = _expected_dimensions(raster["specimen_contract"])
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
        assert expected_projection == {key: row[key] for key in expected_projection}
        assert row["status"] == "PASS"
        left = observations[row["evidence"]["left_observation_id"]]
        right = observations[row["evidence"]["right_observation_id"]]
        left_observed, left_predicted, left_stations = prepared[left["id"]]
        right_observed, right_predicted, right_stations = prepared[right["id"]]
        left_index = {station: position for position, station in enumerate(left_stations)}
        right_index = {station: position for position, station in enumerate(right_stations)}
        common = sorted(set(left_index) & set(right_index))
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
        assert all(difference <= 5e-9 for difference in differences)
        assert row["evidence"]["matched_station_count"] == len(common)
        replayed += 1
        station_samples += len(common)

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
            "verifier_sha256": _sha256(Path(__file__)),
            "raster_masks_sha256": _sha256(masks_path),
            "raster_observations_sha256": _sha256(observations_path),
            "raster_ledger_sha256": _sha256(raster_path),
        },
    }
    if output_path is not None:
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    result = verify_evidence(HERE / "raster-verification.json")
    print(json.dumps(result, indent=2, sort_keys=True))
