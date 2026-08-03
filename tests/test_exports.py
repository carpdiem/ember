from __future__ import annotations

import json
import plistlib
from pathlib import Path

import matplotlib.colors
import numpy as np

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from redshift_safe import categorical, sequential

ROOT = Path(__file__).resolve().parents[1]
SLUGS = (
    "ember-dark",
    "ember-light",
    "lowfire-dark",
    "lowfire-light",
    "safelight-dark",
    "safelight-light",
)


def test_matplotlib_adapters() -> None:
    manifest = json.loads((ROOT / "palettes/redshift-safe-palettes.json").read_text())
    for slug in SLUGS:
        categorical_map = categorical(slug)
        sequential_map = sequential(slug)
        assert isinstance(categorical_map, matplotlib.colors.ListedColormap)
        assert isinstance(sequential_map, matplotlib.colors.ListedColormap)
        assert categorical_map.N == 8
        assert sequential_map.N == 256
        assert np.allclose(sequential_map.colors, manifest["families"][slug]["continuous_rgb"])


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
