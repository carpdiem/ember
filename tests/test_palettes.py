from __future__ import annotations

import json
import re
from itertools import pairwise
from pathlib import Path

import numpy as np

from redshift_safe.color import (
    contrast_ratio,
    delta_e_ok,
    hex_to_srgb,
    pairwise_distances,
    perceived_lab,
    srgb_to_hex,
    srgb_to_oklab,
    warm_transform,
    wcag_luminance,
)
from redshift_safe.generate import generate_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_honest_temperature_families() -> None:
    manifest = generate_manifest()
    assert manifest["schema_version"] == 6
    assert list(manifest["families"]) == [
        "3400k-dark",
        "3400k-light",
        "2000k-dark",
        "1200k-dark",
    ]
    assert {family["mode"] for family in manifest["families"].values()} == {"dark", "light"}
    assert {family["profile"] for family in manifest["families"].values()} == {
        "3400k",
        "2000k",
        "1200k",
    }
    assert [len(family["categorical"]) for family in manifest["families"].values()] == [
        6,
        6,
        4,
        3,
    ]
    assert [
        family["terminal_semantic_color_count"] for family in manifest["families"].values()
    ] == [6, 6, 4, 3]
    assert [
        family["terminal_daylight_color_count"] for family in manifest["families"].values()
    ] == [6, 6, 4, 3]
    for family in manifest["families"].values():
        assert len(family["terminal"]) == 16
        assert len(family["continuous_rgb"]) == 256
        assert len(family["continuous_hex8"]) == 256
        assert [srgb_to_hex(color) for color in family["continuous_rgb"]] == family[
            "continuous_hex8"
        ]
        assert len(family["surfaces"]) == 9


def test_numbered_surface_roles_have_locked_values() -> None:
    manifest = generate_manifest()
    roles = ["bg_0", "bg_1", "bg_2", "bg_3", "bg_4", "bg_5"]
    assert manifest["quality_targets"]["bg_roles_low_to_high"] == roles
    expected = {
        "3400k-dark": ["#090807", "#100E0C", "#181612", "#201D19", "#29251F", "#32241B"],
        "3400k-light": ["#FFF7D6", "#F4EAC7", "#E9DCB9", "#DFCFAA", "#D4C29C", "#C9B796"],
        "2000k-dark": ["#070504", "#0D0A09", "#15110E", "#1E1814", "#271F1B", "#30221B"],
        "1200k-dark": ["#060302", "#0C0806", "#130E0B", "#1C1511", "#251C17", "#2E1E17"],
    }
    expected_foregrounds = {
        "3400k-dark": ["#DDD0B2", "#BDAE93", "#928374"],
        "3400k-light": ["#342F2C", "#504945", "#665C54"],
        "2000k-dark": ["#E9D3AD", "#C8B38F", "#9F8B70"],
        "1200k-dark": ["#FFE5BE", "#CBB58F", "#A28B70"],
    }
    for slug, values in expected.items():
        surfaces = manifest["families"][slug]["surfaces"]
        assert [surfaces[role] for role in roles] == values
        assert [surfaces[role] for role in ("fg_0", "fg_1", "fg_2")] == expected_foregrounds[slug]
        assert not set(surfaces) & set(manifest["legacy_surface_role_aliases"])


