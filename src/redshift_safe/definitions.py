"""Authoritative temperature profiles and restrained, human-chosen palette anchors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShiftProfile:
    slug: str
    name: str
    target: str
    gains: tuple[float, float, float]
    categorical_threshold: float
    description: str


@dataclass(frozen=True)
class FamilyDefinition:
    slug: str
    name: str
    mode: str
    profile: ShiftProfile
    surfaces: dict[str, str]
    categorical_colors: tuple[str, ...]
    terminal_color_count: int
    sequential_anchors: tuple[str, ...]


PROFILES = {
    "3400k": ShiftProfile(
        slug="3400k",
        name="3400 K",
        target="approximately 3400 K warm-white stress profile",
        gains=(1.0, 0.74, 0.53),
        categorical_threshold=6.0,
        description=(
            "A documented surrogate for the undocumented, display-dependent warmest macOS "
            "Night Shift setting. This is the least destructive profile in the set."
        ),
    ),
    "2000k": ShiftProfile(
        slug="2000k",
        name="2000 K",
        target="Redshift 2000 K with reset ramps, brightness 1, gamma 1",
        gains=(1.0, 0.54360078, 0.08679949),
        categorical_threshold=4.0,
        description=(
            "The pinned Redshift 2000 K gamma-ramp signal transform with identity input "
            "ramps, unit brightness, and unit per-channel gamma."
        ),
    ),
    "1200k": ShiftProfile(
        slug="1200k",
        name="1200 K",
        target="Redshift 1200 K with reset ramps, brightness 1, gamma 1",
        gains=(1.0, 0.30942099, 0.0),
        categorical_threshold=4.0,
        description=(
            "The pinned Redshift 1200 K signal-LUT transform: blue is removed and green "
            "is heavily attenuated. This is a severe visibility stress test, not a claim "
            "of physical astronomy safety."
        ),
    ),
}


FAMILIES = (
    FamilyDefinition(
        slug="3400k-dark",
        name="3400K Dark",
        mode="dark",
        profile=PROFILES["3400k"],
        surfaces={
            "background": "#32302F",
            "background_alt": "#383532",
            "background_high": "#403B37",
            "foreground": "#DDD0B2",
            "foreground_soft": "#BDAE93",
            "foreground_muted": "#928374",
            "selection": "#4A433D",
        },
        # Six low-chroma hues remain useful at this mildest shift.  Their wider
        # lightness range is intentional: thin lines also receive dash/marker cues.
        categorical_colors=("#8798C2", "#C9AA78", "#4E8E8A", "#83B89A", "#A0655B", "#B87F99"),
        terminal_color_count=6,
        sequential_anchors=("#282527", "#51404F", "#7F5E69", "#A17C6C", "#C49D70", "#E2CDA1"),
    ),
    FamilyDefinition(
        slug="3400k-light",
        name="3400K Light",
        mode="light",
        profile=PROFILES["3400k"],
        surfaces={
            "background": "#F2E5BC",
            "background_alt": "#EDE0B8",
            "background_high": "#E5D5AD",
            "foreground": "#342F2C",
            "foreground_soft": "#504945",
            "foreground_muted": "#665C54",
            "selection": "#C9B796",
        },
        categorical_colors=("#39806C", "#333360", "#995960", "#6C3333", "#405333", "#666699"),
        terminal_color_count=6,
        sequential_anchors=("#F2E5BC", "#D7BF8D", "#B08061", "#80515A", "#533844", "#252126"),
    ),
    FamilyDefinition(
        slug="2000k-dark",
        name="2000K Dark",
        mode="dark",
        profile=PROFILES["2000k"],
        surfaces={
            "background": "#302722",
            "background_alt": "#352B25",
            "background_high": "#3C3029",
            "foreground": "#E9D3AD",
            "foreground_soft": "#C8B38F",
            "foreground_muted": "#9F8B70",
            "selection": "#48382F",
        },
        # At 2000 K four composed earth tones beat eight forced rainbow slots.
        categorical_colors=("#DCC49F", "#A57C68", "#84977A", "#C28B92"),
        terminal_color_count=2,
        sequential_anchors=("#17110F", "#4B3438", "#795052", "#A8755F", "#C69A70", "#F2D9AE"),
    ),
    FamilyDefinition(
        slug="1200k-dark",
        name="1200K Dark",
        mode="dark",
        profile=PROFILES["1200k"],
        surfaces={
            "background": "#2C211D",
            "background_alt": "#322520",
            "background_high": "#3A2B25",
            "foreground": "#FFE5BE",
            "foreground_soft": "#CBB58F",
            "foreground_muted": "#A28B70",
            "selection": "#473128",
        },
        # Blue is physically gone at this tier.  Three excellent, redundant
        # encodings are more honest than pretending a larger hue set survives.
        categorical_colors=("#E0C49A", "#B08E76", "#8F8A6A"),
        terminal_color_count=1,
        sequential_anchors=("#100C0B", "#4B302D", "#754941", "#9F6D58", "#C09772", "#FFE5B8"),
    ),
)
