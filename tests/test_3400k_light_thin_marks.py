from __future__ import annotations

import hashlib
import importlib.util
import json
import xml.etree.ElementTree as ET
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


def test_dedicated_cat_five_six_crossings_are_structurally_color_only() -> None:
    harness = load_module("harness.py", "thin_marks_harness_color_only")
    baseline = harness.load_baseline()
    category = baseline["family"]["categorical"]
    svg_namespace = {"svg": "http://www.w3.org/2000/svg"}
    href_attribute = "{http://www.w3.org/1999/xlink}href"

    for state in ("commanded", "transformed"):
        root = ET.fromstring((EXPERIMENT / "review" / f"{state}.svg").read_text())
        geometry = root.find(
            "svg:defs/svg:path[@id='cat-five-six-crossing-geometry']", svg_namespace
        )
        assert geometry is not None
        assert geometry.attrib["d"]

        groups = root.findall(
            ".//svg:g[@data-evidence='color-only-cat-five-six-crossing']", svg_namespace
        )
        assert len(groups) == 6
        assert {
            (group.attrib["data-background"], group.attrib["data-width"]) for group in groups
        } == {
            (background, f"{width:g}")
            for background in ("bg_0", "bg_1")
            for width in (1.5, 2.0, 3.0)
        }

        expected_colors = {
            f"cat.{name}": harness.rgb_to_hex(
                harness.transform(harness.hex_to_rgb(value))
                if state == "transformed"
                else harness.hex_to_rgb(value)
            )
            for name, value in (("five", category["five"]), ("six", category["six"]))
        }
        for group in groups:
            marks = group.findall("svg:use", svg_namespace)
            assert len(marks) == 2
            marks_by_role = {mark.attrib["data-role"]: mark for mark in marks}
            assert set(marks_by_role) == set(expected_colors)
            assert {mark.attrib.get("href", mark.attrib.get(href_attribute)) for mark in marks} == {
                "#cat-five-six-crossing-geometry"
            }
            assert marks_by_role["cat.five"].attrib.get("transform") is None
            assert marks_by_role["cat.six"].attrib["transform"] == ("translate(0 38) scale(1 -1)")
            assert {mark.attrib["stroke-width"] for mark in marks} == {group.attrib["data-width"]}
            assert {mark.attrib["fill"] for mark in marks} == {"none"}
            assert {mark.attrib["stroke"] for mark in marks} == set(expected_colors.values())
            for mark in marks:
                assert mark.attrib["stroke"] == expected_colors[mark.attrib["data-role"]]
                assert "stroke-dasharray" not in mark.attrib
                assert "stroke-linecap" not in mark.attrib
                assert not any(attribute.startswith("marker-") for attribute in mark.attrib)


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
    assert failures["intra-categorical-minimum"]["scope"] == "categorical-contract"
    assert failures["intra-categorical-minimum"]["status"] == "FAIL"
    assert failures["cross-cat-two-vs-terminal-red"]["scope"] == "diagnostic-non-contract"
    assert failures["cross-cat-two-vs-terminal-red"]["status"] == "FAIL"
    assert failures["cross-cat-two-vs-fg-1"]["scope"] == "diagnostic-non-contract"
    assert failures["cross-cat-two-vs-fg-1"]["status"] == "FAIL"
    assert {row["background"] for row in metrics["coverage_proxy"]["summary"]} == {
        "bg_0",
        "bg_1",
        "bg_2",
    }


def test_transformed_metric_owns_all_transformed_proxy_distances() -> None:
    harness = load_module("harness.py", "thin_marks_harness_plugin")
    baseline = harness.load_baseline()
    committed = json.loads((EXPERIMENT / "g0-metrics.json").read_text())

    def red_channel_metric(left: np.ndarray, right: np.ndarray) -> float:
        return float(abs(left[0] - right[0]) * 100.0)

    def blue_channel_metric(left: np.ndarray, right: np.ndarray) -> float:
        return float(abs(left[2] - right[2]) * 10_000.0)

    assert harness.compute_metrics(baseline) == committed
    red_metrics = harness.compute_metrics(
        baseline,
        transformed_metric=red_channel_metric,
        transformed_metric_metadata={
            "backend": "test-red-channel",
            "status": "test-only",
            "final_light_metric": None,
        },
    )
    blue_metrics = harness.compute_metrics(
        baseline,
        transformed_metric=blue_channel_metric,
        transformed_metric_metadata={
            "backend": "test-blue-channel",
            "status": "test-only",
            "final_light_metric": None,
        },
    )

    assert red_metrics["transformed_metric"]["backend"] == "test-red-channel"
    assert blue_metrics["transformed_metric"]["backend"] == "test-blue-channel"
    assert (
        red_metrics["transformed_metric"]["solid_minimum_pair"]
        != blue_metrics["transformed_metric"]["solid_minimum_pair"]
    )
    assert red_metrics["coverage_proxy"]["matrix"] != blue_metrics["coverage_proxy"]["matrix"]
    assert red_metrics["g0_failures"] != blue_metrics["g0_failures"]
    assert {row["status"] for row in red_metrics["g0_failures"]} == {"FAIL"}
    assert {row["status"] for row in blue_metrics["g0_failures"]} == {"PASS"}
    assert red_metrics["g0_failures"][0]["roles"] != blue_metrics["g0_failures"][0]["roles"]

    for metrics in (red_metrics, blue_metrics):
        failure_case = next(
            row
            for row in metrics["coverage_proxy"]["matrix"]
            if row["background"] == "bg_0"
            and row["width_css_px"] == 1.5
            and row["dpr"] == 1
            and row["geometry"] == "diagonal"
        )
        failures = {row["id"]: row for row in metrics["g0_failures"]}
        assert (
            failures["intra-categorical-minimum"]["roles"]
            == failure_case["intra_categorical_minimum"]["roles"]
        )
        assert (
            failures["intra-categorical-minimum"]["diagnostic_delta"]
            == failure_case["intra_categorical_minimum"]["delta"]
        )
        assert (
            failures["cross-cat-two-vs-terminal-red"]["diagnostic_delta"]
            == failure_case["cat.two_vs_terminal.red"]
        )
        assert (
            failures["cross-cat-two-vs-fg-1"]["diagnostic_delta"] == failure_case["cat.two_vs_fg_1"]
        )


