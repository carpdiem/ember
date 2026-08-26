from __future__ import annotations

import dataclasses
import hashlib
import json
from itertools import combinations
from pathlib import Path

import numpy as np

from ember.color import hex_to_srgb, srgb_to_hex, srgb_to_oklab, warm_transform
from ember.definitions import FAMILIES
from ember.generate import generate_manifest

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT / "docs/provenance/3400k-light-forbidden-arc-new-a.json"
SOURCE_HUE_ORDER_BANK = ["#70002D", "#B25809", "#6C8D38", "#016869", "#4081D2", "#84499C"]
SOURCE_HUE_ORDER_TRANSFORMED = [
    "#700018",
    "#B24105",
    "#6C681E",
    "#014D38",
    "#405F6F",
    "#843653",
]
PRODUCTION_BANK = ["#B25809", "#4081D2", "#84499C", "#6C8D38", "#016869", "#70002D"]
PRODUCTION_TRANSFORMED = ["#B24105", "#405F6F", "#843653", "#6C681E", "#014D38", "#700018"]
RETIRED_BANK = ["#359984", "#281144", "#A76282", "#6A2600", "#185823", "#445D9B"]
EXPECTED_DEFINITION_HASHES = {
    "3400k-dark": "917858abc2fb20d1b01229fb341355575cd0e308c480fe12a7404fe3887b5797",
    "3400k-light-noncategorical": "7a285169fbb1b345b3aed829c6662f6da4133b34cf6d070c64cdb8d68673f1bd",
    "2000k-dark": "57590380f10a2a94279a83281650981d73edc748e429d7e825c5efefe023e7e6",
    "1200k-dark": "1c8d4f2121968ed1f189aecc507a8f37f7072bdc9d86e247a12265cbbb2832b1",
}


def _definition_hashes() -> dict[str, str]:
    hashes = {}
    for family in FAMILIES:
        payload = dataclasses.asdict(family)
        label = family.slug
        if family.slug == "3400k-light":
            payload.pop("categorical_colors")
            payload.pop("categorical_transformed_targets")
            label += "-noncategorical"
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        hashes[label] = hashlib.sha256(encoded).hexdigest()
    return hashes


def test_canonical_3400k_light_bank_matches_accepted_new_a() -> None:
    family = next(family for family in FAMILIES if family.slug == "3400k-light")
    assert family.surfaces["fg_0"] == "#342F2C"
    assert list(family.categorical_colors) == PRODUCTION_BANK
    assert list(family.categorical_transformed_targets) == PRODUCTION_TRANSFORMED
    assert sorted(family.categorical_colors) == sorted(SOURCE_HUE_ORDER_BANK)
    assert sorted(family.categorical_transformed_targets) == sorted(SOURCE_HUE_ORDER_TRANSFORMED)
    assert family.profile.gains == (1.0, 0.74, 0.53)


def test_transformed_targets_are_exactly_derived_from_unchanged_profile() -> None:
    family = next(family for family in FAMILIES if family.slug == "3400k-light")
    transformed = [
        srgb_to_hex(warm_transform(hex_to_srgb(value), family.profile.gains))
        for value in family.categorical_colors
    ]
    assert transformed == PRODUCTION_TRANSFORMED


def test_accepted_bank_has_no_commanded_hue_in_closed_forbidden_arc() -> None:
    lab = srgb_to_oklab(np.asarray([hex_to_srgb(value) for value in PRODUCTION_BANK]))
    hues = np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360.0
    assert all(not (92.0 <= float(hue) <= 118.0) for hue in hues)


