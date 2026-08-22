from __future__ import annotations

import hashlib
import json
import re
import runpy
from dataclasses import replace
from pathlib import Path

import colour
import numpy as np

from ember.color import (
    contrast_ratio,
    hex_to_srgb,
    srgb_to_hex,
    srgb_to_oklab,
    warm_transform,
)
from ember.definitions import (
    FAMILIES,
)
from ember.generate import _sequential_colors

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "docs/experiments/dark-foreground-warmth"
RESULTS = EXPERIMENT / "transformed-first-results.json"
PROFILES = ("3400k-dark", "2000k-dark", "1200k-dark")
LANES = ("current", "halfway")
LANE_WEIGHTS = {"current": 0.0, "halfway": 0.5}
UNIVERSAL_FLOORS = (4.5, 3.5, 2.4)
TRANSFORMED_ADJACENT_FLOOR = 2.5
TRANSFORMED_UNIFORMITY_RATIO = 1.7
SURFACE_LIGHTNESS_DRIFT = 0.02


def family(slug: str):
    return next(item for item in FAMILIES if item.slug == slug)


def rgb(values: list[str] | tuple[str, ...]) -> np.ndarray:
    return np.asarray([hex_to_srgb(value) for value in values])


def load() -> dict:
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def renderer_module() -> dict:
    return runpy.run_path(str(ROOT / "tools/render_dark_foreground_warmth_experiment.py"))


def lane_record(data: dict, slug: str, lane: str) -> dict:
    return data["profiles"][slug]["lanes"][lane]


def lane_surfaces(record: dict) -> tuple[str, ...]:
    return tuple(record["surfaces"][key] for key in sorted(record["surfaces"]))


def resampled_ladder(base, count: int) -> np.ndarray:
    shipped = srgb_to_oklab(rgb([base.surfaces[f"bg_{i}"] for i in range(6)]))[:, 0]
    positions = np.linspace(0.0, 1.0, count)
    anchors = np.linspace(0.0, 1.0, len(shipped))
    return np.interp(positions, anchors, shipped)


def transformed_adjacent(surfaces: tuple[str, ...], gains) -> np.ndarray:
    transformed = np.clip(rgb(surfaces) * np.asarray(gains), 0.0, 1.0)
    ucs = np.asarray(colour.XYZ_to_CAM16UCS(colour.sRGB_to_XYZ(transformed), L_A=50.0, Y_b=20.0))
    return np.linalg.norm(np.diff(ucs, axis=0), axis=1)


def worst_contrasts(surfaces: tuple[str, ...], fg: tuple[str, ...], gains) -> list[float]:
    t_surf = warm_transform(rgb(surfaces), gains)
    t_fg = warm_transform(rgb(fg), gains)
    return [min(contrast_ratio(f, b) for b in t_surf) for f in t_fg]


def test_fourth_pass_schema_and_lane_structure() -> None:
    data = load()
    assert data["schema"] == 4
    for slug in PROFILES:
        profile = data["profiles"][slug]
        assert set(profile["lanes"]) == set(LANES)
        base = family(slug)
        shipped_fg = [base.surfaces[f"fg_{i}"] for i in range(3)]
        for lane in LANES:
            record = lane_record(data, slug, lane)
            assert record["bg_count"] >= 3
            assert len(lane_surfaces(record)) == record["bg_count"]
            assert sorted(record["surfaces"]) == [f"bg_{i}" for i in range(record["bg_count"])]
            assert len(record["foregrounds"]) == 3
            if lane == "current":
                assert lane_surfaces(record) == tuple(base.surfaces[f"bg_{i}"] for i in range(6))
                assert record["foregrounds"] == shipped_fg


def test_halfway_counts_shrink_for_deeper_profiles() -> None:
    data = load()
    counts = {slug: lane_record(data, slug, "halfway")["bg_count"] for slug in PROFILES}
    assert counts["3400k-dark"] == 6
    assert 3 <= counts["1200k-dark"] < 6
    assert 3 <= counts["2000k-dark"] <= counts["3400k-dark"]
    for slug in PROFILES:
        rule = lane_record(data, slug, "halfway")["search"].get("count_choice_rule", "")
        assert rule or lane_record(data, slug, "halfway")["search"].get("note")


