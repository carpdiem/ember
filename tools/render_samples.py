"""Deterministic terminal, data, and explainer visuals for the Ember README."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from redshift_safe.color import (  # pyright: ignore[reportMissingImports]
    hex_to_srgb,
    srgb_to_hex,
    srgb_to_oklab,
    warm_transform,
    wcag_luminance,
)


def _rgb(value: str) -> tuple[int, int, int]:
    return tuple(round(channel * 255) for channel in hex_to_srgb(value))


def _blend_rgb(foreground: str, background: str, weight: float) -> tuple[int, int, int]:
    foreground_rgb = hex_to_srgb(foreground)
    background_rgb = hex_to_srgb(background)
    mixed = background_rgb * (1.0 - weight) + foreground_rgb * weight
    return tuple(round(channel * 255) for channel in mixed)


def _shift_hex(value: str, gains: list[float]) -> str:
    return srgb_to_hex(warm_transform(hex_to_srgb(value), gains))


def _transform_box(
    image: Image.Image,
    box: tuple[int, int, int, int],
    gains: list[float],
) -> None:
    region = np.asarray(image.crop(box).convert("RGB"), dtype=float) / 255.0
    transformed = np.clip(region * np.asarray(gains), 0.0, 1.0)
    pixels = np.rint(transformed * 255.0).astype(np.uint8)
    image.paste(Image.fromarray(pixels), box[:2])


def _draw_segments(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    segments: list[tuple[str, str]],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    x, y = position
    for text, color in segments:
        draw.text((x, y), text, font=font, fill=_rgb(color))
        x += round(draw.textlength(text, font=font))


def _terminal_samples(manifest: dict, destination: Path) -> None:
    width, header, row_height = 1600, 88, 370
    families = list(manifest["families"].values())
    image = Image.new("RGB", (width, header + row_height * len(families)), "#171512")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default(size=36)
    code_font = ImageFont.load_default(size=34)
    label_font = ImageFont.load_default(size=28)
    draw.text(
        (32, 24),
        "Generated terminal specimen · commanded sRGB",
        font=title_font,
        fill="#D7C8AC",
    )

    for row, family in enumerate(families):
        y = header + row * row_height
        surfaces = family["surfaces"]
        terminal = family["terminal"]
        draw.rounded_rectangle(
            (22, y + 10, width - 22, y + row_height - 12),
            radius=16,
            fill=_rgb(surfaces["bg_0"]),
            outline=_rgb(surfaces["bg_2"]),
            width=2,
        )
        draw.rectangle((24, y + 12, width - 24, y + 64), fill=_rgb(surfaces["bg_1"]))
        draw.text(
            (42, y + 22),
            family["name"],
            font=label_font,
            fill=_rgb(surfaces["fg_0"]),
        )
        day_count = family["terminal_daylight_color_count"]
        night_count = family["terminal_semantic_color_count"]
        draw.text(
            (1030, y + 22),
            f"ANSI accents: {day_count} day · {night_count} night",
            font=label_font,
            fill=_rgb(surfaces["fg_0"]),
        )

        lines = [
            [
                ("def ", terminal["magenta"]),
                ("shifted_distance", terminal["cyan"]),
                ("(colors, gains):", surfaces["fg_0"]),
            ],
            [
                (
                    "    # Measure what survives the display transform",
                    surfaces["fg_1"],
                ),
            ],
            [
                ("    shifted", terminal["blue"]),
                (" = ", surfaces["fg_0"]),
                ("colors", terminal["cyan"]),
                (" * ", surfaces["fg_0"]),
                ("gains", terminal["yellow"]),
            ],
            [
                ("    return ", terminal["magenta"]),
                ("pairwise_oklab", terminal["cyan"]),
                ("(shifted)", surfaces["fg_0"]),
            ],
            [
                ("$ ", terminal["green"]),
                ("pytest -q", surfaces["fg_0"]),
                ("     tests passed", terminal["green"]),
                (" · generated example", surfaces["fg_2"]),
            ],
        ]
        for line_number, segments in enumerate(lines, start=1):
            baseline = y + 82 + (line_number - 1) * 53
            if line_number == 3:
                draw.rounded_rectangle(
                    (38, baseline - 6, width - 40, baseline + 42),
                    radius=6,
                    fill=_rgb(surfaces["bg_5"]),
                )
            draw.text(
                (46, baseline),
                f"{line_number:>2}",
                font=code_font,
                fill=_rgb(surfaces["fg_0"]),
            )
            _draw_segments(draw, (104, baseline), segments, code_font)

    destination.mkdir(parents=True, exist_ok=True)
    image.save(destination / "terminal-commanded.png", optimize=True)
    simulated = image.copy()
    simulated_draw = ImageDraw.Draw(simulated)
    simulated_draw.rectangle((0, 0, width, header), fill="#171512")
    simulated_draw.text(
        (32, 24),
        "Generated terminal specimen · simulated target transforms",
        font=title_font,
        fill="#D7C8AC",
    )
    header_gains = manifest["profiles"][families[0]["profile"]]["rgb_gains"]
    _transform_box(simulated, (0, 0, width, header), header_gains)
    for row, family in enumerate(families):
        y = header + row * row_height
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        _transform_box(simulated, (0, y, width, y + row_height), gains)
    simulated.save(destination / "terminal-simulated.png", optimize=True)


def _draw_marker(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    color: tuple[int, int, int],
    shape: int,
) -> None:
    radius = 7
    if shape % 3 == 0:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    elif shape % 3 == 1:
        draw.rectangle((x - radius, y - radius, x + radius, y + radius), fill=color)
    else:
        draw.polygon(
            (
                (x, y - radius - 1),
                (x - radius - 1, y + radius),
                (x + radius + 1, y + radius),
            ),
            fill=color,
        )


def _data_samples(manifest: dict, destination: Path) -> None:
    width, header, row_height = 1600, 88, 450
    families = list(manifest["families"].values())
    image = Image.new("RGB", (width, header + row_height * len(families)), "#171512")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default(size=36)
    label_font = ImageFont.load_default(size=30)
    small_font = ImageFont.load_default(size=24)
    draw.text(
        (32, 24),
        "Generated data specimen · commanded sRGB",
        font=title_font,
        fill="#D7C8AC",
    )

    for row, family in enumerate(families):
        y = header + row * row_height
        surfaces = family["surfaces"]
        categorical = list(family["categorical"].values())
        continuous = family["continuous_hex8"]
        draw.rounded_rectangle(
            (22, y + 10, width - 22, y + row_height - 12),
            radius=16,
            fill=_rgb(surfaces["bg_0"]),
            outline=_rgb(surfaces["bg_2"]),
            width=2,
        )
        draw.text(
            (42, y + 22),
            family["name"],
            font=label_font,
            fill=_rgb(surfaces["fg_0"]),
        )

        heat_x, heat_y, cell = 42, y + 112, 25
        draw.text(
            (heat_x, y + 74),
            "Sequential heatmap",
            font=small_font,
            fill=_rgb(surfaces["fg_2"]),
        )
        for iy in range(8):
            for ix in range(16):
                value = 0.55 * ix / 15 + 0.45 * (7 - iy) / 7 + 0.10 * np.sin(ix + iy)
                index = int(np.clip(value, 0.0, 1.0) * 255)
                draw.rectangle(
                    (
                        heat_x + ix * cell,
                        heat_y + iy * cell,
                        heat_x + (ix + 1) * cell,
                        heat_y + (iy + 1) * cell,
                    ),
                    fill=_rgb(continuous[index]),
                )

        colorbar_y = heat_y + 218
        for index, color in enumerate(continuous):
            colorbar_x = heat_x + round(index * 400 / 256)
            draw.line((colorbar_x, colorbar_y, colorbar_x, colorbar_y + 10), fill=_rgb(color))
        draw.text(
            (heat_x, colorbar_y + 14),
            "low",
            font=small_font,
            fill=_rgb(surfaces["fg_0"]),
        )
        draw.text(
            (heat_x + 354, colorbar_y + 18),
            "high",
            font=small_font,
            fill=_rgb(surfaces["fg_0"]),
        )

        bar_x, bar_y, bar_w, bar_h = 500, y + 112, 400, 218
        draw.text(
            (bar_x, y + 74),
            "Categorical bars",
            font=small_font,
            fill=_rgb(surfaces["fg_2"]),
        )
        values = (0.78, 0.56, 0.91, 0.68, 0.47, 0.82)
        gap = 10
        each = (bar_w - gap * (len(categorical) - 1)) // len(categorical)
        for index, color in enumerate(categorical):
            height = round(bar_h * values[index])
            left = bar_x + index * (each + gap)
            draw.rounded_rectangle(
                (left, bar_y + bar_h - height, left + each, bar_y + bar_h),
                radius=3,
                fill=_blend_rgb(color, surfaces["bg_0"], 0.30),
                outline=_rgb(color),
                width=2,
            )
            top = bar_y + bar_h - height
            if index % 3 == 0:
                for hatch_x in range(left + 8, left + each, 12):
                    draw.line((hatch_x, top + 3, hatch_x, bar_y + bar_h - 3), fill=_rgb(color))
            elif index % 3 == 1:
                for hatch_y in range(top + 8, bar_y + bar_h, 12):
                    draw.line((left + 3, hatch_y, left + each - 3, hatch_y), fill=_rgb(color))
            else:
                for hatch_y in range(top + 8, bar_y + bar_h, 14):
                    for hatch_x in range(left + 8, left + each, 14):
                        draw.ellipse(
                            (hatch_x - 1, hatch_y - 1, hatch_x + 1, hatch_y + 1),
                            fill=_rgb(color),
                        )
            draw.text(
                (left + 6, bar_y + bar_h + 12),
                chr(65 + index),
                font=small_font,
                fill=_rgb(surfaces["fg_1"]),
            )

        plot_x, plot_y, plot_w, plot_h = 990, y + 112, 500, 218
        draw.text(
            (plot_x, y + 74),
            "Series: color + dash + marker + label",
            font=small_font,
            fill=_rgb(surfaces["fg_2"]),
        )
        axis = _rgb(surfaces["fg_2"])
        draw.line((plot_x, plot_y + plot_h, plot_x + plot_w, plot_y + plot_h), fill=axis)
        draw.line((plot_x, plot_y, plot_x, plot_y + plot_h), fill=axis)
        series_endpoints = []
        for series, color in enumerate(categorical):
            points = []
            for step in range(25):
                progress = step / 24
                px = plot_x + round(step * plot_w / 24)
                wave = np.sin(step * 0.42 + series * 0.9) * 0.18
                trend = (progress - 0.5) * (0.10 - series * 0.01)
                base = 0.50 - wave - trend
                endpoint = 0.16 + series * 0.68 / max(1, len(categorical) - 1)
                endpoint_blend = np.clip((progress - 0.72) / 0.28, 0.0, 1.0)
                normalized_y = base * (1.0 - endpoint_blend) + endpoint * endpoint_blend
                py = plot_y + round(plot_h * normalized_y)
                points.append((px, py))
            color_rgb = _rgb(color)
            dash_period = series + 2
            for segment in range(len(points) - 1):
                if series == 0 or segment % dash_period != dash_period - 1:
                    draw.line(
                        (*points[segment], *points[segment + 1]),
                        fill=color_rgb,
                        width=5,
                    )
            for marker_index in range(series + 2, 25, 6):
                marker_x, marker_y = points[marker_index]
                _draw_marker(draw, marker_x, marker_y, color_rgb, series)
            series_endpoints.append((points[-1], color_rgb, series))
        for (endpoint_x, endpoint_y), color_rgb, series in series_endpoints:
            _draw_marker(draw, endpoint_x, endpoint_y, color_rgb, series)
            draw.text(
                (endpoint_x + 12, endpoint_y - 12),
                chr(65 + series),
                font=small_font,
                fill=color_rgb,
            )

    destination.mkdir(parents=True, exist_ok=True)
    image.save(destination / "data-commanded.png", optimize=True)
    simulated = image.copy()
    simulated_draw = ImageDraw.Draw(simulated)
    simulated_draw.rectangle((0, 0, width, header), fill="#171512")
    simulated_draw.text(
        (32, 24),
        "Generated data specimen · simulated target transforms",
        font=title_font,
        fill="#D7C8AC",
    )
    header_gains = manifest["profiles"][families[0]["profile"]]["rgb_gains"]
    _transform_box(simulated, (0, 0, width, header), header_gains)
    for row, family in enumerate(families):
        y = header + row * row_height
        gains = manifest["profiles"][family["profile"]]["rgb_gains"]
        _transform_box(simulated, (0, y, width, y + row_height), gains)
    simulated.save(destination / "data-simulated.png", optimize=True)


def channel_collapse_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="760" height="760" viewBox="0 0 760 760">
<rect width="760" height="760" rx="22" fill="#1B1815"/>
<g font-family="system-ui, sans-serif">
<text x="36" y="54" fill="#F0DFC0" font-size="32" font-weight="700">A warm filter removes color dimensions</text>
<text x="36" y="90" fill="#BFAF98" font-size="21">Bar length = fraction of each commanded channel that survives.</text>

<g transform="translate(36 136)">
  <text x="0" y="0" fill="#E7D3B0" font-size="28" font-weight="700">3400 K</text>
  <text x="164" y="0" fill="#BFAF98" font-size="21">R 100% · G 74% · B 53%</text>
  <g transform="translate(0 26)" font-size="20" font-family="ui-monospace, monospace">
    <text x="0" y="24" fill="#E8B8A7">R</text><rect x="34" width="640" height="28" rx="7" fill="#352A26"/><rect x="34" width="640" height="28" rx="7" fill="#C87865"/>
    <text x="0" y="66" fill="#BBD8AE">G</text><rect x="34" y="42" width="640" height="28" rx="7" fill="#2A3128"/><rect x="34" y="42" width="473" height="28" rx="7" fill="#82A36F"/>
    <text x="0" y="108" fill="#AFC5E5">B</text><rect x="34" y="84" width="640" height="28" rx="7" fill="#252A32"/><rect x="34" y="84" width="339" height="28" rx="7" fill="#6F86A8"/>
  </g>
</g>

<g transform="translate(36 354)">
  <text x="0" y="0" fill="#E7D3B0" font-size="28" font-weight="700">2000 K</text>
  <text x="164" y="0" fill="#BFAF98" font-size="21">R 100% · G 54% · B 9%</text>
  <g transform="translate(0 26)" font-size="20" font-family="ui-monospace, monospace">
    <text x="0" y="24" fill="#E8B8A7">R</text><rect x="34" width="640" height="28" rx="7" fill="#352A26"/><rect x="34" width="640" height="28" rx="7" fill="#C87865"/>
    <text x="0" y="66" fill="#BBD8AE">G</text><rect x="34" y="42" width="640" height="28" rx="7" fill="#2A3128"/><rect x="34" y="42" width="348" height="28" rx="7" fill="#7B8A5A"/>
    <text x="0" y="108" fill="#AFC5E5">B</text><rect x="34" y="84" width="640" height="28" rx="7" fill="#252A32"/><rect x="34" y="84" width="56" height="28" rx="7" fill="#576477"/>
  </g>
</g>

<g transform="translate(36 572)">
  <text x="0" y="0" fill="#E7D3B0" font-size="28" font-weight="700">1200 K</text>
  <text x="164" y="0" fill="#BFAF98" font-size="21">R 100% · G 31% · B 0%</text>
  <g transform="translate(0 26)" font-size="20" font-family="ui-monospace, monospace">
    <text x="0" y="24" fill="#E8B8A7">R</text><rect x="34" width="640" height="28" rx="7" fill="#352A26"/><rect x="34" width="640" height="28" rx="7" fill="#C87865"/>
    <text x="0" y="66" fill="#BBD8AE">G</text><rect x="34" y="42" width="640" height="28" rx="7" fill="#2A3128"/><rect x="34" y="42" width="198" height="28" rx="7" fill="#736D49"/>
    <text x="0" y="108" fill="#AFC5E5">B</text><rect x="34" y="84" width="640" height="28" rx="7" fill="#252A32"/><rect x="34" y="84" width="2" height="28" fill="#4B5260"/>
  </g>
</g>
</g></svg>"""


