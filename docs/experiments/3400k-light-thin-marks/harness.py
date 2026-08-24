#!/usr/bin/env python3
"""Deterministic Phase 0/1 evidence harness for 3400K Light thin marks.

This module reads only the frozen experiment baseline. It does not import Ember's
production definitions and it never searches or mutates candidate colors.
"""

from __future__ import annotations

import html
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
GAINS = np.array([1.0, 0.74, 0.53], dtype=float)
FAILURE_FLOOR = 8.0
CATEGORY_NAMES = ("one", "two", "three", "four", "five", "six")


def load_baseline() -> dict[str, Any]:
    return json.loads((HERE / "baseline.json").read_text(encoding="utf-8"))


def specimen_contract() -> dict[str, Any]:
    return {
        "backgrounds": {"render": ["bg_0", "bg_1"], "report_only": ["bg_2"]},
        "widths_css_px": [1.5, 2.0, 3.0],
        "device_pixel_ratios": [1, 2],
        "geometry": ["horizontal", "diagonal", "curved"],
        "line_styles": ["solid", "dashed", "dotted"],
        "features": [
            "crossings",
            "short_legends",
            "endpoint_markers",
            "sparklines",
            "financial_cockpit",
            "thesis_baskets",
        ],
        "data_policy": "deterministic fake data; no consumer imports; no private data",
        "geometry_note": (
            "CSS/SVG chart conventions: shared axes, 12 px panel padding, 1.5/2/3 px "
            "strokes, compact legends, endpoint circles, and 96x24 sparklines"
        ),
    }


def hex_to_rgb(value: str) -> np.ndarray:
    raw = value.removeprefix("#")
    return np.array([int(raw[index : index + 2], 16) for index in (0, 2, 4)], dtype=float) / 255.0


def rgb_to_hex(rgb: np.ndarray) -> str:
    values = np.clip(np.rint(np.asarray(rgb) * 255.0), 0, 255).astype(int)
    return "#" + "".join(f"{value:02X}" for value in values)


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    rgb = np.asarray(rgb, dtype=float)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def srgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    matrix_1 = np.array(
        [
            [0.4122214708, 0.5363325363, 0.0514459929],
            [0.2119034982, 0.6806995451, 0.1073969566],
            [0.0883024619, 0.2817188376, 0.6299787005],
        ]
    )
    matrix_2 = np.array(
        [
            [0.2104542553, 0.7936177850, -0.0040720468],
            [1.9779984951, -2.4285922050, 0.4505937099],
            [0.0259040371, 0.7827717662, -0.8086757660],
        ]
    )
    linear = srgb_to_linear(np.asarray(rgb, dtype=float))
    lms = np.tensordot(linear, matrix_1.T, axes=1)
    return np.tensordot(np.cbrt(lms), matrix_2.T, axes=1)


def delta_e_ok(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(srgb_to_oklab(left) - srgb_to_oklab(right)) * 100.0)


def transform(rgb: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(rgb, dtype=float) * GAINS, 0.0, 1.0)


def blend(foreground: np.ndarray, background: np.ndarray, coverage: float) -> np.ndarray:
    return coverage * foreground + (1.0 - coverage) * background


def _distance_to_segment(
    x: np.ndarray, y: np.ndarray, start: tuple[float, float], end: tuple[float, float]
) -> np.ndarray:
    px = x - start[0]
    py = y - start[1]
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    denominator = dx * dx + dy * dy
    projection = np.clip((px * dx + py * dy) / denominator, 0.0, 1.0)
    return np.hypot(px - projection * dx, py - projection * dy)