def test_committed_browser_validation_is_sample_based_and_passes() -> None:
    result = json.loads((EXPERIMENT / "browser-validation.json").read_text())
    assert result["status"] == "PASS"
    assert result["full_image_hash_used"] is False
    assert {row["dpr"] for row in result["by_dpr"]} == {1, 2}
    acceptance = result["acceptance_statuses"]
    assert acceptance["global"]["status"] == "PASS"
    assert acceptance["global"]["scope"] == "pooled samples across all DPRs, backgrounds, and pairs"
    assert acceptance["global"]["minimum_correlation"] == 0.95
    assert acceptance["global"]["maximum_mean_absolute_error"] == 0.75
    assert acceptance["pair_background"]["status"] == "PASS"
    assert acceptance["pair_background"]["maximum_mean_absolute_error"] == 0.75
    assert acceptance["pair_background"]["correlation_gate"] is None
    assert result["comparison"]["pooled_oklab_distance_correlation"] >= 0.95
    assert result["comparison"]["pooled_oklab_distance_mean_absolute_error"] <= 0.75

    pair_rows = [pair for row in result["by_dpr"] for pair in row["pairs"]]
    assert min(pair["correlation"] for pair in pair_rows) < 0.95
    assert all(pair["mae_acceptance_status"] == "PASS" for pair in pair_rows)
    assert all(pair["mean_absolute_error"] <= 0.75 for pair in pair_rows)

    provenance = result["provenance"]
    assert (
        provenance["sha256"]["browser_probe_html"]
        == hashlib.sha256((EXPERIMENT / "review/browser-probe.html").read_bytes()).hexdigest()
    )
    assert (
        provenance["sha256"]["browser_validate_py"]
        == hashlib.sha256((EXPERIMENT / "browser_validate.py").read_bytes()).hexdigest()
    )
    assert len(provenance["sha256"]["gstack_browse_binary"]) == 64
    assert provenance["browser_status"] == {"mode": "launched", "status": "healthy"}
    assert provenance["chromium_version"] is None
    assert provenance["chromium_version_status"] == "unavailable-not-claimed"

    report = (EXPERIMENT / "G0-REPORT.md").read_text()
    assert "review/commanded.svg" in report
    assert "review/transformed.svg" in report
    assert "Global pooled acceptance: **PASS**" in report
    assert "Pair/background MAE acceptance: **PASS**" in report
    assert "not a local 0.95 gate" in report
    assert "Chromium version is unavailable and is not claimed" in report
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


def test_bad_contract_pair_mae_blocks_browser_acceptance() -> None:
    browser = load_module("browser_validate.py", "thin_marks_browser_acceptance")
    comparison = {
        "pooled_oklab_distance_correlation": 0.99,
        "pooled_oklab_distance_mean_absolute_error": 0.2,
    }
    rows = [
        {
            "dpr": 2,
            "pairs": [
                {
                    "background": "bg_0",
                    "roles": ["cat.five", "cat.six"],
                    "correlation": 0.99,
                    "mean_absolute_error": 0.8,
                },
                {
                    "background": "bg_0",
                    "roles": ["cat.two", "terminal.red"],
                    "correlation": 0.99,
                    "mean_absolute_error": 0.1,
                },
            ],
        }
    ]

    statuses = browser._acceptance_statuses(comparison, rows)

    assert statuses["global"]["status"] == "PASS"
    assert statuses["pair_background"]["status"] == "FAIL"
    assert statuses["pair_background"]["failed_pairs"] == [
        {
            "background": "bg_0",
            "dpr": 2,
            "mean_absolute_error": 0.8,
            "roles": ["cat.five", "cat.six"],
        }
    ]
    assert browser._overall_status(statuses) == "FAIL"


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
    assert result["acceptance_statuses"]["global"]["status"] == "PASS"
    assert result["acceptance_statuses"]["pair_background"]["status"] == "PASS"
    assert result["comparison"]["pooled_oklab_distance_correlation"] >= 0.95
    assert result["comparison"]["pooled_oklab_distance_mean_absolute_error"] <= 0.75
