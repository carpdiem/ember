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
    categorical_transformed_targets: tuple[str, ...]
    daylight_minimum_delta_e_ok: float
    terminal_colors: tuple[str, ...]
    terminal_transformed_targets: tuple[str, ...]
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
        categorical_threshold=8.5,
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
        categorical_threshold=8.5,
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
    "bg_5": 0.021,
}

DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST = {
    "3400k-dark": 6.8,
    "2000k-dark": 5.65,
    "1200k-dark": 5.3,
}

MINIMUM_SHIFTED_FOREGROUND_CONTRAST = {
    "fg_0": 4.5,
    "fg_1": 3.5,
    "fg_2": 2.4,
}

DARK_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK = 1.8

BACKGROUND_SURFACE_ROLES = (
    "bg_0",
    "bg_1",
    "bg_2",
    "bg_3",
    "bg_4",
    "bg_5",
)

LEGACY_SURFACE_ROLE_ALIASES = {
    "background": "bg_0",
    "background_alt": "bg_1",
    "background_high": "bg_2",
    "background_higher": "bg_3",
    "background_highest": "bg_4",
    "selection": "bg_5",
    "foreground": "fg_0",
    "foreground_soft": "fg_1",
    "foreground_muted": "fg_2",
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
            "bg_5": "#32241B",
            "fg_0": "#DDD0B2",
            "fg_1": "#BDAE93",
            "fg_2": "#928374",
        },
        # Six moderate-chroma hues are composed for both unshifted daytime use and
        # the transformed view. Thin lines also receive dash and marker cues.
        categorical_colors=("#6E96D5", "#DDAA69", "#2E8A7E", "#67BE95", "#945D48", "#C3779A"),
        categorical_transformed_targets=(
            "#6E6F71",
            "#DD7E38",
            "#2E6643",
            "#678D4F",
            "#944526",
            "#C35852",
        ),
        daylight_minimum_delta_e_ok=14.0,
        terminal_colors=("#B4C6F7", "#CEA866", "#70DBD8", "#9ABEA2", "#F5AD9A", "#D895C2"),
        terminal_transformed_targets=(
            "#B49383",
            "#CE7C36",
            "#70A272",
            "#9A8D56",
            "#F58052",
            "#D86E67",
        ),
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
            "bg_5": "#C9B796",
            "fg_0": "#342F2C",
            "fg_1": "#504945",
            "fg_2": "#665C54",
        },
        categorical_colors=("#158F7A", "#322865", "#AE5D63", "#6E2626", "#33531D", "#676DB1"),
        categorical_transformed_targets=(
            "#156A41",
            "#321E36",
            "#AE4534",
            "#6E1C14",
            "#333D0F",
            "#67515E",
        ),
        daylight_minimum_delta_e_ok=15.0,
        terminal_colors=("#0E7361", "#20214A", "#833C50", "#571C0D", "#0F4510", "#3B4D87"),
        terminal_transformed_targets=(
            "#0E5533",
            "#201827",
            "#832C2A",
            "#571507",
            "#0F3308",
            "#3B3948",
        ),
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
            "bg_5": "#30221B",
            "fg_0": "#E9D3AD",
            "fg_1": "#C8B38F",
            "fg_2": "#9F8B70",
        },
        # Stage 1 selects four warm transformed identities with >= 8.5 dEOK
        # categorical spacing and a terminal 2x2 lightness/chroma grid. Stage 2
        # uses weakly surviving blue to recover a restrained daytime hue set.
        categorical_colors=("#E6C682", "#A07928", "#749DE1", "#CB8991"),
        categorical_transformed_targets=("#E66C0B", "#A04203", "#745514", "#CB4A0D"),
        daylight_minimum_delta_e_ok=14.0,
        terminal_colors=("#B9CBDC", "#D9D68A", "#F1ADE2", "#D3A58D"),
        terminal_transformed_targets=("#B96E13", "#D9740C", "#F15E14", "#D35A0C"),
        terminal_night_groups=(0, 1, 2, 3),
        terminal_daylight_minimum_delta_e_ok=10.0,
        terminal_night_minimum_delta_e_ok=5.8,
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
            "bg_5": "#2E1E17",
            "fg_0": "#FFE5BE",
            "fg_1": "#CBB58F",
            "fg_2": "#A28B70",
        },
        # Stage 1 selects three equally spaced transformed warm identities. Stage 2
        # uses the fully removed blue channel to produce gold, lavender, and olive
        # by day without altering those nighttime outcomes.
        categorical_colors=("#E0C47A", "#B7A7F3", "#8F8A33"),
        categorical_transformed_targets=("#E03D00", "#B73400", "#8F2B00"),
        daylight_minimum_delta_e_ok=20.0,
        terminal_colors=("#D5D27A", "#EACFFF", "#FFCFB5"),
        terminal_transformed_targets=("#D54100", "#EA4000", "#FF4000"),
        terminal_night_groups=(0, 1, 2),
        terminal_daylight_minimum_delta_e_ok=10.0,
        terminal_night_minimum_delta_e_ok=4.0,
        sequential_anchors=("#100C0B", "#4B302D", "#754941", "#9F6D58", "#C09772", "#FFE5B8"),
    ),
)