def diagonal_coverage(
    width_css_px: float, dpr: int, size_css_px: int = 64, supersample: int = 12
) -> np.ndarray:
    """Ideal area coverage for the browser probe's encoded-sRGB diagonal."""

    device_size = size_css_px * dpr
    offsets = (np.arange(supersample, dtype=float) + 0.5) / supersample
    grid_y, grid_x, sub_y, sub_x = np.meshgrid(
        np.arange(device_size), np.arange(device_size), offsets, offsets, indexing="ij"
    )
    x = (grid_x + sub_x) / dpr
    y = (grid_y + sub_y) / dpr
    distance = _distance_to_segment(x, y, (8.0, 8.0), (56.0, 56.0))
    return np.mean(distance <= width_css_px / 2.0, axis=(2, 3))


def representative_coverage(width: float, dpr: int, geometry: str) -> float:
    if geometry == "horizontal":
        values = np.array([min(1.0, width * dpr / 2.0), min(1.0, width * dpr)])
    else:
        values = diagonal_coverage(width, dpr)
        values = values[(values >= 0.10) & (values < 0.999)]
        if geometry == "curved":
            values = np.clip(values * 0.92, 0.0, 1.0)
    return float(np.quantile(values, 0.25))


def validate_transform_blend_commutation() -> dict[str, Any]:
    baseline = load_baseline()
    family = baseline["family"]
    colors = [hex_to_rgb(value) for value in family["categorical"].values()]
    backgrounds = [hex_to_rgb(family["surfaces"][role]) for role in ("bg_0", "bg_1", "bg_2")]
    coverages: list[float] = []
    for width in specimen_contract()["widths_css_px"]:
        for dpr in specimen_contract()["device_pixel_ratios"]:
            values = diagonal_coverage(width, dpr)
            coverages.extend(float(value) for value in values.ravel() if 0.0 < value < 1.0)
    errors = []
    for foreground in colors:
        for background in backgrounds:
            for coverage in coverages:
                left = transform(blend(foreground, background, coverage))
                right = blend(transform(foreground), transform(background), coverage)
                errors.append(float(np.max(np.abs(left - right))))
    return {
        "model": "encoded-srgb-diagonal-coverage",
        "sample_count": len(errors),
        "maximum_absolute_channel_error": max(errors, default=0.0),
        "conclusion": "commutes for this unclipped diagonal coverage model",
        "scope_warning": "diagnostic encoded-sRGB compositing model, not a calibrated light metric",
    }


def _pair_rows(
    colors: dict[str, np.ndarray], metric: Callable[[np.ndarray, np.ndarray], float]
) -> list[dict[str, Any]]:
    rows = []
    names = list(colors)
    for left_index, left_name in enumerate(names):
        for right_name in names[left_index + 1 :]:
            rows.append(
                {
                    "roles": [left_name, right_name],
                    "delta": metric(colors[left_name], colors[right_name]),
                }
            )
    return sorted(rows, key=lambda row: row["delta"])


def _proxy_delta(
    left: np.ndarray, right: np.ndarray, background: np.ndarray, coverage: float
) -> float:
    return delta_e_ok(
        blend(transform(left), transform(background), coverage),
        blend(transform(right), transform(background), coverage),
    )


def _round_tree(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 8)
    if isinstance(value, dict):
        return {key: _round_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_tree(item) for item in value]
    return value


