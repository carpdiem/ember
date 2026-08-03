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
    srgb_to_oklab,
    wcag_luminance,
)


def _rgb(value: str) -> tuple[int, int, int]:
    return tuple(round(channel * 255) for channel in hex_to_srgb(value))


def _blend_rgb(foreground: str, background: str, weight: float) -> tuple[int, int, int]:
    foreground_rgb = hex_to_srgb(foreground)
    background_rgb = hex_to_srgb(background)
    mixed = background_rgb * (1.0 - weight) + foreground_rgb * weight
    return tuple(round(channel * 255) for channel in mixed)


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
    width, header, row_height = 1500, 64, 292
    families = list(manifest["families"].values())
    image = Image.new("RGB", (width, header + row_height * len(families)), "#171512")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default(size=22)
    code_font = ImageFont.load_default(size=24)
    label_font = ImageFont.load_default(size=18)
    draw.text(
        (24, 18),
        "Generated terminal specimen · commanded sRGB",
        font=title_font,
        fill="#D7C8AC",
    )

    for row, family in enumerate(families):
        y = header + row * row_height
        surfaces = family["surfaces"]
        terminal = family["terminal"]
        draw.rounded_rectangle(
            (18, y + 8, width - 18, y + row_height - 10),
            radius=12,
            fill=_rgb(surfaces["background"]),
            outline=_rgb(surfaces["background_high"]),
            width=2,
        )
        draw.rectangle((20, y + 10, width - 20, y + 43), fill=_rgb(surfaces["background_alt"]))
        draw.text(
            (36, y + 18),
            family["name"],
            font=label_font,
            fill=_rgb(surfaces["foreground"]),
        )
        count = family["terminal_semantic_color_count"]
        draw.text(
            (1120, y + 18),
            f"{count} semantic accents · ANSI aliases repeated",
            font=label_font,
            fill=_rgb(surfaces["foreground"]),
        )

        lines = [
            [
                ("def ", terminal["magenta"]),
                ("shifted_distance", terminal["cyan"]),
                ("(colors, gains):", surfaces["foreground"]),
            ],
            [
                (
                    "    # Measure what survives the display transform",
                    surfaces["foreground"],
                ),
            ],
            [
                ("    shifted", terminal["blue"]),
                (" = ", surfaces["foreground"]),
                ("colors", terminal["cyan"]),
                (" * ", surfaces["foreground"]),
                ("gains", terminal["yellow"]),
            ],
            [
                ("    return ", terminal["magenta"]),
                ("pairwise_oklab", terminal["cyan"]),
                ("(shifted)", surfaces["foreground"]),
            ],
            [
                ("$ ", terminal["green"]),
                ("pytest -q", surfaces["foreground"]),
                ("     tests passed", terminal["green"]),
                (" · generated example", surfaces["foreground"]),
            ],
        ]
        for line_number, segments in enumerate(lines, start=1):
            baseline = y + 60 + (line_number - 1) * 42
            if line_number == 3:
                draw.rounded_rectangle(
                    (34, baseline - 4, width - 36, baseline + 31),
                    radius=4,
                    fill=_rgb(surfaces["selection"]),
                )
            draw.text(
                (40, baseline),
                f"{line_number:>2}",
                font=code_font,
                fill=_rgb(surfaces["foreground"]),
            )
            _draw_segments(draw, (84, baseline), segments, code_font)

    destination.mkdir(parents=True, exist_ok=True)
    image.save(destination / "terminal-commanded.png", optimize=True)
    simulated = image.copy()
    simulated_draw = ImageDraw.Draw(simulated)
    simulated_draw.rectangle((0, 0, width, header), fill="#171512")
    simulated_draw.text(
        (24, 18),
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
    radius = 4
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
    width, header, row_height = 1500, 64, 330
    families = list(manifest["families"].values())
    image = Image.new("RGB", (width, header + row_height * len(families)), "#171512")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default(size=22)
    label_font = ImageFont.load_default(size=16)
    small_font = ImageFont.load_default(size=14)
    draw.text(
        (24, 18),
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
            (18, y + 8, width - 18, y + row_height - 10),
            radius=12,
            fill=_rgb(surfaces["background"]),
            outline=_rgb(surfaces["background_high"]),
            width=2,
        )
        draw.text(
            (36, y + 20),
            family["name"],
            font=label_font,
            fill=_rgb(surfaces["foreground"]),
        )

        heat_x, heat_y, cell = 36, y + 62, 22
        draw.text(
            (heat_x, y + 42),
            "heatmap",
            font=small_font,
            fill=_rgb(surfaces["foreground_muted"]),
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

        colorbar_y = heat_y + 190
        for index, color in enumerate(continuous):
            colorbar_x = heat_x + round(index * 352 / 256)
            draw.line((colorbar_x, colorbar_y, colorbar_x, colorbar_y + 10), fill=_rgb(color))
        draw.text(
            (heat_x, colorbar_y + 14),
            "low",
            font=small_font,
            fill=_rgb(surfaces["foreground"]),
        )
        draw.text(
            (heat_x + 320, colorbar_y + 14),
            "high",
            font=small_font,
            fill=_rgb(surfaces["foreground"]),
        )

        bar_x, bar_y, bar_w, bar_h = 430, y + 62, 330, 182
        draw.text(
            (bar_x, y + 42),
            "categories",
            font=small_font,
            fill=_rgb(surfaces["foreground_muted"]),
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
                fill=_blend_rgb(color, surfaces["background"], 0.30),
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
                (left + 4, bar_y + bar_h + 8),
                chr(65 + index),
                font=small_font,
                fill=_rgb(surfaces["foreground_soft"]),
            )

        plot_x, plot_y, plot_w, plot_h = 825, y + 62, 500, 182
        draw.text(
            (plot_x, y + 42),
            "overlapping series · color + dash + marker + direct label",
            font=small_font,
            fill=_rgb(surfaces["foreground_muted"]),
        )
        axis = _rgb(surfaces["foreground_muted"])
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
                        width=3,
                    )
            for marker_index in range(series + 2, 25, 6):
                marker_x, marker_y = points[marker_index]
                _draw_marker(draw, marker_x, marker_y, color_rgb, series)
            series_endpoints.append((points[-1], color_rgb, series))
        for (endpoint_x, endpoint_y), color_rgb, series in series_endpoints:
            _draw_marker(draw, endpoint_x, endpoint_y, color_rgb, series)
            draw.text(
                (endpoint_x + 10, endpoint_y - 8),
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
        (24, 18),
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
    return """<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="330" viewBox="0 0 1180 330">
<rect width="1180" height="330" rx="18" fill="#282522"/>
<text x="34" y="42" fill="#ded0b2" font-size="22" font-family="system-ui">The warm filter squeezes three channels toward one</text>
<text x="34" y="72" fill="#9b8d79" font-size="14" font-family="system-ui">Each rail shows how much of a commanded channel survives. Blue is gone at 1200 K.</text>
<g font-family="ui-monospace, monospace" font-size="14">
<text x="34" y="126" fill="#bda98e">3400 K</text><text x="34" y="192" fill="#bda98e">2000 K</text><text x="34" y="258" fill="#bda98e">1200 K</text>
<g transform="translate(130 98)"><rect width="300" height="22" rx="4" fill="#a86658"/><rect x="315" width="222" height="22" rx="4" fill="#859a65"/><rect x="552" width="159" height="22" rx="4" fill="#6e7e91"/><text x="725" y="17" fill="#d2c2a5">R 100% · G 74% · B 53%</text></g>
<g transform="translate(130 164)"><rect width="300" height="22" rx="4" fill="#a86658"/><rect x="315" width="163" height="22" rx="4" fill="#7c8355"/><rect x="493" width="26" height="22" rx="4" fill="#4f5661"/><text x="535" y="17" fill="#d2c2a5">R 100% · G 54% · B 9%</text></g>
<g transform="translate(130 230)"><rect width="300" height="22" rx="4" fill="#a86658"/><rect x="315" width="93" height="22" rx="4" fill="#6d6a47"/><rect x="423" width="2" height="22" fill="#4f5661"/><text x="445" y="17" fill="#d2c2a5">R 100% · G 31% · B 0%</text></g>
</g><path d="M1030 116 C1080 126 1080 240 1135 240" fill="none" stroke="#c49b6e" stroke-width="3"/><text x="900" y="286" fill="#d2c2a5" font-size="15" font-family="system-ui">Fewer honest colors</text><text x="900" y="307" fill="#9b8d79" font-size="13" font-family="system-ui">plus shape, dash, label</text></svg>"""


def redundant_encoding_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="330" viewBox="0 0 1180 330">
<rect width="1180" height="330" rx="18" fill="#2c211d"/><text x="34" y="42" fill="#f2d9b5" font-size="22" font-family="system-ui">At deep red, color becomes a hint—not the identity</text>
<text x="34" y="72" fill="#a28b70" font-size="14" font-family="system-ui">Direct labels, dash patterns, and markers survive even when hue collapses.</text>
<g transform="translate(45 105)" fill="none"><path d="M0 100 C80 15 160 175 260 70 S430 125 500 35" stroke="#e0c49a" stroke-width="4"/><circle cx="500" cy="35" r="6" fill="#e0c49a"/><path d="M0 130 C90 55 170 155 270 105 S420 35 500 95" stroke="#b08e76" stroke-width="4" stroke-dasharray="14 9"/><rect x="494" y="89" width="12" height="12" fill="#b08e76"/><path d="M0 55 C90 135 190 15 280 80 S420 155 500 115" stroke="#8f8a6a" stroke-width="4" stroke-dasharray="3 8"/><path d="M500 108 L493 121 L507 121 Z" fill="#8f8a6a"/></g>
<g font-family="ui-monospace, monospace" font-size="15"><text x="565" y="145" fill="#e0c49a">A — solid + circle</text><text x="565" y="205" fill="#b08e76">B — dashed + square</text><text x="565" y="225" fill="#8f8a6a">C — dotted + triangle</text></g>
<text x="565" y="273" fill="#a28b70" font-size="14" font-family="system-ui">The label sits on the line it identifies.</text></svg>"""


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
        "## Palette-level comfort gates",
        "",
        "| Family | Categories | Terminal accents | Max raw Oklab chroma | Min shifted category ΔEOK | Min shifted terminal contrast |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for family in manifest["families"].values():
        categorical = family["metrics"]["categorical"]
        lines.append(
            f"| {family['name']} | {len(family['categorical'])} | "
            f"{family['terminal_semantic_color_count']} | "
            f"{categorical['normal_chroma_max']:.4f} | "
            f"{categorical['shifted_min_delta_e_ok']:.2f} | "
            f"{family['terminal_minimum_shifted_foreground_contrast']:.2f}:1 |"
        )
    lines.extend(
        [
            "",
            "Release gates: categorical commanded chroma ≤ 0.09; transformed terminal",
            "foreground-capable ANSI slots ≥ 4.5:1; category and accent counts must never",
            "increase as the target temperature falls.",
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
