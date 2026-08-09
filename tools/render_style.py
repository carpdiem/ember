"""Manifest-derived publication chrome shared by every generated graphic."""

from __future__ import annotations

PUBLICATION_FAMILY_SLUG = "3400k-dark"
PUBLICATION_ROLE_MAP = {
    "canvas": "bg_0",
    "panel": "bg_2",
    "raised_panel": "bg_3",
    "rule": "bg_4",
    "border": "bg_5",
    "primary": "fg_0",
    "secondary": "fg_1",
    "metadata": "fg_2",
}


def publication_chrome(manifest: dict) -> dict[str, str]:
    """Return shared graphic chrome sourced from the 3400K Dark surface ladder."""

    surfaces = manifest["families"][PUBLICATION_FAMILY_SLUG]["surfaces"]
    return {name: surfaces[role] for name, role in PUBLICATION_ROLE_MAP.items()}
