from __future__ import annotations

import hashlib
import json
import re
import runpy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageChops

from ember.color import (
    contrast_ratio,
    hex_to_srgb,
    perceived_lab,
    srgb_to_hex,
    srgb_to_oklab,
    warm_transform,
)
from ember.definitions import (
    BACKGROUND_SURFACE_ROLES,
    DARK_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK,
    DARK_SURFACE_MAXIMUM_COMMANDED_LUMINANCE,
    FAMILIES,
)
from ember.generate import _sequential_colors

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "docs/experiments/dark-foreground-warmth"
RESULTS = EXPERIMENT / "search-results.json"
PROFILES = ("3400k-dark", "2000k-dark", "1200k-dark")
LANES = {"current": 0.0, "halfway": 0.5, "full": 1.0}
UNIVERSAL_FLOORS = (4.5, 3.5, 2.4)


def family(slug: str):
    return next(item for item in FAMILIES if item.slug == slug)


def rgb(values: list[str] | tuple[str, ...]) -> np.ndarray:
    return np.asarray([hex_to_srgb(value) for value in values])


def load() -> dict:
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def renderer_module() -> dict:
    return runpy.run_path(str(ROOT / "tools/render_dark_foreground_warmth_experiment.py"))


def expected_lane_target_ab(slug: str, weight: float) -> np.ndarray:
    base = family(slug)
    light = family("3400k-light")
    shipped = srgb_to_oklab(rgb(tuple(base.surfaces[f"fg_{index}"] for index in range(3))))
    light_lab = srgb_to_oklab(rgb(tuple(light.surfaces[f"fg_{index}"] for index in range(3))))
    light_chroma = np.linalg.norm(light_lab[:, 1:], axis=1)
    mean_vector = light_lab[:, 1:].mean(axis=0)
    direction = mean_vector / np.linalg.norm(mean_vector)
    full_ab = (light_chroma.mean() * np.asarray((1.2, 1.0, 0.8)))[:, None] * direction
    return shipped[:, 1:] + weight * (full_ab - shipped[:, 1:])


def expected_candidate_family(slug: str, record: dict):
    base = family(slug)
    surfaces = dict(base.surfaces)
    surfaces.update(record["surfaces"])
    surfaces.update({f"fg_{index}": value for index, value in enumerate(record["foregrounds"])})
    return replace(
        base,
        surfaces=surfaces,
        categorical_colors=tuple(record["categorical"]),
        categorical_transformed_targets=tuple(record["categorical_transformed_targets"]),
        terminal_colors=tuple(record["terminal"]),
        terminal_transformed_targets=tuple(record["terminal_transformed_targets"]),
        sequential_anchors=tuple(record["sequential_anchors"]),
    )


def test_relaxed_foreground_lanes_follow_warmth_philosophy_and_free_lightness() -> None:
    data = load()
    assert data["schema"] == 2
    assert data["lanes"] == LANES
    for slug in PROFILES:
        base = family(slug)
        shipped_fg = tuple(base.surfaces[f"fg_{index}"] for index in range(3))
        shipped_lab = srgb_to_oklab(rgb(shipped_fg))
        lane_chroma = []
        lane_plus_b = []
        for lane, weight in LANES.items():
            record = data["profiles"][slug]["candidates"][lane]
            np.testing.assert_allclose(
                record["foreground_target_ab"], expected_lane_target_ab(slug, weight), atol=1e-12
            )
            candidate_lab = srgb_to_oklab(rgb(record["foregrounds"]))
            np.testing.assert_allclose(
                record["foreground_lightness_deltas_vs_shipped"],
                candidate_lab[:, 0] - shipped_lab[:, 0],
                atol=1e-12,
            )
            if lane == "current":
                assert tuple(record["foregrounds"]) == shipped_fg
            else:
                assert np.max(np.abs(candidate_lab[:, 0] - shipped_lab[:, 0])) > 0.002
            lane_chroma.append(record["metrics"]["foreground"]["normal_mean_chroma"])
            lane_plus_b.append(record["metrics"]["foreground"]["normal_mean_plus_b"])
        assert lane_chroma[0] > lane_chroma[1] > lane_chroma[2]
        assert lane_plus_b[0] > lane_plus_b[1] > lane_plus_b[2]
        assert lane_chroma[2] < 0.016
        assert lane_plus_b[2] < 0.014


