from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "docs/experiments/3400k-light-thin-marks"
CLEAN_SHEET = EXPERIMENT / "clean-sheet"
REVIEW = EXPERIMENT / "review/g2-clean-sheet"
EVIDENCE = REVIEW / "evidence"
sys.path[:0] = [str(CLEAN_SHEET), str(EXPERIMENT)]

import optimizer as clean
import report

EXPECTED_GATED = {
    "REFERENCE": {
        "categorical": [8.45061119, 11.72933559, 12.07960554],
        "category_fg_0": [5.34772026, 8.46730718, 8.75274293],
    },
    "A": {
        "categorical": [10.71459562, 14.72111734, 15.42553568],
        "category_fg_0": [6.19576033, 8.29851824, 8.34771635],
    },
    "B": {
        "categorical": [10.32223006, 13.85554683, 14.23648775],
        "category_fg_0": [6.69063841, 8.29851824, 8.34771635],
    },
    "C": {
        "categorical": [10.15168599, 13.29463249, 13.58450059],
        "category_fg_0": [7.30273837, 9.19528305, 9.41748066],
    },
}


@pytest.fixture(scope="module")
def rows(tmp_path_factory):
    if sys.version_info[:2] == (3, 10):
        pytest.skip(
            "the committed exact search artifact is bound to the Python 3.11+ optimizer runtime"
        )
    if sys.platform != "darwin":
        inputs = clean.p3.load_inputs(EXPERIMENT)
        clean.p3._REPLAY_CACHE.add(clean.p3.input_chain_sha256(inputs))
    search = tmp_path_factory.mktemp("clean-sheet-search")
    for name in report.SEARCH_FILES:
        shutil.copyfile(EVIDENCE / name, search / name)
    value, _ = report._collect(search, EVIDENCE, EVIDENCE)
    return value


def test_exact_evidence_closure_and_sizes() -> None:
    assert {path.name for path in EVIDENCE.iterdir()} == set(report.EVIDENCE_FILES)
    assert len(report.EVIDENCE_FILES) == 19
    assert len(report.SEARCH_FILES) == 3
    assert len(report.REQUEST_FILES) == 4
    assert len(report.BROWSER_FILES) == 12
    assert all(path.is_file() and path.stat().st_size < 50_000_000 for path in EVIDENCE.iterdir())


def test_exact_metric_derivation_uses_gated_backgrounds_and_separates_bg2(rows) -> None:
    for role, families in EXPECTED_GATED.items():
        for family, expected in families.items():
            actual = [
                rows[role]["browser"][family][width]["gated"]["observed_delta_e_ok"]
                for width in report.WIDTHS
            ]
            assert actual == expected
            assert all(
                rows[role]["browser"][family][width]["gated"]["background"]
                in report.GATED_BACKGROUNDS
                for width in report.WIDTHS
            )
            assert all(
                rows[role]["browser"][family][width]["bg_2_report_only"]["background"] == "bg_2"
                for width in report.WIDTHS
            )


def test_recommendation_c_is_derived_from_all_width_fg0_gains(rows) -> None:
    baseline = EXPECTED_GATED["REFERENCE"]["category_fg_0"]
    c = EXPECTED_GATED["C"]["category_fg_0"]
    assert all(candidate > reference for candidate, reference in zip(c, baseline, strict=True))
    for role in ("A", "B"):
        values = EXPECTED_GATED[role]["category_fg_0"]
        assert values[0] > baseline[0]
        assert values[1] < baseline[1]
        assert values[2] < baseline[2]
    c_category_gain = (
        rows["C"]["browser"]["categorical"]["1.5"]["gated"]["observed_delta_e_ok"]
        - rows["REFERENCE"]["browser"]["categorical"]["1.5"]["gated"]["observed_delta_e_ok"]
    )
    assert round(c_category_gain, 2) == 1.70


def test_deterministic_byte_identical_report_regeneration(rows) -> None:
    inputs = clean.load_authorized_inputs(EXPERIMENT, replay=False)
    first_html = report._render_html(rows, inputs).encode()
    second_html = report._render_html(rows, inputs).encode()
    first_md = report._render_markdown(rows).encode()
    second_md = report._render_markdown(rows).encode()
    first_selection = (
        json.dumps(report._selection(rows), indent=2, sort_keys=True) + "\n"
    ).encode()
    second_selection = (
        json.dumps(report._selection(rows), indent=2, sort_keys=True) + "\n"
    ).encode()
    assert first_html == second_html == (REVIEW / "index.html").read_bytes()
    assert first_md == second_md == (REVIEW / "report.md").read_bytes()
    assert first_selection == second_selection == (REVIEW / "selection.json").read_bytes()