def test_deep_accent_selections_have_locked_two_stage_values() -> None:
    manifest = generate_manifest()
    expected = {
        "2000k-dark": {
            "categorical": ["#E6C682", "#A07928", "#749DE1", "#CB8991"],
            "categorical_transformed_targets": ["#E66C0B", "#A04203", "#745514", "#CB4A0D"],
            "terminal": ["#EE8B98", "#A4EBA5", "#FECE75", "#C9C7F2"],
            "terminal_transformed_targets": ["#EE4C0D", "#A4800E", "#FE700A", "#C96C15"],
            "terminal_ansi_indices": [0, 1, 2, 3, 0, 1],
        },
        "1200k-dark": {
            "categorical": ["#E0C47A", "#B7A7F3", "#8F8A33"],
            "categorical_transformed_targets": ["#E03D00", "#B73400", "#8F2B00"],
            "terminal": ["#F494B4", "#E2F495", "#FFE4C6"],
            "terminal_transformed_targets": ["#F42E00", "#E24B00", "#FF4700"],
            "terminal_ansi_indices": [0, 1, 2, 2, 0, 1],
        },
    }
    semantic_names = ("red", "green", "yellow", "blue", "magenta", "cyan")
    for slug, values in expected.items():
        family = manifest["families"][slug]
        assert list(family["categorical"].values()) == values["categorical"]
        assert (
            family["categorical_transformed_targets"] == values["categorical_transformed_targets"]
        )
        count = family["terminal_daylight_color_count"]
        assert [family["terminal"][name] for name in semantic_names[:count]] == values["terminal"]
        assert family["terminal_transformed_targets"] == values["terminal_transformed_targets"]
        assert family["terminal_ansi_indices"] == values["terminal_ansi_indices"]
        assert [family["terminal"][name] for name in semantic_names] == [
            values["terminal"][index] for index in values["terminal_ansi_indices"]
        ]


def test_terminal_ansi_roles_have_semantic_commanded_hues() -> None:
    manifest = generate_manifest()
    semantic_names = ("red", "green", "yellow", "blue", "magenta", "cyan")
    expected = {
        "3400k-dark": ["#F5AD9A", "#9ABEA2", "#CEA866", "#B4C6F7", "#D895C2", "#70DBD8"],
        "3400k-light": ["#470D05", "#174213", "#745C08", "#162252", "#643563", "#00766E"],
        "2000k-dark": ["#EE8B98", "#A4EBA5", "#FECE75", "#C9C7F2", "#EE8B98", "#A4EBA5"],
        "1200k-dark": ["#F494B4", "#E2F495", "#FFE4C6", "#FFE4C6", "#F494B4", "#E2F495"],
    }
    hue_centers = {
        "red": 20.0,
        "green": 140.0,
        "yellow": 82.0,
        "blue": 275.0,
        "magenta": 335.0,
        "cyan": 185.0,
    }

    for slug, values in expected.items():
        family = manifest["families"][slug]
        assert [family["terminal"][name] for name in semantic_names] == values
        authored_count = family["terminal_daylight_color_count"]
        for role in semantic_names[:authored_count]:
            lab = srgb_to_oklab(hex_to_srgb(family["terminal"][role]))
            hue = float(np.degrees(np.arctan2(lab[2], lab[1])) % 360.0)
            hue_error = abs((hue - hue_centers[role] + 180.0) % 360.0 - 180.0)
            assert hue_error <= 30.0, (slug, role, hue)


def test_categorical_bi_state_separation_and_commanded_chroma_budget() -> None:
    manifest = generate_manifest()
    for family in manifest["families"].values():
        profile = manifest["profiles"][family["profile"]]
        categories = np.asarray([hex_to_srgb(color) for color in family["categorical"].values()])
        shifted = perceived_lab(categories, profile["rgb_gains"])
        transformed_targets = perceived_lab(
            np.asarray([hex_to_srgb(color) for color in family["categorical_transformed_targets"]]),
            (1.0, 1.0, 1.0),
        )
        normal = perceived_lab(categories, (1.0, 1.0, 1.0))
        shifted_min = float(pairwise_distances(shifted).min())
        normal_min = float(pairwise_distances(normal).min())
        lightness_range = float(np.ptp(shifted[:, 0]))
        normal_chroma_max = float(np.linalg.norm(normal[:, 1:], axis=1).max())
        normal_chroma_mean = float(np.linalg.norm(normal[:, 1:], axis=1).mean())
        target_error = float(np.linalg.norm(shifted - transformed_targets, axis=1).max() * 100.0)
        metrics = family["metrics"]["categorical"]
        assert shifted_min >= profile["categorical_minimum_delta_e_ok_target"], family["slug"]
        assert normal_chroma_max <= 0.111, family["slug"]
        assert 0.09 <= normal_chroma_mean <= 0.105, family["slug"]
        assert normal_min >= family["daylight_minimum_delta_e_ok_target"], family["slug"]
        assert metrics["shifted_min_delta_e_ok"] == round(shifted_min, 2)
        assert metrics["normal_min_delta_e_ok"] == round(normal_min, 2)
        assert metrics["shifted_lightness_range"] == round(lightness_range, 4)
        assert metrics["normal_chroma_max"] == round(normal_chroma_max, 4)
        assert metrics["normal_chroma_mean"] == round(normal_chroma_mean, 4)
        assert target_error <= 0.15, family["slug"]
        assert metrics["transformed_target_max_delta_e_ok"] == round(target_error, 2)


