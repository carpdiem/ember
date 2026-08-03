"""Matplotlib adapters for generated Redshift Safe palettes."""

from __future__ import annotations

import json
from collections.abc import Hashable, Iterable, Sequence
from importlib.resources import files

import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap


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


def encode_categories(labels: Iterable[Hashable], order: Sequence[Hashable]) -> np.ndarray:
    """Encode labels into stable palette indices using an explicit global order."""
    if not 1 <= len(order) <= 8:
        raise ValueError("category order must contain between 1 and 8 labels")
    mapping = {label: index for index, label in enumerate(order)}
    if len(mapping) != len(order):
        raise ValueError("category order must not contain duplicates")
    try:
        return np.asarray([mapping[label] for label in labels], dtype=int)
    except KeyError as error:
        raise ValueError(f"label {error.args[0]!r} is missing from category order") from error


def categorical_norm() -> BoundaryNorm:
    """Keep category indices mapped to the same palette slots in every subset."""
    return BoundaryNorm(np.arange(-0.5, 8.5, 1.0), ncolors=8, clip=True)


def sequential(slug: str) -> ListedColormap:
    """Return the 256-sample sequential map for a family."""
    family = _family(slug)
    return ListedColormap(family["continuous_rgb"], name=f"{slug}-sequential")