def test_surfaces_counts_aliases_and_canonical_outputs_are_unchanged() -> None:
    data = load()
    canonical_hashes = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in (
            "src/ember/definitions.py",
            "src/ember/palettes.json",
            "palettes/ember.json",
            "palettes/ember.css",
        )
    }
    # Pinned from the exact origin/main baseline 6d86f44. Constants avoid a
    # runtime dependency on parent history in GitHub Actions' shallow checkout.
    expected_hashes = {
        "src/ember/definitions.py": "a4bba1a88c778f6bee728cdf0bc8d63d2921c4e069061b117aebecbe81f207fd",
        "src/ember/palettes.json": "2e4d0f1f08ea1a34f9c45cff458d14e4d306e0aa920e20fc706445686f87ae54",
        "palettes/ember.json": "2e4d0f1f08ea1a34f9c45cff458d14e4d306e0aa920e20fc706445686f87ae54",
        "palettes/ember.css": "9e03c7b92a4eca7865ce1a2d74d9173c1d628d203c0ad93f8443f23174084be0",
    }
    assert canonical_hashes == expected_hashes
    for slug in PROFILES:
        base = family(slug)
        shipped = data["profiles"][slug]["shipped"]
        for lane in LANES:
            record = data["profiles"][slug]["candidates"][lane]
            assert list(record["surfaces"]) == list(BACKGROUND_SURFACE_ROLES)
            candidate_surface = srgb_to_oklab(rgb(list(record["surfaces"].values())))
            shipped_surface = srgb_to_oklab(
                rgb(tuple(base.surfaces[role] for role in BACKGROUND_SURFACE_ROLES))
            )
            assert record["surface_movement_mean_delta_e_ok"] == pytest.approx(
                np.linalg.norm(candidate_surface - shipped_surface, axis=1).mean() * 100.0
            )
            surface = record["metrics"]["surface"]
            assert np.all(np.diff(surface["normal_relative_luminance"]) >= 0.0)
            assert np.all(np.diff(surface["shifted_relative_luminance"]) >= 0.0)
            assert min(surface["shifted_adjacent_delta_e_ok"]) >= (
                DARK_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK
            )
            for role, value in zip(
                BACKGROUND_SURFACE_ROLES, surface["normal_relative_luminance"], strict=True
            ):
                assert value <= DARK_SURFACE_MAXIMUM_COMMANDED_LUMINANCE[role]
            assert len(record["categorical"]) == len(base.categorical_colors)
            assert len(record["terminal"]) == len(base.terminal_colors)
            assert record["terminal_ansi_indices"] == list(base.terminal_ansi_indices)
            assert record["terminal_night_groups"] == list(base.terminal_night_groups)
        assert shipped["terminal_ansi_indices"] == list(base.terminal_ansi_indices)


