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
G1_CORE_OUTPUTS = (
    "viewing-conditions.json",
    "raster-baseline.json",
    "neutral-confusability.json",
    "gain-grid.json",
    "visibility-trial-protocol.json",
    "proxy-calibration.json",
    "G1-REPORT.md",
    "review/g1-index.html",
    "review/g1-commanded.svg",
    "review/g1-transformed.svg",
    "review/g1-browser-probe.html",
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


def test_g1_viewing_conditions_pin_domains_units_and_scenarios() -> None:
    viewing = json.loads((EXPERIMENT / "viewing-conditions.json").read_text())
    assert (
        viewing["claim_scope"] == "engineering appearance-model assumptions; not device calibration"
    )
    assert viewing["signal_domain"]["input"] == "encoded sRGB in [0, 1]"
    assert viewing["signal_domain"]["colour_science_XYZ_domain"] == "0 to 1 (reference scale)"
    assert viewing["display_white"] == {"chromaticity": "D65", "Y_w_cd_m2": 100.0}
    assert viewing["transform"]["gains"] == [1.0, 0.74, 0.53]
    assert viewing["transform"]["operation_order"] == "transform after rasterization/compositing"
    assert viewing["primary"] == {
        "surround": "Dim",
        "flare_fraction_of_Yw": 0.0,
        "L_A_cd_m2": 14.2,
        "Y_b": {"bg_0": 56.18, "bg_1": 49.82, "bg_2": 44.32},
    }
    sensitivity = viewing["sensitivity"]
    assert sensitivity["surround"] == "Average"
    assert sensitivity["flare_fraction_of_Yw"] == 0.0075
    assert sensitivity["L_A_cd_m2"] == [9.5, 19.0]
    assert sensitivity["transformed_white_adapted_Y_b"] == {
        "bg_0": 94.77,
        "bg_1": 84.05,
        "bg_2": 74.76,
    }
    assert viewing["scenario_policy"] == "report separately; never average"


def test_g1_contract_has_real_geometry_styles_phases_and_compositions() -> None:
    g1 = load_module("g1_harness.py", "thin_marks_g1_contract")
    contract = g1.specimen_contract()
    assert contract["backgrounds"] == {"gate": ["bg_0", "bg_1"], "report_only": ["bg_2"]}
    assert contract["widths_css_px"] == [1.5, 2.0, 3.0]
    assert contract["device_pixel_ratios"] == [1, 2]
    assert contract["orientations"] == [
        "horizontal",
        "vertical",
        "diagonal_45",
        "shallow_1_2",
        "curved",
    ]
    assert contract["phases_css_px"] == [[0.0, 0.0], [0.0, 0.5], [0.5, 0.0], [0.5, 0.5]]
    assert contract["styles"] == {
        "solid": {"dasharray": None, "linecap": "butt", "dashoffset": 0.0},
        "dashed": {"dasharray": [8.0, 5.0], "linecap": "butt", "dashoffset": 0.0},
        "dotted": {"dasharray": [1.0, 5.0], "linecap": "round", "dashoffset": 0.0},
    }
    assert contract["viewports_css_px"] == {"desktop": [1280, 900], "phone": [390, 844]}
    assert set(contract["features"]) >= {
        "isolated_lines",
        "same_style_crossings",
        "short_legends",
        "endpoint_markers",
        "sparklines",
        "financial_cockpit",
        "thesis_baskets",
    }
    core = contract["line_core"]
    assert core["minimum_coverage"] == 0.5
    assert core["aggregation"] == "per-channel median"
    assert "exclude endpoints" in core["definition"]
    assert "max-coverage pixel" in core["definition"]


def test_g1_metric_owns_proxy_and_bad_gate_polarity() -> None:
    g1 = load_module("g1_harness.py", "thin_marks_g1_metric")
    baseline = g1.load_baseline()

    def red_metric(left: np.ndarray, right: np.ndarray, **_: object) -> float:
        return float(abs(left[0] - right[0]) * 100)

    def blue_metric(left: np.ndarray, right: np.ndarray, **_: object) -> float:
        return float(abs(left[2] - right[2]) * 10_000)

    red = g1.compute_proxy_frontier(baseline, transformed_metric=red_metric)
    blue = g1.compute_proxy_frontier(baseline, transformed_metric=blue_metric)
    assert (
        red["transformed_metric"]["solid_minimum_pair"]
        != blue["transformed_metric"]["solid_minimum_pair"]
    )
    assert red["proxy_matrix"] != blue["proxy_matrix"]
    assert g1.proxy_acceptance({"correlation": 0.9499, "pair_background_mae_max": 0.1}) == "FAIL"
    assert g1.proxy_acceptance({"correlation": 0.99, "pair_background_mae_max": 0.7501}) == "FAIL"
    assert g1.proxy_acceptance({"correlation": 0.95, "pair_background_mae_max": 0.75}) == "PASS"


def test_g1_artifact_contract_is_complete_and_honest() -> None:
    raster = json.loads((EXPERIMENT / "raster-baseline.json").read_text())
    neutral = json.loads((EXPERIMENT / "neutral-confusability.json").read_text())
    gains = json.loads((EXPERIMENT / "gain-grid.json").read_text())
    protocol = json.loads((EXPERIMENT / "visibility-trial-protocol.json").read_text())
    calibration = json.loads((EXPERIMENT / "proxy-calibration.json").read_text())

    assert raster["source_bank"] == "CURRENT frozen 3400K Light categorical"
    assert raster["browser_release_oracle"] is True
    assert len(raster["matrix"]) == 2 * 3 * 3 * 3 * 5 * 2 * 4 * 15
    assert set(raster["width_capacity"]) == {"1.5", "2.0", "3.0"}
    assert all(
        row["human_capacity_status"] == "UNKNOWN/UNPROVEN"
        for row in raster["width_capacity"].values()
    )
    reconnaissance = raster["bounded_single_bank_reconnaissance"]
    assert reconnaissance["candidate_optimization_performed"] is False
    assert reconnaissance["categorical_line_created"] is False

    assert {row["comparison_family"] for row in neutral["matrix"]} == {
        "foreground",
        "benchmark_reference",
        "terminal_report_only",
    }
    assert neutral["terminal_policy"] == "report-only defense-in-depth"
    assert gains["grid"]["sample_count"] == 45
    assert len(gains["grid"]["samples"]) == 45
    assert {row["red_gain"] for row in gains["grid"]["samples"]} == {1.0}
    assert len({row["green_gain"] for row in gains["grid"]["samples"]}) == 5
    assert len({row["blue_gain"] for row in gains["grid"]["samples"]}) == 9
    assert gains["claim"] == "sampled grid and local refinement; not a continuous worst case"
    assert gains["brightness_uncertainty"]["separate_from_channel_gain_grid"] is True

    assert protocol["study"] == "preregistered line-to-legend 2AFC"
    assert protocol["pair_count"] == 15
    assert protocol["results"] is None
    assert protocol["final_visibility_threshold"] is None
    assert protocol["final_width_capacity"] is None
    assert protocol["human_status"] == "not run"
    assert set(protocol["states"]) == {"commanded", "transformed"}
    assert set(protocol["backgrounds"]) == {"bg_0", "bg_1"}
    assert protocol["floor_calibration"]["held_out"] is True

    assert calibration["status"] == "PENDING_BROWSER_CALIBRATION"
    assert calibration["full_image_hash_used"] is False
    assert calibration["acceptance"] == {
        "minimum_global_pooled_correlation": 0.95,
        "maximum_pair_background_mae": 0.75,
        "observed_global_pooled_correlation": None,
        "observed_pair_background_mae_max": None,
        "status": "NOT_EVALUATED",
    }
    assert calibration["provenance"]["chromium_version"] is None
    assert calibration["provenance"]["chromium_version_status"] == ("pending-browser-calibration")
    assert calibration["samples"] == []
    assert calibration["coordinates"] is None


def test_g1_core_outputs_are_byte_deterministic(tmp_path: Path) -> None:
    g1 = load_module("g1_harness.py", "thin_marks_g1_determinism")
    g1.build_core_outputs(tmp_path)
    for relative_path in G1_CORE_OUTPUTS:
        assert (tmp_path / relative_path).read_bytes() == (EXPERIMENT / relative_path).read_bytes()


def test_g1_browser_missing_is_skip_but_runtime_failure_is_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    browser = load_module("g1_browser_validate.py", "thin_marks_g1_browser_errors")
    monkeypatch.setenv("GSTACK_BROWSE", str(tmp_path / "missing"))
    assert browser.run_validation(output_dir=tmp_path)["status"] == "SKIP"

    fake = tmp_path / "browse"
    fake.write_text("#!/bin/sh\nexit 23\n")
    fake.chmod(0o755)
    monkeypatch.setenv("GSTACK_BROWSE", str(fake))
    result = browser.run_validation(output_dir=tmp_path)
    assert result["status"] == "ERROR"
    assert "runtime/probe failure" in result["reason"]

    fake.write_text("#!/bin/sh\nprintf 'Status: healthy\\nMode: launched\\n'\n")
    pending = browser.run_validation(output_dir=tmp_path)
    assert pending["status"] == "PENDING_BROWSER_CALIBRATION"
    assert pending["samples"] == []
    assert pending["acceptance"]["status"] == "NOT_EVALUATED"


@pytest.mark.skipif(
    __import__("os").environ.get("EMBER_RUN_BROWSER_TESTS") != "1",
    reason="set EMBER_RUN_BROWSER_TESTS=1 for local GStack/Chromium G1 validation",
)
def test_optional_real_browser_g1_validation(tmp_path: Path) -> None:
    browser = load_module("g1_browser_validate.py", "thin_marks_g1_browser_real")
    result = browser.run_validation(output_dir=tmp_path)
    if result["status"] == "SKIP":
        pytest.skip(result["reason"])
    if result["status"] == "PENDING_BROWSER_CALIBRATION":
        pytest.skip(result["reason"])
    assert result["status"] == "PASS"
    assert result["acceptance"]["global_pooled_correlation"] >= 0.95
    assert result["acceptance"]["maximum_pair_background_mae"] <= 0.75