def test_continuous_maps_are_monotonic_in_both_states_and_nearly_even_after_shift() -> None:
    manifest = generate_manifest()
    for family in manifest["families"].values():
        sequence = np.asarray(family["continuous_rgb"], dtype=float)
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        normal = perceived_lab(sequence, (1.0, 1.0, 1.0))
        shifted = perceived_lab(sequence, gains)
        normal_direction = 1.0 if normal[-1, 0] >= normal[0, 0] else -1.0
        normal_lightness_steps = np.diff(normal[:, 0]) * normal_direction
        normal_perceptual_steps = np.linalg.norm(np.diff(normal, axis=0), axis=1) * 100.0
        normal_cv = float(normal_perceptual_steps.std() / normal_perceptual_steps.mean())
        normal_max_to_min = float(normal_perceptual_steps.max() / normal_perceptual_steps.min())
        direction = 1.0 if shifted[-1, 0] >= shifted[0, 0] else -1.0
        lightness_steps = np.diff(shifted[:, 0]) * direction
        perceptual_steps = np.linalg.norm(np.diff(shifted, axis=0), axis=1) * 100.0
        cv = float(perceptual_steps.std() / perceptual_steps.mean())
        max_to_min = float(perceptual_steps.max() / perceptual_steps.min())
        metrics = family["metrics"]["continuous"]
        assert len({tuple(color) for color in sequence}) == 256, family["slug"]
        assert normal_lightness_steps.min() > 0.0, family["slug"]
        assert np.ptp(normal[:, 0]) >= 0.50, family["slug"]
        assert normal_cv <= 0.18, family["slug"]
        assert normal_max_to_min <= 1.60, family["slug"]
        assert lightness_steps.min() > 0.0, family["slug"]
        assert np.ptp(shifted[:, 0]) >= 0.50, family["slug"]
        assert cv <= 0.08, family["slug"]
        assert max_to_min <= 1.60, family["slug"]
        assert metrics["minimum_signed_lightness_step"] == round(float(lightness_steps.min()), 6)
        assert metrics["normal_minimum_signed_lightness_step"] == round(
            float(normal_lightness_steps.min()), 6
        )
        assert metrics["normal_delta_e_ok_cv"] == round(normal_cv, 4)
        assert metrics["normal_delta_e_ok_max_to_min"] == round(normal_max_to_min, 3)
        assert metrics["delta_e_ok_cv"] == round(cv, 4)
        assert metrics["delta_e_ok_max_to_min"] == round(max_to_min, 3)


def test_primary_text_contrast_survives_profile() -> None:
    manifest = generate_manifest()
    background_roles = manifest["quality_targets"]["bg_roles_low_to_high"]
    for family in manifest["families"].values():
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        foreground = warm_transform(hex_to_srgb(family["surfaces"]["fg_0"]), gains)
        for name in background_roles:
            background = warm_transform(hex_to_srgb(family["surfaces"][name]), gains)
            assert contrast_ratio(foreground, background) >= 4.5, (family["slug"], name)


def test_numbered_foregrounds_meet_role_specific_contrast_floors() -> None:
    manifest = generate_manifest()
    backgrounds = manifest["quality_targets"]["bg_roles_low_to_high"]
    targets = manifest["quality_targets"]["minimum_shifted_foreground_contrast"]
    for family in manifest["families"].values():
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        metrics = family["metrics"]["shifted_text_contrast"]
        for foreground, target in targets.items():
            transformed_foreground = warm_transform(
                hex_to_srgb(family["surfaces"][foreground]), gains
            )
            measured = []
            for background in backgrounds:
                transformed_background = warm_transform(
                    hex_to_srgb(family["surfaces"][background]), gains
                )
                contrast = contrast_ratio(transformed_foreground, transformed_background)
                measured.append(contrast)
                assert metrics[f"{foreground}_on_{background}"] == round(contrast, 2)
            assert min(measured) >= target, (family["slug"], foreground)