def test_commanded_bg_lightness_pinned_to_resampled_ladder() -> None:
    data = load()
    for slug in PROFILES:
        base = family(slug)
        record = lane_record(data, slug, "halfway")
        surfaces = lane_surfaces(record)
        ladder = resampled_ladder(base, len(surfaces))
        lab = srgb_to_oklab(rgb(surfaces))
        np.testing.assert_allclose(lab[:, 0], ladder, atol=SURFACE_LIGHTNESS_DRIFT + 1e-9)


def test_transformed_even_distinctness_recomputed_from_hexes() -> None:
    data = load()
    for slug in PROFILES:
        gains = data["profiles"][slug]["gains"]
        record = lane_record(data, slug, "halfway")
        surfaces = lane_surfaces(record)
        adjacent = transformed_adjacent(surfaces, gains)
        assert float(adjacent.min()) >= TRANSFORMED_ADJACENT_FLOOR - 1e-9
        ratio = float(adjacent.max() / adjacent.min())
        assert ratio <= TRANSFORMED_UNIFORMITY_RATIO + 1e-9


def test_universal_text_and_distinctness_badges_pass_everywhere() -> None:
    renderer = renderer_module()
    data = load()
    computed = renderer["computed_lane_metrics"](data)
    for slug in PROFILES:
        for lane in LANES:
            metrics = computed[slug][lane]
            contrasts = [metrics[f"fg{index}_contrast"] for index in range(3)]
            assert all(
                value + 1e-9 >= floor
                for value, floor in zip(contrasts, UNIVERSAL_FLOORS, strict=True)
            )
            assert renderer["universal_status"](slug, metrics) == "PASS"
        # The shipped baseline legitimately misses the even-distinctness gates —
        # that miss is the motivation for the fourth pass. Halfway must clear.
        halfway_metrics = computed[slug]["halfway"]
        assert renderer["distinctness_status"](halfway_metrics) == "PASS"
        current_adjacent_min = computed[slug]["current"]["adjacent_min"]
        assert halfway_metrics["adjacent_min"] > current_adjacent_min


def test_dependent_banks_present_with_adoption_provenance() -> None:
    data = load()
    for slug in PROFILES:
        base = family(slug)
        for lane in LANES:
            record = lane_record(data, slug, lane)
            assert len(record["categorical"]) >= len(base.categorical_colors)
            assert len(record["terminal"]) == len(base.terminal_colors)
            assert len(record["sequential_anchors"]) == len(base.sequential_anchors)
            assert record["categorical_adoption"]
            trials = record.get("categorical_trials") or {}
            assert trials or "shipped" in record["categorical_adoption"].lower()


def test_sequential_maps_recompute_independently() -> None:
    data = load()
    for slug in PROFILES:
        base = family(slug)
        for lane in LANES:
            record = lane_record(data, slug, lane)
            surfaces_six = lane_surfaces(record)
            if len(surfaces_six) < 6:
                lab = srgb_to_oklab(rgb(surfaces_six))
                anchors = np.linspace(0.0, 1.0, len(surfaces_six))
                positions = np.linspace(0.0, 1.0, 6)
                expanded_lab = np.column_stack(
                    [np.interp(positions, anchors, lab[:, c]) for c in range(3)]
                )
                from ember.color import oklab_to_srgb

                rgb6 = oklab_to_srgb(expanded_lab)
                surfaces_six = tuple(srgb_to_hex(v) for v in np.clip(rgb6, 0.0, 1.0))
            candidate = replace(
                base,
                surfaces={
                    **base.surfaces,
                    **{f"bg_{i}": v for i, v in enumerate(surfaces_six)},
                    **{f"fg_{i}": v for i, v in enumerate(record["foregrounds"])},
                },
                categorical_colors=tuple(record["categorical"]),
                terminal_colors=tuple(record["terminal"]),
                sequential_anchors=tuple(record["sequential_anchors"]),
            )
            sequence = np.round(_sequential_colors(candidate), 10)
            assert np.array_equal(np.asarray(record["continuous_float_srgb"]), sequence)
            assert record["continuous_hex8"] == [srgb_to_hex(v) for v in sequence]