def test_every_dependent_bank_has_controlled_two_seed_search_provenance() -> None:
    data = load()
    run_count = 0
    for profile_index, slug in enumerate(PROFILES):
        records = data["profiles"][slug]["candidates"]
        expected_seed_pairs = {
            "full_system": [7000 + profile_index * 100, 7001 + profile_index * 100],
            "categorical": [17000 + profile_index * 100, 17001 + profile_index * 100],
            "terminal": [27000 + profile_index * 100, 27001 + profile_index * 100],
            "sequential": [37000 + profile_index * 100, 37001 + profile_index * 100],
        }
        for lane in LANES:
            for bank, seeds in expected_seed_pairs.items():
                search = records[lane]["search"][bank]
                assert [run["seed"] for run in search["runs"]] == seeds
                assert all(run["evaluated_exact_hex8_candidates"] > 1 for run in search["runs"])
                assert search["selected_seed"] in seeds
                if bank == "full_system":
                    selected = search["selected_after_coupled_refinement"]
                    changed = (
                        selected["surfaces"]
                        != list(data["profiles"][slug]["shipped"]["surfaces"].values())
                        or selected["foregrounds"]
                        != data["profiles"][slug]["shipped"]["foregrounds"]
                    )
                else:
                    key = {
                        "categorical": "categorical",
                        "terminal": "terminal",
                        "sequential": "sequential_anchors",
                    }[bank]
                    changed = records[lane][key] != data["profiles"][slug]["shipped"][key]
                assert search["changed_from_shipped"] == changed
                run_count += len(search["runs"])
        # Selected surfaces are byte-identical here, so controlled identical
        # dependencies must yield identical maps rather than lane seed noise.
        assert (
            records["current"]["sequential_anchors"]
            == records["halfway"]["sequential_anchors"]
            == records["full"]["sequential_anchors"]
        )
        assert (
            records["current"]["search"]["sequential"]["runs"]
            == records["halfway"]["search"]["sequential"]["runs"]
            == records["full"]["search"]["sequential"]["runs"]
        )
        assert (
            len(
                {
                    records[lane]["search"]["sequential"]["surface_dependency_fingerprint"]
                    for lane in LANES
                }
            )
            == 1
        )
    assert run_count == 72


def test_serialized_transformed_targets_maps_and_metrics_recompute_independently() -> None:
    data = load()
    for slug in PROFILES:
        base = family(slug)
        gains = base.profile.gains
        for lane in LANES:
            record = data["profiles"][slug]["candidates"][lane]
            for bank in ("categorical", "terminal"):
                expected = [
                    srgb_to_hex(warm_transform(hex_to_srgb(value), gains)) for value in record[bank]
                ]
                assert record[f"{bank}_transformed_targets"] == expected
            candidate = expected_candidate_family(slug, record)
            sequence = np.round(_sequential_colors(candidate), 10)
            assert np.array_equal(np.asarray(record["continuous_float_srgb"]), sequence)
            assert record["continuous_hex8"] == [srgb_to_hex(value) for value in sequence]

            foreground = rgb(record["foregrounds"])
            backgrounds = rgb([record["surfaces"][role] for role in BACKGROUND_SURFACE_ROLES])
            transformed_fg = warm_transform(foreground, gains)
            transformed_bg = warm_transform(backgrounds, gains)
            contrast = np.asarray(
                [[contrast_ratio(fg, bg) for bg in transformed_bg] for fg in transformed_fg]
            ).min(axis=1)
            np.testing.assert_allclose(
                contrast,
                record["metrics"]["foreground"]["worst_surface_shifted_contrast"],
                rtol=0,
                atol=1e-12,
            )
            lab = srgb_to_oklab(foreground)
            assert (
                abs(
                    np.linalg.norm(lab[:, 1:], axis=1).mean()
                    - record["metrics"]["foreground"]["normal_mean_chroma"]
                )
                < 1e-12
            )
            assert (
                abs(lab[:, 2].mean() - record["metrics"]["foreground"]["normal_mean_plus_b"])
                < 1e-12
            )

            day = srgb_to_oklab(sequence)
            night = perceived_lab(sequence, gains)
            day_steps = np.linalg.norm(np.diff(day, axis=0), axis=1) * 100
            night_steps = np.linalg.norm(np.diff(night, axis=0), axis=1) * 100
            metrics = record["metrics"]["sequential"]
            assert abs(day_steps.std() / day_steps.mean() - metrics["normal_cv"]) < 1e-12
            assert abs(night_steps.std() / night_steps.mean() - metrics["shifted_cv"]) < 1e-12
            assert abs(np.ptp(day[:, 0]) - metrics["normal_lightness_range"]) < 1e-12
            assert abs(np.ptp(night[:, 0]) - metrics["shifted_lightness_range"]) < 1e-12


def test_relaxed_system_restores_strict_and_universal_status_for_every_lane() -> None:
    data = load()
    renderer = renderer_module()
    for slug in PROFILES:
        for lane in LANES:
            record = data["profiles"][slug]["candidates"][lane]
            assert record["release_status"] == "PASS"
            assert record["release_failures"] == []
            assert record["foreground_failures"] == []
            assert record["dependent_bank_failures"] == []
            contrasts = record["metrics"]["foreground"]["worst_surface_shifted_contrast"]
            assert all(
                value >= floor for value, floor in zip(contrasts, UNIVERSAL_FLOORS, strict=True)
            )
            assert renderer["universal_status"](record) == "PASS"