def test_provenance_pins_candidate_and_exact_21_pair_accounting() -> None:
    record = json.loads(PROVENANCE.read_text())
    assert record["source_review_commit"] == "d54473bf58ab7c5cf94fbc159f687a9f93465061"
    assert record["source_candidate_id"] == (
        "0081fe30792b1dc28cb674fdcf0b6e81522907df075f896c2582697df22b5796"
    )
    assert record["source_review_url"].startswith(
        "https://github.com/carpdiem/ember/blob/d54473bf58ab7c5cf94fbc159f687a9f93465061/"
    )
    assert record["schema_version"] == 2
    assert record["source_hue_order_categorical"] == SOURCE_HUE_ORDER_BANK
    assert record["source_hue_order_transformed_3400k"] == SOURCE_HUE_ORDER_TRANSFORMED
    assert record["categorical"] == PRODUCTION_BANK
    assert record["categorical_transformed_3400k"] == PRODUCTION_TRANSFORMED
    assert record["production_cross_theme_order"]["source_hue_indices_one_based"] == [
        2,
        5,
        6,
        3,
        4,
        1,
    ]
    assert record["selection"] == "NEW-A"
    assert record["production"] is True
    assert record["pair_accounting"] == {
        "role_count": 7,
        "total_unordered_pairs": 21,
        "category_category_pairs": 15,
        "fg0_category_pairs": 6,
        "lane_directions": 2,
    }
    roles = ["fg_0", *(f"category-{index}" for index in range(6))]
    pairs = list(combinations(roles, 2))
    assert len(pairs) == 21
    assert sum("fg_0" in pair for pair in pairs) == 6


def test_unrelated_family_and_light_noncategorical_definitions_are_byte_stable() -> None:
    assert _definition_hashes() == EXPECTED_DEFINITION_HASHES


def test_generated_consumers_preserve_exact_category_order_and_bytes() -> None:
    manifest = generate_manifest()
    light = manifest["families"]["3400k-light"]
    assert list(light["categorical"].values()) == PRODUCTION_BANK
    assert light["categorical_transformed_targets"] == PRODUCTION_TRANSFORMED

    for relative in ("palettes/ember.json", "src/ember/palettes.json"):
        exported = json.loads((ROOT / relative).read_text())
        family = exported["families"]["3400k-light"]
        assert list(family["categorical"].values()) == PRODUCTION_BANK
        assert family["categorical_transformed_targets"] == PRODUCTION_TRANSFORMED

    css = (ROOT / "palettes/ember.css").read_text()
    block = css.split('[data-ember-palette="3400k-light"] {', 1)[1].split("}", 1)[0]
    positions = [block.index(value) for value in PRODUCTION_BANK]
    assert positions == sorted(positions)


def test_active_production_paths_contain_no_retired_light_category_bytes() -> None:
    active_files = [ROOT / "README.md", ROOT / "index.html"]
    for directory in (
        ROOT / "src",
        ROOT / "palettes",
        ROOT / "themes",
        ROOT / "docs/swatches",
        ROOT / "docs/samples",
        ROOT / "docs/diagrams",
    ):
        active_files.extend(path for path in directory.rglob("*") if path.is_file())
    active_files.extend((ROOT / "docs/sample-analysis.md", ROOT / "docs/validation.md"))
    text_suffixes = {".css", ".html", ".json", ".md", ".py", ".svg", ".toml", ".itermcolors"}
    hits = {}
    for path in active_files:
        if path.suffix.lower() not in text_suffixes:
            continue
        text = path.read_text(errors="ignore")
        found = [value for value in RETIRED_BANK if value in text]
        if found:
            hits[str(path.relative_to(ROOT))] = found
    assert hits == {}


def test_reader_paths_use_finished_product_language_and_link_provenance() -> None:
    public = "\n".join((ROOT / path).read_text() for path in ("README.md", "index.html"))
    assert "3400k-light-forbidden-arc-new-a.json" in public
    assert "reserving the commanded Oklch hue arc from 92° through 118°" in public
    assert "keep series IDs and category indices unchanged" in public
    rejected = (
        "promotion required",
        "not canonical",
        "candidate new a",
        "branch experiment",
    )
    assert not [phrase for phrase in rejected if phrase in public.lower()]
