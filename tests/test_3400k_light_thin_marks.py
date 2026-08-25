from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import itertools
import json
import random
import re
import shutil
import subprocess
import sys
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
    "neutral-confusability.json",
    "gain-grid.json",
    "visibility-trial-protocol.json",
    "review/g1-commanded.svg",
    "review/g1-transformed.svg",
    "review/g1-phone-commanded.svg",
    "review/g1-phone-transformed.svg",
    "review/g1-browser-probe.html",
)


def load_module(filename: str, name: str):
    path = EXPERIMENT / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_g1_replay_evidence(destination: Path) -> Path:
    destination.mkdir()
    for filename in (
        "baseline.json",
        "proxy-calibration.json",
        "raster-baseline.json",
        "raster-masks.json",
        "raster-observations.json",
        "raster-verification.json",
    ):
        shutil.copy2(EXPERIMENT / filename, destination / filename)
    (destination / "review").mkdir()
    shutil.copy2(
        EXPERIMENT / "review/g1-browser-probe.html",
        destination / "review/g1-browser-probe.html",
    )
    return destination


def run_g1_replay(
    evidence_dir: Path, *, optimized: bool = False
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable]
    if optimized:
        command.append("-O")
    command.extend(
        [
            str(EXPERIMENT / "g1_evidence_verify.py"),
            "--evidence-dir",
            str(evidence_dir),
            "--output",
            str(evidence_dir / "verification-output.json"),
        ]
    )
    return subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)


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
    assert contract["state_order"] == ["commanded", "transformed"]
    assert contract["background_order"] == ["bg_0", "bg_1", "bg_2"]
    assert contract["category_order"] == ["one", "two", "three", "four", "five", "six"]
    assert contract["style_order"] == ["solid", "dashed", "dotted"]
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


def test_g1_browser_payload_case_mapping_matches_planned_ledger() -> None:
    probe = (EXPERIMENT / "review/g1-browser-probe.html").read_text()
    match = re.search(
        r'<script id="g1-contract" type="application/json">(.*?)</script>', probe, re.DOTALL
    )
    assert match is not None
    payload = json.loads(match.group(1))
    contract = payload["contract"]
    ledger = json.loads((EXPERIMENT / "raster-baseline.json").read_text())["matrix"]
    pairs = list(itertools.combinations(contract["category_order"], 2))
    browser_dimensions = list(
        itertools.product(
            contract["state_order"],
            contract["background_order"],
            contract["widths_css_px"],
            contract["style_order"],
            contract["orientations"],
            contract["device_pixel_ratios"],
            contract["phases_css_px"],
            pairs,
        )
    )
    assert len(browser_dimensions) == len(ledger) == 32_400
    strides = (1, 15, 60, 120, 600, 1_800, 5_400, 16_200)
    indices = {0, len(ledger) - 1}
    for stride in strides:
        indices.update({stride - 1, stride})
    indices.update(random.Random(3400).sample(range(len(ledger)), 48))

    for index in sorted(indices):
        state, background, width, style, orientation, dpr, phase, pair = browser_dimensions[index]
        reconstructed = {
            "id": f"planned-{index + 1:05d}",
            "state": state,
            "background": background,
            "background_policy": "gate" if background in ("bg_0", "bg_1") else "report-only",
            "width_css_px": width,
            "style": style,
            "orientation": orientation,
            "dpr": dpr,
            "phase_css_px": list(phase),
            "roles": [f"cat.{name}" for name in pair],
        }
        assert reconstructed == {key: ledger[index][key] for key in reconstructed}

    assert "Object.keys(spec.categorical)" not in probe
    assert "Object.keys(spec.contract.styles)" not in probe
    assert "data-planned-id" in probe


def test_g1_browser_probe_malformed_cases_are_never_blank() -> None:
    probe = (EXPERIMENT / "review/g1-browser-probe.html").read_text()
    assert "Number.isFinite(numericCase)" in probe
    assert "Math.floor(numericCase)" in probe
    assert "Math.max(0,Math.min(product.length-1" in probe
    assert 'data-status="ERROR"' in probe
    assert "ERROR: invalid case selector" in probe


