from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEVEN = ROOT / "docs/experiments/3400k-light-thin-marks/seven-point"
SPEC = importlib.util.spec_from_file_location(
    "warm_pair_report_test", SEVEN / "warm_pair_report.py"
)
assert SPEC is not None and SPEC.loader is not None
report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = report
SPEC.loader.exec_module(report)


def _row(role: str, compliance: str = "FULL_3_0") -> dict:
    bank = ["#342F2C", "#82251A", "#8B7A2B", "#0A6109", "#2B8CAD", "#5D53AE", "#B34B71"]
    return {
        "role": role,
        "label": report.LABELS[role],
        "candidate_id": role * 64,
        "bank": bank,
        "transformed_bank": bank,
        "compliance": compliance,
        "warm_red": bank[1],
        "warm_gold": bank[2],
        "hard_gate_failures": [],
        "contrast": {
            warm_role: {
                state: {
                    "bg_0": 3.2,
                    "bg_1": 2.75
                    if compliance != "FULL_3_0"
                    and warm_role == "warm_gold"
                    and state == "transformed"
                    else 3.1,
                }
                for state in ("commanded", "transformed")
            }
            for warm_role in ("warm_red", "warm_gold")
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
        "rows": {
            "reference": _row("reference"),
            "benchmark-c": _row("benchmark-c"),
            "a": _row("a"),
            "b": _row("b"),
            "c": _row("c", "TRANSFORMED_BG1_2_7_EXCEPTION"),
        }
    }


def test_page_frames_human_complaint_and_photopic_exception_honestly() -> None:
    page = report.build_html(_data())
    assert "ugly as sin" in page
    assert "Human taste—not scalar optimization" in page
    assert page.count('class="variant ') == 5
    assert "2.7 challenge · not PASS" in page
    assert "not an automatic recommendation" in page
    assert "No 2.5 lane was generated" in page
    assert "overflow:visible" in page
    assert "@media(max-width:1100px)" in page
    assert "@media(max-width:680px)" in page


def test_selection_has_no_automatic_recommendation(monkeypatch) -> None:
    monkeypatch.setattr(
        report.browser,
        "_source_binding",
        lambda filename: {"file": filename, "sha256": "0" * 64, "commit": "1" * 40},
    )
    payload = report.selection_payload(_data())
    assert payload["status"] == "AWAITING_MICHAEL_WARM_PAIR_SELECTION"
    assert payload["selection"] is None
    assert payload["allowed_selections"] == [
        "KEEP-A",
        "LIFT-ONLY",
        "CLEAN-GOLD",
        "BRIGHT-WARM",
        "PHOTOPIC-2.7",
    ]
    assert payload["automatic_recommendation"] is None
    assert payload["photopic_lane_status"] == "HUMAN_CHALLENGE_NOT_PASS"
    assert payload["production_promotion"] is False


def test_contrast_table_shows_all_four_commanded_and_transformed_contexts() -> None:
    table = report.contrast_table(_row("a"))
    assert "Cmd bg0" in table and "Cmd bg1" in table
    assert "3400K bg0" in table and "3400K bg1" in table
    assert "Warm red" in table and "Gold / olive" in table


def test_source_is_narrow_and_environment_free() -> None:
    source = (SEVEN / "warm_pair_report.py").read_text()
    assert "/Users/" not in source
    assert "timestamp" not in source.lower()
    assert "2.5 lane" in source
    assert report.EXPECTED_EVIDENCE_COUNT == 22
