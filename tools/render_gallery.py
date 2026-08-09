"""Render the deterministic Matplotlib gallery from a generated manifest."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap

matplotlib.use("Agg")
import matplotlib.pyplot as plt

TOOLS = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for local_path in (TOOLS, SRC):
    if str(local_path) not in sys.path:
        sys.path.insert(0, str(local_path))

from render_style import publication_chrome

from ember.generate import generate_manifest

GALLERY_FINGERPRINT_KEY = "Ember-Source-SHA256"


def gallery_source_fingerprint(manifest: dict) -> str:
    """Identify the exact palette data and renderer source used by a gallery."""

    digest = hashlib.sha256()
    digest.update(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
    digest.update(Path(__file__).read_bytes())
    return digest.hexdigest()


def render_matplotlib_gallery(manifest: dict, destination: Path) -> None:
    """Render categorical and sequential maps from the provided manifest."""

    families = list(manifest["families"].values())
    chrome = publication_chrome(manifest)
    figure, axes = plt.subplots(
        len(families),
        2,
        figsize=(11, 7),
        constrained_layout=True,
        facecolor=chrome["canvas"],
    )
    heat = np.outer(np.linspace(0, 1, 80), np.ones(320))
    for row, family in enumerate(families):
        categories = list(family["categorical"].values())
        categorical_map = ListedColormap(categories, name=f"{family['slug']}-categorical")
        categorical_norm = BoundaryNorm(
            np.arange(-0.5, len(categories) + 0.5, 1.0),
            ncolors=len(categories),
            clip=True,
        )
        sequential_map = ListedColormap(
            family["continuous_rgb"], name=f"{family['slug']}-sequential"
        )
        axes[row, 0].imshow(
            np.arange(len(categories))[None, :],
            cmap=categorical_map,
            norm=categorical_norm,
            aspect="auto",
        )
        axes[row, 0].set_title(f"{family['slug']} · categorical", color=chrome["primary"])
        axes[row, 1].imshow(heat.T, cmap=sequential_map, aspect="auto", origin="lower")
        axes[row, 1].set_title(f"{family['slug']} · sequential", color=chrome["primary"])
        for axis in axes[row]:
            axis.set_axis_off()

    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        destination,
        dpi=180,
        facecolor=chrome["canvas"],
        metadata={GALLERY_FINGERPRINT_KEY: gallery_source_fingerprint(manifest)},
    )
    plt.close(figure)


if __name__ == "__main__":
    render_matplotlib_gallery(generate_manifest(), ROOT / "docs/matplotlib-gallery.png")