def test_g1_review_sheets_contain_real_structurally_tagged_features() -> None:
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    href = "{http://www.w3.org/1999/xlink}href"
    sheets = (
        ("g1-commanded.svg", "desktop"),
        ("g1-transformed.svg", "desktop"),
        ("g1-phone-commanded.svg", "phone"),
        ("g1-phone-transformed.svg", "phone"),
    )
    for filename, layout in sheets:
        root = ET.fromstring((EXPERIMENT / "review" / filename).read_text())
        geometry = root.find("svg:defs/svg:path[@id='g1-crossing-geometry']", namespace)
        assert geometry is not None and geometry.attrib["d"]
        evidence_groups = [
            group
            for group in root.findall(".//svg:g", namespace)
            if group.attrib.get("data-layout") == layout
        ]
        assert {group.attrib["data-background"] for group in evidence_groups} == {
            "bg_0",
            "bg_1",
        }
        for group in evidence_groups:
            legends = group.findall(".//svg:line[@data-feature='short-category-legend']", namespace)
            assert [legend.attrib["data-role"] for legend in legends] == [
                "cat.one",
                "cat.two",
                "cat.three",
                "cat.four",
                "cat.five",
                "cat.six",
            ]
            assert all(
                float(mark.attrib["x2"]) - float(mark.attrib["x1"]) == 26 for mark in legends
            )
            assert (
                len(group.findall(".//svg:circle[@data-feature='endpoint-marker']", namespace)) == 2
            )
            assert len(group.findall(".//svg:path[@data-feature='sparkline']", namespace)) == 3
            assert len(group.findall(".//svg:g[@data-feature='financial-cockpit']", namespace)) == 1
            assert len(group.findall(".//svg:g[@data-feature='thesis-baskets']", namespace)) == 1

            crossings = group.findall(
                ".//svg:g[@data-feature='same-style-color-only-crossing']", namespace
            )
            assert len(crossings) == 1
            crossing_marks = crossings[0].findall("svg:use", namespace)
            assert len(crossing_marks) == 2
            assert {mark.attrib.get("href", mark.attrib.get(href)) for mark in crossing_marks} == {
                "#g1-crossing-geometry"
            }
            assert {mark.attrib["data-role"] for mark in crossing_marks} == {
                "cat.five",
                "cat.six",
            }
            for attribute in ("fill", "stroke-width", "stroke-linecap", "stroke-dashoffset"):
                assert len({mark.attrib[attribute] for mark in crossing_marks}) == 1
            assert len({mark.attrib["stroke"] for mark in crossing_marks}) == 2


