from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEVEN = ROOT / "docs/experiments/3400k-light-thin-marks/seven-point"
REVIEW = ROOT / "docs/experiments/3400k-light-thin-marks/review/g2-seven-point"
SPEC = importlib.util.spec_from_file_location("seven_point_report_test", SEVEN / "report.py")
assert SPEC is not None and SPEC.loader is not None
report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = report
SPEC.loader.exec_module(report)


def _row(role: str, value: float) -> dict:
    bank = ["#342F2C", "#7C140A", "#857D0B", "#0A6109", "#2B8CAD", "#5D53AE", "#B34B71"]
    binding = {
        "delta_e_ok": value,
        "roles": ["fg_0", "category-2"],
        "background": "bg_0",
        "pair_id": "pair-1",
    }
    return {
        "role": role,
        "label": report.ROLE_LABELS[role],
        "candidate_id": role * 64,
        "bank": bank,
        "transformed_bank": bank,
        "status": "PASS",
        "metrics": {
            state: {width: value for width in ("1.5", "2", "3")}
            for state in ("commanded", "transformed")
        },
        "bindings": {
            state: {width: dict(binding) for width in ("1.5", "2", "3")}
            for state in ("commanded", "transformed")
        },
    }


def _data() -> dict:
    values = {"reference": 5.3, "benchmark-c": 7.3, "a": 9.4, "b": 8.7, "c": 8.3}
    return {
        "rows": {role: _row(role, value) for role, value in values.items()},
        "recommendation": "a",
    }


def test_closed_selection_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        report.browser,
        "_source_binding",
        lambda filename: {"file": filename, "sha256": "0" * 64, "commit": "1" * 40},
    )
    payload = report.selection_payload(_data())
    assert payload == {
        "schema_version": 1,
        "artifact_kind": "seven-point-human-selection",
        "status": "AWAITING_MICHAEL_SELECTION",
        "selection": None,
        "allowed_selections": ["A", "B", "C"],
        "candidate_ids": {"A": "a" * 64, "B": "b" * 64, "C": "c" * 64},
        "recommendation": "A",
        "human_1_5px_capacity": "UNKNOWN",
        "production_promotion": False,
        "fixed_fg0": "#342F2C",
        "evidence_file_count": 22,
        "report_source": {"file": "report.py", "sha256": "0" * 64, "commit": "1" * 40},
    }


def test_page_shows_all_banks_and_three_simultaneous_finalists() -> None:
    page = report.build_html(_data())
    assert page.count('class="candidate"') == 3
    assert page.count('class="benchmark"') == 2
    assert all(f'id="candidate-{role}"' in page for role in ("a", "b", "c"))
    assert "AWAITING MICHAEL SELECTION" in page
    assert "Human 1.5px capacity: UNKNOWN" in page
    assert "Production promotion: FALSE" in page
    assert "Evidence: 22 files" in page
    assert "Recommendation: A" in page
    assert "carousel" not in page.lower()
    assert "overflow-y" not in page.lower()
    assert "@media(max-width:1180px)" in page
    assert "@media(max-width:680px)" in page
    assert ".summary-wrap th:nth-child(5),.summary-wrap td:nth-child(5){display:none}" in page


def test_report_table_is_actual_chromium_first() -> None:
    markdown = report.build_report_md(_data())
    assert "| Candidate A | 9.40000000 | 9.40000000 | 9.40000000 |" in markdown
    assert "All 21 pairs use both subpixel lane directions" in markdown
    assert "Production promotion:** `false`" in markdown


def test_gated_metric_excludes_report_only_bg2() -> None:
    result = {
        "pair_metrics_by_family": {
            "seven_point": {
                "actual_by_width_state_background": {
                    "1.5": {
                        "transformed": {
                            "bg_0": {"minimum_observed_delta_e_ok": 9.0},
                            "bg_1": {"minimum_observed_delta_e_ok": 8.0},
                            "bg_2": {"minimum_observed_delta_e_ok": 1.0},
                        }
                    }
                }
            }
        }
    }
    assert report.gated_metric(result, "1.5", "transformed") == 8.0


