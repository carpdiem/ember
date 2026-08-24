from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ember.generate import ANSI_NAMES, generate_manifest

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_RESULTS = (
    ROOT / "docs" / "experiments" / "dark-foreground-warmth" / "transformed-first-results.json"
)
DARK_SLUGS = ("3400k-dark", "2000k-dark", "1200k-dark")
ANSI_ACCENTS = ("red", "green", "yellow", "blue", "magenta", "cyan")


def approved_halfway() -> dict:
    return json.loads(EXPERIMENT_RESULTS.read_text(encoding="utf-8"))


def test_promoted_dark_families_equal_the_byte_frozen_approved_lanes() -> None:
    approved = approved_halfway()
    manifest = generate_manifest()

    for slug in DARK_SLUGS:
        lane = approved["profiles"][slug]["lanes"]["halfway"]
        family = manifest["families"][slug]
        unique = [lane["surfaces"][f"bg_{index}"] for index in range(lane["bg_count"])]
        expanded = [unique[index] for index in lane["background_role_alias_indices"]]

        assert family["background_surface_count"] == lane["bg_count"]
        assert family["background_surface_values"] == unique
        assert family["background_role_indices"] == lane["background_role_alias_indices"]
        assert [family["surfaces"][f"bg_{index}"] for index in range(6)] == expanded
        assert [family["surfaces"][f"fg_{index}"] for index in range(3)] == lane["foregrounds"]
        assert list(family["categorical"].values()) == lane["categorical"]
        assert (
            family["categorical_semantic_slots"]
            == lane["categorical_ordering"]["semantic_families"]
        )
        assert [
            family["terminal"][ANSI_ACCENTS[index]] for index in range(len(lane["terminal"]))
        ] == lane["terminal"]
        assert family["continuous_preview_anchors"] == lane["sequential_anchors"]
        assert family["continuous_source"] == "canonical_float_srgb"
        assert np.array_equal(
            np.asarray(family["continuous_rgb"]),
            np.asarray(lane["continuous_float_srgb"]),
        )


def test_promoted_manifest_exposes_usage_and_precision_contracts() -> None:
    manifest = generate_manifest()
    assert manifest["schema_version"] == 14
    usage = manifest["quality_targets"]["foreground_usage"]
    assert usage["opacity_derived_text_allowed"] is False
    assert usage["alpha_composited_foregrounds_allowed"] is False
    assert "not body text" in usage["fg_2"]

    expected_aliases = {
        "3400k-dark": [0, 1, 2, 3, 4, 4],
        "3400k-light": [0, 1, 2, 3, 4, 5],
        "2000k-dark": [0, 1, 1, 2, 3, 3],
        "1200k-dark": [0, 1, 1, 2, 3, 3],
    }
    for slug, indices in expected_aliases.items():
        family = manifest["families"][slug]
        assert family["background_role_indices"] == indices
        assert len(family["surfaces"]) == 9
        assert len(family["continuous_rgb"]) == 256
        assert list(family["terminal"]) == list(ANSI_NAMES)


def test_dark_cam16_release_metrics_match_the_approved_profile_policies() -> None:
    families = generate_manifest()["families"]
    limits = {
        "3400k-dark": {"nominal": 0.05, "grid": 0.10},
        "2000k-dark": {"nominal": 0.05, "grid": 0.10},
        "1200k-dark": {"nominal": 0.10, "grid": 0.17},
    }
    for slug, limit in limits.items():
        metrics = families[slug]["metrics"]["transformed_cam16_ucs"]
        assert metrics["continuous_delta_e_cv"] <= limit["nominal"]
        assert metrics["gain_grid_continuous_maximum_delta_e_cv"] <= limit["grid"]
        assert metrics["continuous_minimum_signed_j_step"] > 0.0
        assert metrics["gain_grid_continuous_minimum_signed_j_step"] > 0.0
        assert min(metrics["unique_surface_adjacent_distances"]) >= 2.5


def test_light_family_remains_the_independent_unchanged_reference() -> None:
    family = generate_manifest()["families"]["3400k-light"]
    assert family["surfaces"] == {
        "bg_0": "#F9F9F8",
        "bg_1": "#ECECEB",
        "bg_2": "#E0E0DD",
        "bg_3": "#D5D3D0",
        "bg_4": "#CAC7C3",
        "bg_5": "#BFBCB5",
        "fg_0": "#342F2C",
        "fg_1": "#4D4540",
        "fg_2": "#665C54",
    }
    assert family["continuous_source"] == "generated_from_hex8_anchors"
    assert family["categorical_semantic_slots"] is None
