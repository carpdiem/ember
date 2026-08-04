"""Render the generated Matplotlib gallery."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
SRC = ROOT / "src"
for path in (TOOLS, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from render_gallery import render_matplotlib_gallery

from redshift_safe.generate import generate_manifest

render_matplotlib_gallery(generate_manifest(), ROOT / "docs/matplotlib-gallery.png")