def test_pair_binding_uses_both_gating_backgrounds_and_exact_width() -> None:
    request = {
        "requested_pairs": [
            {
                "id": "wrong-bg",
                "width_css_px": 1.5,
                "state": "transformed",
                "background": "bg_2",
                "roles": ["fg_0", "category-0"],
            },
            {
                "id": "right",
                "width_css_px": 1.5,
                "state": "transformed",
                "background": "bg_1",
                "roles": ["category-1", "category-2"],
            },
        ]
    }
    pairs = {
        "rows": [
            {"id": "wrong-bg", "observed_delta_e_ok": 1.0},
            {"id": "right", "observed_delta_e_ok": 8.5},
        ]
    }
    assert report.pair_binding(request, pairs, 1.5, "transformed") == {
        "delta_e_ok": 8.5,
        "roles": ["category-1", "category-2"],
        "background": "bg_1",
        "pair_id": "right",
    }


def test_evidence_copy_contract_is_exactly_22_files(tmp_path: Path) -> None:
    search = tmp_path / "search"
    requests = tmp_path / "requests"
    browser = tmp_path / "browser"
    output = tmp_path / "evidence"
    for directory in (search, requests, browser):
        directory.mkdir()
    for name in ("catalog-summary.json", "results.json"):
        (search / name).write_text("{}")
    for role in report.ROLE_ORDER:
        (requests / f"browser-request-{role}.json").write_text("{}")
        for kind in ("result", "observations", "pairs"):
            (browser / f"browser-{kind}-{role}.json").write_text("{}")
    report.copy_evidence(search, requests, browser, output)
    assert len(list(output.iterdir())) == 22


def test_source_has_no_environment_paths_or_timestamp_fields() -> None:
    source = (SEVEN / "report.py").read_text()
    assert "/Users/" not in source
    assert '"timestamp"' not in source
    assert "datetime" not in source
    assert report.EXPECTED_EVIDENCE_COUNT == 22


def test_committed_review_package_is_closed_and_selection_matches_finalists() -> None:
    evidence = REVIEW / "evidence"
    files = sorted(path.name for path in evidence.iterdir() if path.is_file())
    expected = ["catalog-summary.json", "results.json"]
    expected += [f"browser-request-{role}.json" for role in report.ROLE_ORDER]
    expected += [
        f"browser-{kind}-{role}.json"
        for role in report.ROLE_ORDER
        for kind in ("result", "observations", "pairs")
    ]
    assert files == sorted(expected)
    assert len(files) == 22
    assert all((evidence / name).stat().st_size < 50_000_000 for name in files)
    selection = json.loads((REVIEW / "selection.json").read_text())
    results = json.loads((evidence / "results.json").read_text())
    assert selection["candidate_ids"] == {
        row["lane"]: row["candidate_id"] for row in results["candidates"]
    }
    assert selection["status"] == "AWAITING_MICHAEL_SELECTION"
    assert selection["selection"] is None
    assert selection["allowed_selections"] == ["A", "B", "C"]
    assert selection["human_1_5px_capacity"] == "UNKNOWN"
    assert selection["production_promotion"] is False


def test_committed_page_and_report_match_actual_browser_minima() -> None:
    page = (REVIEW / "index.html").read_text()
    markdown = (REVIEW / "report.md").read_text()
    assert page.count('class="candidate"') == 3
    assert page.count('class="benchmark"') == 2
    for role in report.ROLE_ORDER:
        result = json.loads((REVIEW / "evidence" / f"browser-result-{role}.json").read_text())
        value = report.gated_metric(result, "1.5", "transformed")
        assert f"{value:.8f}" in markdown
    assert "Recommendation: A" in page
    assert "Production promotion: FALSE" in page


def test_committed_review_chrome_has_no_private_paths_or_runtime_metadata() -> None:
    for name in ("index.html", "report.md", "selection.json"):
        payload = (REVIEW / name).read_text()
        assert "/Users/" not in payload
        assert "timestamp" not in payload.lower()
        assert "screenshot" not in payload.lower()
