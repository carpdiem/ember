"""Authoritative temperature profiles and bi-state palette anchors."""

from __future__ import annotations

from dataclasses import dataclass

from .sequential_data import DARK_SEQUENTIAL_RGB


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
    background_surface_values: tuple[str, ...]
    background_role_indices: tuple[int, int, int, int, int, int]
    categorical_colors: tuple[str, ...]
    categorical_semantic_slots: tuple[str, ...] | None
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
    sequential_rgb: tuple[tuple[float, float, float], ...] | None

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
        categorical_threshold=10.0,
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
    "bg_1": 0.007,
    "bg_2": 0.011,
    "bg_3": 0.017,
    "bg_4": 0.025,
    "bg_5": 0.025,
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

SEQUENTIAL_3400K_ANCHORS = (
    "#282527",
    "#51404F",
    "#7F5E69",
    "#A17C6C",
    "#C49D70",
    "#E2CDA1",
)

SEQUENTIAL_3400K_LIGHT_ANCHORS = (
    "#2A2424",
    "#524150",
    "#7B616B",
    "#9B7F73",
    "#BC9D73",
    "#E8CA9C",
)

FAMILIES = (
    FamilyDefinition(
        slug="3400k-dark",
        name="3400K Dark",
        mode="dark",
        profile=PROFILES["3400k"],
        surfaces={
            "bg_0": "#050404",
            "bg_1": "#13100F",
            "bg_2": "#1E1918",
            "bg_3": "#29211F",
            "bg_4": "#322926",
            "bg_5": "#322926",
            "fg_0": "#DCD9BF",
            "fg_1": "#9B9784",
            "fg_2": "#7D7564",
        },
        background_surface_values=("#050404", "#13100F", "#1E1918", "#29211F", "#322926"),
        background_role_indices=(0, 1, 2, 3, 4, 4),
        # Six moderate-chroma hues are composed for both unshifted daytime use and
        # the transformed view. Thin lines also receive dash and marker cues.
        categorical_colors=("#DEA460", "#6BA0DE", "#C7779E", "#71CFA5", "#2B8B7F", "#915E42"),
        categorical_semantic_slots=(
            "primary warm",
            "cool blue/cyan",
            "secondary warm/red",
            "green/mint",
            "teal",
            "earth/brown",
        ),
        categorical_transformed_targets=(
            "#DE7932",
            "#6B7675",
            "#C75854",
            "#719957",
            "#2B6743",
            "#914623",
        ),
        daylight_minimum_delta_e_ok=15.0,
        daylight_minimum_hue_gap_degrees=20.0,
        categorical_shifted_background_contrast_minimum=3.0,
        categorical_daylight_minimum_foreground_delta_e_ok=6.0,
        categorical_night_minimum_foreground_delta_e_ok=5.0,
        terminal_colors=("#F7B7AA", "#7BB48F", "#BE8236", "#A4C0FC", "#D486C3", "#69EBD5"),
        terminal_transformed_targets=(
            "#F7875A",
            "#7B854C",
            "#BE601C",
            "#A48E86",
            "#D46367",
            "#69AE71",
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
        foreground_daylight_maximum_adjacent_delta_e_ok=21.0,
        foreground_night_minimum_adjacent_delta_e_ok=9.0,
        foreground_night_maximum_adjacent_delta_e_ok=18.0,
        foreground_minimum_lightness_gap_ratio=0.50,
        foreground_daylight_minimum_lightness_share=0.98,
        foreground_night_minimum_lightness_share=0.98,
        foreground_maximum_hue_span_degrees=16.0,
        foreground_night_maximum_hue_span_degrees=4.0,
        foreground_maximum_chroma=0.036,
        foreground_daylight_minimum_chroma_vector_cosine=0.96,
        foreground_night_minimum_chroma_vector_cosine=0.997,
        foreground_chroma_direction="decreasing",
        foreground_chroma_order_tolerance=0.003,
        sequential_anchors=("#282527", "#4D3D4A", "#765863", "#9D796C", "#C39E75", "#E2CDA1"),
        sequential_rgb=DARK_SEQUENTIAL_RGB["3400k-dark"],
    ),
    FamilyDefinition(
        slug="3400k-light",
        name="3400K Light",
        mode="light",
        profile=PROFILES["3400k"],
        surfaces={
            "bg_0": "#F9F9F8",
            "bg_1": "#ECECEB",
            "bg_2": "#E0E0DD",
            "bg_3": "#D5D3D0",
            "bg_4": "#CAC7C3",
            "bg_5": "#BFBCB5",
            "fg_0": "#342F2C",
            "fg_1": "#4D4540",
            "fg_2": "#665C54",
        },
        background_surface_values=(
            "#F9F9F8",
            "#ECECEB",
            "#E0E0DD",
            "#D5D3D0",
            "#CAC7C3",
            "#BFBCB5",
        ),
        background_role_indices=(0, 1, 2, 3, 4, 5),
        categorical_colors=("#B25809", "#4081D2", "#84499C", "#6C8D38", "#016869", "#70002D"),
        categorical_semantic_slots=None,
        categorical_transformed_targets=(
            "#B24105",
            "#405F6F",
            "#843653",
            "#6C681E",
            "#014D38",
            "#700018",
        ),
        daylight_minimum_delta_e_ok=16.0,
        daylight_minimum_hue_gap_degrees=30.0,
        categorical_shifted_background_contrast_minimum=3.0,
        categorical_daylight_minimum_foreground_delta_e_ok=8.0,
        categorical_night_minimum_foreground_delta_e_ok=5.0,
        terminal_colors=("#98074F", "#517304", "#844601", "#396EDB", "#8339A7", "#0B7F8C"),
        terminal_transformed_targets=(
            "#98052A",
            "#515502",
            "#843401",
            "#395174",
            "#832A59",
            "#0B5E4A",
        ),
        terminal_ansi_indices=(0, 1, 2, 3, 4, 5),
        terminal_night_groups=(0, 1, 2, 3, 4, 5),
        terminal_daylight_minimum_delta_e_ok=14.0,
        terminal_night_minimum_delta_e_ok=7.5,
        terminal_daylight_minimum_fg_0_delta_e_ok=9.0,
        terminal_night_minimum_fg_0_delta_e_ok=6.0,
        terminal_daylight_minimum_fg_1_delta_e_ok=9.0,
        terminal_night_minimum_fg_1_delta_e_ok=6.0,
        terminal_daylight_minimum_fg_2_delta_e_ok=9.0,
        terminal_night_minimum_fg_2_delta_e_ok=6.5,
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
        sequential_anchors=SEQUENTIAL_3400K_LIGHT_ANCHORS,
        sequential_rgb=None,
    ),
    FamilyDefinition(
        slug="2000k-dark",
        name="2000K Dark",
        mode="dark",
        profile=PROFILES["2000k"],
        surfaces={
            "bg_0": "#050404",
            "bg_1": "#171312",
            "bg_2": "#171312",
            "bg_3": "#251F1D",
            "bg_4": "#322926",
            "bg_5": "#322926",
            "fg_0": "#ECDCBF",
            "fg_1": "#B4AA8E",
            "fg_2": "#8D8570",
        },
        background_surface_values=("#050404", "#171312", "#251F1D", "#322926"),
        background_role_indices=(0, 1, 1, 2, 3, 3),
        # The four transformed identities remain distinct and clear 3:1 against bg_0.
        # Their daytime preimages deliberately use unrelated hue families: weak blue is
        # optimization freedom, not a cross-state appearance-preservation constraint.
        categorical_colors=("#E99894", "#54B7E2", "#A36043", "#A8EDB1"),
        categorical_semantic_slots=(
            "primary warm",
            "cool blue/cyan",
            "secondary warm/red",
            "green/mint",
        ),
        categorical_transformed_targets=("#E9530E", "#546313", "#A33406", "#A88110"),
        daylight_minimum_delta_e_ok=14.0,
        daylight_minimum_hue_gap_degrees=20.0,
        categorical_shifted_background_contrast_minimum=3.0,
        categorical_daylight_minimum_foreground_delta_e_ok=9.0,
        categorical_night_minimum_foreground_delta_e_ok=5.5,
        terminal_colors=("#F490AC", "#85EEB8", "#C29E39", "#A9C6FC"),
        terminal_transformed_targets=("#F44E0E", "#85810F", "#C25605", "#A96C17"),
        terminal_ansi_indices=(0, 1, 2, 3, 0, 1),
        terminal_night_groups=(0, 1, 2, 3),
        terminal_daylight_minimum_delta_e_ok=12.5,
        terminal_night_minimum_delta_e_ok=6.0,
        terminal_daylight_minimum_fg_0_delta_e_ok=12.5,
        terminal_night_minimum_fg_0_delta_e_ok=7.5,
        terminal_daylight_minimum_fg_1_delta_e_ok=7.5,
        terminal_night_minimum_fg_1_delta_e_ok=2.5,
        terminal_daylight_minimum_fg_2_delta_e_ok=6.0,
        terminal_night_minimum_fg_2_delta_e_ok=4.0,
        foreground_daylight_minimum_adjacent_delta_e_ok=12.0,
        foreground_daylight_maximum_adjacent_delta_e_ok=17.0,
        foreground_night_minimum_adjacent_delta_e_ok=9.0,
        foreground_night_maximum_adjacent_delta_e_ok=13.0,
        foreground_minimum_lightness_gap_ratio=0.70,
        foreground_daylight_minimum_lightness_share=0.99,
        foreground_night_minimum_lightness_share=0.96,
        foreground_maximum_hue_span_degrees=9.0,
        foreground_night_maximum_hue_span_degrees=2.5,
        foreground_maximum_chroma=0.043,
        foreground_daylight_minimum_chroma_vector_cosine=0.98,
        foreground_night_minimum_chroma_vector_cosine=0.999,
        foreground_chroma_direction="decreasing",
        foreground_chroma_order_tolerance=0.003,
        sequential_anchors=("#17110F", "#3D2B31", "#684657", "#986979", "#C79B8E", "#F2D9AE"),
        sequential_rgb=DARK_SEQUENTIAL_RGB["2000k-dark"],
    ),
    FamilyDefinition(
        slug="1200k-dark",
        name="1200K Dark",
        mode="dark",
        profile=PROFILES["1200k"],
        surfaces={
            "bg_0": "#050404",
            "bg_1": "#171313",
            "bg_2": "#171313",
            "bg_3": "#261F1D",
            "bg_4": "#322926",
            "bg_5": "#322926",
            "fg_0": "#FFFBEE",
            "fg_1": "#CDC4BA",
            "fg_2": "#A1978F",
        },
        background_surface_values=("#050404", "#171313", "#261F1D", "#322926"),
        background_role_indices=(0, 1, 1, 2, 3, 3),
        # Three warm transformed identities clear 3:1 against bg_0. Their daytime
        # preimages use blue's exact null direction for a mature rose/sky/apricot triad;
        # category identity is stable, but cross-state hue appearance is intentionally not.
        categorical_colors=("#F3AC74", "#8DEEFF", "#B76270"),
        categorical_semantic_slots=("primary warm", "cool blue/cyan", "secondary warm/red"),
        categorical_transformed_targets=("#F33500", "#8D4A01", "#B71E00"),
        daylight_minimum_delta_e_ok=20.0,
        daylight_minimum_hue_gap_degrees=45.0,
        categorical_shifted_background_contrast_minimum=3.0,
        categorical_daylight_minimum_foreground_delta_e_ok=6.0,
        categorical_night_minimum_foreground_delta_e_ok=4.4,
        terminal_colors=("#F68F96", "#C8FFC4", "#DED872"),
        terminal_transformed_targets=("#F62C00", "#C84F00", "#DE4300"),
        terminal_ansi_indices=(0, 1, 2, 2, 0, 1),
        terminal_night_groups=(0, 1, 2),
        terminal_daylight_minimum_delta_e_ok=9.4,
        terminal_night_minimum_delta_e_ok=4.0,
        terminal_daylight_minimum_fg_0_delta_e_ok=9.4,
        terminal_night_minimum_fg_0_delta_e_ok=4.0,
        terminal_daylight_minimum_fg_1_delta_e_ok=6.0,
        terminal_night_minimum_fg_1_delta_e_ok=3.0,
        terminal_daylight_minimum_fg_2_delta_e_ok=5.0,
        terminal_night_minimum_fg_2_delta_e_ok=3.5,
        foreground_daylight_minimum_adjacent_delta_e_ok=14.0,
        foreground_daylight_maximum_adjacent_delta_e_ok=17.0,
        foreground_night_minimum_adjacent_delta_e_ok=9.0,
        foreground_night_maximum_adjacent_delta_e_ok=11.0,
        foreground_minimum_lightness_gap_ratio=0.85,
        foreground_daylight_minimum_lightness_share=0.99,
        foreground_night_minimum_lightness_share=0.94,
        foreground_maximum_hue_span_degrees=32.0,
        foreground_night_maximum_hue_span_degrees=1.0,
        foreground_maximum_chroma=0.018,
        foreground_daylight_minimum_chroma_vector_cosine=0.85,
        foreground_night_minimum_chroma_vector_cosine=0.999,
        foreground_chroma_direction="decreasing",
        foreground_chroma_order_tolerance=0.003,
        sequential_anchors=("#100C0B", "#37242F", "#633E58", "#95657F", "#C8A099", "#FFE5B8"),
        sequential_rgb=DARK_SEQUENTIAL_RGB["1200k-dark"],
    ),
)
