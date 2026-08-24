#!/usr/bin/env python3
"""Optional real-Chromium check for the encoded-sRGB diagonal proxy.

Uses the project-supported GStack browse binary when present. The permanent
report contains sampled-pixel statistics, never a full-image hash.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def _load_harness():
    path = HERE / "harness.py"
    spec = importlib.util.spec_from_file_location("thin_marks_browser_harness", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _browse_binary() -> Path | None:
    explicit = os.environ.get("GSTACK_BROWSE")
    if explicit is not None:
        candidate = Path(explicit).expanduser()
        return candidate if candidate.is_file() and os.access(candidate, os.X_OK) else None
    candidates = (
        ROOT / ".hermes/skills/gstack/browse/dist/browse",
        Path.home() / ".hermes/skills/gstack/browse/dist/browse",
    )
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.is_file() and os.access(candidate, os.X_OK)
        ),
        None,
    )


def _run(browse: Path, cwd: Path, *arguments: str) -> None:
    completed = subprocess.run(
        [str(browse), *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"gstack browse {' '.join(arguments)} failed: {detail}")


def _safe_correlation(left: np.ndarray, right: np.ndarray) -> float:
    if np.std(left) == 0 or np.std(right) == 0:
        return 1.0 if np.allclose(left, right) else 0.0
    return float(np.corrcoef(left, right)[0, 1])


def _analyze(path: Path, dpr: int, baseline: dict[str, Any]) -> dict[str, Any]:
    harness = _load_harness()
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=float) / 255.0
    expected_shape = (128 * dpr, 320 * dpr, 3)
    if rgb.shape != expected_shape:
        raise RuntimeError(f"browser probe shape {rgb.shape}, expected {expected_shape}")

    family = baseline["family"]
    role_values = {
        "cat.five": family["categorical"]["five"],
        "cat.six": family["categorical"]["six"],
        "cat.two": family["categorical"]["two"],
        "terminal.red": family["terminal"]["red"],
        "fg_1": family["surfaces"]["fg_1"],
    }
    role_order = list(role_values)
    coverage = harness.diagonal_coverage(1.5, dpr)
    predicted_tiles: dict[tuple[str, str], np.ndarray] = {}
    observed_tiles: dict[tuple[str, str], np.ndarray] = {}
    channel_errors = []
    for background_index, background_name in enumerate(("bg_0", "bg_1")):
        background = harness.hex_to_rgb(
            harness.rgb_to_hex(
                harness.transform(harness.hex_to_rgb(family["surfaces"][background_name]))
            )
        )
        for role_index, role in enumerate(role_order):
            foreground = harness.hex_to_rgb(
                harness.rgb_to_hex(harness.transform(harness.hex_to_rgb(role_values[role])))
            )
            predicted = coverage[..., None] * foreground + (1.0 - coverage[..., None]) * background
            y0 = background_index * 64 * dpr
            x0 = role_index * 64 * dpr
            observed = rgb[y0 : y0 + 64 * dpr, x0 : x0 + 64 * dpr]
            predicted_tiles[(background_name, role)] = predicted
            observed_tiles[(background_name, role)] = observed
            active = coverage >= 0.05
            channel_errors.extend(np.abs(predicted[active] - observed[active]).ravel().tolist())

    comparisons = (
        ("cat.five", "cat.six"),
        ("cat.two", "terminal.red"),
        ("cat.two", "fg_1"),
    )
    predicted_distances = []
    observed_distances = []
    pair_rows = []
    active = coverage >= 0.05
    for background_name in ("bg_0", "bg_1"):
        for left_role, right_role in comparisons:
            predicted_left = predicted_tiles[(background_name, left_role)][active]
            predicted_right = predicted_tiles[(background_name, right_role)][active]
            observed_left = observed_tiles[(background_name, left_role)][active]
            observed_right = observed_tiles[(background_name, right_role)][active]
            predicted = (
                np.linalg.norm(
                    harness.srgb_to_oklab(predicted_left) - harness.srgb_to_oklab(predicted_right),
                    axis=1,
                )
                * 100.0
            )
            observed = (
                np.linalg.norm(
                    harness.srgb_to_oklab(observed_left) - harness.srgb_to_oklab(observed_right),
                    axis=1,
                )
                * 100.0
            )
            predicted_distances.extend(predicted.tolist())
            observed_distances.extend(observed.tolist())
            pair_rows.append(
                {
                    "background": background_name,
                    "roles": [left_role, right_role],
                    "sample_count": len(predicted),
                    "correlation": _safe_correlation(predicted, observed),
                    "mean_absolute_error": float(np.mean(np.abs(predicted - observed))),
                }
            )
    predicted_array = np.asarray(predicted_distances)
    observed_array = np.asarray(observed_distances)
    errors = np.abs(predicted_array - observed_array)
    return {
        "dpr": dpr,
        "sampled_pair_distance_count": len(errors),
        "oklab_distance_correlation": _safe_correlation(predicted_array, observed_array),
        "oklab_distance_mean_absolute_error": float(np.mean(errors)),
        "oklab_distance_p95_absolute_error": float(np.quantile(errors, 0.95)),
        "encoded_channel_mean_absolute_error_8bit": float(np.mean(channel_errors) * 255.0),
        "pairs": pair_rows,
    }


def _rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 8)
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    return value


def run_validation(output_dir: Path = HERE) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "browser-validation.json"
    browse = _browse_binary()
    if browse is None:
        result = {
            "status": "SKIP",
            "reason": "gstack browse binary unavailable",
            "dependency": "optional local GStack/Chromium",
        }
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    harness = _load_harness()
    baseline = harness.load_baseline()
    try:
        with tempfile.TemporaryDirectory(prefix="ember-g0-browser-") as temporary:
            scratch = Path(temporary)
            probe = scratch / "browser-probe.html"
            shutil.copyfile(HERE / "review/browser-probe.html", probe)
            rows = []
            for dpr in (1, 2):
                screenshot = scratch / f"probe-dpr-{dpr}.png"
                _run(browse, scratch, "viewport", "320x128", "--scale", str(dpr))
                _run(browse, scratch, "goto", probe.as_uri())
                _run(browse, scratch, "screenshot", str(screenshot), "--selector", "#probe")
                rows.append(_analyze(screenshot, dpr, baseline))
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        result = {
            "status": "SKIP",
            "reason": f"local GStack/Chromium unavailable: {error}",
            "dependency": "optional local GStack/Chromium",
        }
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    predicted = []
    observed_error = []
    # Aggregate by weighted sample count. Correlation is recomputed conservatively as the
    # minimum per-DPR correlation so one scale cannot hide the other.
    for row in rows:
        predicted.append(row["oklab_distance_correlation"])
        observed_error.extend(
            [row["oklab_distance_mean_absolute_error"]] * row["sampled_pair_distance_count"]
        )
    comparison = {
        "oklab_distance_correlation": min(predicted),
        "oklab_distance_mean_absolute_error": float(np.mean(observed_error)),
        "oklab_distance_p95_absolute_error": max(
            row["oklab_distance_p95_absolute_error"] for row in rows
        ),
        "acceptance": {"minimum_correlation": 0.95, "maximum_mean_absolute_error": 0.75},
    }
    status = (
        "PASS"
        if comparison["oklab_distance_correlation"] >= 0.95
        and comparison["oklab_distance_mean_absolute_error"] <= 0.75
        else "FAIL"
    )
    result = _rounded(
        {
            "status": status,
            "baseline_source_commit": baseline["baseline_source_commit"],
            "browser": "GStack-managed Chromium",
            "model": "encoded-sRGB 1.5 CSS px diagonal area-coverage proxy",
            "full_image_hash_used": False,
            "comparison": comparison,
            "by_dpr": rows,
        }
    )
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    result = run_validation()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] in {"PASS", "SKIP"} else 1)
