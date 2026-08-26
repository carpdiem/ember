from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
EXPERIMENT = ROOT / "docs/experiments/3400k-light-terminal-raster"


def load_script(name: str):
    path = EXPERIMENT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"terminal_raster_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_search_is_deterministic_and_freezes_nonterminal_system() -> None:
    search = load_script("search")
    recorded = json.loads((EXPERIMENT / "results.json").read_text())
    recomputed = search.run(recorded["seed"])

    assert recomputed == recorded
    assert recorded["source"] == {
        "commit": "016c6b37b283baf44711af3330d2872305b9398c",
        "manifest_sha256": "e7044ae9e629975df2db19ef0c472c74b99efb0ce0e56a46f862387a863f9f4c",
    }
    family = next(item for item in search.FAMILIES if item.slug == "3400k-light")
    assert recorded["frozen"]["surfaces"] == family.surfaces
    assert recorded["frozen"]["categorical"] == list(family.categorical_colors)
    assert recorded["frozen"]["sequential_anchors"] == list(family.sequential_anchors)
    assert recorded["contract"]["production_promotion_authorized"] is False
    assert recorded["contract"]["human_visibility_floor"] is None
    assert recorded["viewing_conditions"]["commanded"] == search.NORMAL_VIEW
    assert recorded["viewing_conditions"]["transformed"] == search.LOW_LIGHT_VIEW


def test_exactly_one_browser_eligible_human_review_candidate() -> None:
    results = json.loads((EXPERIMENT / "results.json").read_text())
    evidence = json.loads((EXPERIMENT / "browser-evidence.json").read_text())
    selection = json.loads((EXPERIMENT / "review/selection.json").read_text())

    assert len(results["finalists"]) == 3
    assert len({tuple(row["values"]) for row in results["finalists"]}) == 3
    statuses = {row["bank"]: row["status"] for row in evidence["acceptance"]}
    assert statuses == {
        "A-raster-maximum": "PASS",
        "B-photopic-balance": "FAIL",
        "C-low-churn-contrast": "FAIL",
    }
    assert selection["eligible_candidates"] == ["A-raster-maximum"]
    assert selection["selection"] is None
    assert selection["automatic_recommendation"] is None
    assert selection["production_promotion"] is False


def test_candidate_a_improves_target_glyphs_and_removes_nominal_near_tail() -> None:
    evidence = json.loads((EXPERIMENT / "browser-evidence.json").read_text())
    rows = evidence["role_aggregates"]

    def row(bank: str, state: str, dpr: int, role: str):
        return next(
            item
            for item in rows
            if item["bank"] == bank
            and item["state"] == state
            and item["dpr"] == dpr
            and item["role"] == role
        )

    for state in ("commanded-normal-light", "transformed-low-light"):
        for dpr in (1, 2):
            for role in ("red", "green", "blue"):
                current = row("current-light", state, dpr, role)
                candidate = row("A-raster-maximum", state, dpr, role)
                assert candidate["active_min_p10"] > current["active_min_p10"]
            for role in ("red", "green", "yellow", "blue", "magenta", "cyan"):
                current = row("current-light", state, dpr, role)
                candidate = row("A-raster-maximum", state, dpr, role)
                assert candidate["active_min_p10"] >= 0.85 * current["active_min_p10"]
                assert candidate["active_max_near_fraction"] == 0.0
                assert candidate["active_max_exact_fraction"] == 0.0


def test_review_page_is_complete_and_production_safe() -> None:
    page = (EXPERIMENT / "review/index.html").read_text()
    report = (EXPERIMENT / "review/report.md").read_text()

    assert "Commanded · normal daytime viewing" in page
    assert "Exact 3400K transform · low-light viewing" in page
    assert page.count("class='candidate ") == 5
    assert "A raster maximum" in page
    assert "Rejected by browser gate" in page
    assert "Production remains unchanged until Michael selects" in page
    assert "Only **A-raster-maximum** passes" in report
    for role in ("red", "green", "yellow", "blue", "magenta", "cyan"):
        assert f">{role}</th>" in page


def test_review_manifest_binds_every_artifact() -> None:
    manifest = json.loads((EXPERIMENT / "manifest.json").read_text())

    assert manifest["eligible_candidates"] == ["A-raster-maximum"]
    assert manifest["human_selection"] is None
    assert manifest["production_promotion"] is False
    for relative, expected in manifest["artifacts"].items():
        path = ROOT / relative
        assert path.is_file(), relative
        assert path.stat().st_size == expected["bytes"], relative
        assert oct(path.stat().st_mode & 0o777) == expected["mode"], relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"], relative