def test_current_lane_is_fresh_and_reported_honestly() -> None:
    data = load()
    report = (EXPERIMENT / "README.md").read_text(encoding="utf-8")
    for slug in PROFILES:
        record = data["profiles"][slug]["candidates"]["current"]
        assert all(
            len(record["search"][bank]["runs"]) == 2
            for bank in ("full_system", "categorical", "terminal", "sequential")
        )
        for bank in ("full_system", "categorical", "terminal", "sequential"):
            phrase = (
                "changed"
                if record["search"][bank]["changed_from_shipped"]
                else "reselected shipped exact values"
            )
            assert phrase in report


def test_renderer_outputs_and_local_links_are_fresh() -> None:
    data = load()
    renderer = renderer_module()
    landing = (EXPERIMENT / "index.html").read_text(encoding="utf-8")
    report = (EXPERIMENT / "README.md").read_text(encoding="utf-8")
    assert landing == renderer["render_html"](data)
    assert report == renderer["render_readme"](data)
    targets = [
        target
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", report)
        if "://" not in target and not target.startswith("#")
    ]
    assert targets
    assert not [target for target in targets if not (EXPERIMENT / target).resolve().exists()]


def test_best_cell_decoration_is_correct_in_html_and_markdown() -> None:
    data = load()
    renderer = renderer_module()
    landing = renderer["render_html"](data)
    report = renderer["render_readme"](data)
    for _label, key, direction, extractor, _spec in renderer["METRICS"]:
        html_row = re.search(rf'<tr data-metric="{key}">(.*?)</tr>', landing, re.DOTALL)
        assert html_row
        cells = re.findall(
            r"<td(?: class=\"direction\")?>(.*?)</td>", html_row.group(1), re.DOTALL
        )[1:]
        assert len(cells) == 9
        for profile_index, slug in enumerate(PROFILES):
            values = {
                lane: float(extractor(data["profiles"][slug]["candidates"][lane])) for lane in LANES
            }
            best_value = min(values.values()) if direction == "lower" else max(values.values())
            for lane_index, lane in enumerate(LANES):
                decorated = "<strong>" in cells[profile_index * 3 + lane_index]
                assert decorated == (abs(values[lane] - best_value) <= 1e-12)
        markdown_line = next(
            line for line in report.splitlines() if line.startswith(f"| {_label} |")
        )
        assert markdown_line.count("**") == 2 * sum(
            1
            for slug in PROFILES
            for lane in LANES
            if lane in renderer["best_lanes"](data["profiles"][slug], extractor, direction)
        )


def test_html_contains_all_required_domains_controls_and_default_comparison() -> None:
    landing = (EXPERIMENT / "index.html").read_text(encoding="utf-8")
    assert '<body data-profile="3400k-dark" data-state="commanded" data-focus="all">' in landing
    for section in ("anatomy", "editorial", "terminal", "dashboard", "science", "metrics"):
        assert f'id="{section}"' in landing
    for phrase in (
        "Complete anatomy",
        "Editorial hierarchy",
        "Code and terminal",
        "Dense dashboard",
        "SEQUENTIAL HEATMAP",
        "Real Mars scalar image",
        "Mona Lisa photographic mapping",
        "Scientific figure",
        "EVENT TABLE",
        "COMMAND FORM",
    ):
        assert phrase in landing
    assert landing.count('data-profile-button="') == 3
    assert landing.count('data-state-button="') == 2
    assert landing.count('data-focus-button="') == 4
    assert landing.count('class="domain-head"') == 36
    # Three warmth lanes for the default profile exist in every proof domain.
    for lane in LANES:
        assert landing.count(f'data-profile="3400k-dark" data-candidate="{lane}"') == 5
    assert "overflow-x:hidden" not in landing
    assert "min-height:44px" in landing
    assert '.control[aria-label="Candidate focus"]{grid-template-columns:repeat(2,1fr)}' in landing
    assert "@media(max-width:680px)" in landing


