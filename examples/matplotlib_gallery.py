"""Print a compact usage gallery for manual Matplotlib smoke testing."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from redshift_safe import categorical, sequential

SLUGS = (
    "ember-dark",
    "ember-light",
    "lowfire-dark",
    "lowfire-light",
    "safelight-dark",
    "safelight-light",
)

fig, axes = plt.subplots(len(SLUGS), 2, figsize=(11, 10), constrained_layout=True)
heat = np.outer(np.linspace(0, 1, 80), np.ones(320))
for row, slug in enumerate(SLUGS):
    axes[row, 0].imshow(np.arange(8)[None, :], cmap=categorical(slug), aspect="auto")
    axes[row, 0].set_title(f"{slug} · categorical")
    axes[row, 1].imshow(heat.T, cmap=sequential(slug), aspect="auto", origin="lower")
    axes[row, 1].set_title(f"{slug} · sequential")
    for axis in axes[row]:
        axis.set_axis_off()

fig.savefig("docs/matplotlib-gallery.png", dpi=180)
