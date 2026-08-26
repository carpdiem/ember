from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
EXPERIMENT = ROOT / "docs/experiments/3400k-light-terminal-raster"
CAPTURE_RUNTIME = {
    "python": (3, 11),
    "colour": "0.4.7",
    "numpy": "2.4.6",
}
NUMERIC_TOLERANCE = 1e-9


def load_script(name: str):
    path = EXPERIMENT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"terminal_raster_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_identity(payload: dict) -> dict:
    return {
        "schema_version": payload["schema_version"],
        "artifact_kind": payload["artifact_kind"],
        "source": payload["source"],
        "frozen": payload["frozen"],
        "viewing_conditions": payload["viewing_conditions"],
        "contract": payload["contract"],
        "baseline_values": payload["baseline"]["values"],
        "catalog_counts": payload["catalog_counts"],
        "seed": payload["seed"],
        "combination_budget": payload["combination_budget"],
        "finalists": [
            {"id": finalist["id"], "values": finalist["values"]}
            for finalist in payload["finalists"]
        ],
    }


def assert_semantically_equal(actual, expected, path: str = "$") -> None:
    assert type(actual) is type(expected), f"{path}: type changed"
    if isinstance(expected, dict):
        assert set(actual) == set(expected), f"{path}: object structure changed"
        for key in expected:
            assert_semantically_equal(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert len(actual) == len(expected), f"{path}: list count changed"
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected, strict=True)):
            assert_semantically_equal(actual_item, expected_item, f"{path}[{index}]")
    elif isinstance(expected, float):
        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=NUMERIC_TOLERANCE), (
            f"{path}: numeric drift {actual!r} != {expected!r}"
        )
    else:
        assert actual == expected, f"{path}: exact value changed"


def capture_runtime_matches(search) -> bool:
    return (
        sys.version_info[:2] == CAPTURE_RUNTIME["python"]
        and search.colour.__version__ == CAPTURE_RUNTIME["colour"]
        and search.np.__version__ == CAPTURE_RUNTIME["numpy"]
    )


def test_search_is_deterministic_and_freezes_nonterminal_system() -> None:
    search = load_script("search")
    recorded = json.loads((EXPERIMENT / "results.json").read_text())
    recomputed = search.run(recorded["seed"])

    recorded_without_hash = {
        key: value for key, value in recorded.items() if key != "payload_sha256"
    }
    recomputed_without_hash = {
        key: value for key, value in recomputed.items() if key != "payload_sha256"
    }
    assert recorded["payload_sha256"] == search.sha256_json(recorded_without_hash)
    assert search.sha256_json(canonical_identity(recomputed)) == search.sha256_json(
        canonical_identity(recorded)
    )
    if capture_runtime_matches(search):
        assert recomputed == recorded
    else:
        assert_semantically_equal(recomputed_without_hash, recorded_without_hash)
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


def test_semantic_comparator_accepts_only_sub_tolerance_numeric_drift() -> None:
    recorded = json.loads((EXPERIMENT / "results.json").read_text())
    drifted = deepcopy(recorded)
    drifted["baseline"]["normal_cam_pair"] += NUMERIC_TOLERANCE / 2
    del drifted["payload_sha256"]
    expected = {key: value for key, value in recorded.items() if key != "payload_sha256"}

    assert_semantically_equal(drifted, expected)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload["finalists"][0]["values"].__setitem__(0, "#980750"),
        lambda payload: payload["finalists"][0].__setitem__("id", "A-renamed"),
        lambda payload: payload["finalists"].reverse(),
        lambda payload: payload["finalists"].pop(),
        lambda payload: payload["baseline"].__setitem__(
            "normal_cam_pair", payload["baseline"]["normal_cam_pair"] + NUMERIC_TOLERANCE * 2
        ),
    ),
    ids=("hex", "candidate-id", "order", "count", "material-float"),
)
def test_semantic_comparator_rejects_identity_or_material_numeric_change(mutation) -> None:
    recorded = json.loads((EXPERIMENT / "results.json").read_text())
    changed = deepcopy(recorded)
    mutation(changed)
    del changed["payload_sha256"]
    expected = {key: value for key, value in recorded.items() if key != "payload_sha256"}

    with pytest.raises(AssertionError):
        assert_semantically_equal(changed, expected)


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