def redundant_encoding_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="760" height="830" viewBox="0 0 760 830">
<rect width="760" height="830" rx="22" fill="#1B1512"/>
<g font-family="system-ui, sans-serif">
<text x="36" y="54" fill="#F2D9B5" font-size="32" font-weight="700">When hue compresses, color alone is fragile</text>
<text x="36" y="90" fill="#BFA98C" font-size="21">The same transformed colors are used in both charts.</text>

<g transform="translate(36 126)">
  <text x="0" y="0" fill="#F0A991" font-size="27" font-weight="700">Wrong: identity lives only in hue</text>
  <rect x="0" y="24" width="688" height="270" rx="14" fill="#090402" stroke="#53200F" stroke-width="2"/>
  <path d="M34 210 C120 70 215 250 330 115 S540 180 625 62" fill="none" stroke="#F22D00" stroke-width="7"/>
  <path d="M34 238 C130 115 235 230 345 165 S535 72 625 145" fill="none" stroke="#C94F00" stroke-width="7"/>
  <path d="M34 112 C130 220 245 62 355 142 S535 245 625 205" fill="none" stroke="#DD3F00" stroke-width="7"/>
  <text x="24" y="328" fill="#A9846E" font-size="20">At crossings and small sizes, A/B/C become guesswork.</text>
