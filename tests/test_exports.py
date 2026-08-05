from __future__ import annotations

import json
import plistlib
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib.colors
import numpy as np
import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from redshift_safe import categorical, categorical_norm, encode_categories, sequential, surfaces

ROOT = Path(__file__).resolve().parents[1]
SLUGS = (
    "3400k-dark",
    "3400k-light",
    "2000k-dark",
    "1200k-dark",
)
LEGACY_ALIASES = {
    "ember-dark": "3400k-dark",
    "ember-light": "3400k-light",
    "lowfire-dark": "2000k-dark",
    "safelight-dark": "1200k-dark",
}


def test_matplotlib_adapters() -> None:
    manifest = json.loads((ROOT / "palettes/redshift-safe-palettes.json").read_text())
    for slug in SLUGS:
        categorical_map = categorical(slug)
        sequential_map = sequential(slug)
        assert isinstance(categorical_map, matplotlib.colors.ListedColormap)
        assert isinstance(sequential_map, matplotlib.colors.ListedColormap)
        assert categorical_map.N == len(manifest["families"][slug]["categorical"])
        assert sequential_map.N == 256
        assert np.allclose(sequential_map.colors, manifest["families"][slug]["continuous_rgb"])


def test_surface_api_returns_an_independent_copy() -> None:
    manifest = json.loads((ROOT / "palettes/redshift-safe-palettes.json").read_text())
    for slug in SLUGS:
        result = surfaces(slug)
        assert result == manifest["families"][slug]["surfaces"]
        result["bg_0"] = "#FFFFFF"
        assert surfaces(slug)["bg_0"] != "#FFFFFF"


@pytest.mark.parametrize(
    ("legacy", "current"),
    list(LEGACY_ALIASES.items()),
)
def test_legacy_matplotlib_slugs_resolve(legacy: str, current: str) -> None:
    assert categorical(legacy).colors == categorical(current).colors
    assert surfaces(legacy) == surfaces(current)


@pytest.mark.parametrize("legacy", ["lowfire-light", "safelight-light"])
def test_removed_deep_light_slugs_fail_with_migration_message(legacy: str) -> None:
    with pytest.raises(KeyError, match="No deep-shift light replacement"):
        categorical(legacy)


def test_legacy_css_and_terminal_exports_remain_available() -> None:
    manifest = json.loads((ROOT / "palettes/redshift-safe-palettes.json").read_text())
    css = (ROOT / "palettes/redshift-safe-palettes.css").read_text()
    for role in ("bg_0", "bg_1", "bg_2", "bg_3", "bg_4", "selection"):
        assert f"--rs-{role.replace('_', '-')}:" in css
    for family in manifest["families"].values():
        for legacy_role, canonical_role in manifest["legacy_surface_role_aliases"].items():
            expected = (
                f"--rs-{legacy_role.replace('_', '-')}: "
                f"{family['surfaces'][canonical_role]}; /* legacy alias */"
            )
            assert expected in css
    for legacy in LEGACY_ALIASES:
        assert f'data-redshift-palette="{legacy}"' in css
        assert (ROOT / f"themes/terminal/alacritty/{legacy}.toml").is_file()
        assert (ROOT / f"themes/terminal/iterm2/{legacy}.itermcolors").is_file()
        assert (ROOT / f"themes/terminal/windows-terminal/{legacy}.json").is_file()


def test_generated_swatch_rectangles_fit_their_canvas() -> None:
    for path in (ROOT / "docs/swatches").glob("*.svg"):
        root = ET.parse(path).getroot()
        width = float(root.attrib["width"])
        height = float(root.attrib["height"])
        for rectangle in root.findall("{http://www.w3.org/2000/svg}rect"):
            x = float(rectangle.attrib.get("x", 0.0))
            y = float(rectangle.attrib.get("y", 0.0))
            raw_width = rectangle.attrib.get("width", "0")
            raw_height = rectangle.attrib.get("height", "0")
            rectangle_width = width if raw_width.endswith("%") else float(raw_width)
            rectangle_height = height if raw_height.endswith("%") else float(raw_height)
            assert x + rectangle_width <= width + 0.01, path
            assert y + rectangle_height <= height + 0.01, path


def test_categorical_encoding_is_stable_for_strings_and_subsets() -> None:
    order = ["control", "alpha", "beta", "gamma"]
    assert encode_categories(["control", "beta", "gamma"], order).tolist() == [0, 2, 3]
    assert encode_categories(["beta", "gamma"], order).tolist() == [2, 3]
    assert categorical_norm("2000k-dark")(np.asarray([0, 2, 3])).tolist() == [0, 2, 3]
    with pytest.raises(ValueError, match="1 and 6"):
        encode_categories(["a"], list("abcdefg"))
    with pytest.raises(ValueError, match="1 and 4"):
        encode_categories(["a"], list("abcde"), slug="2000k-dark")


def test_alacritty_exports_parse() -> None:
    for slug in SLUGS:
        data = tomllib.loads((ROOT / f"themes/terminal/alacritty/{slug}.toml").read_text())
        assert len(data["colors"]["normal"]) == 8
        assert len(data["colors"]["bright"]) == 8


def test_windows_terminal_exports_parse() -> None:
    for slug in SLUGS:
        data = json.loads((ROOT / f"themes/terminal/windows-terminal/{slug}.json").read_text())
        assert data["name"]
        assert data["background"].startswith("#")


def test_iterm_exports_parse() -> None:
    for slug in SLUGS:
        data = plistlib.loads((ROOT / f"themes/terminal/iterm2/{slug}.itermcolors").read_bytes())
        assert "Background Color" in data
        assert all(f"Ansi {index} Color" in data for index in range(16))