def test_g1_phone_sheets_and_review_index_obey_390px_contract() -> None:
    for filename in ("g1-phone-commanded.svg", "g1-phone-transformed.svg"):
        root = ET.fromstring((EXPERIMENT / "review" / filename).read_text())
        assert root.attrib["width"] == "390"
        assert root.attrib["height"] == "844"
        assert root.attrib["viewBox"] == "0 0 390 844"

    index = (EXPERIMENT / "review/g1-index.html").read_text()
    assert 'src="g1-phone-commanded.svg"' in index
    assert 'src="g1-phone-transformed.svg"' in index
    assert ".desktop-frame{overflow-x:auto;overflow-y:hidden}" in index
    assert ".phone-frame{overflow:hidden}" in index
    assert "section{min-width:0}" in index
    assert ".desktop-sheet{display:block;width:1280px;max-width:none}" in index
    assert "html,body{margin:0;max-width:100%;overflow-x:hidden" in index


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
    assert raster["planned_case_count"] == 32_400
    assert len(raster["matrix"]) == 2 * 3 * 3 * 3 * 5 * 2 * 4 * 15
    assert {row["status"] for row in raster["matrix"]} == {"PASS"}
    assert all(row["observed_line_core_rgb8"] is not None for row in raster["matrix"])
    assert all(row["observed_distance"] is not None for row in raster["matrix"])
    assert all(row["proxy_prediction"] is not None for row in raster["matrix"])
    assert all(row["proxy_error"] is not None for row in raster["matrix"])
    assert raster["observed_case_count"] == 32_400
    assert raster["unsupported_case_count"] == 0
    assert raster["phase3_search_authorized"] is True
    assert raster["production_promotion_blocked"] is True
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
    assert protocol["design"] == "balanced incomplete fractional-block design"
    base_cells = protocol["base_cells"]
    assert base_cells["count_per_observer"] == 15 * 2 * 2 * 3 == 180
    assert base_cells["repeats_per_observer"] == 2
    assert base_cells["noncatch_trials_per_observer"] == 360
    assert base_cells["noncatch_trials_per_observer"] <= 400
    assert protocol["fractional_factors"]["not_full_factorial_per_observer"] is True
    assert protocol["observers"]["minimum"] == 15
    assert protocol["aggregate_coverage_at_minimum"] == {
        "observers": 15,
        "noncatch_trials": 5_400,
        "observations_per_base_cell": 30,
        "observations_per_style_orientation_per_base_cell": 2,
    }
    assert protocol["catch_trials"]["count_per_observer"] == 40
    assert protocol["catch_trials"]["fraction_of_total"] == pytest.approx(0.1)
    assert protocol["session_plan"]["blocks_per_observer"] == 4
    assert protocol["session_plan"]["trials_per_block_including_catches"] == 100
    assert protocol["session_plan"]["target_total_duration_minutes_max"] <= 60
    assert protocol["power_analysis_before_run"]["required"] is True
    assert protocol["power_analysis_before_run"]["observed_results_used"] is False
    assert protocol["floor_calibration"]["held_out"] is True
    assert protocol["floor_calibration"]["no_proxy_tuning_on_held_out"] is True

    styles = protocol["fractional_factors"]["styles"]
    orientations = protocol["fractional_factors"]["orientations"]
    for base_cell_index in range(base_cells["count_per_observer"]):
        assignments = [
            (
                styles[(observer + repeat + base_cell_index) % 3],
                orientations[(observer + 2 * repeat + base_cell_index) % 5],
            )
            for observer in range(protocol["observers"]["minimum"])
            for repeat in range(base_cells["repeats_per_observer"])
        ]
        assert set(assignments) == set(itertools.product(styles, orientations))
        assert all(assignments.count(combination) == 2 for combination in set(assignments))
        sides = [
            (observer + repeat + base_cell_index) % 2
            for observer in range(protocol["observers"]["minimum"])
            for repeat in range(base_cells["repeats_per_observer"])
        ]
        assert sides.count(0) == sides.count(1) == 15

    for observer in range(protocol["observers"]["minimum"]):
        assignments = [
            (
                styles[(observer + repeat + base_cell_index) % 3],
                orientations[(observer + 2 * repeat + base_cell_index) % 5],
            )
            for repeat in range(base_cells["repeats_per_observer"])
            for base_cell_index in range(base_cells["count_per_observer"])
        ]
        assert len(assignments) == 360
        assert all(assignments.count(combination) == 24 for combination in set(assignments))

    assert calibration["status"] == "PASS"
    assert calibration["full_image_hash_used"] is False
    assert calibration["acceptance"]["status"] == "PASS"
    assert calibration["acceptance"]["global_pooled_correlation"] >= 0.95
    assert calibration["acceptance"]["global_pooled_mae_delta_e_ok"] <= 0.75
    assert calibration["acceptance"]["observed_gate_pair_background_mae_max_delta_e_ok"] <= 0.75
    assert all(
        row["status"] == "PASS"
        for row in calibration["acceptance"]["pair_background"]
        if row["background_policy"] == "gate"
    )
    assert calibration["provenance"]["chromium_version"] is None
    assert calibration["provenance"]["chromium_version_status"] == "unavailable-unclaimed"
    assert calibration["provenance"]["browser_status"] == {
        "mode": "launched",
        "status": "healthy",
    }
    assert calibration["counts"]["observed_pair_rows"] == 32_400
    assert calibration["counts"]["unsupported_pair_rows"] == 0
    assert calibration["phase3_search_authorized"] is True

    report = (EXPERIMENT / "G1-REPORT.md").read_text()
    assert "Phase 3 candidate search is authorized" in report
    assert "UNKNOWN/UNPROVEN" in report
    assert "Before any production promotion" in report


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="the committed Chromium replay receipt is bound to the macOS capture runtime",
)
def test_g1_browser_evidence_hashes_and_independent_replay_are_fresh(tmp_path: Path) -> None:
    calibration = json.loads((EXPERIMENT / "proxy-calibration.json").read_text())
    raster = json.loads((EXPERIMENT / "raster-baseline.json").read_text())
    for key, filename in (
        ("raster_masks", "raster-masks.json"),
        ("raster_observations", "raster-observations.json"),
    ):
        expected = hashlib.sha256((EXPERIMENT / filename).read_bytes()).hexdigest()
        assert calibration["evidence"][key]["sha256"] == expected
        assert raster["evidence"][f"{key}_sha256"] == expected
    assert (
        calibration["evidence"]["raster_ledger"]["sha256"]
        == hashlib.sha256((EXPERIMENT / "raster-baseline.json").read_bytes()).hexdigest()
    )
    verifier = load_module("g1_evidence_verify.py", "thin_marks_g1_evidence_replay")
    output = tmp_path / "verification.json"
    replayed = verifier.verify_evidence(output)
    assert replayed == json.loads((EXPERIMENT / "raster-verification.json").read_text())
    assert replayed["pair_rows_replayed"] == 32_400
    assert replayed["planned_id_mapping_rows_verified"] == 32_400


