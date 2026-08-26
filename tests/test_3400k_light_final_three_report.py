from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEVEN = ROOT / "docs/experiments/3400k-light-thin-marks/seven-point"
SPEC = importlib.util.spec_from_file_location(
    "final_three_report_test", SEVEN / "final_three_report.py"
)
assert SPEC is not None and SPEC.loader is not None
report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = report
SPEC.loader.exec_module(report)


def _row(role: str, value: float) -> dict:
    bank = ["#342F2C", "#790C1A", "#91772A", "#0A6109", "#2B8CAD", "#5D53AE", "#AC507C"]
    binding = {
        "roles": ["category-1", "category-5"],
        "delta_e_ok": value,
        "background": "bg_0",
        "pair_id": "x",
    }
    return {
        "role": role,
        "label": report.LABELS[role],
        "change_copy": report.CHANGE_COPY[role],
        "candidate_id": role * 64,
        "bank": bank,
        "transformed_bank": bank,
        "oklch": [[0.4, 0.1, 30.0] for _ in bank],
        "transformed_oklch": [[0.35, 0.09, 28.0] for _ in bank],
        "contrast": [
            {
                "role": f"category-{index}",
                "hex8": value,
                "commanded": {"bg_0": 3.4, "bg_1": 3.1},
                "transformed": {"bg_0": 3.3, "bg_1": 3.05},
            }
            for index, value in enumerate(bank[1:])
        ],
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
    return {
        "rows": {
            "reference": _row("reference", 9.484),
            "benchmark-c": _row("benchmark-c", 9.137),
            "a": _row("a", 7.725),
        }
    }


def test_page_is_three_way_visual_identity_board() -> None:
    page = report.build_html(_data())
    assert page.count('class="option"') == 3
    assert "Three complete palette identities." in page
    assert "Full commanded identity" in page
    assert "Exact 3400K identity" in page
    assert page.count('class="finance"') == 3
    assert page.count('class="terminal"') == 6
    assert page.count('class="application"') == 6
    assert "Automatic recommendation: NONE" in page
    assert "Original A 9.484" in page
    assert "Fixed-four yellow 9.137" in page
    assert "Pink-relaxed golden 7.725" in page
    assert "prior clean-sheet C at 7.303" in page


def test_role_change_copy_is_explicit() -> None:
    page = report.build_html(_data())
    assert "Changes only the two warm roles" in page
    assert "Changes three roles: warm red, golden hue-family color, and pink" in page
    assert "Green, teal, and blue-violet remain exact" in page


def test_selection_is_closed_and_has_no_recommendation(monkeypatch) -> None:
    monkeypatch.setattr(
        report.browser,
        "_source_binding",
        lambda filename: {"file": filename, "sha256": "0" * 64, "commit": "1" * 40},
    )
    payload = report.selection_payload(_data())
    assert payload["status"] == "AWAITING_MICHAEL_FINAL_THREE_SELECTION"
    assert payload["selection"] is None
    assert payload["allowed_selections"] == [
        "ORIGINAL-A",
        "FIXED-FOUR-YELLOW",
        "PINK-RELAXED-GOLDEN",
    ]
    assert payload["automatic_recommendation"] is None
    assert payload["production_promotion"] is False


def test_all_exact_identity_and_contrast_channels_are_present() -> None:
    row = _row("a", 7.725)
    identity = report.identity_table(row)
    contrast = report.contrast_table(row)
    assert "Commanded" in identity and "3400K" in identity
    assert "Oklch L/C/h" in identity and "3400K Oklch" in identity
    assert "category-0" in contrast and "category-1" in contrast and "category-5" in contrast
    assert "Cmd bg0" in contrast and "3400K bg1" in contrast


def test_source_is_narrow_responsive_and_environment_free() -> None:
    source = (SEVEN / "final_three_report.py").read_text()
    assert "/Users/" not in source
    assert "timestamp" not in source.lower()
    assert "@media(max-width:1180px)" in source
    assert "@media(max-width:680px)" in source
    assert report.EXPECTED_EVIDENCE_COUNT == 14
