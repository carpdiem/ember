from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

from ember.color import hex_to_srgb, srgb_to_hex, warm_transform
from ember.definitions import FAMILIES
from ember.generate import generate_manifest

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT / "docs/provenance/3400k-light-terminal-a.json"
ROLES = ("red", "green", "yellow", "blue", "magenta", "cyan")
ACCEPTED = ("#98074F", "#517304", "#844601", "#396EDB", "#8339A7", "#0B7F8C")
TRANSFORMED = ("#98052A", "#515502", "#843401", "#395174", "#832A59", "#0B5E4A")
RETIRED = ("#430000", "#10420E", "#8A4805", "#131851", "#5D3777", "#007672")
SOURCE_REVIEW_COMMIT = "e702e402771f364f7ff8614cb425b53289e668b8"
SOURCE_MANIFEST_SHA256 = "e7044ae9e629975df2db19ef0c472c74b99efb0ce0e56a46f862387a863f9f4c"
RESULTS_SHA256 = "da7b86988aaa7fa75b1cd8afe05a1f78a1ec0b5fe5c8af8276ce056cca43f2b9"
BROWSER_EVIDENCE_SHA256 = "41c3edf9414b474055a0e84dfe70dbcf643c7222cd9f25a162dc196c951680df"
EXPECTED_DEFINITION_HASHES = {
    "3400k-dark": "917858abc2fb20d1b01229fb341355575cd0e308c480fe12a7404fe3887b5797",
    "3400k-light-frozen-unrelated": "b0ecdc26a8db119c89ac042abb088e9c1594b61189b692ce220ebacf9858a738",
    "2000k-dark": "57590380f10a2a94279a83281650981d73edc748e429d7e825c5efefe023e7e6",
    "1200k-dark": "1c8d4f2121968ed1f189aecc507a8f37f7072bdc9d86e247a12265cbbb2832b1",
}


def definition_hashes() -> dict[str, str]:
    hashes = {}
    for family in FAMILIES:
        payload = dataclasses.asdict(family)
        label = family.slug
        if family.slug == "3400k-light":
            for key in (
                "categorical_colors",
                "categorical_transformed_targets",
                "terminal_colors",
                "terminal_transformed_targets",
                "terminal_night_minimum_delta_e_ok",
                "terminal_night_minimum_fg_2_delta_e_ok",
            ):
                payload.pop(key)
            label += "-frozen-unrelated"
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        hashes[label] = hashlib.sha256(encoded).hexdigest()
    return hashes


def test_canonical_terminal_bank_is_exact_accepted_a() -> None:
    family = next(family for family in FAMILIES if family.slug == "3400k-light")

    assert family.terminal_colors == ACCEPTED
    assert family.terminal_transformed_targets == TRANSFORMED
    assert family.terminal_ansi_indices == (0, 1, 2, 3, 4, 5)
    assert family.terminal_night_groups == (0, 1, 2, 3, 4, 5)
    assert family.terminal_daylight_minimum_delta_e_ok == 14.0
    assert family.terminal_night_minimum_delta_e_ok == 7.5
    assert family.terminal_night_minimum_fg_2_delta_e_ok == 6.5
    assert family.profile.gains == (1.0, 0.74, 0.53)


def test_transformed_targets_are_exactly_derived_from_accepted_hex() -> None:
    family = next(family for family in FAMILIES if family.slug == "3400k-light")
    derived = tuple(
        srgb_to_hex(warm_transform(hex_to_srgb(value), family.profile.gains))
        for value in family.terminal_colors
    )

    assert derived == TRANSFORMED


def test_provenance_binds_review_evidence_and_production_selection() -> None:
    record = json.loads(PROVENANCE.read_text())

    assert record["source_review_commit"] == SOURCE_REVIEW_COMMIT
    assert record["source_candidate_id"] == "A-raster-maximum"
    assert record["source_manifest_sha256"] == SOURCE_MANIFEST_SHA256
    assert record["source_results_sha256"] == RESULTS_SHA256
    assert record["source_browser_evidence_sha256"] == BROWSER_EVIDENCE_SHA256
    assert record["source_review_url"].startswith(
        f"https://github.com/carpdiem/ember/blob/{SOURCE_REVIEW_COMMIT}/"
    )
    assert record["role_order"] == list(ROLES)
    assert record["terminal"] == list(ACCEPTED)
    assert record["terminal_transformed_3400k"] == list(TRANSFORMED)
    assert record["cam16_viewing_conditions"]["commanded"] == {
        "adapting_luminance": 64.0,
        "background_luminance": 20.0,
        "flare_fraction": 0.0075,
        "rgb_gains": [1.0, 1.0, 1.0],
        "label": "normal-daytime",
    }
    assert record["cam16_viewing_conditions"]["transformed"] == {
        "adapting_luminance": 8.0,
        "background_luminance": 3.0,
        "flare_fraction": 0.0075,
        "rgb_gains": [1.0, 0.74, 0.53],
        "label": "low-light",
    }
    assert record["selection"] == "A-raster-maximum"
    assert record["production"] is True


