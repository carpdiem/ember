from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEVEN = ROOT / "docs/experiments/3400k-light-thin-marks/seven-point"
REVIEW = ROOT / "docs/experiments/3400k-light-thin-marks/review/g2-seven-point-hue-frontier"
SPEC = importlib.util.spec_from_file_location(
    "hue_frontier_report_test", SEVEN / "hue_frontier_report.py"
)
assert SPEC is not None and SPEC.loader is not None
report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = report
SPEC.loader.exec_module(report)


def _row(role: str, hue: float) -> dict:
    bank = ["#342F2C", "#7F180E", "#867412", "#0A6109", "#2B8CAD", "#5D53AE", "#B34B71"]
    return {
        "role": role,
        "label": report.LABELS[role],
        "candidate_id": role * 64,
        "bank": bank,
        "transformed_bank": bank,
        "free_1": bank[1],
        "free_2": bank[2],
        "free_1_oklch": [0.4, 0.13, 30.0],
        "free_2_oklch": [0.56, 0.11, hue],
        "free_1_transformed_oklch": [0.38, 0.12, 28.0],
        "free_2_transformed_oklch": [0.49, 0.10, hue - 2],
        "contrast": {
            free_role: {state: {"bg_0": 3.4, "bg_1": 3.1} for state in ("commanded", "transformed")}
            for free_role in ("free_1", "free_2")
        },
        "metrics": {
            state: {width: 8.0 for width in ("1.5", "2", "3")}
            for state in ("commanded", "transformed")
        },
        "bindings": {
            state: {
                width: {
                    "roles": ["category-0", "category-4"],
                    "delta_e_ok": 8.0,
                    "background": "bg_0",
                    "pair_id": "x",
                }
                for width in ("1.5", "2", "3")
            }
            for state in ("commanded", "transformed")
        },
    }


def _data() -> dict:
    return {
        "search": {
            "feasible_hue_support": {
                "exact_color_count": 258,
                "intervals_degrees": [[29.8, 60.2], [82.1, 112.5], [315.1, 329.8]],
            }
        },
        "rows": {
            "reference": _row("reference", 104.9),
            "benchmark-c": _row("benchmark-c", 60.2),
            "a": _row("a", 89.9),
            "b": _row("b", 97.6),
            "c": _row("c", 104.9),
        },
    }


def test_page_leads_with_hue_and_reports_actual_support() -> None:
    page = report.build_html(_data())
    assert "Hue first. No olive anchor." in page
    assert "Actual feasible hue support" in page
    assert "29.8–60.2°" in page and "82.1–112.5°" in page
    assert "60.2–82.1° gap" in page
    assert "target-distance" in page
    assert "Automatic recommendation: NONE" in page
    assert page.count('class="frontier"') == 5
    assert "overflow:visible" in page
    assert "@media(max-width:1100px)" in page
    assert "@media(max-width:680px)" in page


def test_selection_is_closed_without_recommendation(monkeypatch) -> None:
    monkeypatch.setattr(
        report.browser,
        "_source_binding",
        lambda filename: {"file": filename, "sha256": "0" * 64, "commit": "1" * 40},
    )
    payload = report.selection_payload(_data())
    assert payload["status"] == "AWAITING_MICHAEL_HUE_FRONTIER_SELECTION"
    assert payload["selection"] is None
    assert payload["allowed_selections"] == [
        "KEEP-A",
        "AMBER-ORANGE",
        "GOLDEN-YELLOW",
        "YELLOW",
        "YELLOW-GREEN-EDGE",
    ]
    assert payload["automatic_recommendation"] is None
    assert payload["production_promotion"] is False


def test_oklch_and_contrast_are_visible() -> None:
    page = report.card(_row("a", 89.9))
    assert "L 0.560 · C 0.110 · h 89.9°" in page
    assert "3400K" in page
    assert "Cmd bg0" in page and "Cmd bg1" in page
    assert "3400K bg0" in page and "3400K bg1" in page
    assert "Actual transformed minima" in page


def test_source_is_environment_free_and_evidence_count_closed() -> None:
    source = (SEVEN / "hue_frontier_report.py").read_text()
    assert "/Users/" not in source
    assert "timestamp" not in source.lower()
    assert report.EXPECTED_EVIDENCE_COUNT == 22


def test_committed_hue_review_is_closed_and_awaiting_human_selection() -> None:
    evidence = REVIEW / "evidence"
    assert len(list(evidence.iterdir())) == 22
    assert all(path.stat().st_size < 50_000_000 for path in evidence.iterdir())
    selection = json.loads((REVIEW / "selection.json").read_text())
    assert selection["status"] == "AWAITING_MICHAEL_HUE_FRONTIER_SELECTION"
    assert selection["selection"] is None
    assert selection["automatic_recommendation"] is None
    assert selection["production_promotion"] is False


def test_committed_hue_page_reports_actual_frontier_metrics_and_support() -> None:
    page = (REVIEW / "index.html").read_text()
    assert "Hue first. No olive anchor." in page
    assert "258 exact colors" in page
    assert "1.5px 9.484" in page
    assert "1.5px 8.024" in page
    assert "1.5px 8.202" in page
    assert "1.5px 9.137" in page
    assert "/Users/" not in page
