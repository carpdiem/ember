from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from ember.color import hex_to_srgb, pairwise_distances, srgb_to_oklab
from ember.definitions import FAMILIES
from ember.generate import generate_manifest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/verify_categorical_assignment.py"
PROVENANCE = ROOT / "docs/provenance/3400k-light-forbidden-arc-new-a.json"
SPEC = importlib.util.spec_from_file_location("categorical_assignment_test", TOOL)
assert SPEC is not None and SPEC.loader is not None
assignment = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = assignment
SPEC.loader.exec_module(assignment)


def test_all_720_assignments_prove_unique_global_optimum() -> None:
    rows = assignment.enumerate_assignments()
    assert len(rows) == 720
    assert len({tuple(row["old_indices_one_based"]) for row in rows}) == 720
    assert rows[0]["old_indices_one_based"] == [2, 5, 6, 3, 4, 1]
    assert rows[0]["total_delta_e_ok"] == pytest.approx(179.1181628675322, abs=1e-12)
    assert rows[0]["maximum_hue_mismatch_degrees"] == pytest.approx(41.75643047766084, abs=1e-12)
    assert rows[0]["total_delta_e_ok"] < rows[1]["total_delta_e_ok"]


def test_michael_proposed_assignment_is_second_but_has_large_hue_mismatch() -> None:
    proof = assignment.proof()
    assert proof["production_rank"] == 1
    assert proof["proposed_rank"] == 2
    assert proof["proposed"]["old_indices_one_based"] == [2, 5, 1, 3, 4, 6]
    assert proof["proposed"]["total_delta_e_ok"] == pytest.approx(193.0567155023287, abs=1e-12)
    assert proof["proposed"]["maximum_hue_mismatch_degrees"] == pytest.approx(
        93.90311495838131, abs=1e-12
    )


def test_canonical_light_order_is_exact_optimal_source_mapping() -> None:
    families = {family.slug: family for family in FAMILIES}
    light = families["3400k-light"]
    mapping = [index - 1 for index in assignment.PRODUCTION_OLD_INDICES_ONE_BASED]
    expected_commanded = [assignment.SOURCE_HUE_ORDER_COMMANDED[index] for index in mapping]
    expected_transformed = [assignment.SOURCE_HUE_ORDER_TRANSFORMED[index] for index in mapping]
    assert list(light.categorical_colors) == expected_commanded
    assert list(light.categorical_transformed_targets) == expected_transformed
    assert light.categorical_colors[2] == "#84499C"
    assert light.categorical_colors[5] == "#70002D"
    assert families["3400k-dark"].categorical_colors[2] == "#C7779E"
    assert families["3400k-dark"].categorical_colors[5] == "#915E42"


def test_unordered_bank_wide_oklab_geometry_is_permutation_invariant() -> None:
    light = next(family for family in FAMILIES if family.slug == "3400k-light")
    for source, production in (
        (assignment.SOURCE_HUE_ORDER_COMMANDED, light.categorical_colors),
        (assignment.SOURCE_HUE_ORDER_TRANSFORMED, light.categorical_transformed_targets),
    ):
        source_lab = srgb_to_oklab(np.asarray([hex_to_srgb(value) for value in source]))
        production_lab = srgb_to_oklab(np.asarray([hex_to_srgb(value) for value in production]))
        assert sorted(source) == sorted(production)
        assert np.allclose(
            np.sort(pairwise_distances(source_lab)),
            np.sort(pairwise_distances(production_lab)),
            rtol=0.0,
            atol=1e-15,
        )


def test_prefix_quality_floors_preserve_first_two_and_bound_first_three_tradeoff() -> None:
    record = json.loads(PROVENANCE.read_text())
    prefix = record["source_review_actual_browser_prefix_quality"]
    first_two = prefix["first_two_production_minima"]
    first_three = prefix["first_three_production_minima"]
    floors = prefix["first_three_production_floors"]
    proposed = prefix["first_three_michael_proposed_minima"]
    assert first_two == [13.08638167, 19.60330802, 20.93652811]
    assert all(actual >= floor for actual, floor in zip(first_three, floors, strict=True))
    assert prefix["production_first_three_sum_delta_e_ok"] == pytest.approx(
        sum(first_three), abs=1e-8
    )
    assert prefix["michael_proposed_first_three_sum_delta_e_ok"] == pytest.approx(
        sum(proposed), abs=1e-8
    )
    assert prefix["production_prefix_sum_tradeoff_delta_e_ok"] == pytest.approx(
        sum(proposed) - sum(first_three), abs=1e-8
    )
    assert prefix["production_prefix_sum_tradeoff_delta_e_ok"] < 0.385


def test_manifest_slots_preserve_same_series_identity_across_3400k_themes() -> None:
    manifest = generate_manifest()["families"]
    dark = list(manifest["3400k-dark"]["categorical"].values())
    light = list(manifest["3400k-light"]["categorical"].values())
    assert list(zip(dark, light, strict=True)) == [
        ("#DEA460", "#B25809"),
        ("#6BA0DE", "#4081D2"),
        ("#C7779E", "#84499C"),
        ("#71CFA5", "#6C8D38"),
        ("#2B8B7F", "#016869"),
        ("#915E42", "#70002D"),
    ]


def test_live_sparklines_bind_stable_series_index_to_category_slot() -> None:
    landing = (ROOT / "index.html").read_text()
    assert 'var SPARK_LABELS = ["DET-A 512nm", "DET-B 640nm", "DET-C 760nm"' in landing
    assert (
        '"--ember-category-one", "--ember-category-two", "--ember-category-three",\n'
        '    "--ember-category-four", "--ember-category-five", "--ember-category-six"' in landing
    )
    assert "lab.textContent = SPARK_LABELS[s];" in landing
    assert 'line.style.stroke = "var(" + CAT_VARS[s] + ")";' in landing
