"""Matplotlib adapters for generated Ember palettes."""

from __future__ import annotations

import json
from collections.abc import Hashable, Iterable, Sequence
from importlib.resources import files

import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap


def _manifest() -> dict:
    path = files("ember").joinpath("palettes.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _family(slug: str) -> dict:
    manifest = _manifest()
    families = manifest["families"]
    if slug not in families:
        choices = ", ".join(sorted(families))
        raise KeyError(f"unknown family {slug!r}; choose one of: {choices}")
    return families[slug]


def categorical(slug: str) -> ListedColormap:
    """Return the profile-sized categorical map for a family."""
    family = _family(slug)
    return ListedColormap(list(family["categorical"].values()), name=f"{slug}-categorical")


def surfaces(slug: str) -> dict[str, str]:
    """Return a copy of the family's named UI surface and foreground colors."""

    return dict(_family(slug)["surfaces"])


def encode_categories(
    labels: Iterable[Hashable],
    order: Sequence[Hashable],
    *,
    slug: str | None = None,
) -> np.ndarray:
    """Encode labels into stable palette indices using an explicit global order."""
    available = (
        max(len(family["categorical"]) for family in _manifest()["families"].values())
        if slug is None
        else len(_family(slug)["categorical"])
    )
    if not 1 <= len(order) <= available:
        target = "the selected palette" if slug else "Ember's largest palette"
        raise ValueError(f"{target} supports between 1 and {available} category identities")
    mapping = {label: index for index, label in enumerate(order)}
    if len(mapping) != len(order):
        raise ValueError("category order must not contain duplicates")
    try:
        return np.asarray([mapping[label] for label in labels], dtype=int)
    except KeyError as error:
        raise ValueError(f"label {error.args[0]!r} is missing from category order") from error


def categorical_norm(slug: str = "3400k-dark") -> BoundaryNorm:
    """Keep category indices mapped to the same palette slots in every subset.

    The default matches the largest current palette. Pass the selected family slug
    whenever its category count is smaller.
    """

    count = len(_family(slug)["categorical"])
    return BoundaryNorm(np.arange(-0.5, count + 0.5, 1.0), ncolors=count, clip=True)


def sequential(slug: str) -> ListedColormap:
    """Return the 256-sample sequential map for a family."""
    family = _family(slug)
    return ListedColormap(family["continuous_rgb"], name=f"{slug}-sequential")
