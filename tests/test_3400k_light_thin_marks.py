from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "docs/experiments/3400k-light-thin-marks"
BASELINE_COMMIT = "c4c25e480912f8f54cbd8c992c0b6eb520dc0b8f"
CORE_OUTPUTS = (
    "g0-metrics.json",
    "G0-REPORT.md",
    "review/commanded.svg",
    "review/transformed.svg",
    "review/index.html",
    "review/browser-probe.html",
)


def load_module(filename: str, name: str):
    path = EXPERIMENT / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_baseline_is_exact_schema_14_payload() -> None:
    baseline = json.loads((EXPERIMENT / "baseline.json").read_text())
    family = baseline["family"]

    assert baseline["baseline_source_commit"] == BASELINE_COMMIT
    assert baseline["schema_version"] == 14
    assert baseline["profile_gains"] == [1.0, 0.74, 0.53]
    assert family["surfaces"]["bg_0"] == "#F9F9F8"
    assert family["surfaces"]["bg_1"] == "#ECECEB"
    assert family["surfaces"]["bg_2"] == "#E0E0DD"
    assert list(family["categorical"].values()) == [
        "#359984",
        "#281144",
        "#A76282",
        "#6A2600",
        "#185823",
        "#445D9B",
    ]
    assert family["terminal"]["red"] == "#430000"
    assert len(family["continuous_rgb"]) == 256
    assert len(family["continuous_hex8"]) == 256

    for relative_path, record in baseline["production_artifacts"].items():
        payload = (ROOT / relative_path).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == record["sha256"], relative_path
        assert len(payload) == record["bytes"], relative_path


def test_harness_matrix_and_specimens_cover_the_g0_contract() -> None:
    harness = load_module("harness.py", "thin_marks_harness_contract")
    contract = harness.specimen_contract()

    assert contract["backgrounds"] == {
        "render": ["bg_0", "bg_1"],
        "report_only": ["bg_2"],
    }
    assert contract["widths_css_px"] == [1.5, 2.0, 3.0]
    assert contract["device_pixel_ratios"] == [1, 2]
    assert set(contract["geometry"]) == {"horizontal", "diagonal", "curved"}
    assert set(contract["line_styles"]) == {"solid", "dashed", "dotted"}
    assert set(contract["features"]) == {
        "crossings",
        "short_legends",
        "endpoint_markers",
        "sparklines",
        "financial_cockpit",
        "thesis_baskets",
    }
    assert (
        contract["data_policy"] == "deterministic fake data; no consumer imports; no private data"
    )


def test_transform_and_encoded_blend_commute_for_diagonal_model() -> None:
    harness = load_module("harness.py", "thin_marks_harness_commutation")
    result = harness.validate_transform_blend_commutation()

    assert result["model"] == "encoded-srgb-diagonal-coverage"
    assert result["sample_count"] >= 1000
    assert result["maximum_absolute_channel_error"] < 1e-12


def test_metrics_reproduce_current_failures_without_claiming_light_cam16() -> None:
    metrics = json.loads((EXPERIMENT / "g0-metrics.json").read_text())

    assert metrics["baseline_source_commit"] == BASELINE_COMMIT
    assert metrics["commanded_solid_oklab"]["minimum_pair"]["roles"] == [
        "cat.three",
        "cat.six",
    ]
    assert metrics["commanded_solid_oklab"]["minimum_pair"]["delta_e_ok"] == pytest.approx(
        16.6381, abs=1e-4
    )
    transformed = metrics["transformed_metric"]
    assert transformed["backend"] == "oklab-diagnostic"
    assert transformed["status"] == "diagnostic-only-not-calibrated-for-light-mode"
    assert transformed["final_light_metric"] is None
    assert "CAM16" not in transformed["backend"]

    failures = {row["id"]: row for row in metrics["g0_failures"]}
    assert failures["intra-cat-five-vs-six"]["scope"] == "categorical-contract"
    assert failures["intra-cat-five-vs-six"]["status"] == "FAIL"
    assert failures["cross-cat-two-vs-terminal-red"]["scope"] == "diagnostic-non-contract"
    assert failures["cross-cat-two-vs-terminal-red"]["status"] == "FAIL"
    assert failures["cross-cat-two-vs-fg-1"]["scope"] == "diagnostic-non-contract"
    assert failures["cross-cat-two-vs-fg-1"]["status"] == "FAIL"
    assert {row["background"] for row in metrics["coverage_proxy"]["summary"]} == {
        "bg_0",
        "bg_1",
        "bg_2",
    }


def test_transformed_metric_backend_is_pluggable() -> None:
    harness = load_module("harness.py", "thin_marks_harness_plugin")
    baseline = harness.load_baseline()

    def encoded_rgb_metric(left: np.ndarray, right: np.ndarray) -> float:
        return float(np.linalg.norm(left - right) * 100.0)

    metrics = harness.compute_metrics(
        baseline,
        transformed_metric=encoded_rgb_metric,
        transformed_metric_metadata={
            "backend": "test-encoded-rgb",
            "status": "test-only",
            "final_light_metric": None,
        },
    )
    assert metrics["transformed_metric"]["backend"] == "test-encoded-rgb"
    assert metrics["transformed_metric"]["solid_minimum_pair"]["delta"] > 0


def test_committed_browser_validation_is_sample_based_and_passes() -> None:
    result = json.loads((EXPERIMENT / "browser-validation.json").read_text())
    assert result["status"] == "PASS"
    assert result["full_image_hash_used"] is False
    assert {row["dpr"] for row in result["by_dpr"]} == {1, 2}
    assert result["comparison"]["oklab_distance_correlation"] >= 0.95
    assert result["comparison"]["oklab_distance_mean_absolute_error"] <= 0.75

    report = (EXPERIMENT / "G0-REPORT.md").read_text()
    assert "review/commanded.svg" in report
    assert "review/transformed.svg" in report
    assert "genuinely ready **for the human stop-gate decision**" in report


def test_core_outputs_are_byte_deterministic(tmp_path: Path) -> None:
    harness = load_module("harness.py", "thin_marks_harness_determinism")
    harness.build_outputs(tmp_path)

    for relative_path in CORE_OUTPUTS:
        assert (tmp_path / relative_path).read_bytes() == (EXPERIMENT / relative_path).read_bytes()


def test_browser_validation_skip_is_clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    browser = load_module("browser_validate.py", "thin_marks_browser_skip")
    monkeypatch.setenv("GSTACK_BROWSE", str(tmp_path / "missing-browse"))
    result = browser.run_validation(output_dir=tmp_path)
    assert result["status"] == "SKIP"
    assert result["reason"] == "gstack browse binary unavailable"


@pytest.mark.skipif(
    __import__("os").environ.get("EMBER_RUN_BROWSER_TESTS") != "1",
    reason="set EMBER_RUN_BROWSER_TESTS=1 for local GStack/Chromium validation",
)
def test_optional_real_browser_proxy_validation(tmp_path: Path) -> None:
    browser = load_module("browser_validate.py", "thin_marks_browser_real")
    result = browser.run_validation(output_dir=tmp_path)
    if result["status"] == "SKIP":
        pytest.skip(result["reason"])
    assert result["status"] == "PASS"
    assert result["comparison"]["oklab_distance_correlation"] >= 0.95
    assert result["comparison"]["oklab_distance_mean_absolute_error"] <= 0.75
