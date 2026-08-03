from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from redshift_safe.color import (
    contrast_ratio,
    hex_to_srgb,
    pairwise_distances,
    perceived_lab,
    srgb_to_hex,
    warm_transform,
)
from redshift_safe.generate import generate_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_six_complete_families() -> None:
    manifest = generate_manifest()
    assert len(manifest["families"]) == 6
    assert {family["mode"] for family in manifest["families"].values()} == {"dark", "light"}
    assert {family["profile"] for family in manifest["families"].values()} == {
        "nightshift",
        "redshift",
        "safelight",
    }
    for family in manifest["families"].values():
        assert len(family["terminal"]) == 16
        assert len(family["categorical"]) == 8
        assert len(family["continuous_rgb"]) == 256
        assert len(family["continuous_hex8"]) == 256
        assert [srgb_to_hex(color) for color in family["continuous_rgb"]] == family[
            "continuous_hex8"
        ]
        assert len(family["surfaces"]) >= 7


def test_categorical_shifted_separation_and_lightness_budget() -> None:
    manifest = generate_manifest()
    for family in manifest["families"].values():
        profile = manifest["profiles"][family["profile"]]
        categories = np.asarray(
            [hex_to_srgb(color) for color in family["categorical"].values()]
        )
        shifted = perceived_lab(categories, profile["rgb_gains"])
        normal = perceived_lab(categories, (1.0, 1.0, 1.0))
        shifted_min = float(pairwise_distances(shifted).min())
        normal_min = float(pairwise_distances(normal).min())
        lightness_range = float(np.ptp(shifted[:, 0]))
        metrics = family["metrics"]["categorical"]
        assert shifted_min >= profile[
            "categorical_minimum_delta_e_ok_target"
        ], family["slug"]
        assert lightness_range <= 0.11, family["slug"]
        assert normal_min >= 8.0, family["slug"]
        assert metrics["shifted_min_delta_e_ok"] == round(shifted_min, 2)
        assert metrics["normal_min_delta_e_ok"] == round(normal_min, 2)
        assert metrics["shifted_lightness_range"] == round(lightness_range, 4)


def test_continuous_maps_are_monotonic_and_nearly_even_after_shift() -> None:
    manifest = generate_manifest()
    for family in manifest["families"].values():
        sequence = np.asarray(family["continuous_rgb"], dtype=float)
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        shifted = perceived_lab(sequence, gains)
        direction = 1.0 if shifted[-1, 0] >= shifted[0, 0] else -1.0
        lightness_steps = np.diff(shifted[:, 0]) * direction
        perceptual_steps = np.linalg.norm(np.diff(shifted, axis=0), axis=1) * 100.0
        cv = float(perceptual_steps.std() / perceptual_steps.mean())
        max_to_min = float(perceptual_steps.max() / perceptual_steps.min())
        metrics = family["metrics"]["continuous"]
        assert len({tuple(color) for color in sequence}) == 256, family["slug"]
        assert lightness_steps.min() > 0.0, family["slug"]
        assert np.ptp(shifted[:, 0]) >= 0.50, family["slug"]
        assert cv <= 0.08, family["slug"]
        assert max_to_min <= 1.60, family["slug"]
        assert metrics["minimum_signed_lightness_step"] == round(float(lightness_steps.min()), 6)
        assert metrics["delta_e_ok_cv"] == round(cv, 4)
        assert metrics["delta_e_ok_max_to_min"] == round(max_to_min, 3)


def test_primary_text_contrast_survives_profile() -> None:
    manifest = generate_manifest()
    for family in manifest["families"].values():
        contrasts = family["metrics"]["shifted_text_contrast"]
        primary = [value for key, value in contrasts.items() if key.startswith("foreground_on_")]
        assert min(primary) >= 4.5, family["slug"]
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        foreground = warm_transform(hex_to_srgb(family["surfaces"]["foreground"]), gains)
        selection = warm_transform(hex_to_srgb(family["surfaces"]["selection"]), gains)
        assert contrast_ratio(foreground, selection) >= 4.5, family["slug"]


def test_terminal_foregrounds_remain_visible_after_shift() -> None:
    manifest = generate_manifest()
    for family in manifest["families"].values():
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        background = warm_transform(hex_to_srgb(family["surfaces"]["background"]), gains)
        transformed = {
            name: warm_transform(hex_to_srgb(value), gains)
            for name, value in family["terminal"].items()
        }
        visible_slots = {
            name: value for name, value in transformed.items() if name != "black"
        }
        assert min(contrast_ratio(value, background) for value in visible_slots.values()) >= 3.0
        if family["mode"] == "light":
            assert contrast_ratio(transformed["black"], background) >= 4.5


def test_hex_round_trip_is_stable() -> None:
    for value in ("#000000", "#123456", "#ABCDEF", "#FFFFFF"):
        assert srgb_to_hex(hex_to_srgb(value)) == value


def test_committed_manifest_matches_generator() -> None:
    expected = generate_manifest()
    actual = json.loads((ROOT / "palettes/redshift-safe-palettes.json").read_text())
    packaged = json.loads((ROOT / "src/redshift_safe/palettes.json").read_text())
    assert actual == expected
    assert packaged == expected


def test_readme_local_links_exist() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    local_targets = [
        target
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text)
        if "://" not in target and not target.startswith("#")
    ]
    assert local_targets
    assert not [target for target in local_targets if not (ROOT / target).exists()]