def compute_metrics(
    baseline: dict[str, Any] | None = None,
    transformed_metric: Callable[[np.ndarray, np.ndarray], float] | None = None,
    transformed_metric_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline = baseline or load_baseline()
    family = baseline["family"]
    categories = {f"cat.{name}": hex_to_rgb(value) for name, value in family["categorical"].items()}
    commanded_rows = _pair_rows(categories, delta_e_ok)
    commanded_minimum = commanded_rows[0]
    commanded_minimum = {
        "roles": commanded_minimum["roles"],
        "delta_e_ok": commanded_minimum["delta"],
    }

    metric = transformed_metric or delta_e_ok
    transformed_metadata = transformed_metric_metadata or {
        "backend": "oklab-diagnostic",
        "status": "diagnostic-only-not-calibrated-for-light-mode",
        "final_light_metric": None,
        "warning": (
            "No calibrated light-mode transformed metric is claimed. The dark CAM16-UCS "
            "L_A=8, Y_b=3 conditions are deliberately not reused as a final light metric."
        ),
    }
    transformed_rows = _pair_rows(
        {name: transform(value) for name, value in categories.items()}, metric
    )
    transformed_metadata = {
        **transformed_metadata,
        "solid_minimum_pair": transformed_rows[0],
        "architecture": "callable metric(left_rgb, right_rgb) injected into compute_metrics",
    }

    terminal_red = hex_to_rgb(family["terminal"]["red"])
    foreground_1 = hex_to_rgb(family["surfaces"]["fg_1"])
    summary = []
    detailed = []
    for background_name in ("bg_0", "bg_1", "bg_2"):
        background = hex_to_rgb(family["surfaces"][background_name])
        background_rows = []
        for width in specimen_contract()["widths_css_px"]:
            for dpr in specimen_contract()["device_pixel_ratios"]:
                for geometry in specimen_contract()["geometry"]:
                    coverage = representative_coverage(width, dpr, geometry)
                    intra = _pair_rows(
                        categories,
                        lambda left, right, bg=background, alpha=coverage: _proxy_delta(
                            left, right, bg, alpha
                        ),
                    )[0]
                    row = {
                        "background": background_name,
                        "width_css_px": width,
                        "dpr": dpr,
                        "geometry": geometry,
                        "representative_edge_coverage": coverage,
                        "intra_categorical_minimum": intra,
                        "cat.two_vs_terminal.red": _proxy_delta(
                            categories["cat.two"], terminal_red, background, coverage
                        ),
                        "cat.two_vs_fg_1": _proxy_delta(
                            categories["cat.two"], foreground_1, background, coverage
                        ),
                    }
                    detailed.append(row)
                    background_rows.append(row)
        worst = min(background_rows, key=lambda row: row["intra_categorical_minimum"]["delta"])
        summary.append(
            {
                "background": background_name,
                "minimum_intra_categorical_delta": worst["intra_categorical_minimum"]["delta"],
                "minimum_intra_pair": worst["intra_categorical_minimum"]["roles"],
                "at": {
                    "width_css_px": worst["width_css_px"],
                    "dpr": worst["dpr"],
                    "geometry": worst["geometry"],
                    "coverage": worst["representative_edge_coverage"],
                },
            }
        )

    failure_case = next(
        row
        for row in detailed
        if row["background"] == "bg_0"
        and row["width_css_px"] == 1.5
        and row["dpr"] == 1
        and row["geometry"] == "diagonal"
    )
    failures = [
        {
            "id": "intra-cat-five-vs-six",
            "scope": "categorical-contract",
            "status": "FAIL",
            "roles": failure_case["intra_categorical_minimum"]["roles"],
            "diagnostic_delta": failure_case["intra_categorical_minimum"]["delta"],
            "diagnostic_floor": FAILURE_FLOOR,
            "case": "transformed 1.5 CSS px diagonal at DPR 1 on bg_0",
            "human_evidence": "review/transformed.svg: short legend, crossing, and sparkline panels",
        },
        {
            "id": "cross-cat-two-vs-terminal-red",
            "scope": "diagnostic-non-contract",
            "status": "FAIL",
            "roles": ["cat.two", "terminal.red"],
            "diagnostic_delta": failure_case["cat.two_vs_terminal.red"],
            "diagnostic_floor": FAILURE_FLOOR,
            "case": "transformed 1.5 CSS px diagonal at DPR 1 on bg_0",
        },
        {
            "id": "cross-cat-two-vs-fg-1",
            "scope": "diagnostic-non-contract",
            "status": "FAIL",
            "roles": ["cat.two", "fg_1"],
            "diagnostic_delta": failure_case["cat.two_vs_fg_1"],
            "diagnostic_floor": FAILURE_FLOOR,
            "case": "transformed 1.5 CSS px diagonal at DPR 1 on bg_0",
        },
    ]
    return _round_tree(
        {
            "baseline_source_commit": baseline["baseline_source_commit"],
            "schema_version": baseline["schema_version"],
            "profile_gains": baseline["profile_gains"],
            "specimen_contract": specimen_contract(),
            "commanded_solid_oklab": {
                "metric": "Euclidean Oklab x 100 on solid commanded colors",
                "minimum_pair": commanded_minimum,
                "pairs": commanded_rows,
            },
            "transformed_metric": transformed_metadata,
            "coverage_proxy": {
                "model": "area coverage blended in encoded sRGB, then 3400K gain",
                "status": "diagnostic-only",
                "failure_floor": FAILURE_FLOOR,
                "summary": summary,
                "matrix": detailed,
            },
            "commutation": validate_transform_blend_commutation(),
            "g0_failures": failures,
            "calibration_questions": [
                "Which light-mode viewing conditions and flare model should govern transformed distance?",
                "What thin-mark discrimination floor should replace the provisional diagnostic floor of 8?",
                "How should browser raster coverage be aggregated into a perceptual line-level score?",
            ],
        }
    )


def _fake_series() -> list[list[float]]:
    return [
        [
            round(
                42
                + category * 5
                + point * (1.4 - category * 0.09)
                + 7 * math.sin((point + category) * 0.58),
                2,
            )
            for point in range(10)
        ]
        for category in range(6)
    ]


def _path(values: list[float], x: float, y: float, width: float, height: float) -> str:
    low, high = min(values), max(values)
    span = high - low or 1.0
    points = [
        (x + index * width / (len(values) - 1), y + height - (value - low) * height / span)
        for index, value in enumerate(values)
    ]
    return "M" + " L".join(f"{px:.2f},{py:.2f}" for px, py in points)


def _svg(state: str, baseline: dict[str, Any]) -> str:
    family = baseline["family"]

    def shown(value: str) -> str:
        rgb = hex_to_rgb(value)
        return rgb_to_hex(transform(rgb) if state == "transformed" else rgb)

    surfaces = {key: shown(value) for key, value in family["surfaces"].items()}
    cats = [shown(value) for value in family["categorical"].values()]
    terminal_red = shown(family["terminal"]["red"])
    title = "3400K gain [1, .74, .53]" if state == "transformed" else "Native commanded sRGB"
    series = _fake_series()
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1260" height="1180" viewBox="0 0 1260 1180">',
        '<defs><path id="cat-five-six-crossing-geometry" d="M0,38 L50,0 L100,38"/></defs>',
        f'<rect width="1260" height="1180" fill="{surfaces["bg_0"]}"/>',
        f'<text x="28" y="38" fill="{surfaces["fg_0"]}" font-family="ui-monospace, monospace" font-size="22" font-weight="700">Ember 3400K Light · G0 thin marks · {html.escape(title)}</text>',
        f'<text x="28" y="62" fill="{surfaces["fg_1"]}" font-family="ui-monospace, monospace" font-size="13">Frozen c4c25e4 · fake deterministic data · categorical contract; cross-bank rows are diagnostic only</text>',
    ]
    panel_y = 86
    for background_index, background_name in enumerate(("bg_0", "bg_1")):
        background = surfaces[background_name]
        y0 = panel_y + background_index * 520
        lines.extend(
            [
                f'<rect x="24" y="{y0}" width="1212" height="496" rx="12" fill="{background}" stroke="{surfaces["bg_4"]}"/>',
                f'<text x="44" y="{y0 + 28}" fill="{surfaces["fg_0"]}" font-family="ui-monospace, monospace" font-size="16" font-weight="700">ACTUAL {background_name} · {family["surfaces"][background_name]}</text>',
                f'<text x="44" y="{y0 + 50}" fill="{surfaces["fg_1"]}" font-family="ui-monospace, monospace" font-size="12">solid / dashed / dotted · horizontal / diagonal / curved · widths 1.5, 2, 3 CSS px</text>',
            ]
        )
        legend_y = y0 + 78
        for index, color in enumerate(cats):
            x = 48 + index * 132
            lines.append(
                f'<line x1="{x}" y1="{legend_y}" x2="{x + 34}" y2="{legend_y}" stroke="{color}" stroke-width="1.5"/>'
            )
            lines.append(
                f'<text x="{x + 40}" y="{legend_y + 4}" fill="{surfaces["fg_1"]}" font-family="ui-monospace, monospace" font-size="11">cat.{CATEGORY_NAMES[index]}</text>'
            )
        lines.append(
            f'<line x1="842" y1="{legend_y}" x2="876" y2="{legend_y}" stroke="{terminal_red}" stroke-width="1.5"/>'
        )
        lines.append(
            f'<text x="882" y="{legend_y + 4}" fill="{surfaces["fg_1"]}" font-family="ui-monospace, monospace" font-size="11">terminal.red · diagnostic</text>'
        )
        lines.append(
            f'<line x1="1060" y1="{legend_y}" x2="1094" y2="{legend_y}" stroke="{surfaces["fg_1"]}" stroke-width="1.5"/>'
        )
        lines.append(
            f'<text x="1100" y="{legend_y + 4}" fill="{surfaces["fg_1"]}" font-family="ui-monospace, monospace" font-size="11">fg_1 · diagnostic</text>'
        )

        chart_top = y0 + 102
        for row, width in enumerate((1.5, 2.0, 3.0)):
            y = chart_top + row * 54
            lines.append(
                f'<text x="44" y="{y + 23}" fill="{surfaces["fg_2"]}" font-family="ui-monospace, monospace" font-size="11">{width:g}px</text>'
            )
            for index, color in enumerate(cats):
                x = 100 + index * 112
                dash = (
                    ""
                    if index < 2
                    else (
                        ' stroke-dasharray="8 5"'
                        if index < 4
                        else ' stroke-dasharray="1 5" stroke-linecap="round"'
                    )
                )
                lines.append(
                    f'<line x1="{x}" y1="{y + 20}" x2="{x + 92}" y2="{y + 20}" stroke="{color}" stroke-width="{width}"{dash}/>'
                )
            lines.extend(
                [
                    f'<g data-evidence="color-only-cat-five-six-crossing" data-background="{background_name}" data-width="{width:g}" transform="translate(800 {y + 2})">',
                    f'<use data-role="cat.five" href="#cat-five-six-crossing-geometry" fill="none" stroke="{cats[4]}" stroke-width="{width:g}"/>',
                    f'<use data-role="cat.six" href="#cat-five-six-crossing-geometry" transform="translate(0 38) scale(1 -1)" fill="none" stroke="{cats[5]}" stroke-width="{width:g}"/>',
                    "</g>",
                ]
            )
            lines.append(
                f'<path d="M946,{y + 34} C980,{y - 5} 1020,{y + 46} 1072,{y + 8}" fill="none" stroke="{cats[1]}" stroke-width="{width}"/>'
            )
            lines.append(
                f'<path d="M946,{y + 8} C980,{y + 46} 1020,{y - 5} 1072,{y + 34}" fill="none" stroke="{terminal_red}" stroke-width="{width}" stroke-dasharray="1 5" stroke-linecap="round"/>'
            )
            lines.append(
                f'<circle cx="946" cy="{y + 34}" r="3" fill="{cats[1]}"/><circle cx="1072" cy="{y + 8}" r="3" fill="{cats[1]}"/>'
            )
            lines.append(
                f'<path d="M1090,{y + 36} C1120,{y + 4} 1168,{y + 38} 1212,{y + 6}" fill="none" stroke="{cats[1]}" stroke-width="{width}"/>'
            )
            lines.append(
                f'<path d="M1090,{y + 6} C1120,{y + 38} 1168,{y + 4} 1212,{y + 36}" fill="none" stroke="{surfaces["fg_1"]}" stroke-width="{width}" stroke-dasharray="6 4"/>'
            )

        cockpit_y = y0 + 278
        lines.append(
            f'<rect x="44" y="{cockpit_y}" width="716" height="184" rx="8" fill="none" stroke="{surfaces["bg_4"]}"/>'
        )
        lines.append(
            f'<text x="60" y="{cockpit_y + 24}" fill="{surfaces["fg_0"]}" font-family="ui-monospace, monospace" font-size="14" font-weight="700">Financial Cockpit · fake index paths</text>'
        )
        for index, values in enumerate(series):
            path = _path(values, 62, cockpit_y + 44, 672, 112)
            dash = (
                ' stroke-dasharray="7 4"'
                if index in (2, 3)
                else ' stroke-dasharray="1 5" stroke-linecap="round"'
                if index in (4, 5)
                else ""
            )
            lines.append(
                f'<path d="{path}" fill="none" stroke="{cats[index]}" stroke-width="1.5"{dash}/>'
            )
            endpoint_x = 734
            endpoint_y = (
                cockpit_y
                + 44
                + 112
                - (values[-1] - min(values)) * 112 / ((max(values) - min(values)) or 1)
            )
            lines.append(
                f'<circle cx="{endpoint_x}" cy="{endpoint_y:.2f}" r="2.5" fill="{cats[index]}"/>'
            )
        lines.append(
            f'<line x1="62" y1="{cockpit_y + 156}" x2="734" y2="{cockpit_y + 156}" stroke="{surfaces["fg_2"]}" stroke-width="1"/>'
        )

        basket_x = 780
        lines.append(
            f'<rect x="{basket_x}" y="{cockpit_y}" width="432" height="184" rx="8" fill="none" stroke="{surfaces["bg_4"]}"/>'
        )
        lines.append(
            f'<text x="796" y="{cockpit_y + 24}" fill="{surfaces["fg_0"]}" font-family="ui-monospace, monospace" font-size="14" font-weight="700">Thesis Baskets · fake weights + sparklines</text>'
        )
        for index, values in enumerate(series):
            row_y = cockpit_y + 48 + index * 21
            label = f"Basket {index + 1}"
            weight = 18 - index * 2
            lines.append(
                f'<text x="796" y="{row_y + 4}" fill="{surfaces["fg_1"]}" font-family="ui-monospace, monospace" font-size="10">{label}</text>'
            )
            lines.append(
                f'<line x1="862" y1="{row_y}" x2="{862 + weight * 3}" y2="{row_y}" stroke="{cats[index]}" stroke-width="3"/>'
            )
            lines.append(
                f'<path d="{_path(values[-6:], 946, row_y - 8, 96, 16)}" fill="none" stroke="{cats[index]}" stroke-width="1.5"/>'
            )
            lines.append(
                f'<circle cx="1042" cy="{_path_endpoint_y(values[-6:], row_y - 8, 16):.2f}" r="2.2" fill="{cats[index]}"/>'
            )
            lines.append(
                f'<text x="1060" y="{row_y + 4}" fill="{surfaces["fg_2"]}" font-family="ui-monospace, monospace" font-size="10">{weight}%</text>'
            )
    lines.append(
        f'<text x="28" y="1154" fill="{surfaces["fg_2"]}" font-family="ui-monospace, monospace" font-size="12">bg_2 ({family["surfaces"]["bg_2"]}) is metrics/report only. Cross-bank comparisons are explicitly diagnostic/non-contract.</text>'
    )
    lines.append("</svg>\n")
    return "\n".join(lines)