</g>

<g transform="translate(36 492)">
  <text x="0" y="0" fill="#C8E8AC" font-size="27" font-weight="700">Ember: color + pattern + marker + label</text>
  <rect x="0" y="24" width="688" height="270" rx="14" fill="#090402" stroke="#53200F" stroke-width="2"/>
  <path d="M34 210 C120 70 215 250 330 115 S540 180 625 62" fill="none" stroke="#F22D00" stroke-width="7"/>
  <circle cx="625" cy="62" r="10" fill="#F22D00"/><text x="644" y="70" fill="#F57A59" font-size="24" font-weight="700">A</text>
  <path d="M34 238 C130 115 235 230 345 165 S535 72 625 145" fill="none" stroke="#C94F00" stroke-width="7" stroke-dasharray="20 13"/>
  <rect x="615" y="135" width="20" height="20" fill="#C94F00"/><text x="644" y="154" fill="#D88942" font-size="24" font-weight="700">B</text>
  <path d="M34 112 C130 220 245 62 355 142 S535 245 625 205" fill="none" stroke="#DD3F00" stroke-width="7" stroke-dasharray="4 12"/>
  <path d="M625 193 L613 215 L637 215 Z" fill="#DD3F00"/><text x="644" y="214" fill="#EA865B" font-size="24" font-weight="700">C</text>
