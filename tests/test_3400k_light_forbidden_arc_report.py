from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEVEN = ROOT / "docs/experiments/3400k-light-thin-marks/seven-point"
REVIEW = ROOT / "docs/experiments/3400k-light-thin-marks/review/g2-seven-point-forbidden-arc"
SPEC = importlib.util.spec_from_file_location(
    "forbidden_arc_report_test", SEVEN / "forbidden_arc_report.py"
)
assert SPEC is not None and SPEC.loader is not None
report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = report
SPEC.loader.exec_module(report)


def synthetic_data() -> dict:
    rows = {}
    for role in report.ALL_ROLES:
        rows[role] = {
            "role": role,
            "label": report.LABELS[role],
            "candidate_id": role * 16,
            "bank": ["#342F2C", "#70002D", "#B25809", "#6C8D38", "#016869", "#4081D2", "#84499C"],
            "transformed_bank": ["#30251E"] * 7,
            "oklch": [[0.3, 0.1, 20.0]] * 7,
            "transformed_oklch": [[0.3, 0.1, 30.0]] * 7,
            "contrast": [],
            "metrics": {"transformed": {"1.5": 9.0, "2": 10.0, "3": 11.0}},
            "bindings": {"transformed": {"1.5": {"roles": ["fg_0", "category-0"]}}},
            "forbidden_hues": [],
        }
    return {
        "rows": rows,
        "search": {"catalog": {"full_before": 7184, "full_after": 7024, "full_rejected": 160}},
    }


def test_report_contract_is_three_finalists_plus_two_compact_benchmarks() -> None:
    assert report.FINALIST_ROLES == ("a", "b", "c")
    assert report.BENCHMARK_ROLES == ("reference", "benchmark-c")
    assert report.EXPECTED_EVIDENCE_COUNT == 22


def test_html_is_visual_first_and_has_no_recommendation() -> None:
    source = report.build_html(synthetic_data())
    assert "Three de novo six-color systems." in source
    assert "Full commanded and 3400K identities" in source
    assert source.count("Forbidden-arc finalist") == 3
    assert "Candidate A and prior C are compact evidence controls only" in source
    assert "Automatic recommendation: NONE" in source
    assert "92.0°–118.0°" in source
    assert "15 category↔category plus 6 fg₀↔category" in source
    assert "terminal" in source and "finance" in source and "application" in source


def test_selection_is_null_and_allowlist_is_exact(monkeypatch) -> None:
    monkeypatch.setattr(
        report.browser,
        "_source_binding",
        lambda filename: {"file": filename, "sha256": "0" * 64, "commit": "0" * 40},
    )
    selection = report.selection_payload(synthetic_data())
    assert selection["selection"] is None
    assert selection["allowed_selections"] == ["NEW-A", "NEW-B", "NEW-C"]
    assert selection["automatic_recommendation"] is None
    assert selection["production_promotion"] is False
    assert selection["forbidden_commanded_oklch_hue_arc_closed"] == [92.0, 118.0]
    assert selection["total_unordered_pairs"] == 21


def test_contrast_rows_cover_all_seven_roles_and_four_states() -> None:
    inputs = report.seven.load_inputs(replay=False)
    rows = report.contrast_rows(
        ["#342F2C", "#70002D", "#B25809", "#6C8D38", "#016869", "#4081D2", "#84499C"],
        inputs,
    )
    assert len(rows) == 7
    assert [row["role"] for row in rows] == [
        "fg₀",
        "category-0",
        "category-1",
        "category-2",
        "category-3",
        "category-4",
        "category-5",
    ]
    assert all(set(row["commanded"]) == {"bg_0", "bg_1"} for row in rows)
    assert all(set(row["transformed"]) == {"bg_0", "bg_1"} for row in rows)


def test_phone_and_compact_desktop_breakpoints_are_encoded() -> None:
    source = (SEVEN / "forbidden_arc_report.py").read_text()
    assert "@media(max-width:1180px)" in source
    assert "@media(max-width:680px)" in source
    assert "overflow-x:hidden" in source
    assert "target_distance" not in source
    assert "Pink-relaxed" not in source


def test_committed_review_package_is_closed_when_present() -> None:
    if not REVIEW.is_dir():
        return
    assert {path.name for path in REVIEW.iterdir()} == {
        "evidence",
        "index.html",
        "report.md",
        "selection.json",
    }
    assert len(list((REVIEW / "evidence").iterdir())) == 22
