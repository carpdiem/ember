"""Authoritative temperature profiles and bi-state palette anchors."""

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
    daylight_minimum_delta_e_ok: float
    terminal_colors: tuple[str, ...]
    terminal_night_groups: tuple[int, ...]
    terminal_daylight_minimum_delta_e_ok: float
    terminal_night_minimum_delta_e_ok: float | None
    sequential_anchors: tuple[str, ...]

    @property
    def terminal_color_count(self) -> int:
        """Number of distinct accent groups after the target transform."""

        return len(set(self.terminal_night_groups))


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

DARK_SURFACE_MAXIMUM_COMMANDED_LUMINANCE = {
    "bg_0": 0.003,
    "bg_1": 0.005,
    "bg_2": 0.009,
    "bg_3": 0.013,
    "bg_4": 0.020,
    "selection": 0.021,
}

DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST = {
    "3400k-dark": 6.8,
    "2000k-dark": 5.65,
    "1200k-dark": 5.3,
}

DARK_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK = 2.3
DARK_MINIMUM_SELECTION_TO_SURFACE_DELTA_E_OK = 1.8

BACKGROUND_SURFACE_ROLES = (
    "bg_0",
    "bg_1",
    "bg_2",
    "bg_3",
    "bg_4",
)

LEGACY_BACKGROUND_ROLE_ALIASES = {
    "background": "bg_0",
    "background_alt": "bg_1",
    "background_high": "bg_2",
    "background_higher": "bg_3",
    "background_highest": "bg_4",
}


FAMILIES = (
    FamilyDefinition(
        slug="3400k-dark",
        name="3400K Dark",
        mode="dark",
        profile=PROFILES["3400k"],
        surfaces={
            "bg_0": "#090807",
            "bg_1": "#100E0C",
            "bg_2": "#181612",
            "bg_3": "#201D19",
            "bg_4": "#29251F",
            "foreground": "#DDD0B2",
            "foreground_soft": "#BDAE93",
            "foreground_muted": "#928374",
            "selection": "#32241B",
        },
        # Six moderate-chroma hues are composed for both unshifted daytime use and
        # the transformed view. Thin lines also receive dash and marker cues.
        categorical_colors=("#6E96D5", "#DDAA69", "#2E8A7E", "#67BE95", "#945D48", "#C3779A"),
        daylight_minimum_delta_e_ok=14.0,
        terminal_colors=("#B4C6F7", "#CEA866", "#70DBD8", "#9ABEA2", "#F5AD9A", "#D895C2"),
        terminal_night_groups=(0, 1, 2, 3, 4, 5),
        terminal_daylight_minimum_delta_e_ok=9.0,
        terminal_night_minimum_delta_e_ok=7.0,
        sequential_anchors=("#282527", "#51404F", "#7F5E69", "#A17C6C", "#C49D70", "#E2CDA1"),
    ),
    FamilyDefinition(
        slug="3400k-light",
        name="3400K Light",
        mode="light",
        profile=PROFILES["3400k"],
        surfaces={
            "bg_0": "#FFF7D6",
            "bg_1": "#F4EAC7",
            "bg_2": "#E9DCB9",
            "bg_3": "#DFCFAA",
            "bg_4": "#D4C29C",
            "foreground": "#342F2C",
            "foreground_soft": "#504945",
            "foreground_muted": "#665C54",
            "selection": "#C9B796",
        },
        categorical_colors=("#158F7A", "#322865", "#AE5D63", "#6E2626", "#33531D", "#676DB1"),
        daylight_minimum_delta_e_ok=15.0,
        terminal_colors=("#0E7361", "#20214A", "#833C50", "#571C0D", "#0F4510", "#3B4D87"),
        terminal_night_groups=(0, 1, 2, 3, 4, 5),
        terminal_daylight_minimum_delta_e_ok=14.0,
        terminal_night_minimum_delta_e_ok=11.0,
        sequential_anchors=("#F2E5BC", "#D7BF8D", "#B08061", "#80515A", "#533844", "#252126"),
    ),
    FamilyDefinition(
        slug="2000k-dark",
        name="2000K Dark",
        mode="dark",
        profile=PROFILES["2000k"],
        surfaces={
            "bg_0": "#070504",
            "bg_1": "#0D0A09",
            "bg_2": "#15110E",
            "bg_3": "#1E1814",
            "bg_4": "#271F1B",
            "foreground": "#E9D3AD",
            "foreground_soft": "#C8B38F",
            "foreground_muted": "#9F8B70",
            "selection": "#30221B",
        },
        # Blue contributes little after this transform, so its commanded range
        # improves daytime identity while the transformed composition stays warm.
        categorical_colors=("#DCC482", "#A57C29", "#8497E0", "#C28B93"),
        daylight_minimum_delta_e_ok=13.0,
        terminal_colors=("#DCC4D5", "#DCC464", "#D8B3FF", "#D8B396"),
        terminal_night_groups=(0, 0, 1, 1),
        terminal_daylight_minimum_delta_e_ok=8.0,
        terminal_night_minimum_delta_e_ok=2.0,
        sequential_anchors=("#17110F", "#4B3438", "#795052", "#A8755F", "#C69A70", "#F2D9AE"),
    ),
    FamilyDefinition(
        slug="1200k-dark",
        name="1200K Dark",
        mode="dark",
        profile=PROFILES["1200k"],
        surfaces={
            "bg_0": "#060302",
            "bg_1": "#0C0806",
            "bg_2": "#130E0B",
            "bg_3": "#1C1511",
            "bg_4": "#251C17",
            "foreground": "#FFE5BE",
            "foreground_soft": "#CBB58F",
            "foreground_muted": "#A28B70",
            "selection": "#2E1E17",
        },
        # Blue is absent after this transform. Its commanded values can therefore
        # separate the daytime gold, lavender, and olive without changing night.
        categorical_colors=("#E0C48E", "#B08ED7", "#8F8A31"),
        daylight_minimum_delta_e_ok=20.0,
        terminal_colors=("#EACF6F", "#EACFFF", "#EACFBC"),
        terminal_night_groups=(0, 0, 0),
        terminal_daylight_minimum_delta_e_ok=9.0,
        terminal_night_minimum_delta_e_ok=None,
        sequential_anchors=("#100C0B", "#4B302D", "#754941", "#9F6D58", "#C09772", "#FFE5B8"),
    ),
)