</g>
</g></svg>"""


def failure_modes_svg(manifest: dict) -> str:
    """Show three common failures using the exact authored transforms and colors."""

    gains_1200 = manifest["profiles"]["1200k"]["rgb_gains"]
    gains_2000 = manifest["profiles"]["2000k"]["rgb_gains"]
    family_1200 = manifest["families"]["1200k-dark"]
    family_2000 = manifest["families"]["2000k-dark"]

    naive_cyan = "#8BC1FF"
    naive_chartreuse = "#8BC100"
    collapsed = _shift_hex(naive_cyan, gains_1200)
    assert collapsed == _shift_hex(naive_chartreuse, gains_1200)

    ordinary_canvas = "#282828"
    ember_canvas = family_1200["surfaces"]["bg_0"]
    ordinary_shifted = _shift_hex(ordinary_canvas, gains_1200)
    ember_shifted = _shift_hex(ember_canvas, gains_1200)
    ordinary_luminance = wcag_luminance(hex_to_srgb(ordinary_shifted))
    ember_luminance = wcag_luminance(hex_to_srgb(ember_shifted))

    pure_white = "#FFFFFF"
    ember_text = family_2000["surfaces"]["fg_0"]
    pure_white_shifted = _shift_hex(pure_white, gains_2000)
    ember_text_shifted = _shift_hex(ember_text, gains_2000)
    background_2000 = _shift_hex(family_2000["surfaces"]["bg_0"], gains_2000)
    accent_2000 = _shift_hex(family_2000["terminal"]["red"], gains_2000)

    accent_targets = [
        _shift_hex(family_1200["terminal"][role], gains_1200)
        for role in ("red", "green", "yellow")
    ]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="760" height="1250" viewBox="0 0 760 1250">
<rect width="760" height="1250" rx="22" fill="#171411"/>
<g font-family="system-ui, sans-serif">
<text x="36" y="54" fill="#F1DFC0" font-size="32" font-weight="700">Why ordinary palettes fail</text>
<text x="36" y="91" fill="#F1DFC0" font-size="32" font-weight="700">under aggressive warm shifts</text>
<text x="36" y="126" fill="#BFAE96" font-size="21">Every transformed swatch below uses Ember's exact signal model.</text>

<g transform="translate(36 172)">
  <text x="0" y="0" fill="#E7D1AC" font-size="27" font-weight="700">1 · Daytime colors can become identical</text>
  <text x="0" y="34" fill="#BFAE96" font-size="20">At 1200 K, blue is removed. These commands differ only in blue.</text>
  <text x="0" y="82" fill="#D98DA1" font-size="20" font-weight="700">Naive commands</text>
  <rect x="0" y="100" width="214" height="78" rx="10" fill="{naive_cyan}"/><text x="18" y="149" fill="#151310" font-size="21" font-family="ui-monospace, monospace">{naive_cyan}</text>
  <rect x="232" y="100" width="214" height="78" rx="10" fill="{naive_chartreuse}"/><text x="250" y="149" fill="#151310" font-size="21" font-family="ui-monospace, monospace">{naive_chartreuse}</text>
  <path d="M472 139 H520" stroke="#BFAE96" stroke-width="4"/><path d="M520 139 l-14 -9 v18 z" fill="#BFAE96"/>
  <rect x="540" y="100" width="148" height="78" rx="10" fill="{collapsed}"/><text x="554" y="149" fill="#FFF0D8" font-size="20" font-family="ui-monospace, monospace">same</text>
  <text x="0" y="218" fill="#B8D89F" font-size="20" font-weight="700">Ember target identities</text>
  <rect x="0" y="236" width="214" height="64" rx="10" fill="{accent_targets[0]}"/>
  <rect x="232" y="236" width="214" height="64" rx="10" fill="{accent_targets[1]}"/>
  <rect x="464" y="236" width="214" height="64" rx="10" fill="{accent_targets[2]}"/>
</g>

<g transform="translate(36 532)">
  <text x="0" y="0" fill="#E7D1AC" font-size="27" font-weight="700">2 · Ordinary dark gray becomes a rust field</text>
  <text x="0" y="34" fill="#BFAE96" font-size="20">Large surfaces amplify the filter. Near-black keeps the canvas quiet.</text>
  <text x="0" y="80" fill="#D98DA1" font-size="20" font-weight="700">Ordinary dark theme</text>
  <rect x="0" y="98" width="324" height="122" rx="12" fill="{ordinary_shifted}" stroke="#75401E" stroke-width="2"/>
  <text x="18" y="146" fill="#F3D3B4" font-size="21" font-family="ui-monospace, monospace">{ordinary_canvas} → {ordinary_shifted}</text>
  <text x="18" y="184" fill="#D9AE8C" font-size="19">modeled luminance {ordinary_luminance:.5f}</text>
  <text x="360" y="80" fill="#B8D89F" font-size="20" font-weight="700">Ember 1200K canvas</text>
  <rect x="360" y="98" width="324" height="122" rx="12" fill="{ember_shifted}" stroke="#4C2B1C" stroke-width="2"/>
  <text x="378" y="146" fill="#F3D3B4" font-size="21" font-family="ui-monospace, monospace">{ember_canvas} → {ember_shifted}</text>
  <text x="378" y="184" fill="#D9AE8C" font-size="19">modeled luminance {ember_luminance:.5f}</text>
</g>

<g transform="translate(36 842)">
  <text x="0" y="0" fill="#E7D1AC" font-size="27" font-weight="700">3 · Pure white becomes the loudest warm signal</text>
  <text x="0" y="34" fill="#BFAE96" font-size="20">At 2000 K, neutral source text turns orange. Restraint still matters.</text>
  <text x="0" y="80" fill="#D98DA1" font-size="20" font-weight="700">Pure white everywhere</text>
  <rect x="0" y="98" width="324" height="196" rx="12" fill="{background_2000}" stroke="#5A260F" stroke-width="2"/>
  <text x="18" y="143" fill="{pure_white_shifted}" font-size="24" font-family="ui-monospace, monospace">{pure_white} → {pure_white_shifted}</text>
  <text x="18" y="187" fill="{pure_white_shifted}" font-size="23" font-family="ui-monospace, monospace">Every glyph competes.</text>
  <text x="18" y="231" fill="{pure_white_shifted}" font-size="23" font-family="ui-monospace, monospace">Nothing is quiet.</text>
  <text x="360" y="80" fill="#B8D89F" font-size="20" font-weight="700">Ember neutral + sparse color</text>
  <rect x="360" y="98" width="324" height="196" rx="12" fill="{background_2000}" stroke="#5A260F" stroke-width="2"/>
  <text x="378" y="143" fill="{ember_text_shifted}" font-size="24" font-family="ui-monospace, monospace">{ember_text} → {ember_text_shifted}</text>
  <text x="378" y="187" fill="{ember_text_shifted}" font-size="23" font-family="ui-monospace, monospace">Body text stays primary.</text>
  <text x="378" y="231" fill="{accent_2000}" font-size="23" font-family="ui-monospace, monospace">Color marks meaning.</text>
</g>
</g></svg>"""