def test_g1_report_capture_chunks_are_consistent() -> None:
    calibration = json.loads((EXPERIMENT / "proxy-calibration.json").read_text())
    capture = calibration["capture"]
    dpr_count = len(capture["dpr"])
    assert capture["mask_tiles"] % dpr_count == 0
    assert capture["color_tiles"] % dpr_count == 0
    chunk_sizes = [
        min(capture["chunk_tiles"], tile_count - start)
        for tile_count in (
            *([capture["mask_tiles"] // dpr_count] * dpr_count),
            *([capture["color_tiles"] // dpr_count] * dpr_count),
        )
        for start in range(0, tile_count, capture["chunk_tiles"])
    ]
    assert sum(chunk_sizes) == capture["total_tiles"] == 22_320
    assert max(chunk_sizes) <= 128
    assert len(chunk_sizes) == capture["chunks"] == 176
    assert sorted(size for size in chunk_sizes if size < 128) == [48, 48, 104, 104]

    report_line = next(
        line
        for line in (EXPERIMENT / "G1-REPORT.md").read_text().splitlines()
        if line.startswith("- Each chunk used")
    )
    assert report_line == (
        "- Each chunk used up to 128 eager same-origin `srcdoc` iframes and one chained "
        "`goto` + `screenshot`; each iframe rasterized at local `(0,0)`. DPR 1 and 2 were "
        "captured with screenshot scale equal to DPR."
    )


def test_g1_verifier_has_no_optimization_sensitive_asserts() -> None:
    tree = ast.parse((EXPERIMENT / "g1_evidence_verify.py").read_text())
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Assert)]


def test_g1_verifier_rejects_corrupted_observation_with_and_without_optimization(
    tmp_path: Path,
) -> None:
    evidence = copy_g1_replay_evidence(tmp_path / "corrupted-observation")
    observations_path = evidence / "raster-observations.json"
    observations = json.loads(observations_path.read_text())
    record = observations["observations"][0]
    observed = np.frombuffer(
        base64.b64decode(record["observed_rgb8_base64"]), dtype=np.uint8
    ).copy()
    observed[::3] = np.where(observed[::3] == 255, 254, observed[::3] + 1)
    record["observed_rgb8_base64"] = base64.b64encode(observed.tobytes()).decode("ascii")
    record["observed_rgb8_median"] = np.median(observed.reshape(-1, 3), axis=0).tolist()
    observations_path.write_text(json.dumps(observations, separators=(",", ":")) + "\n")

    observation_hash = hashlib.sha256(observations_path.read_bytes()).hexdigest()
    raster_path = evidence / "raster-baseline.json"
    raster = json.loads(raster_path.read_text())
    raster["evidence"]["raster_observations_sha256"] = observation_hash
    raster_path.write_text(json.dumps(raster, separators=(",", ":")) + "\n")
    raster_hash = hashlib.sha256(raster_path.read_bytes()).hexdigest()

    receipt_path = evidence / "raster-verification.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["provenance"]["raster_observations_sha256"] = observation_hash
    receipt["provenance"]["raster_ledger_sha256"] = raster_hash
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    proxy_path = evidence / "proxy-calibration.json"
    proxy = json.loads(proxy_path.read_text())
    proxy["evidence"]["raster_observations"]["sha256"] = observation_hash
    proxy["evidence"]["raster_ledger"]["sha256"] = raster_hash
    proxy["evidence"]["independent_replay"]["sha256"] = hashlib.sha256(
        receipt_path.read_bytes()
    ).hexdigest()
    proxy_path.write_text(json.dumps(proxy, indent=2, sort_keys=True) + "\n")

    for optimized in (False, True):
        completed = run_g1_replay(evidence, optimized=optimized)
        assert completed.returncode != 0, completed.stdout + completed.stderr
        assert "ERROR:" in completed.stderr


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="the committed Chromium replay receipt is bound to the macOS capture runtime",
)
def test_g1_verifier_rejects_corrupted_acceptance_and_replay_receipt(tmp_path: Path) -> None:
    acceptance_evidence = copy_g1_replay_evidence(tmp_path / "corrupted-acceptance")
    proxy_path = acceptance_evidence / "proxy-calibration.json"
    proxy = json.loads(proxy_path.read_text())
    proxy["acceptance"]["global_pooled_mae_delta_e_ok"] += 0.1
    proxy_path.write_text(json.dumps(proxy, indent=2, sort_keys=True) + "\n")
    completed = run_g1_replay(acceptance_evidence)
    assert completed.returncode != 0
    assert "acceptance aggregate" in completed.stderr

    receipt_evidence = copy_g1_replay_evidence(tmp_path / "corrupted-receipt")
    receipt_path = receipt_evidence / "raster-verification.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["pair_rows_replayed"] -= 1
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    proxy_path = receipt_evidence / "proxy-calibration.json"
    proxy = json.loads(proxy_path.read_text())
    proxy["evidence"]["independent_replay"]["sha256"] = hashlib.sha256(
        receipt_path.read_bytes()
    ).hexdigest()
    proxy_path.write_text(json.dumps(proxy, indent=2, sort_keys=True) + "\n")
    completed = run_g1_replay(receipt_evidence)
    assert completed.returncode != 0
    assert "independent replay receipt content" in completed.stderr


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="the committed Chromium replay receipt is bound to the macOS capture runtime",
)
def test_g1_verifier_valid_evidence_passes_with_and_without_optimization(tmp_path: Path) -> None:
    evidence = copy_g1_replay_evidence(tmp_path / "valid")
    for optimized in (False, True):
        completed = run_g1_replay(evidence, optimized=optimized)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert json.loads(completed.stdout)["status"] == "PASS"


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
    failed_probe = browser.run_validation(output_dir=tmp_path)
    assert failed_probe["status"] == "ERROR"
    assert "runtime/probe failure" in failed_probe["reason"]