def test_bg_5_remains_visible_from_the_base_after_shift() -> None:
    manifest = generate_manifest()
    for family in manifest["families"].values():
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        transformed = perceived_lab(
            np.asarray(
                [
                    hex_to_srgb(family["surfaces"]["bg_0"]),
                    hex_to_srgb(family["surfaces"]["bg_5"]),
                ]
            ),
            gains,
        )
        assert delta_e_ok(transformed[0], transformed[1]) >= 6.0, family["slug"]


def test_dark_surfaces_are_near_black_with_strong_primary_text_contrast() -> None:
    manifest = generate_manifest()
    targets = manifest["quality_targets"]
    luminance_caps = targets["dark_surface_maximum_commanded_relative_luminance"]
    contrast_targets = targets["dark_minimum_shifted_primary_text_contrast"]
    background_roles = targets["bg_roles_low_to_high"]
    measured_roles = background_roles
    for family in manifest["families"].values():
        if family["mode"] != "dark":
            continue
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        foreground = warm_transform(hex_to_srgb(family["surfaces"]["fg_0"]), gains)
        normal_luminance = []
        shifted_luminance = []
        shifted_contrast = []
        shifted_labs = []
        for role in measured_roles:
            commanded = hex_to_srgb(family["surfaces"][role])
            shifted = warm_transform(commanded, gains)
            normal_luminance.append(float(wcag_luminance(commanded)))
            shifted_luminance.append(float(wcag_luminance(shifted)))
            shifted_contrast.append(contrast_ratio(foreground, shifted))
            shifted_labs.append(perceived_lab(commanded, gains))
            assert normal_luminance[-1] <= luminance_caps[role], (family["slug"], role)
        assert np.all(np.diff(normal_luminance) > 0.0), family["slug"]
        assert np.all(np.diff(shifted_luminance) > 0.0), family["slug"]
        adjacent_distance = [delta_e_ok(left, right) for left, right in pairwise(shifted_labs)]
        assert min(adjacent_distance) >= targets["dark_minimum_adjacent_surface_delta_e_ok"]
        assert min(shifted_contrast) >= contrast_targets[family["slug"]], family["slug"]
        metrics = family["metrics"]["surface"]
        assert metrics["normal_relative_luminance"] == {
            role: round(value, 5) for role, value in zip(measured_roles, normal_luminance)
        }
        assert metrics["shifted_relative_luminance"] == {
            role: round(value, 5) for role, value in zip(measured_roles, shifted_luminance)
        }
        assert metrics["shifted_primary_text_contrast"] == {
            role: round(value, 2) for role, value in zip(measured_roles, shifted_contrast)
        }


def test_light_surface_ladder_is_symmetric_and_ordered() -> None:
    manifest = generate_manifest()
    family = manifest["families"]["3400k-light"]
    roles = manifest["quality_targets"]["bg_roles_low_to_high"]
    gains = manifest["profiles"][family["profile"]]["rgb_gains"]
    rgb = np.asarray([hex_to_srgb(family["surfaces"][role]) for role in roles])
    normal_luminance = np.asarray([wcag_luminance(value) for value in rgb])
    shifted_luminance = np.asarray([wcag_luminance(warm_transform(value, gains)) for value in rgb])
    shifted_labs = perceived_lab(rgb, gains)
    assert normal_luminance[0] >= 0.9
    assert normal_luminance[-1] <= 0.6
    assert np.all(np.diff(normal_luminance) < 0.0)
    assert np.all(np.diff(shifted_luminance) < 0.0)
    assert min(delta_e_ok(left, right) for left, right in pairwise(shifted_labs)) >= 1.8


