"""Matplotlib adapters for generated Redshift Safe palettes."""

from __future__ import annotations

import json
from importlib.resources import files

from matplotlib.colors import ListedColormap


def _manifest() -> dict:
    path = files("redshift_safe").joinpath("palettes.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _family(slug: str) -> dict:
    families = _manifest()["families"]
    if slug not in families:
        choices = ", ".join(sorted(families))
        raise KeyError(f"unknown family {slug!r}; choose one of: {choices}")
    return families[slug]


def categorical(slug: str) -> ListedColormap:
    """Return the eight-color categorical map for a family."""
    family = _family(slug)
    return ListedColormap(list(family["categorical"].values()), name=f"{slug}-categorical")


def sequential(slug: str) -> ListedColormap:
    """Return the 256-sample sequential map for a family."""
    family = _family(slug)
    return ListedColormap(family["continuous_rgb"], name=f"{slug}-sequential")
