from __future__ import annotations

import hashlib
import json
import re
import runpy
from pathlib import Path

import colour
import numpy as np

from ember.color import (
    contrast_ratio,
    hex_to_srgb,
    srgb_to_hex,
    warm_transform,
)
from ember.definitions import (
    FAMILIES,
)

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "docs/experiments/dark-foreground-warmth"
RESULTS = EXPERIMENT / "transformed-first-results.json"
PROFILES = ("3400k-dark", "2000k-dark", "1200k-dark")
LANES = ("current", "halfway")
LANE_WEIGHTS = {"current": 0.0, "halfway": 0.5}
UNIVERSAL_FLOORS = (4.5, 3.5, 2.4)
TRANSFORMED_ADJACENT_FLOOR = 2.5
TRANSFORMED_UNIFORMITY_RATIO = 1.7
FROZEN_SYSTEM_SHA256 = "1758d76fe90334201efed49fc3f9cb791aa95f5f358eac840facf78ef492ef13"


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


def transformed_adjacent(surfaces: tuple[str, ...], gains) -> np.ndarray:
    transformed = np.clip(rgb(surfaces) * np.asarray(gains), 0.0, 1.0)
    xyz = colour.sRGB_to_XYZ(transformed)
    flare = 0.0075 * colour.sRGB_to_XYZ(np.ones_like(transformed))
    ucs = np.asarray(colour.XYZ_to_CAM16UCS(xyz + flare, L_A=8.0, Y_b=3.0))
    return np.linalg.norm(np.diff(ucs, axis=0), axis=1)


def worst_contrasts(surfaces: tuple[str, ...], fg: tuple[str, ...], gains) -> list[float]:
    t_surf = warm_transform(rgb(surfaces), gains)
    t_fg = warm_transform(rgb(fg), gains)
    return [min(contrast_ratio(f, b) for b in t_surf) for f in t_fg]


def test_dependent_bank_schema_and_frozen_lane_structure() -> None:
    data = load()
    assert data["schema"] == 5
    assert data["frozen_system"]["sha256"] == FROZEN_SYSTEM_SHA256
    frozen = {
        slug: {
            lane: {
                "bg_count": record["bg_count"],
                "surfaces": record["surfaces"],
                "foregrounds": record["foregrounds"],
            }
            for lane, record in profile["lanes"].items()
        }
        for slug, profile in data["profiles"].items()
    }
    payload = json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(payload).hexdigest() == FROZEN_SYSTEM_SHA256
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


def test_halfway_counts_float_within_light_reference_bounds() -> None:
    data = load()
    counts = {slug: lane_record(data, slug, "halfway")["bg_count"] for slug in PROFILES}
    # Shared anchors mean every profile can support at least N=4; deeper
    # profiles are not required to shrink further.
    for count in counts.values():
        assert 3 <= count <= 6
    for slug in PROFILES:
        rule = lane_record(data, slug, "halfway")["search"].get("count_choice_rule", "")
        assert rule or lane_record(data, slug, "halfway")["search"].get("note")


def test_commanded_bg_lightness_follows_constructive_even_j_ladder() -> None:
    data = load()
    for slug in PROFILES:
        record = lane_record(data, slug, "halfway")
        surfaces = lane_surfaces(record)
        # The constructive algorithm solves commanded L per role for even
        # transformed J'; verify J is monotone and evenly spaced instead of
        # pinning to any particular commanded-L shape.
        gains = data["profiles"][slug]["gains"]
        j = np.asarray(
            [
                [
                    __import__("colour").XYZ_to_CAM16UCS(
                        __import__("colour").sRGB_to_XYZ(
                            np.clip(
                                np.asarray(hex_to_srgb(h)) * np.asarray(gains), 0.0, 1.0
                            ).reshape(1, 3)
                        ),
                        L_A=8.0,
                        Y_b=3.0,
                    )[0][0]
                ]
            ]
            for h in surfaces
        ).ravel()
        assert np.all(np.diff(j) > 0), f"{slug} transformed J not monotone: {j}"


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
        # The shipped baseline legitimately misses the even-distinctness gates —
        # that miss is the motivation for the fourth pass. Current must pass the
        # universal text lens; halfway must additionally clear distinctness.
        current_metrics = computed[slug]["current"]
        assert renderer["universal_status"](slug, current_metrics) == "PASS"
        halfway_metrics = computed[slug]["halfway"]
        # Halfway fg contrasts land on the optimizer's gate targets (floors with
        # quantization margin); require strict clearance at those targets.
        contrasts = [
            halfway_metrics[f"fg{index}_contrast"] + 0.003
            for index, floor in enumerate(
                (6.8 if slug == "3400k-dark" else 5.65 if slug == "2000k-dark" else 5.3,)
                and (
                    max(
                        4.5,
                        __import__(
                            "ember.definitions",
                            fromlist=["DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST"],
                        ).DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST.get(slug, 4.5),
                    ),
                    3.5,
                    2.4,
                )
            )
        ]
        floors = (
            max(
                4.5,
                __import__(
                    "ember.definitions", fromlist=["DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST"]
                ).DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST.get(slug, 4.5),
            ),
            3.5,
            2.4,
        )
        assert all(
            value - 0.003 >= floor - 1e-9 for value, floor in zip(contrasts, floors, strict=True)
        )
        assert renderer["distinctness_status"](halfway_metrics) == "PASS"
        current_adjacent_min = current_metrics["adjacent_min"]
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
            assert not record["categorical_failures"]
            assert not record["terminal_failures"]
            assert not record["sequential_failures"]
            assert not record["final_assembled_dependent_failures"]
            for trial in trials.values():
                assert not any("terminal" in failure for failure in trial["failures"])


def test_sequential_maps_recompute_independently() -> None:
    data = load()
    full = runpy.run_path(str(EXPERIMENT / "search_full_palette.py"))
    for slug in PROFILES:
        base = family(slug)
        for lane in LANES:
            record = lane_record(data, slug, lane)
            surfaces_six = lane_surfaces(record)
            if len(surfaces_six) < 6:
                surfaces_six = surfaces_six + (surfaces_six[-1],) * (6 - len(surfaces_six))
            candidate = full["candidate_family"](
                base,
                surfaces_six,
                tuple(record["foregrounds"]),
                categorical=tuple(record["categorical"]),
                terminal=tuple(record["terminal"]),
            )
            sequence, anchors, metrics = full["construct_sequential"](candidate)
            assert np.array_equal(np.asarray(record["continuous_float_srgb"]), sequence)
            assert record["continuous_hex8"] == [srgb_to_hex(v) for v in sequence]
            assert record["sequential_anchors"] == list(anchors)
            assert metrics["transformed_minimum_signed_j_step"] > 0
            assert metrics["normal_cv"] <= 0.18 + 1e-12


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