def test_terminal_accents_are_distinct_by_day_and_grouped_at_night() -> None:
    manifest = generate_manifest()
    semantic_names = ("red", "green", "yellow", "blue", "magenta", "cyan")
    for family in manifest["families"].values():
        count = family["terminal_daylight_color_count"]
        colors = np.asarray(
            [hex_to_srgb(family["terminal"][name]) for name in semantic_names[:count]]
        )
        normal = perceived_lab(colors, (1.0, 1.0, 1.0))
        shifted = perceived_lab(colors, manifest["profiles"][family["profile"]]["rgb_gains"])
        transformed_targets = perceived_lab(
            np.asarray([hex_to_srgb(color) for color in family["terminal_transformed_targets"]]),
            (1.0, 1.0, 1.0),
        )
        groups = np.asarray(family["terminal_night_groups"])
        group_ids = sorted(set(groups))
        group_members = [shifted[groups == group_id] for group_id in group_ids]
        group_spreads = [
            float(pairwise_distances(members).max()) if len(members) > 1 else 0.0
            for members in group_members
        ]
        group_centers = np.asarray([members.mean(axis=0) for members in group_members])
        day_min = float(pairwise_distances(normal).min())
        metrics = family["metrics"]["terminal"]
        target_error = float(np.linalg.norm(shifted - transformed_targets, axis=1).max() * 100.0)

        assert len(groups) == count
        assert len(group_ids) == family["terminal_semantic_color_count"]
        assert day_min >= family["terminal_daylight_minimum_delta_e_ok_target"]
        assert max(group_spreads) <= 1.5
        assert np.linalg.norm(normal[:, 1:], axis=1).max() <= 0.121
        assert metrics["normal_min_delta_e_ok"] == round(day_min, 2)
        assert metrics["shifted_group_max_delta_e_ok"] == round(max(group_spreads), 2)
        assert target_error <= 0.15, family["slug"]
        assert metrics["transformed_target_max_delta_e_ok"] == round(target_error, 2)
        night_target = family["terminal_night_minimum_delta_e_ok_target"]
        if night_target is None:
            assert len(group_centers) == 1
            assert metrics["shifted_group_center_min_delta_e_ok"] is None
        else:
            night_min = float(pairwise_distances(group_centers).min())
            assert night_min >= night_target
            assert metrics["shifted_group_center_min_delta_e_ok"] == round(night_min, 2)


def test_terminal_foregrounds_remain_visible_after_shift() -> None:
    manifest = generate_manifest()
    for family in manifest["families"].values():
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        background = warm_transform(hex_to_srgb(family["surfaces"]["bg_0"]), gains)
        transformed = {
            name: warm_transform(hex_to_srgb(value), gains)
            for name, value in family["terminal"].items()
        }
        foreground_slots = {
            name: value
            for name, value in transformed.items()
            if family["mode"] == "light" or name != "black"
        }
        measured = min(contrast_ratio(value, background) for value in foreground_slots.values())
        assert measured >= 4.5
        assert family["terminal_minimum_shifted_foreground_contrast"] == round(measured, 2)


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


def test_readme_bi_state_metrics_match_manifest() -> None:
    manifest = generate_manifest()
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for family in manifest["families"].values():
        categorical = family["metrics"]["categorical"]
        expected = (
            f"| {family['name']} | {len(family['categorical'])} | "
            f"{categorical['normal_min_delta_e_ok']:.2f} | "
            f"{categorical['shifted_min_delta_e_ok']:.2f} | "
            f"{categorical['normal_chroma_mean']:.4f} / "
            f"{categorical['normal_chroma_max']:.4f} | "
            f"{categorical['shifted_lightness_range']:.4f} | "
            f"{family['terminal_minimum_shifted_foreground_contrast']:.2f}:1 |"
        )
        assert expected in text, family["slug"]
        if family["mode"] == "dark":
            surface = family["metrics"]["surface"]
            luminance = surface["normal_relative_luminance"]
            contrast = surface["shifted_primary_text_contrast"]
            surface_row = (
                f"| {family['name']} | `{family['surfaces']['bg_0']}` | "
                f"{luminance['bg_0']:.5f} → {luminance['bg_5']:.5f} | "
                f"{min(contrast.values()):.2f}–{max(contrast.values()):.2f}:1 |"
            )
            assert surface_row in text, family["slug"]
