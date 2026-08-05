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
            fill=_rgb(surfaces["foreground"]),
        )
        day_count = family["terminal_daylight_color_count"]
        night_count = family["terminal_semantic_color_count"]
        draw.text(
            (1030, y + 22),
            f"ANSI accents: {day_count} day · {night_count} night",
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
            baseline = y + 82 + (line_number - 1) * 53
            if line_number == 3:
                draw.rounded_rectangle(
                    (38, baseline - 6, width - 40, baseline + 42),
                    radius=6,
                    fill=_rgb(surfaces["selection"]),
                )
            draw.text(
                (46, baseline),
                f"{line_number:>2}",
                font=code_font,
                fill=_rgb(surfaces["foreground"]),
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
            fill=_rgb(surfaces["foreground"]),
        )

        heat_x, heat_y, cell = 42, y + 112, 25
        draw.text(
            (heat_x, y + 74),
            "Sequential heatmap",
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

        colorbar_y = heat_y + 218
        for index, color in enumerate(continuous):
            colorbar_x = heat_x + round(index * 400 / 256)
            draw.line((colorbar_x, colorbar_y, colorbar_x, colorbar_y + 10), fill=_rgb(color))
        draw.text(
            (heat_x, colorbar_y + 14),
            "low",
            font=small_font,
            fill=_rgb(surfaces["foreground"]),
        )
        draw.text(
            (heat_x + 354, colorbar_y + 18),
            "high",
            font=small_font,
            fill=_rgb(surfaces["foreground"]),
        )

        bar_x, bar_y, bar_w, bar_h = 500, y + 112, 400, 218
        draw.text(
            (bar_x, y + 74),
            "Categorical bars",
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
                fill=_rgb(surfaces["foreground_soft"]),
            )

        plot_x, plot_y, plot_w, plot_h = 990, y + 112, 500, 218
        draw.text(
            (plot_x, y + 74),
            "Series: color + dash + marker + label",
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
    return """<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="390" viewBox="0 0 1180 390">
<rect width="1180" height="390" rx="18" fill="#282522"/>
<text x="38" y="52" fill="#ded0b2" font-size="32" font-family="system-ui">Warm filters compress the available color dimensions</text>
<text x="38" y="86" fill="#b3a48d" font-size="20" font-family="system-ui">Each rail shows how much commanded red, green, and blue survives the transform.</text>
<g font-family="ui-monospace, monospace" font-size="21">
<text x="38" y="158" fill="#d2c2a5">3400 K</text><text x="38" y="238" fill="#d2c2a5">2000 K</text><text x="38" y="318" fill="#d2c2a5">1200 K</text>
<g transform="translate(150 126)"><rect width="300" height="30" rx="5" fill="#a86658"/><rect x="315" width="222" height="30" rx="5" fill="#859a65"/><rect x="552" width="159" height="30" rx="5" fill="#6e7e91"/><text x="730" y="23" fill="#e0d2b9">R 100% · G 74% · B 53%</text></g>
<g transform="translate(150 206)"><rect width="300" height="30" rx="5" fill="#a86658"/><rect x="315" width="163" height="30" rx="5" fill="#7c8355"/><rect x="493" width="26" height="30" rx="5" fill="#4f5661"/><text x="540" y="23" fill="#e0d2b9">R 100% · G 54% · B 9%</text></g>
<g transform="translate(150 286)"><rect width="300" height="30" rx="5" fill="#a86658"/><rect x="315" width="93" height="30" rx="5" fill="#6d6a47"/><rect x="423" width="3" height="30" fill="#4f5661"/><text x="446" y="23" fill="#e0d2b9">R 100% · G 31% · B 0%</text></g>
</g><text x="150" y="360" fill="#b3a48d" font-size="19" font-family="system-ui">The lost channels create room to improve daytime colors without disturbing the transformed view.</text></svg>"""


def redundant_encoding_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="390" viewBox="0 0 1180 390">
<rect width="1180" height="390" rx="18" fill="#2c211d"/><text x="38" y="52" fill="#f2d9b5" font-size="32" font-family="system-ui">At deep red, color supports identity rather than carrying it alone</text>
<text x="38" y="86" fill="#b8a184" font-size="20" font-family="system-ui">Direct labels, dash patterns, and markers remain distinct when hue collapses.</text>
<g transform="translate(50 125)" fill="none"><path d="M0 110 C80 15 165 190 270 75 S445 135 520 35" stroke="#e0c49a" stroke-width="6"/><circle cx="520" cy="35" r="9" fill="#e0c49a"/><path d="M0 145 C95 60 175 175 280 115 S440 35 520 100" stroke="#b08e76" stroke-width="6" stroke-dasharray="18 12"/><rect x="511" y="91" width="18" height="18" fill="#b08e76"/><path d="M0 60 C95 150 195 15 290 90 S440 170 520 125" stroke="#8f8a6a" stroke-width="6" stroke-dasharray="4 11"/><path d="M520 114 L509 135 L531 135 Z" fill="#8f8a6a"/></g>
<g font-family="ui-monospace, monospace" font-size="22"><text x="620" y="170" fill="#e0c49a">A  solid + circle</text><text x="620" y="230" fill="#b08e76">B  dashed + square</text><text x="620" y="290" fill="#8f8a6a">C  dotted + triangle</text></g>
<text x="620" y="340" fill="#b8a184" font-size="20" font-family="system-ui">Labels sit beside the lines they identify.</text></svg>"""


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
        "| Family | Categories | Day min ΔEOK | Shifted min ΔEOK | Mean / max raw chroma | Min shifted terminal contrast |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for family in manifest["families"].values():
        categorical = family["metrics"]["categorical"]
        lines.append(
            f"| {family['name']} | {len(family['categorical'])} | "
            f"{categorical['normal_min_delta_e_ok']:.2f} | "
            f"{categorical['shifted_min_delta_e_ok']:.2f} | "
            f"{categorical['normal_chroma_mean']:.4f} / {categorical['normal_chroma_max']:.4f} | "
            f"{family['terminal_minimum_shifted_foreground_contrast']:.2f}:1 |"
        )
    lines.extend(
        [
            "",
            "Release gates: categorical commanded mean chroma 0.09–0.105 and maximum",
            "chroma ≤ 0.111; family-specific daytime and transformed separation floors;",
            "transformed terminal foreground-capable ANSI slots ≥ 4.5:1; category and",
            "accent counts must never increase as the target temperature falls.",
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