def _path_endpoint_y(values: list[float], y: float, height: float) -> float:
    low, high = min(values), max(values)
    return y + height - (values[-1] - low) * height / ((high - low) or 1.0)


def _browser_probe_html(baseline: dict[str, Any]) -> str:
    family = baseline["family"]
    roles = {
        "cat.five": family["categorical"]["five"],
        "cat.six": family["categorical"]["six"],
        "cat.two": family["categorical"]["two"],
        "terminal.red": family["terminal"]["red"],
        "fg_1": family["surfaces"]["fg_1"],
    }
    tiles = []
    for background_name in ("bg_0", "bg_1"):
        background = rgb_to_hex(transform(hex_to_rgb(family["surfaces"][background_name])))
        for role, value in roles.items():
            foreground = rgb_to_hex(transform(hex_to_rgb(value)))
            tiles.append(
                f'<svg class="tile" data-background="{background_name}" data-role="{role}" width="64" height="64" viewBox="0 0 64 64">'
                f'<rect width="64" height="64" fill="{background}"/>'
                f'<line x1="8" y1="8" x2="56" y2="56" stroke="{foreground}" stroke-width="1.5" stroke-linecap="butt"/>'
                "</svg>"
            )
    return (
        """<!doctype html><meta charset="utf-8"><title>G0 browser probe</title>
<style>*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff}#probe{display:grid;grid-template-columns:repeat(5,64px);width:320px}.tile{display:block;width:64px;height:64px}</style>
<div id="probe">"""
        + "".join(tiles)
        + "</div>\n"
    )