def test_g1_standalone_sentinel_count_is_bounded_at_api_and_cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    browser = load_module("g1_browser_validate.py", "thin_marks_g1_sentinel_bounds")
    assert browser.DEFAULT_STANDALONE_SENTINELS == 48
    monkeypatch.setenv("GSTACK_BROWSE", str(tmp_path / "missing"))

    for invalid in (0, -1, browser.MAX_STANDALONE_SENTINELS + 1, 1.5, True):
        output = tmp_path / f"api-{invalid}"
        result = browser.run_validation(output_dir=output, standalone_sentinels=invalid)
        assert result["status"] == "ERROR"
        assert "standalone_sentinels must be an integer in range" in result["reason"]

    assert (
        browser.run_validation(output_dir=tmp_path / "valid", standalone_sentinels=1)["status"]
        == "SKIP"
    )

    for invalid in ("0", "-1", str(browser.MAX_STANDALONE_SENTINELS + 1)):
        output = tmp_path / f"cli-{invalid}"
        completed = subprocess.run(
            [
                sys.executable,
                str(EXPERIMENT / "g1_browser_validate.py"),
                "--output-dir",
                str(output),
                "--standalone-sentinels",
                invalid,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env={"GSTACK_BROWSE": str(tmp_path / "missing")},
        )
        assert completed.returncode != 0
        assert json.loads(completed.stdout)["status"] == "ERROR"
        assert "standalone_sentinels must be an integer in range" in completed.stdout


def test_g1_changed_role_observation_changes_reconstructed_pair() -> None:
    browser = load_module("g1_browser_validate.py", "thin_marks_g1_reconstruct")
    mask = {"samples": [[10.0, 1.0, 1.0, 1, 1, 1.0, 0.0]]}
    base = {"state": "commanded", "background": "bg_0"}
    baseline = {
        "categorical": {"one": "#ff0000", "two": "#0000ff"},
        "surfaces": {"bg_0": "#ffffff"},
    }
    left = {
        "role": "cat.one",
        "sample_count": 1,
        "observed_rgb8_base64": browser._encode_rgb8(np.array([[255, 0, 0]], dtype=np.uint8)),
    }
    right = {
        "role": "cat.two",
        "sample_count": 1,
        "observed_rgb8_base64": browser._encode_rgb8(np.array([[0, 0, 255]], dtype=np.uint8)),
    }
    original = browser.reconstruct_pair_metrics(left, right, mask, mask, base, baseline)
    left["observed_rgb8_base64"] = browser._encode_rgb8(np.array([[0, 255, 0]], dtype=np.uint8))
    changed = browser.reconstruct_pair_metrics(left, right, mask, mask, base, baseline)
    assert original["observed_distance"] != changed["observed_distance"]


def test_g1_mask_core_polarity_selects_darkest_max_coverage_pixel() -> None:
    browser = load_module("g1_browser_validate.py", "thin_marks_g1_mask_polarity")
    mask = np.full((5, 5, 3), 255, dtype=np.uint8)
    mask[2, 2] = 0
    mask[2, 1] = 127
    samples = browser.select_line_core(
        mask,
        [{"s": 1.0, "x": 2.5, "y": 2.5, "tx": 1.0, "ty": 0.0}],
        1.5,
        1,
        (0.0, 0.0),
        0,
    )
    assert samples[0][3:6] == [2, 2, 1.0]


def test_g1_bad_contract_pair_background_mae_blocks_acceptance() -> None:
    browser = load_module("g1_browser_validate.py", "thin_marks_g1_bad_mae")
    rows = [
        {
            "status": "PASS",
            "state": "commanded",
            "background": "bg_0",
            "dpr": 1,
            "roles": ["cat.five", "cat.six"],
            "_observed_by_station": [1.0, 2.0, 3.0],
            "_predicted_by_station": [2.0, 3.0, 4.0],
            "_absolute_residual_by_station": [1.0, 1.0, 1.0],
        }
    ]
    result = browser.evaluate_acceptance(rows)
    assert result["status"] == "FAIL"
    assert result["observed_gate_pair_background_mae_max_delta_e_ok"] == 1.0


@pytest.mark.skipif(
    __import__("os").environ.get("EMBER_RUN_BROWSER_TESTS") != "1",
    reason="set EMBER_RUN_BROWSER_TESTS=1 for local GStack/Chromium G1 validation",
)
def test_optional_real_browser_g1_validation(tmp_path: Path) -> None:
    browser = load_module("g1_browser_validate.py", "thin_marks_g1_browser_real")
    result = browser.run_validation(output_dir=tmp_path)
    if result["status"] == "SKIP":
        pytest.skip(result["reason"])
    assert result["status"] == "PASS"
    assert result["acceptance"]["global_pooled_correlation"] >= 0.95
    assert result["acceptance"]["observed_gate_pair_background_mae_max_delta_e_ok"] <= 0.75