def test_manifest_exposes_dual_viewing_terminal_contract_and_aliases() -> None:
    manifest = generate_manifest()
    light = manifest["families"]["3400k-light"]

    assert manifest["schema_version"] == 15
    assert manifest["quality_targets"]["terminal_cam16_viewing_conditions"] == {
        "commanded": {
            "adapting_luminance": 64.0,
            "background_luminance": 20.0,
            "flare_fraction": 0.0075,
        },
        "transformed": {
            "adapting_luminance": 8.0,
            "background_luminance": 3.0,
            "flare_fraction": 0.0075,
        },
    }
    assert [light["terminal"][role] for role in ROLES] == list(ACCEPTED)
    assert [light["terminal"][f"bright_{role}"] for role in ROLES] == list(ACCEPTED)
    assert light["terminal"]["black"] == light["surfaces"]["fg_0"]
    assert light["terminal"]["white"] == light["surfaces"]["fg_0"]
    assert light["terminal_transformed_targets"] == list(TRANSFORMED)
    dual = light["metrics"]["transformed_cam16_ucs"]
    assert dual["terminal_viewing_conditions"]["commanded"]["rgb_gains"] == [1.0, 1.0, 1.0]
    assert dual["terminal_viewing_conditions"]["transformed"]["rgb_gains"] == [1.0, 0.74, 0.53]
    assert dual["terminal_commanded_minimum_pair_distance"] > 20.0
    assert dual["terminal_transformed_minimum_pair_distance"] > 15.0
    assert dual["terminal_commanded_minimum_foreground_distance"] > 15.0
    assert dual["terminal_transformed_minimum_foreground_distance"] > 10.0


def test_generated_exports_use_exact_terminal_roles_and_ansi_aliases() -> None:
    for relative in ("palettes/ember.json", "src/ember/palettes.json"):
        payload = json.loads((ROOT / relative).read_text())
        light = payload["families"]["3400k-light"]
        assert [light["terminal"][role] for role in ROLES] == list(ACCEPTED)
        assert [light["terminal"][f"bright_{role}"] for role in ROLES] == list(ACCEPTED)
        assert light["terminal_transformed_targets"] == list(TRANSFORMED)

    css = (ROOT / "palettes/ember.css").read_text()
    block = css.split('[data-ember-palette="3400k-light"] {', 1)[1].split("}", 1)[0]
    assert [block.index(value) for value in ACCEPTED] == sorted(
        block.index(value) for value in ACCEPTED
    )


def test_dark_and_unrelated_light_definitions_remain_byte_stable() -> None:
    assert definition_hashes() == EXPECTED_DEFINITION_HASHES


def test_active_production_paths_contain_no_retired_terminal_bytes() -> None:
    active_files = [ROOT / "README.md", ROOT / "index.html", ROOT / "docs/validation.md"]
    for directory in (
        ROOT / "src",
        ROOT / "palettes",
        ROOT / "themes",
        ROOT / "docs/swatches",
        ROOT / "docs/samples",
        ROOT / "docs/diagrams",
    ):
        active_files.extend(path for path in directory.rglob("*") if path.is_file())
    text_suffixes = {".css", ".html", ".json", ".md", ".py", ".svg", ".toml", ".itermcolors"}
    hits = {}
    for path in active_files:
        if path.suffix.lower() not in text_suffixes:
            continue
        found = [value for value in RETIRED if value in path.read_text(errors="ignore")]
        if found:
            hits[str(path.relative_to(ROOT))] = found
    assert hits == {}


def test_reader_paths_present_finished_terminal_product() -> None:
    public = "\n".join((ROOT / path).read_text() for path in ("README.md", "index.html"))

    assert "3400k-light-terminal-a.json" in public
    assert "real small-glyph Chromium pixels" in public
    for phrase in ("A-raster-maximum", "promotion required", "not production", "branch experiment"):
        assert phrase not in public