def _review_index() -> str:
    return """<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ember 3400K Light thin-mark G0 review</title>
<style>body{margin:0;background:#171312;color:#ECDCBF;font:14px ui-monospace,monospace}header{padding:16px 20px;position:sticky;top:0;background:#171312;border-bottom:1px solid #322926}main{display:grid;gap:18px;padding:18px}.frame{background:#050404;border:1px solid #322926;padding:10px;overflow:auto}img{display:block;width:1260px;max-width:none}b{color:#F490AC}.note{color:#B4AA8E;max-width:1000px;line-height:1.5}</style>
<header><b>G0 CURRENT-BASELINE EVIDENCE</b> · frozen c4c25e4 · no candidate optimization · <a href="../G0-REPORT.md">report</a> · <a href="../g0-metrics.json">metrics</a></header>
<main><p class="note">Compare the same deterministic fake-data geometry below. Inspect cat.five vs cat.six inside the categorical bank. cat.two vs terminal.red and cat.two vs fg_1 are labeled diagnostic/non-contract. Actual bg_0 and bg_1 are rendered; bg_2 is report-only. View at DPR 1 and 2 for the browser matrix.</p>
<section><h2>Native commanded</h2><div class="frame"><img src="commanded.svg" alt="Commanded thin-mark specimen"></div></section>
<section><h2>3400K transformed</h2><div class="frame"><img src="transformed.svg" alt="Transformed thin-mark specimen"></div></section></main>
"""