def test_candidate_rasters_are_hash_locked_source_mapped_exact_simulations() -> None:
    data = load()
    assets = EXPERIMENT / "candidate-assets"
    commanded_sha256 = {
        "3400k-dark": {
            "mars": "c1995cf04cc095ca7aa2b778868a90db33d4bfa2f7b280beaa25fd6b57eb20cc",
            "mona": "00a8faa5d010aee2d462a8f021271c1fa5cdb9cb781b0d15da3f9afd99054bb5",
        },
        "2000k-dark": {
            "mars": "1915ac974009c5c454b875838c92ba6aa872b750f8363590f417e8dc801da597",
            "mona": "944c41bf09b22584db13ed24e5bc7d4d2bbb145b79fbd825b902756b1b574412",
        },
        "1200k-dark": {
            "mars": "ddeab5c5b6991a34690df10dfda3c152682b91988b31c9527dd756479050ff00",
            "mona": "cb650685b94d517494726fe745b33319c70470c645ad1dbb7043eb37230c7aa8",
        },
    }

    elevation = np.fromfile(ROOT / "assets/megt90n000cb.img", dtype=">i2").reshape((720, 1440))
    low, high = np.quantile(elevation, (0.01, 0.99))
    mars_indices = np.rint(np.clip((elevation - low) / (high - low), 0.0, 1.0) * 255).astype(
        np.uint8
    )

    with Image.open(ROOT / "assets/mona-lisa-c2rmf-public-domain.jpg") as source:
        source = source.convert("RGB")
        height = round(source.height * 640 / source.width)
        source = source.resize((640, height), Image.Resampling.LANCZOS)
        source_lightness = srgb_to_oklab(np.asarray(source, dtype=float) / 255.0)[..., 0]
    low, high = np.quantile(source_lightness, (0.01, 0.99))
    mona_indices = np.rint(np.clip((source_lightness - low) / (high - low), 0.0, 1.0) * 255).astype(
        np.uint8
    )

    for slug in PROFILES:
        gains = np.asarray(data["profiles"][slug]["gains"])
        sequence = np.asarray(
            data["profiles"][slug]["candidates"]["current"]["continuous_float_srgb"]
        )
        palette_rgb8 = np.rint(sequence * 255).astype(np.uint8)
        expected_commanded = {
            "mars": palette_rgb8[mars_indices],
            "mona": palette_rgb8[mona_indices],
        }
        # The profile-level sequential invariant makes commanded assets identical
        # across lanes. Verify container hashes, decoded source mapping, then every
        # simulated derivative independently.
        for lane in LANES:
            stem = f"{slug}-{lane}"
            for subject in ("mars", "mona"):
                commanded_path = assets / f"{subject}-{stem}-commanded.png"
                simulated_path = assets / f"{subject}-{stem}-simulated.png"
                assert (
                    hashlib.sha256(commanded_path.read_bytes()).hexdigest()
                    == commanded_sha256[slug][subject]
                )
                with (
                    Image.open(commanded_path) as commanded_source,
                    Image.open(simulated_path) as simulated_source,
                ):
                    commanded = commanded_source.convert("RGB")
                    simulated = simulated_source.convert("RGB")
                    assert np.array_equal(np.asarray(commanded), expected_commanded[subject])
                    expected_simulated = np.rint(
                        np.clip(np.asarray(commanded, dtype=float) / 255.0 * gains, 0.0, 1.0)
                        * 255.0
                    ).astype(np.uint8)
                    assert np.array_equal(np.asarray(simulated), expected_simulated)
                    assert ImageChops.difference(commanded, simulated).getbbox() is not None


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
        "phone-2000k-full-simulated.png",
        "metrics-table.png",
        "phone-metrics.png",
    ]
    assert sorted(path.name for path in captures.glob("*.png")) == sorted(expected)
    for name in expected:
        with Image.open(captures / name) as image:
            if name.startswith("phone-"):
                assert image.size == (390, 844)
            else:
                assert image.width == 1440
                assert image.height >= 500
