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
    daylight_minimum_hue_gap_degrees: float | None
    categorical_shifted_background_contrast_minimum: float | None
    categorical_daylight_minimum_foreground_delta_e_ok: float
    categorical_night_minimum_foreground_delta_e_ok: float
    terminal_colors: tuple[str, ...]
    terminal_transformed_targets: tuple[str, ...]
    terminal_ansi_indices: tuple[int, ...]
    terminal_night_groups: tuple[int, ...]
    terminal_daylight_minimum_delta_e_ok: float
    terminal_night_minimum_delta_e_ok: float | None
    terminal_daylight_minimum_fg_0_delta_e_ok: float | None
    terminal_night_minimum_fg_0_delta_e_ok: float | None
    terminal_daylight_minimum_fg_1_delta_e_ok: float | None
    terminal_night_minimum_fg_1_delta_e_ok: float | None
    terminal_daylight_minimum_fg_2_delta_e_ok: float | None
    terminal_night_minimum_fg_2_delta_e_ok: float | None
    foreground_daylight_minimum_adjacent_delta_e_ok: float | None
    foreground_daylight_maximum_adjacent_delta_e_ok: float | None
    foreground_night_minimum_adjacent_delta_e_ok: float | None
    foreground_night_maximum_adjacent_delta_e_ok: float | None
    foreground_minimum_lightness_gap_ratio: float | None
    foreground_daylight_minimum_lightness_share: float | None
    foreground_night_minimum_lightness_share: float | None
    foreground_maximum_hue_span_degrees: float | None
    foreground_night_maximum_hue_span_degrees: float | None
    foreground_maximum_chroma: float | None
    foreground_daylight_minimum_chroma_vector_cosine: float | None
    foreground_night_minimum_chroma_vector_cosine: float | None
    foreground_chroma_direction: str | None
    foreground_chroma_order_tolerance: float | None
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
        categorical_threshold=11.0,
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

GAIN_SENSITIVITY_FRACTION = 0.05

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

LIGHT_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST = {"3400k-light": 5.0}

MINIMUM_SHIFTED_FOREGROUND_CONTRAST = {
    "fg_0": 4.5,
    "fg_1": 3.5,
    "fg_2": 2.4,
}

DARK_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK = 1.8
LIGHT_MINIMUM_ADJACENT_SURFACE_DELTA_E_OK = 2.8
LIGHT_MINIMUM_SURFACE_SPAN_DELTA_E_OK = 15.0