def test_required_page_structures_rows_and_complete_simultaneous_cards() -> None:
    page = (REVIEW / "index.html").read_text()
    assert 'class="comparison-grid"' in page
    assert [
        page.count(f'id="candidate-{role.lower()}" data-candidate="{role}"')
        for role in report.ROLES
    ] == [1, 1, 1, 1]
    assert page.count('data-review-state="commanded"') == 4
    assert page.count('data-review-state="exact transformed"') == 4
    assert page.count('data-width="1.5"') == 8
    assert page.count('data-width="2"') == 8
    for structure in (
        "weakest-three-failure-analog",
        "luminance-only-strip",
        "category-fg0-nearest-binding",
        "fake-finance-baskets",
        "worst-sensitivity",
        "gated-browser-minima",
    ):
        assert page.count(f'data-specimen="{structure}"') == (
            0 if structure == "gated-browser-minima" else 4
        )
    assert 'data-table="gated-browser-minima"' in page
    assert "Constructive cool-lighter / warm-darker" in page
    assert "Transformed-native targets inverted through exact gains" in page
    assert "Continuity compromise with zero-to-two broad anchors" in page
    assert "Recommendation: C. Michael decides." in page
    assert "carousel" in page.lower() and "nested horizontal scroller" in page.lower()
    assert "30,240" in page and "58,320" in page


def test_status_null_unknown_and_no_promotion() -> None:
    selection = json.loads((REVIEW / "selection.json").read_text())
    assert selection == {
        "allowed": ["A", "B", "C"],
        "candidate_ids": selection["candidate_ids"],
        "human_1_5px_capacity": "UNKNOWN",
        "production_promotion_authorized": False,
        "recommendation": "C",
        "schema_version": 1,
        "selection": None,
        "status": "AWAITING_MICHAEL_SELECTION",
    }
    assert set(selection["candidate_ids"]) == {"A", "B", "C"}


def test_no_overflow_prone_nested_scroll_contract_and_all_links_resolve() -> None:
    page = (REVIEW / "index.html").read_text()
    assert "overflow:auto" not in page.replace(" ", "").lower()
    assert "overflow-x:auto" not in page.replace(" ", "").lower()
    assert "overflow:scroll" not in page.replace(" ", "").lower()
    links = re.findall(r'href="([^"]+)"', page)
    assert len(links) == len(report.EVIDENCE_FILES)
    assert all((REVIEW / link).is_file() for link in links)


def test_no_paths_timestamps_secrets_screenshots_or_full_image_hash_payloads() -> None:
    for path in [
        REVIEW / "index.html",
        REVIEW / "report.md",
        REVIEW / "selection.json",
        *EVIDENCE.iterdir(),
    ]:
        text = path.read_text(errors="strict")
        assert "/Users/" not in text and "/tmp/" not in text
        assert not re.search(r'"timestamp(?:_utc)?"\s*:', text, re.IGNORECASE)
        assert not re.search(r'"(?:secret|password|token)"\s*:', text, re.IGNORECASE)
        assert "raw_screenshot" not in text.lower()
        assert "full_image_sha256" not in text.lower()
    assert not [
        path for path in REVIEW.rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ]


@pytest.mark.parametrize("flags", [[], ["-O"]], ids=["normal", "optimized"])
def test_explicit_integrity_failure_survives_python_optimization(flags: list[str]) -> None:
    script = f"""
import sys
sys.path[:0] = [{str(CLEAN_SHEET)!r}, {str(EXPERIMENT)!r}]
import report
report.require(False, 'synthetic report corruption')
"""
    completed = subprocess.run(
        [sys.executable, *flags, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "synthetic report corruption" in completed.stderr


def test_source_has_explicit_output_only_and_no_history_or_production_mutators() -> None:
    source = (CLEAN_SHEET / "report.py").read_text()
    assert 'parser.add_argument("--output-dir", type=Path, required=True)' in source
    assert "datetime" not in source and "timestamp" not in source.lower()
    assert "git checkout" not in source and "git reset" not in source
    assert "subprocess.run" not in source
    assert 'promotion_authorized": False' in source