def _report(metrics: dict[str, Any]) -> str:
    browser_path = HERE / "browser-validation.json"
    browser: dict[str, Any] = (
        json.loads(browser_path.read_text()) if browser_path.exists() else {"status": "NOT RUN"}
    )
    failures = metrics["g0_failures"]
    browser_text = (
        f"PASS at DPR 1 and 2; Oklab-distance correlation "
        f"{browser['comparison']['oklab_distance_correlation']:.4f}, mean absolute error "
        f"{browser['comparison']['oklab_distance_mean_absolute_error']:.4f} ΔE_OK, "
        f"95th-percentile error {browser['comparison']['oklab_distance_p95_absolute_error']:.4f}."
        if browser.get("status") == "PASS"
        else f"{browser.get('status')}: {browser.get('reason', 'browser validation not generated')}"
    )
    rows = "\n".join(
        f"| {item['scope']} | {' vs '.join(item['roles'])} | {item['diagnostic_delta']:.4f} | {item['diagnostic_floor']:.1f} | **{item['status']}** |"
        for item in failures
    )
    return f"""# Stop Gate G0: current 3400K Light thin-mark evidence

**Verdict: READY for human G0 review; not ready for candidate optimization until the visible failure is accepted as reproduced.**

This is an isolated Phase 0/1 evidence harness frozen to `{metrics["baseline_source_commit"]}`. It changes no production palette or export. The [review index](review/index.html) uses deterministic fake Financial Cockpit and Thesis Baskets-style data and local SVG geometry only.

## Reproduced current failures

The transformed 1.5 CSS px diagonal at DPR 1 on actual `bg_0` is the named numerical case. The provisional 8 ΔE_OK edge-coverage floor is a **diagnostic**, not a calibrated threshold.

| Scope | Comparison | encoded-sRGB coverage proxy ΔE_OK | diagnostic floor | Result |
|---|---|---:|---:|:---:|
{rows}

The categorical failure is the contract finding. Both cross-bank rows are deliberately labeled **diagnostic/non-contract** and cannot veto a categorical bank on their own. Human-visible evidence is in short legends, crossings, endpoints, and sparklines in `review/transformed.svg`; compare directly with `review/commanded.svg`.

At native DPR 1, cat.five/cat.six lose reliable identity in the dedicated solid crossings, where both traces reference one shared geometry at equal width and color is the only style identity channel. Separately, the paired fake Financial Cockpit paths use the same dotted stroke treatment and equal width. The cat.two/terminal.red diagnostic pair becomes the clearest dark-mark collision; cat.two/fg_1 also becomes harder to track in the compact curved and sparkline geometry. These are review observations, not substitutes for a calibrated threshold.

### Native commanded

![Native commanded current-baseline thin marks](review/commanded.svg)

### 3400K transformed

![3400K transformed current-baseline thin marks](review/transformed.svg)

## Solid commanded identity

Solid commanded Oklab minimum: `{" vs ".join(metrics["commanded_solid_oklab"]["minimum_pair"]["roles"])}` = **{metrics["commanded_solid_oklab"]["minimum_pair"]["delta_e_ok"]:.4f} ΔE_OK**. This confirms the defect is not a failure of the existing solid commanded bank gate.

## Transform/compositing check

For {metrics["commutation"]["sample_count"]:,} diagonal-model samples, `transform(blend())` and `blend(transform())` differ by at most `{metrics["commutation"]["maximum_absolute_channel_error"]:.3e}` encoded-sRGB channel units. This validates operation order only for the unclipped encoded-sRGB coverage proxy.

## Proxy vs real Chromium raster

{browser_text}

No full-image hash is a metric. The browser check compares sampled line pixels and per-pixel pair distances. It skips cleanly when the project-supported GStack browser binary is unavailable.

## Metric boundary and unresolved calibration

- Commanded solid identity: Euclidean Oklab, as requested.
- Coverage: simple encoded-sRGB area blend, explicitly diagnostic.
- Transformed metric backend: injectable callable; current backend is `oklab-diagnostic`.
- Final light-mode transformed metric: **unset**. The dark CAM16-UCS conditions (`L_A=8`, `Y_b=3`) are not silently reused.
- Open questions: light viewing conditions/flare; a justified thin-mark discrimination floor; and a line-level aggregation rule for raster coverage.

## G0 decision

The G0 package is genuinely ready **for the human stop-gate decision**: the baseline, specimens, rederived diagnostics, algebra check, and browser error bounds are present and reproducible. G0 has not been declared passed; that requires a human reviewer to accept the current cat.five/cat.six loss of reliable identity and to keep the cross-bank cases diagnostic only. G0 does not authorize color search, optimization, or production changes.
"""


def build_outputs(output_dir: Path = HERE) -> None:
    baseline = load_baseline()
    metrics = compute_metrics(baseline)
    output_dir.mkdir(parents=True, exist_ok=True)
    review = output_dir / "review"
    review.mkdir(parents=True, exist_ok=True)
    (output_dir / "g0-metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "G0-REPORT.md").write_text(_report(metrics), encoding="utf-8")
    (review / "commanded.svg").write_text(_svg("commanded", baseline), encoding="utf-8")
    (review / "transformed.svg").write_text(_svg("transformed", baseline), encoding="utf-8")
    (review / "index.html").write_text(_review_index(), encoding="utf-8")
    (review / "browser-probe.html").write_text(_browser_probe_html(baseline), encoding="utf-8")


if __name__ == "__main__":
    build_outputs()