def render_samples(manifest: dict, destination: Path) -> None:
    _terminal_samples(manifest, destination)
    _data_samples(manifest, destination)


def _image_metrics(path: Path) -> dict[str, float]:
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=float) / 255.0
    lab = srgb_to_oklab(rgb)
    chroma = np.linalg.norm(lab[..., 1:], axis=-1)
    luminance = wcag_luminance(rgb)
    horizontal = np.abs(np.diff(luminance, axis=1))
    vertical = np.abs(np.diff(luminance, axis=0))
    edge_count = np.count_nonzero(horizontal > 0.25) + np.count_nonzero(vertical > 0.25)
    edge_total = horizontal.size + vertical.size
    return {
        "high_contrast_edge_fraction": float(edge_count / edge_total),
        "high_chroma_pixel_fraction": float(np.mean(chroma > 0.12)),
        "chroma_p99": float(np.quantile(chroma, 0.99)),
    }


def sample_analysis_markdown(manifest: dict, destination: Path) -> str:
    image_names = (
        "terminal-commanded.png",
        "terminal-simulated.png",
        "data-commanded.png",
        "data-simulated.png",
    )
    lines = [
        "# Sample-screen analysis",
        "",
        "Generated from the exact README screenshots. These image-level diagnostics are",
        "guardrails, not a model of eye strain: they detect saturation and abrupt luminance",
        "edges but cannot substitute for long-duration viewing on real hardware.",
        "",
        "## Palette-level bi-state gates",
        "",
        "| Family | Categories | Day min ΔEOK | Day min hue gap | Shifted min ΔEOK | Min shifted category / bg contrast | Mean / max raw chroma | Terminal day / shifted min to fg_0 | Terminal day / shifted min to fg_1 | Terminal day / shifted min to fg_2 | FG ladder day / shifted adjacent min | Min shifted terminal contrast |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for family in manifest["families"].values():
        categorical = family["metrics"]["categorical"]
        lines.append(
            f"| {family['name']} | {len(family['categorical'])} | "
            f"{categorical['normal_min_delta_e_ok']:.2f} | "
            f"{categorical['normal_minimum_hue_gap_degrees']:.2f}° | "
            f"{categorical['shifted_min_delta_e_ok']:.2f} | "
            f"{categorical['minimum_shifted_background_contrast']:.2f}:1 | "
            f"{categorical['normal_chroma_mean']:.4f} / {categorical['normal_chroma_max']:.4f} | "
            f"{family['metrics']['terminal']['normal_min_delta_e_ok_to_foregrounds']['fg_0']:.2f} / "
            f"{family['metrics']['terminal']['shifted_min_delta_e_ok_to_foregrounds']['fg_0']:.2f} | "
            f"{family['metrics']['terminal']['normal_min_delta_e_ok_to_foregrounds']['fg_1']:.2f} / "
            f"{family['metrics']['terminal']['shifted_min_delta_e_ok_to_foregrounds']['fg_1']:.2f} | "
            f"{family['metrics']['terminal']['normal_min_delta_e_ok_to_foregrounds']['fg_2']:.2f} / "
            f"{family['metrics']['terminal']['shifted_min_delta_e_ok_to_foregrounds']['fg_2']:.2f} | "
            f"{min(family['metrics']['foreground_ladder']['normal_adjacent_delta_e_ok']):.2f} / "
            f"{min(family['metrics']['foreground_ladder']['shifted_adjacent_delta_e_ok']):.2f} | "
            f"{family['terminal_minimum_shifted_foreground_contrast']:.2f}:1 |"
        )
    lines.extend(
        [
            "",
            "Release gates: categorical commanded mean chroma 0.09–0.105 and maximum",
            "chroma ≤ 0.111; family-specific daytime, hue-gap, transformed-separation, and",
            "graphical category/background contrast floors; cross-state hue consistency is",
            "intentionally not required;",
            "authored transformed accent targets reproduced within 0.15 ΔEOK; transformed",
            "terminal foreground-capable ANSI slots ≥ 4.5:1; deep terminal accents also clear",
            "their day and transformed separation floors against every foreground role, while",
            "the foreground ladder preserves bounded adjacent distances, balanced lightness gaps,",
            "lightness-dominant steps, aligned chroma direction, and bounded hue/chroma; category",
            "and accent counts",
            "must never increase as the target temperature falls.",
            "",
            "## Screenshot-level diagnostics",
            "",
            "| Screenshot | High-contrast edge fraction | High-chroma pixel fraction | Oklab chroma p99 |",
            "|---|---:|---:|---:|",
        ]
    )
    for name in image_names:
        metrics = _image_metrics(destination / name)
        lines.append(
            f"| `{name}` | {metrics['high_contrast_edge_fraction']:.4%} | "
            f"{metrics['high_chroma_pixel_fraction']:.4%} | {metrics['chroma_p99']:.4f} |"
        )
    lines.extend(
        [
            "",
            "Interpretation: small high-contrast edge fractions are expected around glyphs,",
            "axes, and markers. Commanded high-chroma area should remain scarce. A deep warm",
            "transform itself makes most surviving pixels red, so transformed chroma is",
            "descriptive rather than a release gate. Lines use dash, marker, and text-label",
            "redundancy because no color metric can rescue information after the display",
            "transform removes a channel.",
            "",
        ]
    )
    return "\n".join(lines)