BACKGROUND_SURFACE_ROLES = (
    "bg_0",
    "bg_1",
    "bg_2",
    "bg_3",
    "bg_4",
    "bg_5",
)

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
            "fg_2": "#908472",
        },
        # Six moderate-chroma hues are composed for both unshifted daytime use and
        # the transformed view. Thin lines also receive dash and marker cues.
        categorical_colors=("#6E96D5", "#DDAA69", "#2E8B7E", "#67BE95", "#945D48", "#C3779A"),
        categorical_transformed_targets=(
            "#6E6F71",
            "#DD7E38",
            "#2E6743",
            "#678D4F",
            "#944526",
            "#C35852",
        ),
        daylight_minimum_delta_e_ok=15.0,
        daylight_minimum_hue_gap_degrees=20.0,
        categorical_shifted_background_contrast_minimum=3.0,
        categorical_daylight_minimum_foreground_delta_e_ok=6.0,
        categorical_night_minimum_foreground_delta_e_ok=5.0,
        terminal_colors=("#F5AD9A", "#7EB798", "#CA9246", "#B4C6F7", "#D895C2", "#70DBD8"),
        terminal_transformed_targets=(
            "#F58052",
            "#7E8750",
            "#CA6C25",
            "#B49383",
            "#D86E67",
            "#70A272",
        ),
        terminal_ansi_indices=(0, 1, 2, 3, 4, 5),
        terminal_night_groups=(0, 1, 2, 3, 4, 5),
        terminal_daylight_minimum_delta_e_ok=9.0,
        terminal_night_minimum_delta_e_ok=7.0,
        terminal_daylight_minimum_fg_0_delta_e_ok=8.5,
        terminal_night_minimum_fg_0_delta_e_ok=6.5,
        terminal_daylight_minimum_fg_1_delta_e_ok=8.0,
        terminal_night_minimum_fg_1_delta_e_ok=5.0,
        terminal_daylight_minimum_fg_2_delta_e_ok=10.0,
        terminal_night_minimum_fg_2_delta_e_ok=9.0,
        foreground_daylight_minimum_adjacent_delta_e_ok=10.0,
        foreground_daylight_maximum_adjacent_delta_e_ok=14.0,
        foreground_night_minimum_adjacent_delta_e_ok=8.5,
        foreground_night_maximum_adjacent_delta_e_ok=12.0,
        foreground_minimum_lightness_gap_ratio=0.72,
        foreground_daylight_minimum_lightness_share=0.98,
        foreground_night_minimum_lightness_share=0.98,
        foreground_maximum_hue_span_degrees=10.0,
        foreground_night_maximum_hue_span_degrees=3.0,
        foreground_maximum_chroma=0.045,
        foreground_daylight_minimum_chroma_vector_cosine=0.98,
        foreground_night_minimum_chroma_vector_cosine=0.998,
        foreground_chroma_direction="decreasing",
        foreground_chroma_order_tolerance=0.003,
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
            "fg_1": "#4D4540",
            "fg_2": "#665C54",
        },
        categorical_colors=("#2C9A84", "#321853", "#B36875", "#5B2A07", "#2A632D", "#556BAA"),
        categorical_transformed_targets=(
            "#2C7246",
            "#32122C",
            "#B34D3E",
            "#5B1F04",
            "#2A4918",
            "#554F5A",
        ),
        daylight_minimum_delta_e_ok=16.0,
        daylight_minimum_hue_gap_degrees=30.0,
        categorical_shifted_background_contrast_minimum=3.0,
        categorical_daylight_minimum_foreground_delta_e_ok=8.0,
        categorical_night_minimum_foreground_delta_e_ok=5.0,
        terminal_colors=("#470D05", "#174213", "#894C03", "#162252", "#643563", "#00766E"),
        terminal_transformed_targets=(
            "#470A03",
            "#17310A",
            "#893801",
            "#16192B",
            "#642734",
            "#01573A",
        ),
        terminal_ansi_indices=(0, 1, 2, 3, 4, 5),
        terminal_night_groups=(0, 1, 2, 3, 4, 5),
        terminal_daylight_minimum_delta_e_ok=14.0,
        terminal_night_minimum_delta_e_ok=11.0,
        terminal_daylight_minimum_fg_0_delta_e_ok=9.0,
        terminal_night_minimum_fg_0_delta_e_ok=6.0,
        terminal_daylight_minimum_fg_1_delta_e_ok=9.0,
        terminal_night_minimum_fg_1_delta_e_ok=6.0,
        terminal_daylight_minimum_fg_2_delta_e_ok=9.0,
        terminal_night_minimum_fg_2_delta_e_ok=7.0,
        foreground_daylight_minimum_adjacent_delta_e_ok=8.3,
        foreground_daylight_maximum_adjacent_delta_e_ok=9.0,
        foreground_night_minimum_adjacent_delta_e_ok=7.0,
        foreground_night_maximum_adjacent_delta_e_ok=8.0,
        foreground_minimum_lightness_gap_ratio=0.95,
        foreground_daylight_minimum_lightness_share=0.98,
        foreground_night_minimum_lightness_share=0.98,
        foreground_maximum_hue_span_degrees=8.0,
        foreground_night_maximum_hue_span_degrees=2.0,
        foreground_maximum_chroma=0.020,
        foreground_daylight_minimum_chroma_vector_cosine=0.98,
        foreground_night_minimum_chroma_vector_cosine=0.999,
        foreground_chroma_direction="increasing",
        foreground_chroma_order_tolerance=0.003,
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
            "fg_0": "#EED5AE",
            "fg_1": "#D3BB99",
            "fg_2": "#AA9D8B",
        },
        # The four transformed identities remain distinct and clear 3:1 against bg_0.
        # Their daytime preimages deliberately use unrelated hue families: weak blue is
        # optimization freedom, not a cross-state appearance-preservation constraint.
        categorical_colors=("#66B1D4", "#DB93A7", "#A46056", "#A3DBA9"),
        categorical_transformed_targets=("#666012", "#DB500F", "#A43407", "#A3770F"),
        daylight_minimum_delta_e_ok=14.0,
        daylight_minimum_hue_gap_degrees=20.0,
        categorical_shifted_background_contrast_minimum=3.0,
        categorical_daylight_minimum_foreground_delta_e_ok=9.0,
        categorical_night_minimum_foreground_delta_e_ok=4.0,
        terminal_colors=("#EC8B96", "#74E5C0", "#C39C49", "#A7D1FB"),
        terminal_transformed_targets=("#EC4C0E", "#747C10", "#C35507", "#A77216"),
        terminal_ansi_indices=(0, 1, 2, 3, 0, 1),
        terminal_night_groups=(0, 1, 2, 3),
        terminal_daylight_minimum_delta_e_ok=12.5,
        terminal_night_minimum_delta_e_ok=7.5,
        terminal_daylight_minimum_fg_0_delta_e_ok=12.5,
        terminal_night_minimum_fg_0_delta_e_ok=7.5,
        terminal_daylight_minimum_fg_1_delta_e_ok=7.5,
        terminal_night_minimum_fg_1_delta_e_ok=5.0,
        terminal_daylight_minimum_fg_2_delta_e_ok=6.0,
        terminal_night_minimum_fg_2_delta_e_ok=4.0,
        foreground_daylight_minimum_adjacent_delta_e_ok=8.0,
        foreground_daylight_maximum_adjacent_delta_e_ok=16.0,
        foreground_night_minimum_adjacent_delta_e_ok=6.0,
        foreground_night_maximum_adjacent_delta_e_ok=12.0,
        foreground_minimum_lightness_gap_ratio=0.70,
        foreground_daylight_minimum_lightness_share=0.92,
        foreground_night_minimum_lightness_share=0.92,
        foreground_maximum_hue_span_degrees=12.0,
        foreground_night_maximum_hue_span_degrees=3.0,
        foreground_maximum_chroma=0.065,
        foreground_daylight_minimum_chroma_vector_cosine=0.95,
        foreground_night_minimum_chroma_vector_cosine=0.98,
        foreground_chroma_direction="decreasing",
        foreground_chroma_order_tolerance=0.003,
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
            "fg_0": "#FFE5BD",
            "fg_1": "#CBAF89",
            "fg_2": "#A18C73",
        },
        # Three warm transformed identities clear 3:1 against bg_0. Their daytime
        # preimages use blue's exact null direction for a mature rose/sky/apricot triad;
        # category identity is stable, but cross-state hue appearance is intentionally not.
        categorical_colors=("#C26D76", "#92DBFF", "#EFB371"),
        categorical_transformed_targets=("#C22200", "#924400", "#EF3700"),
        daylight_minimum_delta_e_ok=20.0,
        daylight_minimum_hue_gap_degrees=45.0,
        categorical_shifted_background_contrast_minimum=3.0,
        categorical_daylight_minimum_foreground_delta_e_ok=6.0,
        categorical_night_minimum_foreground_delta_e_ok=3.5,
        terminal_colors=("#F29298", "#C9FFB4", "#DDCD81"),
        terminal_transformed_targets=("#F22D00", "#C94F00", "#DD3F00"),
        terminal_ansi_indices=(0, 1, 2, 2, 0, 1),
        terminal_night_groups=(0, 1, 2),
        terminal_daylight_minimum_delta_e_ok=9.4,
        terminal_night_minimum_delta_e_ok=4.0,
        terminal_daylight_minimum_fg_0_delta_e_ok=9.4,
        terminal_night_minimum_fg_0_delta_e_ok=4.0,
        terminal_daylight_minimum_fg_1_delta_e_ok=6.0,
        terminal_night_minimum_fg_1_delta_e_ok=4.0,
        terminal_daylight_minimum_fg_2_delta_e_ok=5.0,
        terminal_night_minimum_fg_2_delta_e_ok=3.5,
        foreground_daylight_minimum_adjacent_delta_e_ok=11.0,
        foreground_daylight_maximum_adjacent_delta_e_ok=17.5,
        foreground_night_minimum_adjacent_delta_e_ok=9.0,
        foreground_night_maximum_adjacent_delta_e_ok=12.0,
        foreground_minimum_lightness_gap_ratio=0.70,
        foreground_daylight_minimum_lightness_share=0.92,
        foreground_night_minimum_lightness_share=0.92,
        foreground_maximum_hue_span_degrees=12.0,
        foreground_night_maximum_hue_span_degrees=3.0,
        foreground_maximum_chroma=0.065,
        foreground_daylight_minimum_chroma_vector_cosine=0.95,
        foreground_night_minimum_chroma_vector_cosine=0.98,
        foreground_chroma_direction="decreasing",
        foreground_chroma_order_tolerance=0.003,
        sequential_anchors=("#100C0B", "#4B302D", "#754941", "#9F6D58", "#C09772", "#FFE5B8"),
    ),
)
