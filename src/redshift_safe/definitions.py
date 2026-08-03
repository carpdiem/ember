"""Authoritative design profiles and human-chosen path anchors."""

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
    categorical_lightness: float
    sequential_anchors: tuple[str, ...]


PROFILES = {
    "nightshift": ShiftProfile(
        slug="nightshift",
        name="Maximum Night Shift surrogate",
        target="approximately 3400 K warm-white stress profile",
        gains=(1.0, 0.74, 0.53),
        categorical_threshold=9.0,
        description=(
            "A documented surrogate for the undocumented, display-dependent warmest macOS "
            "Night Shift setting. This is the least destructive profile in the set."
        ),
    ),
    "redshift": ShiftProfile(
        slug="redshift",
        name="Redshift 2000 K signal-LUT",
        target="Redshift 2000 K with reset ramps, brightness 1, gamma 1",
        gains=(1.0, 0.54360078, 0.08679949),
        categorical_threshold=4.5,
        description=(
            "The pinned Redshift 2000 K gamma-ramp signal transform with identity input "
            "ramps, unit brightness, and unit per-channel gamma."
        ),
    ),
    "safelight": ShiftProfile(
        slug="safelight",
        name="Deep-red 1200 K stress profile",
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
        slug="ember-dark",
        name="Ember Dark",
        mode="dark",
        profile=PROFILES["nightshift"],
        surfaces={
            "background": "#171512",
            "background_alt": "#211E19",
            "background_high": "#2D2922",
            "foreground": "#F4E9D5",
            "foreground_soft": "#D8CBB7",
            "foreground_muted": "#A99C88",
            "selection": "#493F32",
        },
        categorical_lightness=0.66,
        sequential_anchors=("#15120F", "#3B2448", "#3D5875", "#398273", "#B18E43", "#F6E4AF"),
    ),
    FamilyDefinition(
        slug="ember-light",
        name="Ember Light",
        mode="light",
        profile=PROFILES["nightshift"],
        surfaces={
            "background": "#F8F0E2",
            "background_alt": "#EDE2D1",
            "background_high": "#DFD1BD",
            "foreground": "#29251F",
            "foreground_soft": "#453E34",
            "foreground_muted": "#6B6153",
            "selection": "#D2C1A7",
        },
        categorical_lightness=0.43,
        sequential_anchors=("#F8F0E2", "#C9B874", "#6E926F", "#486783", "#56334E", "#1B1514"),
    ),
    FamilyDefinition(
        slug="lowfire-dark",
        name="Lowfire Dark",
        mode="dark",
        profile=PROFILES["redshift"],
        surfaces={
            "background": "#140D0B",
            "background_alt": "#201510",
            "background_high": "#2E2118",
            "foreground": "#FFF0D0",
            "foreground_soft": "#E2CCAA",
            "foreground_muted": "#AD967A",
            "selection": "#503624",
        },
        categorical_lightness=0.52,
        sequential_anchors=("#100807", "#3B1652", "#68415D", "#47796B", "#C78B39", "#FFE7A6"),
    ),
    FamilyDefinition(
        slug="lowfire-light",
        name="Lowfire Light",
        mode="light",
        profile=PROFILES["redshift"],
        surfaces={
            "background": "#FFF2D8",
            "background_alt": "#F0DCBC",
            "background_high": "#DEC49D",
            "foreground": "#281A14",
            "foreground_soft": "#493226",
            "foreground_muted": "#72513E",
            "selection": "#D7B17C",
        },
        categorical_lightness=0.44,
        sequential_anchors=("#FFF2D8", "#D5A94D", "#758257", "#66516E", "#5B2948", "#1B0C0B"),
    ),
    FamilyDefinition(
        slug="safelight-dark",
        name="Safelight Dark",
        mode="dark",
        profile=PROFILES["safelight"],
        surfaces={
            "background": "#0D0404",
            "background_alt": "#180706",
            "background_high": "#260B08",
            "foreground": "#FFE9C8",
            "foreground_soft": "#DDBA94",
            "foreground_muted": "#AE8669",
            "selection": "#4B1D13",
        },
        categorical_lightness=0.54,
        sequential_anchors=("#090203", "#38104D", "#7C315B", "#B85E4C", "#EFA24E", "#FFE0A0"),
    ),
    FamilyDefinition(
        slug="safelight-light",
        name="Safelight Light",
        mode="light",
        profile=PROFILES["safelight"],
        surfaces={
            "background": "#FFE8C5",
            "background_alt": "#EFCBA1",
            "background_high": "#E2B689",
            "foreground": "#160403",
            "foreground_soft": "#48170F",
            "foreground_muted": "#70301F",
            "selection": "#E5A876",
        },
        categorical_lightness=0.28,
        sequential_anchors=("#FFE8C5", "#D98C3E", "#A85B45", "#74304E", "#45143C", "#160405"),
    ),
)