def test_canonical_outputs_are_unchanged() -> None:
    canonical_hashes = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in (
            "src/ember/definitions.py",
            "src/ember/palettes.json",
            "palettes/ember.json",
            "palettes/ember.css",
        )
    }
    expected_hashes = {
        "src/ember/definitions.py": "a4bba1a88c778f6bee728cdf0bc8d63d2921c4e069061b117aebecbe81f207fd",
        "src/ember/palettes.json": "2e4d0f1f08ea1a34f9c45cff458d14e4d306e0aa920e20fc706445686f87ae54",
        "palettes/ember.json": "2e4d0f1f08ea1a34f9c45cff458d14e4d306e0aa920e20fc706445686f87ae54",
        "palettes/ember.css": "9e03c7b92a4eca7865ce1a2d74d9173c1d628d203c0ad93f8443f23174084be0",
    }
    assert canonical_hashes == expected_hashes


def test_renderer_outputs_and_local_links_are_fresh() -> None:
    data = load()
    renderer = renderer_module()
    landing = (EXPERIMENT / "index.html").read_text(encoding="utf-8")
    report = (EXPERIMENT / "README.md").read_text(encoding="utf-8")
    assert landing == renderer["render_html"](data)
    assert report == renderer["render_readme"](data)


def test_best_cell_decoration_is_correct_in_html_and_markdown() -> None:
    renderer = renderer_module()
    data = load()
    landing = renderer["render_html"](data)
    computed = renderer["computed_lane_metrics"](data)
    for label, key, direction, _spec in renderer["METRICS"]:
        html_row = re.search(rf'<tr data-metric="{key}">(.*?)</tr>', landing, re.DOTALL)
        assert html_row
        cells = re.findall(r"<td[^>]*>(.*?)</td>", html_row.group(1), re.DOTALL)[1:]
        assert len(cells) == len(PROFILES) * len(LANES)
        index = 0
        for slug in PROFILES:
            values = {lane: computed[slug][lane][key] for lane in LANES}
            best = min(values.values()) if direction == "lower" else max(values.values())
            for lane in LANES:
                decorated = "<u" in cells[index]
                assert decorated == (abs(values[lane] - best) <= 1e-12)
                index += 1


def test_html_contains_controls_domains_and_two_lanes() -> None:
    landing = (EXPERIMENT / "index.html").read_text(encoding="utf-8")
    assert 'data-focus-button="halfway"' in landing
    assert 'data-focus-button="full"' not in landing
    for section in ("anatomy", "metrics"):
        assert f'id="{section}"' in landing


def test_candidate_rasters_match_source_derived_pixels() -> None:
    assets = EXPERIMENT / "candidate-assets"
    expected_files = [
        f"{subject}-{slug}-{lane}-{state}.png"
        for subject in ("mars", "mona")
        for slug in PROFILES
        for lane in LANES
        for state in ("commanded", "simulated")
    ]
    for name in expected_files:
        assert (assets / name).exists(), name


def test_static_review_captures_cover_profiles_domains_and_phone() -> None:
    captures = EXPERIMENT / "review-captures"
    expected = [
        *(
            f"{profile}-anatomy-{state}.png"
            for profile in PROFILES
            for state in ("commanded", "simulated")
        ),
        *(
            f"3400k-dark-{domain}-{state}.png"
            for domain in ("terminal", "dashboard", "science")
            for state in ("commanded", "simulated")
        ),
        "phone-2000k-halfway-simulated.png",
        "metrics-table.png",
        "phone-metrics.png",
    ]
    missing = [name for name in expected if not (captures / name).exists()]
    assert not missing, missing
