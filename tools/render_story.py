"""Deterministic, mobile-readable visual story for the Ember README opening."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from redshift_safe.color import (  # noqa: I001  # pyright: ignore[reportMissingImports]
    hex_to_srgb,
    warm_transform,
)


CANVAS = "#171512"
PANEL = "#211E1A"
PRIMARY = "#F2E3C8"
SECONDARY = "#BFAF98"
RULE = "#3B342C"


def _rgb(value: str) -> tuple[int, int, int]:
    return tuple(round(channel * 255) for channel in hex_to_srgb(value))


def _state_rgb(value: str, gains: list[float], transformed: bool) -> tuple[int, int, int]:
    color = hex_to_srgb(value)
    if transformed:
        color = warm_transform(color, gains)
    return tuple(round(channel * 255) for channel in color)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _draw_text_segments(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    segments: list[tuple[str, tuple[int, int, int]]],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    x, y = position
    for text, color in segments:
        draw.text((x, y), text, font=font, fill=color)
        x += round(draw.textlength(text, font=font))


def _render_palette_story(manifest: dict, path: Path) -> None:
    width, header, section_height, footer = 760, 126, 160, 72
    families = list(manifest["families"].values())
    height = header + section_height * len(families) + footer
    image = Image.new("RGB", (width, height), CANVAS)
    draw = ImageDraw.Draw(image)

    draw.text(
        (24, 20),
        "You ask for these colors. The filter leaves you these.",
        font=_font(28),
        fill=PRIMARY,
    )
    draw.text(
        (24, 62),
        "Each lower row is the exact upper row multiplied by that profile's RGB gains.",
        font=_font(17),
        fill=SECONDARY,
    )
    draw.text((146, 102), "DISTINCT SERIES / STATES", font=_font(14), fill=SECONDARY)
    draw.text((520, 102), "ORDERED DATA / LOW TO HIGH", font=_font(14), fill=SECONDARY)

    for row, family in enumerate(families):
        y = header + row * section_height
        profile = manifest["profiles"][family["profile"]]
        gains = profile["rgb_gains"]
        categorical = list(family["categorical"].values())
        count = len(categorical)

        if row:
            draw.line((24, y, width - 24, y), fill=RULE, width=1)
        draw.text((24, y + 12), family["name"], font=_font(21), fill=PRIMARY)
        draw.text(
            (width - 226, y + 16),
            f"{count} supported identities",
            font=_font(15),
            fill=SECONDARY,
        )

        state_rows = ((False, y + 45), (True, y + 105))
        for transformed, state_y in state_rows:
            state_title = "AFTER FILTER" if transformed else "ASKED FOR"
            draw.text((24, state_y + 12), state_title, font=_font(15), fill=PRIMARY)

            swatch_x, swatch_width, gap = 146, 336, 6
            each = (swatch_width - gap * (count - 1)) / count
            for index, color in enumerate(categorical):
                left = round(swatch_x + index * (each + gap))
                right = round(left + each)
                draw.rounded_rectangle(
                    (left, state_y, right, state_y + 42),
                    radius=5,
                    fill=_state_rgb(color, gains, transformed),
                )

            gradient_x, gradient_width = 520, 216
            sequence = family["continuous_hex8"]
            for index, color in enumerate(sequence):
                x = gradient_x + round(index * gradient_width / len(sequence))
                next_x = gradient_x + round((index + 1) * gradient_width / len(sequence))
                draw.rectangle(
                    (x, state_y, max(x + 1, next_x), state_y + 42),
                    fill=_state_rgb(color, gains, transformed),
                )

    footer_y = header + section_height * len(families)
    draw.rounded_rectangle((24, footer_y + 10, width - 24, height - 14), radius=12, fill=PANEL)
    draw.text(
        (42, footer_y + 20),
        "At 1200 K, blue x 0: colors that differed only in blue become the same pixel.",
        font=_font(16),
        fill=PRIMARY,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def _draw_terminal_pane(
    draw: ImageDraw.ImageDraw,
    family: dict,
    gains: list[float],
    transformed: bool,
    box: tuple[int, int, int, int],
) -> None:
    left, top, right, _bottom = box
    surfaces = family["surfaces"]
    terminal = family["terminal"]
    state = lambda value: _state_rgb(value, gains, transformed)

    draw.rounded_rectangle(
        box,
        radius=12,
        fill=state(surfaces["bg_0"]),
        outline=state(surfaces["bg_2"]),
        width=2,
    )
    draw.rectangle((left + 2, top + 2, right - 2, top + 34), fill=state(surfaces["bg_1"]))
    label = "FILTER ON / modeled output" if transformed else "FILTER OFF / app-requested terminal"
    draw.text((left + 14, top + 8), label, font=_font(15), fill=state(surfaces["fg_0"]))

    code_font = _font(19)
    lines = [
        [
            ("def ", state(terminal["magenta"])),
            ("shifted_distance", state(terminal["cyan"])),
            ("(colors, gains):", state(surfaces["fg_0"])),
        ],
        [
            ("  shifted", state(terminal["blue"])),
            (" = ", state(surfaces["fg_0"])),
            ("colors", state(terminal["cyan"])),
            (" x ", state(surfaces["fg_0"])),
            ("gains", state(terminal["yellow"])),
        ],
        [
            ("$ pytest -q   ", state(surfaces["fg_0"])),
            ("tests passed", state(terminal["green"])),
            (" / metadata", state(surfaces["fg_2"])),
        ],
    ]
    for index, segments in enumerate(lines):
        y = top + 46 + index * 28
        if index == 1:
            draw.rounded_rectangle(
                (left + 10, y - 3, right - 10, y + 24),
                radius=5,
                fill=state(surfaces["bg_5"]),
            )
        _draw_text_segments(draw, (left + 18, y), segments, code_font)


def _render_terminal_story(manifest: dict, path: Path) -> None:
    width, header, section_height, footer = 760, 112, 384, 62
    slugs = ("3400k-dark", "1200k-dark")
    height = header + section_height * len(slugs) + footer
    image = Image.new("RGB", (width, height), CANVAS)
    draw = ImageDraw.Draw(image)

    draw.text((24, 18), "Terminal hierarchy survives the transform", font=_font(30), fill=PRIMARY)
    draw.text(
        (24, 60),
        "Same code and selection. Only the modeled display signal changes.",
        font=_font(17),
        fill=SECONDARY,
    )

    callouts = {
        "3400k-dark": "6 accents remain distinct; text and selection keep their hierarchy.",
        "1200k-dark": "Blue is gone. Ember uses 3 honest accents; text and labels carry the rest.",
    }
    profile_labels = {
        "3400k-dark": "MODERATE FILTER / 6 ACCENTS",
        "1200k-dark": "EXTREME FILTER / 3 ACCENTS",
    }

    for index, slug in enumerate(slugs):
        family = manifest["families"][slug]
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        y = header + index * section_height
        if index:
            draw.line((24, y, width - 24, y), fill=RULE)
        draw.text((24, y + 14), family["name"], font=_font(22), fill=PRIMARY)
        draw.text((442, y + 19), profile_labels[slug], font=_font(14), fill=SECONDARY)
        _draw_terminal_pane(draw, family, gains, False, (24, y + 48, width - 24, y + 178))
        draw.text(
            (24, y + 189),
            f"same pixels x RGB [{', '.join(f'{gain:.2f}' for gain in gains)}]",
            font=_font(14),
            fill=SECONDARY,
        )
        _draw_terminal_pane(draw, family, gains, True, (24, y + 216, width - 24, y + 346))
        draw.text((24, y + 355), callouts[slug], font=_font(16), fill=PRIMARY)

    footer_y = header + section_height * len(slugs)
    draw.text(
        (24, footer_y + 18),
        "Success means preserved hierarchy and meaning; not preserving every daytime hue.",
        font=_font(16),
        fill=SECONDARY,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def _draw_marker(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    color: tuple[int, int, int],
    shape: int,
    radius: int = 5,
) -> None:
    if shape % 3 == 0:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    elif shape % 3 == 1:
        draw.rectangle((x - radius, y - radius, x + radius, y + radius), fill=color)
    else:
        draw.polygon(
            ((x, y - radius - 1), (x - radius - 1, y + radius), (x + radius + 1, y + radius)),
            fill=color,
        )


def _draw_data_pane(
    draw: ImageDraw.ImageDraw,
    family: dict,
    gains: list[float],
    transformed: bool,
    box: tuple[int, int, int, int],
) -> None:
    left, top, right, _bottom = box
    surfaces = family["surfaces"]
    categorical = list(family["categorical"].values())
    sequence = family["continuous_hex8"]
    state = lambda value: _state_rgb(value, gains, transformed)

    draw.rounded_rectangle(
        box,
        radius=12,
        fill=state(surfaces["bg_0"]),
        outline=state(surfaces["bg_2"]),
        width=2,
    )
    draw.rectangle((left + 2, top + 2, right - 2, top + 32), fill=state(surfaces["bg_1"]))
    label = "FILTER ON / modeled output" if transformed else "FILTER OFF / app-requested charts"
    draw.text((left + 12, top + 7), label, font=_font(15), fill=state(surfaces["fg_0"]))

    titles_y = top + 40
    draw.text((left + 14, titles_y), "ORDERED VALUE", font=_font(15), fill=state(surfaces["fg_2"]))
    draw.text(
        (left + 222, titles_y), "DISTINCT CATEGORIES", font=_font(15), fill=state(surfaces["fg_2"])
    )
    draw.text(
        (left + 440, titles_y), "LABELED SERIES", font=_font(15), fill=state(surfaces["fg_2"])
    )

    heat_x, heat_y, cell = left + 14, top + 62, 12
    for iy in range(6):
        for ix in range(14):
            value = 0.58 * ix / 13 + 0.42 * (5 - iy) / 5 + 0.08 * np.sin(ix + iy)
            color = sequence[int(np.clip(value, 0.0, 1.0) * 255)]
            draw.rectangle(
                (
                    heat_x + ix * cell,
                    heat_y + iy * cell,
                    heat_x + (ix + 1) * cell,
                    heat_y + (iy + 1) * cell,
                ),
                fill=state(color),
            )
    draw.text((heat_x, heat_y + 78), "low", font=_font(14), fill=state(surfaces["fg_1"]))
    draw.text((heat_x + 140, heat_y + 78), "high", font=_font(14), fill=state(surfaces["fg_1"]))

    bar_x, bar_y, bar_w, bar_h = left + 222, top + 64, 188, 72
    gap = 5
    each = (bar_w - gap * (len(categorical) - 1)) // len(categorical)
    values = (0.72, 0.50, 0.88, 0.62, 0.42, 0.78)
    for index, color in enumerate(categorical):
        bar_height = round(bar_h * values[index])
        x = bar_x + index * (each + gap)
        y = bar_y + bar_h - bar_height
        color_rgb = state(color)
        draw.rounded_rectangle(
            (x, y, x + each, bar_y + bar_h), radius=2, outline=color_rgb, width=2
        )
        if index % 3 == 0:
            for hatch_x in range(x + 4, x + each, 7):
                draw.line((hatch_x, y + 3, hatch_x, bar_y + bar_h - 2), fill=color_rgb)
        elif index % 3 == 1:
            for hatch_y in range(y + 5, bar_y + bar_h, 7):
                draw.line((x + 2, hatch_y, x + each - 2, hatch_y), fill=color_rgb)
        else:
            for dot_y in range(y + 5, bar_y + bar_h, 8):
                for dot_x in range(x + 4, x + each, 8):
                    draw.point((dot_x, dot_y), fill=color_rgb)
        draw.text(
            (x + max(0, each // 2 - 3), bar_y + bar_h + 3),
            chr(65 + index),
            font=_font(12),
            fill=state(surfaces["fg_1"]),
        )

    plot_x, plot_y, plot_w, plot_h = left + 440, top + 64, 250, 78
    axis = state(surfaces["fg_2"])
    draw.line((plot_x, plot_y + plot_h, plot_x + plot_w, plot_y + plot_h), fill=axis)
    for series, color in enumerate(categorical):
        color_rgb = state(color)
        points = []
        for step in range(17):
            progress = step / 16
            x = plot_x + round(progress * plot_w)
            wave = np.sin(step * 0.55 + series * 0.9) * 0.18
            endpoint = 0.16 + series * 0.68 / max(1, len(categorical) - 1)
            blend = np.clip((progress - 0.70) / 0.30, 0.0, 1.0)
            normalized_y = (0.50 - wave) * (1.0 - blend) + endpoint * blend
            points.append((x, plot_y + round(plot_h * normalized_y)))
        period = series + 2
        for segment in range(len(points) - 1):
            if series == 0 or segment % period != period - 1:
                draw.line((*points[segment], *points[segment + 1]), fill=color_rgb, width=3)
        for marker_index in range(series + 2, len(points), 6):
            marker_x, marker_y = points[marker_index]
            _draw_marker(draw, marker_x, marker_y, color_rgb, series, radius=3)
        end_x, end_y = points[-1]
        _draw_marker(draw, end_x, end_y, color_rgb, series, radius=4)
        draw.text((end_x + 7, end_y - 7), chr(65 + series), font=_font(12), fill=color_rgb)


def _render_data_story(manifest: dict, path: Path) -> None:
    width, header, section_height, footer = 760, 112, 450, 62
    slugs = ("3400k-dark", "1200k-dark")
    height = header + section_height * len(slugs) + footer
    image = Image.new("RGB", (width, height), CANVAS)
    draw = ImageDraw.Draw(image)

    draw.text((24, 18), "Charts keep order, identity, and structure", font=_font(30), fill=PRIMARY)
    draw.text(
        (24, 60),
        "Color carries meaning; labels, markers, and patterns make that meaning harder to lose.",
        font=_font(16),
        fill=SECONDARY,
    )

    callouts = {
        "3400k-dark": "6 categories remain distinct; the heatmap still reads low to high.",
        "1200k-dark": "3 categories survive; labels, markers, and patterns carry the rest.",
    }
    profile_labels = {
        "3400k-dark": "MODERATE FILTER / 6 CATEGORIES",
        "1200k-dark": "EXTREME FILTER / 3 CATEGORIES",
    }

    for index, slug in enumerate(slugs):
        family = manifest["families"][slug]
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        y = header + index * section_height
        if index:
            draw.line((24, y, width - 24, y), fill=RULE)
        draw.text((24, y + 14), family["name"], font=_font(22), fill=PRIMARY)
        draw.text((426, y + 19), profile_labels[slug], font=_font(14), fill=SECONDARY)
        _draw_data_pane(draw, family, gains, False, (24, y + 48, width - 24, y + 206))
        draw.text(
            (24, y + 216),
            f"same pixels x RGB [{', '.join(f'{gain:.2f}' for gain in gains)}]",
            font=_font(14),
            fill=SECONDARY,
        )
        _draw_data_pane(draw, family, gains, True, (24, y + 244, width - 24, y + 402))
        draw.text((24, y + 407), callouts[slug], font=_font(15), fill=PRIMARY)

    footer_y = header + section_height * len(slugs)
    draw.text(
        (24, footer_y + 18),
        "The palette protects the signal; redundant encoding protects the message.",
        font=_font(16),
        fill=SECONDARY,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def render_readme_story(manifest: dict, destination: Path) -> None:
    """Render the three causal figures used at the top of the README."""

    _render_palette_story(manifest, destination / "swatches/command-vs-simulated.png")
    _render_terminal_story(manifest, destination / "samples/terminal-story.png")
    _render_data_story(manifest, destination / "samples/data-story.png")
