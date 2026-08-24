#!/usr/bin/env python3
"""Render the complete dark foreground-warmth comparison experiment."""

from __future__ import annotations

import io
import json
import sys
from dataclasses import replace
from html import escape
from pathlib import Path
from typing import Any

import colour
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TOOLS = ROOT / "tools"
for path in (SRC, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_all import _mars_topography_colormap_image, _mona_lisa_colormap_image

from ember.color import (
    contrast_ratio,
    hex_to_srgb,
    srgb_to_hex,
    srgb_to_oklab,
    warm_transform,
)
from ember.definitions import DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST, FAMILIES
from ember.generate import generate_family

OUT = ROOT / "docs/experiments/dark-foreground-warmth"
RESULTS = OUT / "transformed-first-results.json"
SEARCH_SCRIPT = OUT / "search_transformed_first.py"
ASSETS = OUT / "candidate-assets"
PROFILE_SLUGS = ("3400k-dark", "2000k-dark", "1200k-dark")
LANES = ("current", "halfway")
LANE_LABELS = {
    "current": ("Current", "Shipped dark palette"),
    "halfway": ("Halfway", "Halfway warmth · transformed-first"),
}
TERM_NAMES = ("red", "green", "yellow", "blue", "magenta", "cyan")
TRANSFORMED_ADJACENT_FLOOR = 2.5
TRANSFORMED_UNIFORMITY_CEILING = 1.65
TRANSFORMED_SPAN_FLOOR = 6.0
CAM16_ADAPTATION_LUMINANCE = 8.0
CAM16_BACKGROUND_LUMINANCE = 3.0
CAM16_FLARE_FRACTION = 0.0075
UNIVERSAL_FOREGROUND_FLOORS = (4.5, 3.5, 2.4)

# Pareto-ranked competing directions. Every value is recomputed in this renderer
# from the serialized exact Hex8 records; nothing is trusted from upstream caches.
METRICS = (
    ("Background surface count", "bg_count", "higher", ".0f"),
    ("Transformed adjacent CAM16-UCS minimum", "adjacent_min", "higher", ".2f"),
    ("Transformed uniformity ratio, max:min step", "uniformity_ratio", "lower", ".3f"),
    ("Transformed surface span CAM16-UCS", "span", "higher", ".2f"),
    ("Transformed fg-background clearance minimum", "clearance_min", "higher", ".2f"),
    ("FG-0 transformed worst-surface contrast", "fg0_contrast", "higher", ".2f"),
    ("FG-1 transformed worst-surface contrast", "fg1_contrast", "higher", ".2f"),
    ("FG-2 transformed worst-surface contrast", "fg2_contrast", "higher", ".2f"),
    ("Commanded foreground mean +b", "fg_mean_plus_b", "lower", ".4f"),
    ("Commanded foreground mean chroma", "fg_mean_chroma", "lower", ".4f"),
)


def family(slug: str):
    return next(item for item in FAMILIES if item.slug == slug)


def load_data() -> dict[str, Any]:
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def lane_gains(slug: str) -> tuple[float, float, float]:
    red, green, blue = family(slug).profile.gains
    return (float(red), float(green), float(blue))


def lane_surface_values(record: dict[str, Any]) -> list[str]:
    """Selected surface Hex8 values ordered bg_0 .. bg_{bg_count - 1}."""
    keys = sorted(record["surfaces"], key=lambda key: int(key.split("_")[1]))
    return [record["surfaces"][key] for key in keys]


def expand_to_six(values: list[str], aliases: list[int]) -> tuple[str, ...]:
    """Apply the explicit six-role production alias contract."""

    if len(aliases) != 6 or any(index >= len(values) for index in aliases):
        raise ValueError(f"invalid background alias contract: {aliases} for {len(values)} values")
    return tuple(values[index] for index in aliases)


def candidate_definition(slug: str, record: dict[str, Any]):
    base = family(slug)
    gains = lane_gains(slug)
    surfaces = {
        f"bg_{index}": value
        for index, value in enumerate(
            expand_to_six(lane_surface_values(record), record["background_role_alias_indices"])
        )
    }
    surfaces.update({f"fg_{index}": value for index, value in enumerate(record["foregrounds"])})
    return replace(
        base,
        surfaces=surfaces,
        categorical_colors=tuple(record["categorical"]),
        categorical_transformed_targets=tuple(
            transform_hex(value, gains) for value in record["categorical"]
        ),
        terminal_colors=tuple(record["terminal"]),
        terminal_transformed_targets=tuple(
            transform_hex(value, gains) for value in record["terminal"]
        ),
        sequential_anchors=tuple(record["sequential_anchors"]),
    )


def asset_stem(profile: str, lane: str) -> str:
    return f"{profile}-{lane}"


def transformed_image(content: bytes, gains: tuple[float, float, float]) -> bytes:
    with Image.open(io.BytesIO(content)) as source:
        rgb = np.asarray(source.convert("RGB"), dtype=float) / 255.0
    shifted = np.rint(np.clip(rgb * np.asarray(gains), 0.0, 1.0) * 255.0).astype(np.uint8)
    output = io.BytesIO()
    Image.fromarray(shifted, mode="RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def render_candidate_assets(data: dict[str, Any]) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    for profile in PROFILE_SLUGS:
        gains = tuple(data["profiles"][profile]["gains"])
        for lane in LANES:
            record = data["profiles"][profile]["lanes"][lane]
            generated = dict(generate_family(candidate_definition(profile, record)))
            # The float ramp in the experiment result is canonical. Six Hex8
            # anchors are previews/compatibility exports only; both scalar and
            # photographic renderers consume this one float ramp.
            generated["continuous_rgb"] = record["continuous_float_srgb"]
            stem = asset_stem(profile, lane)
            for subject, renderer in (
                ("mars", _mars_topography_colormap_image),
                ("mona", _mona_lisa_colormap_image),
            ):
                commanded = renderer(generated)
                (ASSETS / f"{subject}-{stem}-commanded.png").write_bytes(commanded)
                (ASSETS / f"{subject}-{stem}-simulated.png").write_bytes(
                    transformed_image(commanded, gains)
                )


def transform_hex(value: str, gains: tuple[float, float, float]) -> str:
    return srgb_to_hex(warm_transform(hex_to_srgb(value), gains))


def css_variables(profile: str, lane: str, record: dict[str, Any], gains, simulated: bool) -> str:
    def state(value: str) -> str:
        return transform_hex(value, gains) if simulated else value

    variables = []
    role_surfaces = expand_to_six(
        lane_surface_values(record), record["background_role_alias_indices"]
    )
    for index, value in enumerate(role_surfaces):
        variables.append(f"--bg-{index}:{state(value)}")
    for index, value in enumerate(record["foregrounds"]):
        variables.append(f"--fg-{index}:{state(value)}")
    for index, value in enumerate(record["categorical"]):
        variables.append(f"--cat-{index + 1}:{state(value)}")
    expanded_terminal = [
        record["terminal"][index] for index in family(profile).terminal_ansi_indices
    ]
    for name, value in zip(TERM_NAMES, expanded_terminal, strict=True):
        variables.append(f"--term-{name}:{state(value)}")
    stops = [record["continuous_hex8"][round(index * 255 / 10)] for index in range(11)]
    gradient = ",".join(f"{state(value)} {index * 10}%" for index, value in enumerate(stops))
    variables.append(f"--seq:linear-gradient(90deg,{gradient})")
    state_name = "simulated" if simulated else "commanded"
    return (
        f'body[data-state="{state_name}"] [data-profile="{profile}"]'
        f'[data-candidate="{lane}"]{{' + ";".join(variables) + "}"
    )


def universal_floors(slug: str) -> tuple[float, float, float]:
    """fg_0 uses the stricter of the universal 4.5 floor and the family's own."""
    primary = max(4.5, DARK_MINIMUM_SHIFTED_PRIMARY_TEXT_CONTRAST.get(slug, 4.5))
    return (primary, UNIVERSAL_FOREGROUND_FLOORS[1], UNIVERSAL_FOREGROUND_FLOORS[2])


def cam16_ucs(rgb01: np.ndarray, gains) -> np.ndarray:
    """CAM16-UCS coordinates under transformed sRGB and night viewing conditions."""

    transformed = np.clip(rgb01 * np.asarray(gains), 0.0, 1.0)
    xyz = colour.sRGB_to_XYZ(transformed)
    flare = CAM16_FLARE_FRACTION * colour.sRGB_to_XYZ(np.ones_like(transformed))
    return np.asarray(
        colour.XYZ_to_CAM16UCS(
            xyz + flare,
            L_A=CAM16_ADAPTATION_LUMINANCE,
            Y_b=CAM16_BACKGROUND_LUMINANCE,
        )
    )


def lane_metrics(slug: str, record: dict[str, Any]) -> dict[str, float]:
    """Recompute every published metric from the serialized exact Hex8 record."""
    gains = lane_gains(slug)
    surfaces = np.asarray([hex_to_srgb(value) for value in lane_surface_values(record)])
    foregrounds = np.asarray([hex_to_srgb(value) for value in record["foregrounds"]])
    transformed_surfaces = warm_transform(surfaces, gains)
    transformed_foregrounds = warm_transform(foregrounds, gains)
    surface_ucs = cam16_ucs(surfaces, gains)
    foreground_ucs = cam16_ucs(foregrounds, gains)
    adjacent = np.linalg.norm(np.diff(surface_ucs, axis=0), axis=1)
    contrasts = [
        min(contrast_ratio(foreground, background) for background in transformed_surfaces)
        for foreground in transformed_foregrounds
    ]
    clearance = np.linalg.norm(surface_ucs[:, None, :] - foreground_ucs[None, :, :], axis=2).min(
        axis=0
    )
    commanded_lab = srgb_to_oklab(foregrounds)
    return {
        "bg_count": float(record["bg_count"]),
        "adjacent_min": float(adjacent.min()),
        "uniformity_ratio": float(adjacent.max() / max(adjacent.min(), 1e-9)),
        "span": float(np.linalg.norm(surface_ucs[-1] - surface_ucs[0])),
        "clearance_min": float(clearance.min()),
        "fg0_contrast": contrasts[0],
        "fg1_contrast": contrasts[1],
        "fg2_contrast": contrasts[2],
        "fg_mean_plus_b": float(commanded_lab[:, 2].mean()),
        "fg_mean_chroma": float(np.linalg.norm(commanded_lab[:, 1:], axis=1).mean()),
    }


def computed_lane_metrics(data: dict[str, Any]) -> dict[str, dict[str, dict[str, float]]]:
    return {
        slug: {lane: lane_metrics(slug, data["profiles"][slug]["lanes"][lane]) for lane in LANES}
        for slug in PROFILE_SLUGS
    }


def distinctness_status(metrics: dict[str, float]) -> str:
    """Lightweight re-check of the fourth pass transformed distinctness gates."""
    passes = (
        metrics["adjacent_min"] + 1e-9 >= TRANSFORMED_ADJACENT_FLOOR
        and metrics["uniformity_ratio"] <= TRANSFORMED_UNIFORMITY_CEILING + 1e-9
        and metrics["span"] + 1e-9 >= TRANSFORMED_SPAN_FLOOR
    )
    return "PASS" if passes else "FAIL"


def universal_status(slug: str, metrics: dict[str, float]) -> str:
    floors = universal_floors(slug)
    passes = all(
        metrics[f"fg{index}_contrast"] + 1e-12 >= floor for index, floor in enumerate(floors)
    )
    return "PASS" if passes else "FAIL"


def best_lanes(values: dict[str, float], direction: str) -> set[str]:
    best = min(values.values()) if direction == "lower" else max(values.values())
    return {lane for lane, value in values.items() if abs(value - best) <= 1e-12}


def format_metric(value: float, spec: str) -> str:
    return format(value, spec)


def metrics_html(data: dict[str, Any], computed: dict[str, dict[str, dict[str, float]]]) -> str:
    headers = "".join(
        f'<th colspan="2">{escape(data["profiles"][profile]["name"])}</th>'
        for profile in PROFILE_SLUGS
    )
    lanes = "".join(f"<th>{LANE_LABELS[lane][0]}</th>" for _ in PROFILE_SLUGS for lane in LANES)
    rows = []
    for label, key, direction, spec in METRICS:
        cells = []
        for profile in PROFILE_SLUGS:
            values = {lane: computed[profile][lane][key] for lane in LANES}
            best = best_lanes(values, direction)
            for lane in LANES:
                rendered = format_metric(values[lane], spec)
                decorated = f'<u class="winner">{rendered}</u>' if lane in best else rendered
                cells.append(f"<td>{decorated}</td>")
        arrow = "↓ lower" if direction == "lower" else "↑ higher"
        rows.append(
            f'<tr data-metric="{key}"><th>{escape(label)}</th><td class="direction">{arrow}</td>{"".join(cells)}</tr>'
        )
    return (
        '<div class="table-scroll"><table class="metrics"><thead><tr><th rowspan="2">Metric</th>'
        f'<th rowspan="2">Direction</th>{headers}</tr><tr>{lanes}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def metrics_markdown(data: dict[str, Any], computed: dict[str, dict[str, dict[str, float]]]) -> str:
    columns = [
        f"{data['profiles'][profile]['name']} {LANE_LABELS[lane][0]}"
        for profile in PROFILE_SLUGS
        for lane in LANES
    ]
    lines = [
        "| Metric | Direction | " + " | ".join(columns) + " |",
        "|---|:---:|" + "|".join("---:" for _ in columns) + "|",
    ]
    for label, key, direction, spec in METRICS:
        cells = []
        for profile in PROFILE_SLUGS:
            values = {lane: computed[profile][lane][key] for lane in LANES}
            best = best_lanes(values, direction)
            for lane in LANES:
                rendered = format_metric(values[lane], spec)
                cells.append(f"**{rendered}**" if lane in best else rendered)
        arrow = "↓ lower" if direction == "lower" else "↑ higher"
        lines.append(f"| {label} | {arrow} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def dependent_frontiers_html(data: dict[str, Any]) -> str:
    rows = []
    for profile in PROFILE_SLUGS:
        for lane in LANES:
            record = data["profiles"][profile]["lanes"][lane]
            frontier_cells = []
            for entry in record["categorical_frontier"]:
                rendered = (
                    f"N={entry['count']}: {entry['sampled_grid_pair_cam16_ucs']:.2f} "
                    f"({'pass' if entry['passes'] else 'blocked'})"
                )
                if entry.get("selected_bank"):
                    if entry.get("selected_trial"):
                        rendered += " · selected"
                    else:
                        rendered += (
                            " · trial rejected; shipped bank selected at "
                            f"{entry['selected_bank_sampled_grid_pair_cam16_ucs']:.2f} (pass)"
                        )
                frontier_cells.append(rendered)
            frontier = "; ".join(frontier_cells)
            terminal = record["terminal_metrics"]
            sequential = record["sequential_metrics"]
            rows.append(
                "<tr>"
                f"<th>{escape(data['profiles'][profile]['name'])}</th>"
                f"<td>{escape(LANE_LABELS[lane][0])}</td>"
                f"<td>{escape(frontier)}</td>"
                f"<td>{terminal['sampled_gain_pair_min_cam16_ucs']:.2f}</td>"
                f"<td>{terminal['sampled_gain_foreground_clearance_min_cam16_ucs']:.2f}</td>"
                f"<td>{sequential['transformed_cam16_cv']:.4f}</td>"
                f"<td>{sequential['normal_cv']:.3f}</td>"
                f"<td>{sequential['sampled_gain_cv_max']:.3f}</td>"
                f"<td>{sequential['sampled_gain_max_to_min_max']:.2f}</td>"
                "</tr>"
            )
    return (
        '<div class="table-scroll"><table class="metrics dependent-metrics"><thead><tr>'
        "<th>Profile</th><th>Lane</th><th>Categorical capacity frontier</th>"
        "<th>Terminal pair</th><th>Terminal↔fg</th>"
        "<th>Sequential transformed CV</th><th>Commanded CV</th>"
        "<th>Sampled-gain CV max</th><th>Sampled-gain max:min</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def swatches(values: list[str], kind: str) -> str:
    return "".join(
        f'<span class="swatch {kind}-{index + 1}"><code>{value}</code></span>'
        for index, value in enumerate(values)
    )


def anatomy(slug: str, lane: str, record: dict[str, Any], metrics: dict[str, float]) -> str:
    surfaces = "".join(
        f'<span class="surface bg-{index}"><b>BG-{index}</b><code>{value}</code></span>'
        for index, value in enumerate(lane_surface_values(record))
    )
    foregrounds = "".join(
        f'<p class="fg-{index}"><b>FG-{index}</b> {record["foregrounds"][index]} · hierarchy sample</p>'
        for index in range(3)
    )
    distinct = distinctness_status(metrics)
    universal = universal_status(slug, metrics)
    search = record["search"]
    if record["search"].get("note"):
        provenance = [escape(record["search"]["note"])]
    else:
        chosen = str(record["bg_count"])
        run = search["per_count"][chosen]
        provenance = [
            escape(
                f"surface count {record['bg_count']} chosen by rule: {search['count_choice_rule']}"
            ),
            escape(
                f"seed {run['seed']} · {run['iterations']} iterations · "
                f"{run['evaluated_exact_hex8_candidates']} exact Hex8 candidates · "
                f"{run['accepted_moves']} accepted moves"
            ),
        ]
    provenance.append(escape(f"categorical adoption: {record['categorical_adoption']}"))
    ordering = record.get("categorical_ordering")
    if ordering:
        prefix = ", ".join(
            f"N={index + 2}: {value:.2f}"
            for index, value in enumerate(ordering["prefix_transformed_pair_minima_cam16_ucs"])
        )
        provenance.append(
            escape(
                "categorical display order: cross-profile broad hue identity; "
                f"families {ordering['semantic_families']}; "
                f"search-slot permutation {ordering['permutation_from_search_order']}; "
                f"prefix pair minima {prefix} CAM16-UCS"
            )
        )
    for frontier in record.get("categorical_frontier", []):
        trial = record["categorical_trials"][str(frontier["count"])]
        failure_text = "; ".join(trial["failures"]) if trial["failures"] else "all bank gates pass"
        provenance.append(
            escape(
                f"categorical N={frontier['count']}: sampled-grid pair "
                f"{frontier['sampled_grid_pair_cam16_ucs']:.2f} CAM16-UCS; {failure_text}"
            )
        )
    provenance.append(escape(f"terminal adoption: {record['terminal_adoption']}"))
    sequential_metrics = record["sequential_metrics"]
    target_note = (
        "target met"
        if sequential_metrics["transformed_cam16_cv_target_met"]
        else sequential_metrics["target_deviation_reason"]
    )
    provenance.append(
        escape(
            f"sequential canonical float ramp: transformed CAM16-UCS CV "
            f"{sequential_metrics['transformed_cam16_cv']:.4f}; commanded CV "
            f"{sequential_metrics['normal_cv']:.4f}; sampled-gain CV max "
            f"{sequential_metrics['sampled_gain_cv_max']:.4f}; weight "
            f"{sequential_metrics['transformed_arc_weight']:.2f}; {target_note}"
        )
    )
    details = "".join(f"<li>{item}</li>" for item in provenance)
    return f"""
<header class="card-head"><div><p>{LANE_LABELS[lane][1]}</p><h3>{LANE_LABELS[lane][0]}</h3></div><div class="status"><span class="status-{distinct.lower()}">Distinctness {distinct}</span><span class="status-{universal.lower()}">Universal text {universal}</span></div></header>
<div class="surface-strip">{surfaces}</div><div class="foregrounds">{foregrounds}</div>
<div class="bank"><b>Categorical · {len(record["categorical"])}</b><div class="swatches">{swatches(record["categorical"], "cat")}</div></div>
<div class="bank"><b>Terminal authored · {len(record["terminal"])}</b><div class="swatches">{swatches(record["terminal"], "term")}</div></div>
<div class="gradient"></div><p class="search-summary">Transformed-first pass {int(record["weight"] * 100)}% toward the Light Mid-Depth warmth step. Every metric on this page is recomputed from the serialized exact Hex8 values.</p>
<details><summary>Search provenance</summary><ul>{details}</ul></details>
"""


def editorial() -> str:
    return """
<article class="editorial"><p class="kicker">FIELD NOTE · 08:42 UTC · FG-2</p><h3>Warmth should support attention, not announce itself</h3><p class="standfirst">A dark interface can retain Ember's material character while its text approaches a quieter neutral.</p><p>The test is sustained reading: a <a href="#metrics">linked measurement</a>, <strong>important evidence</strong>, ordinary body copy, and <mark>selected language</mark> must keep their hierarchy without a yellow cast becoming the subject.</p><h4>Foreground is a system</h4><p class="support">Primary text carries the argument. Secondary text carries context. Tertiary text carries metadata, never body copy.</p><blockquote>Neutrality is not the absence of identity. It is deciding where identity earns attention.</blockquote><p class="caption">Figure 04 · Commanded appearance and exact signal simulation are separate claims.</p></article>
"""


def terminal(record: dict[str, Any]) -> str:
    names = [TERM_NAMES[index] for index in range(6)]
    statuses = "".join(f'<span class="term-{name}">{name.upper()}</span>' for name in names)
    return f"""
<div class="terminal"><header><i></i><i></i><i></i><b>ember-audit / {len(record["terminal"])} authored semantic identities</b></header><pre><code><span class="prompt">$</span> ember compare <span class="string">--state exact-simulated</span>
<span class="keyword">from</span> ember.audit <span class="keyword">import</span> <span class="function">measure</span>
profile = <span class="string">"{record["weight"]:.1f}-warmth"</span>
<span class="selection">result = measure(profile, optimize_system=True)</span>
<span class="comment"># comments use bright-black / FG-0 mapping</span>
<span class="term-red">error:</span> strict floor miss
<span class="term-green">ok:</span> serialized Hex8 verified
<span class="term-yellow">warn:</span> competing metric directions
<span class="term-blue">info:</span> two deterministic seeds
<span class="term-magenta">note:</span> bounded search only
<span class="term-cyan">data:</span> gain corners sampled</code></pre><div class="terminal-status">{statuses}</div></div>
"""


def dashboard(record: dict[str, Any]) -> str:
    count = len(record["categorical"])
    series = "".join(
        f'<path class="series cat-stroke-{index + 1}" d="M8 {90 - index * 5} C50 {18 + index * 11},100 {104 - index * 7},158 {35 + index * 8} S260 {100 - index * 6},312 {24 + index * 9}"/>'
        for index in range(count)
    )
    statuses = (
        '<span class="term-green">● NOMINAL</span><span class="term-yellow">▲ WATCH</span>'
        '<span class="term-red">■ FAULT</span>'
    )
    return f"""
<div class="dashboard"><header><div><b>THARSIS OPERATIONS</b><small>MET 0412:06:57</small></div><button>EXPORT FRAME</button></header>
<div class="dash-grid"><section class="summary"><b>NETWORK LOAD</b><strong>78.4%</strong><progress value="78" max="100"></progress><p>{statuses}</p></section><section><b>COMMAND QUEUE</b><dl><div><dt>Pending</dt><dd>14</dd></div><div><dt>Ack</dt><dd>382</dd></div><div><dt>Latency</dt><dd>118 ms</dd></div></dl></section>
<section class="chart"><b>{count} CATEGORICAL CHANNELS</b><svg viewBox="0 0 320 120"><path class="grid" d="M8 20H312M8 50H312M8 80H312M8 110H312"/>{series}</svg></section>
<section class="heat"><b>SEQUENTIAL HEATMAP</b><div>{"".join(f'<i style="--n:{index}"></i>' for index in (0, 2, 4, 6, 8, 10, 1, 3, 5, 7, 9, 0, 3, 6, 9, 10, 2, 4, 7, 8))}</div></section>
<section class="events"><b>EVENT TABLE</b><table><thead><tr><th>UTC</th><th>Subsystem</th><th>Status</th></tr></thead><tbody><tr><td>06:40</td><td>SSR playback</td><td class="term-green">NOM</td></tr><tr class="selected"><td>06:55</td><td>Payload-B</td><td class="term-yellow">WATCH</td></tr><tr><td>07:02</td><td>Star tracker</td><td class="term-red">FAULT</td></tr></tbody></table></section>
<section class="controls"><b>COMMAND FORM</b><form><label>Subsystem<select><option>Payload-B</option></select></label><label>Window<input value="07:20–07:45"></label><label><input type="checkbox" checked> Require acknowledgement</label><button type="button">QUEUE COMMAND</button></form></section></div></div>
"""


def science(profile: str, lane: str, record: dict[str, Any]) -> str:
    stem = asset_stem(profile, lane)
    return f"""
<div class="sequence-proof"><div class="gradient"></div><div class="heatmap">{"".join(f'<i style="--n:{index}"></i>' for index in (0, 2, 4, 6, 8, 10, 1, 3, 5, 7, 9, 0, 3, 6, 9, 10, 2, 4, 7, 8))}</div></div>
<figure><img data-commanded="candidate-assets/mars-{stem}-commanded.png" data-simulated="candidate-assets/mars-{stem}-simulated.png" src="candidate-assets/mars-{stem}-commanded.png" alt="Real Mars MOLA scalar elevation mapped through {profile} {lane}"><figcaption><b>Real Mars scalar image</b><span>NASA MGS MOLA elevation · candidate sequential map</span></figcaption></figure>
<figure><img data-commanded="candidate-assets/mona-{stem}-commanded.png" data-simulated="candidate-assets/mona-{stem}-simulated.png" src="candidate-assets/mona-{stem}-commanded.png" alt="Mona Lisa photographic lightness mapping through {profile} {lane}"><figcaption><b>Mona Lisa photographic mapping</b><span>Public-domain source · Oklab-L transfer · candidate ramp</span></figcaption></figure>
<figure class="scientific"><svg viewBox="0 0 420 220" role="img" aria-label="Scientific electromagnetic propagation figure"><path class="axis" d="M35 180V25M35 180H395M35 180L380 40"/><path class="wave cat-stroke-1" d="M42 155C84 44 125 47 165 140S250 206 291 101S352 47 390 75"/><path class="wave cat-stroke-2 dashed" d="M42 170C87 200 115 122 165 146S245 190 292 125S352 93 390 112"/><path class="marker cat-stroke-3" d="M255 35V188"/><circle class="cat-fill-1" cx="165" cy="140" r="5"/><circle class="cat-fill-2" cx="292" cy="125" r="5"/></svg><figcaption><b>Scientific figure · E/B propagation</b><span>Categorical identities, direct marks, redundant line style</span></figcaption></figure>
"""


def candidate_card(
    profile: str,
    lane: str,
    record: dict[str, Any],
    metrics: dict[str, float],
    domain: str,
) -> str:
    content = {
        "anatomy": anatomy(profile, lane, record, metrics),
        "editorial": editorial(),
        "terminal": terminal(record),
        "dashboard": dashboard(record),
        "science": science(profile, lane, record),
    }[domain]
    label = (
        ""
        if domain == "anatomy"
        else (
            f'<header class="domain-head"><p>{escape(family(profile).name)}</p>'
            f"<h3>{escape(LANE_LABELS[lane][0])}</h3></header>"
        )
    )
    return (
        f'<article class="candidate-card {domain}-card" data-profile="{profile}" '
        f'data-candidate="{lane}">{label}{content}</article>'
    )


def render_html(data: dict[str, Any]) -> str:
    wrapper = family("3400k-dark").surfaces
    computed = computed_lane_metrics(data)
    candidate_css = "\n".join(
        css_variables(
            profile,
            lane,
            data["profiles"][profile]["lanes"][lane],
            tuple(data["profiles"][profile]["gains"]),
            simulated,
        )
        for profile in PROFILE_SLUGS
        for lane in LANES
        for simulated in (False, True)
    )
    sections = []
    for section_id, title, description, domain in (
        (
            "anatomy",
            "01 · Complete anatomy",
            "Surfaces and foregrounds are jointly selected at exact Hex8 before dependent banks.",
            "anatomy",
        ),
        (
            "editorial",
            "02 · Editorial hierarchy",
            "Headline, standfirst, body, link, emphasis, selection, quote, caption, and metadata.",
            "editorial",
        ),
        (
            "terminal",
            "03 · Code and terminal",
            "All six ANSI semantic roles, comments, selection, syntax, prompts, and status output.",
            "terminal",
        ),
        (
            "dashboard",
            "04 · Dense dashboard",
            "Categories, statuses, chart crossings, heatmap, table, and realistic form controls.",
            "dashboard",
        ),
        (
            "science",
            "05 · Sequential, image, and science proof",
            "Gradient + heatmap, real Mars scalar data, Mona Lisa photography, and a scientific figure.",
            "science",
        ),
    ):
        cards = "".join(
            candidate_card(
                profile,
                lane,
                data["profiles"][profile]["lanes"][lane],
                computed[profile][lane],
                domain,
            )
            for profile in PROFILE_SLUGS
            for lane in LANES
        )
        sections.append(
            f'<section class="proof" id="{section_id}"><header><p>PROOF DOMAIN</p><h2>{title}</h2><span>{description}</span></header><div class="candidate-grid">{cards}</div></section>'
        )
    profile_buttons = "".join(
        f'<button type="button" data-profile-button="{profile}" aria-pressed="{str(profile == PROFILE_SLUGS[0]).lower()}">{data["profiles"][profile]["name"].replace(" Dark", "")}</button>'
        for profile in PROFILE_SLUGS
    )
    focus_buttons = (
        '<button type="button" data-focus-button="all" aria-pressed="true">All lanes</button>'
        + "".join(
            f'<button type="button" data-focus-button="{lane}" aria-pressed="false">{LANE_LABELS[lane][0]}</button>'
            for lane in LANES
        )
    )
    statuses = "".join(
        f"<tr><th>{data['profiles'][profile]['name']}</th>"
        + "".join(
            f'<td><b class="status-{distinctness_status(computed[profile][lane]).lower()}">Distinctness {distinctness_status(computed[profile][lane])}</b><br><span>Universal text {universal_status(profile, computed[profile][lane])}</span></td>'
            for lane in LANES
        )
        + "</tr>"
        for profile in PROFILE_SLUGS
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ember dark foreground warmth experiment</title><style>
:root{{--wrap-0:{wrapper["bg_0"]};--wrap-1:{wrapper["bg_1"]};--wrap-2:{wrapper["bg_2"]};--wrap-3:{wrapper["bg_3"]};--wrap-4:{wrapper["bg_4"]};--wrap-5:{wrapper["bg_5"]};--wrap-fg-0:{wrapper["fg_0"]};--wrap-fg-1:{wrapper["fg_1"]};--wrap-fg-2:{wrapper["fg_2"]};color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif}}*{{box-sizing:border-box}}html,body{{margin:0;max-width:100%;background:var(--wrap-0);color:var(--wrap-fg-0)}}button,input,select{{font:inherit}}.topbar{{position:sticky;top:0;z-index:50;display:grid;grid-template-columns:minmax(16rem,1fr) auto auto auto;gap:.65rem;align-items:center;padding:.65rem clamp(.65rem,2vw,1.4rem);background:rgba(16,14,12,.97);border-bottom:1px solid var(--wrap-4)}}.brand h1{{font-size:.85rem;letter-spacing:.08em;margin:0}}.brand p{{font-size:.62rem;color:var(--wrap-fg-2);margin:.2rem 0 0}}.control{{display:flex;gap:2px;padding:2px;background:var(--wrap-2);border:1px solid var(--wrap-4)}}.control button{{min-height:44px;padding:.35rem .65rem;border:0;background:transparent;color:var(--wrap-fg-1);cursor:pointer;white-space:nowrap}}.control button[aria-pressed="true"]{{background:var(--wrap-5);color:var(--wrap-fg-0)}}.intro,.proof,.metrics-section{{max-width:118rem;margin:0 auto;padding:clamp(1rem,3vw,2.8rem) clamp(.65rem,2vw,1.5rem)}}.eyebrow,.proof>header p{{font:700 .58rem ui-monospace,monospace;letter-spacing:.16em;color:var(--wrap-fg-2);margin:0}}.intro h2{{font:500 clamp(2rem,5vw,5rem)/.95 Georgia,serif;max-width:18ch;margin:.5rem 0 1rem}}.intro>p{{max-width:72rem;color:var(--wrap-fg-1);line-height:1.55}}.truth-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.6rem;margin-top:1.2rem}}.truth-card{{padding:1rem;background:var(--wrap-1);border:1px solid var(--wrap-4)}}.truth-card h3{{font-size:.8rem;margin:0 0 .4rem}}.truth-card p{{font-size:.7rem;line-height:1.5;color:var(--wrap-fg-1);margin:0}}.status-table{{margin-top:1rem;border-collapse:collapse;font-size:.68rem}}.status-table th,.status-table td{{padding:.5rem;border:1px solid var(--wrap-4);text-align:left}}.status-pass{{color:#7EB798}}.status-fail{{color:#F5AD9A}}.metrics-section,.proof{{border-top:1px solid var(--wrap-4);scroll-margin-top:4.5rem}}.metrics-section h2,.proof>header h2{{font-size:1rem;margin:.25rem 0}}.metrics-note,.proof>header span{{font-size:.68rem;color:var(--wrap-fg-2)}}.table-scroll{{overflow-x:auto;margin-top:1rem;border:1px solid var(--wrap-4)}}.metrics{{border-collapse:collapse;min-width:min(118rem,180vw);width:max-content;max-width:none;font:500 .58rem ui-monospace,monospace}}.metrics th,.metrics td{{padding:.42rem .5rem;border:1px solid var(--wrap-4);text-align:right}}.metrics thead th{{background:var(--wrap-2);color:var(--wrap-fg-1);text-align:center}}.metrics tbody th{{position:sticky;left:0;background:var(--wrap-1);text-align:left;min-width:min(18rem,32vw)}}.metrics .direction{{color:var(--wrap-fg-2);white-space:nowrap}}.metrics strong{{color:var(--wrap-fg-0);font-weight:inherit;text-decoration:underline 2px;text-underline-offset:3px}}.proof>header{{margin-bottom:.8rem}}.domain-head{{display:flex;align-items:baseline;justify-content:space-between;gap:.5rem;padding:.55rem .7rem;background:var(--bg-1);border-bottom:1px solid var(--bg-4)}}.domain-head p{{margin:0;font:.48rem ui-monospace,monospace;color:var(--fg-2)}}.domain-head h3{{margin:0;font-size:.72rem}}.candidate-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.65rem}}.candidate-card{{min-width:0;background:var(--bg-0);color:var(--fg-0);border:1px solid var(--bg-5);overflow:hidden}}body:not([data-profile="3400k-dark"]) [data-profile="3400k-dark"],body:not([data-profile="2000k-dark"]) [data-profile="2000k-dark"],body:not([data-profile="1200k-dark"]) [data-profile="1200k-dark"]{{display:none}}body[data-focus="current"] [data-candidate]:not([data-candidate="current"]),body[data-focus="halfway"] [data-candidate]:not([data-candidate="halfway"]){{display:none}}body[data-focus]:not([data-focus="all"]) .candidate-grid{{grid-template-columns:minmax(0,38rem);justify-content:center}}.card-head{{display:flex;justify-content:space-between;gap:.5rem;align-items:end;padding:.7rem;background:var(--bg-1);border-bottom:1px solid var(--bg-4)}}.card-head p{{font:.5rem ui-monospace,monospace;color:var(--fg-2);margin:0}}.card-head h3{{font-size:.9rem;margin:.15rem 0 0}}.status{{display:flex;gap:.25rem;flex-wrap:wrap;justify-content:flex-end}}.status span{{font:700 .46rem ui-monospace,monospace;padding:.2rem .3rem;border:1px solid currentColor}}.surface-strip{{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;margin:.7rem;border:1px solid var(--bg-5)}}.surface{{height:64px;display:flex;flex-direction:column;justify-content:end;padding:.3rem;min-width:0}}.surface b,.surface code{{font:.43rem ui-monospace,monospace;overflow:hidden}}.surface code{{color:var(--fg-2)}}.bg-0{{background:var(--bg-0)}}.bg-1{{background:var(--bg-1)}}.bg-2{{background:var(--bg-2)}}.bg-3{{background:var(--bg-3)}}.bg-4{{background:var(--bg-4)}}.bg-5{{background:var(--bg-5)}}.foregrounds,.bank{{padding:0 .7rem}}.foregrounds p{{font:.58rem ui-monospace,monospace;margin:.28rem 0}}.fg-0{{color:var(--fg-0)}}.fg-1{{color:var(--fg-1)}}.fg-2{{color:var(--fg-2)}}.bank{{display:grid;grid-template-columns:7rem 1fr;align-items:center;gap:.4rem;margin-top:.65rem;font:.52rem ui-monospace,monospace}}.swatches{{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:2px}}.swatch{{height:30px;display:block}}.swatch code{{display:none}}.cat-1{{background:var(--cat-1)}}.cat-2{{background:var(--cat-2)}}.cat-3{{background:var(--cat-3)}}.cat-4{{background:var(--cat-4)}}.cat-5{{background:var(--cat-5)}}.cat-6{{background:var(--cat-6)}}.term-1{{background:var(--term-red)}}.term-2{{background:var(--term-green)}}.term-3{{background:var(--term-yellow)}}.term-4{{background:var(--term-blue)}}.term-5{{background:var(--term-magenta)}}.term-6{{background:var(--term-cyan)}}.gradient{{height:20px;margin:.7rem;background:var(--seq);border:1px solid var(--bg-4)}}.search-summary,details{{font:.5rem/1.4 ui-monospace,monospace;color:var(--fg-2);margin:.5rem .7rem}}details ul{{padding-left:1.2rem}}.editorial,.terminal,.dashboard,.sequence-proof,figure{{margin:.7rem}}.editorial{{padding:clamp(1rem,3vw,2rem);background:var(--bg-1);min-height:31rem}}.editorial .kicker,.editorial .caption{{font:.54rem ui-monospace,monospace;color:var(--fg-2)}}.editorial h3{{font:500 1.55rem/1.05 Georgia,serif;margin:.65rem 0}}.editorial h4{{font:.8rem ui-sans-serif,sans-serif;margin:1.2rem 0 .25rem}}.editorial p,.editorial blockquote{{font:.76rem/1.6 Georgia,serif}}.editorial .standfirst,.editorial .support{{color:var(--fg-1)}}.editorial a{{color:var(--cat-1)}}.editorial mark{{background:var(--bg-5);color:var(--fg-0)}}.editorial blockquote{{margin:1rem 0;padding:.7rem;border-left:3px solid var(--cat-3);background:var(--bg-2)}}.terminal{{background:var(--bg-1);border:1px solid var(--bg-4);min-height:22rem}}.terminal header{{display:flex;gap:.3rem;align-items:center;padding:.55rem;background:var(--bg-2);border-bottom:1px solid var(--bg-4);font:.5rem ui-monospace,monospace}}.terminal header i{{width:7px;height:7px;border-radius:50%;background:var(--bg-5)}}.terminal pre{{padding:.85rem;margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:.57rem/1.75 ui-monospace,monospace}}.prompt,.comment{{color:var(--fg-2)}}.keyword{{color:var(--term-magenta)}}.function{{color:var(--term-cyan)}}.string{{color:var(--term-green)}}.selection{{background:var(--bg-5)}}.terminal-status{{display:grid;grid-template-columns:repeat(3,1fr);gap:.25rem;padding:.7rem;border-top:1px solid var(--bg-4);font:700 .48rem ui-monospace,monospace}}.terminal-status span{{background:var(--bg-2);padding:.35rem}}.term-red{{color:var(--term-red)}}.term-green{{color:var(--term-green)}}.term-yellow{{color:var(--term-yellow)}}.term-blue{{color:var(--term-blue)}}.term-magenta{{color:var(--term-magenta)}}.term-cyan{{color:var(--term-cyan)}}.dashboard{{border:1px solid var(--bg-4);background:var(--bg-1);font-family:ui-monospace,monospace}}.dashboard>header{{display:flex;justify-content:space-between;align-items:center;padding:.6rem;background:var(--bg-2);font-size:.52rem}}.dashboard header small{{display:block;color:var(--fg-2);margin-top:.2rem}}.dashboard button,.dashboard input,.dashboard select{{background:var(--bg-2);color:var(--fg-0);border:1px solid var(--bg-5);min-height:32px}}.dash-grid{{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--bg-4)}}.dash-grid section{{min-width:0;padding:.65rem;background:var(--bg-1)}}.dash-grid section>b{{font-size:.5rem;letter-spacing:.06em}}.summary strong{{display:block;font-size:1.6rem;margin:.5rem 0}}progress{{width:100%;accent-color:var(--cat-1)}}.summary p{{display:flex;gap:.3rem;flex-wrap:wrap;font-size:.42rem}}dl{{display:grid;grid-template-columns:repeat(3,1fr);gap:.2rem}}dl div{{padding:.35rem;background:var(--bg-2)}}dt{{font-size:.42rem;color:var(--fg-2)}}dd{{font-size:.62rem;margin:.1rem 0 0}}.chart,.events,.controls{{grid-column:1/-1}}.chart svg{{display:block;width:100%;height:130px;background:var(--bg-0);margin-top:.45rem}}.grid{{stroke:var(--bg-4);fill:none}}.series,.wave{{fill:none;stroke-width:2}}.cat-stroke-1{{stroke:var(--cat-1)}}.cat-stroke-2{{stroke:var(--cat-2)}}.cat-stroke-3{{stroke:var(--cat-3)}}.cat-stroke-4{{stroke:var(--cat-4)}}.cat-stroke-5{{stroke:var(--cat-5)}}.cat-stroke-6{{stroke:var(--cat-6)}}.cat-fill-1{{fill:var(--cat-1)}}.cat-fill-2{{fill:var(--cat-2)}}.heat>div,.heatmap{{display:grid;grid-template-columns:repeat(5,1fr);gap:2px;margin-top:.5rem}}.heat i,.heatmap i{{height:32px;background:var(--seq);background-size:1100% 100%;background-position:calc(var(--n) * -10%) 0}}.events table{{width:100%;border-collapse:collapse;margin-top:.4rem;font-size:.48rem}}.events th,.events td{{padding:.35rem;border:1px solid var(--bg-4);text-align:left}}.events .selected{{background:var(--bg-5)}}form{{display:grid;grid-template-columns:1fr 1fr;gap:.5rem;margin-top:.5rem;font-size:.5rem}}form label{{display:grid;gap:.25rem}}form label:nth-child(3){{display:flex;align-items:center}}form button{{grid-column:1/-1}}.sequence-proof{{padding:.2rem;background:var(--bg-1);border:1px solid var(--bg-4)}}figure{{padding:.55rem;background:var(--bg-1);border:1px solid var(--bg-4)}}figure img,figure svg{{display:block;width:100%;height:auto}}figcaption{{display:grid;gap:.15rem;margin-top:.4rem;font-size:.5rem}}figcaption span{{color:var(--fg-2)}}.scientific svg{{background:var(--bg-0)}}.axis{{fill:none;stroke:var(--fg-2)}}.wave{{stroke-width:3}}.dashed{{stroke-dasharray:9 5}}.marker{{stroke-dasharray:4 4}}.footer{{padding:2rem;text-align:center;color:var(--wrap-fg-2);font:.58rem ui-monospace,monospace}}{candidate_css}
@media(max-width:1100px){{.topbar{{grid-template-columns:1fr 1fr}}.brand{{grid-column:1/-1}}.candidate-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(max-width:680px){{.topbar{{position:static;display:flex;flex-direction:column;align-items:stretch}}.control{{display:grid;overflow:visible}}.control[aria-label="Profile"]{{grid-template-columns:repeat(3,1fr)}}.control[aria-label="Display state"]{{grid-template-columns:repeat(2,1fr)}}.control[aria-label="Candidate focus"]{{grid-template-columns:repeat(3,1fr)}}.control button{{min-width:0;white-space:normal}}.truth-grid,.candidate-grid{{grid-template-columns:1fr}}.intro h2{{font-size:2.4rem}}.proof{{padding:.9rem .55rem}}.metrics-section{{padding:1rem .55rem}}.card-head{{align-items:start;flex-direction:column}}.status{{justify-content:flex-start}}.surface{{height:56px}}.surface code{{font-size:.38rem}}.bank{{grid-template-columns:1fr}}.editorial,.terminal,.dashboard,.sequence-proof,figure{{margin:.45rem}}.dash-grid{{grid-template-columns:1fr}}.chart,.events,.controls{{grid-column:auto}}form{{grid-template-columns:1fr}}form button{{grid-column:auto}}.status-table{{width:100%;font-size:.58rem}}.status-table th,.status-table td{{padding:.3rem}}}}
@media(prefers-reduced-motion:reduce){{*{{animation:none!important;scroll-behavior:auto!important}}}}
</style></head><body data-profile="3400k-dark" data-state="commanded" data-focus="all">
<header class="topbar"><div class="brand"><h1>EMBER · DARK FOREGROUND WARMTH</h1><p>Fifth pass · frozen system · dependent-bank CAM16-UCS redesign</p></div><div class="control" role="group" aria-label="Profile">{profile_buttons}</div><div class="control" role="group" aria-label="Display state"><button type="button" data-state-button="commanded" aria-pressed="true">Commanded</button><button type="button" data-state-button="simulated" aria-pressed="false">Exact simulated</button></div><div class="control" role="group" aria-label="Candidate focus">{focus_buttons}</div></header>
<main><section class="intro"><p class="eyebrow">BRANCH EXPERIMENT · NOT CANONICAL · FULL ARTIFACT BYTE-LOCKED</p><h2>Optimize around the approved system</h2><p>The complete approved artifact is frozen at SHA <code>{escape(data["approved_artifact_freeze"]["sha256"][:12])}</code>, including profile gains, background/foreground systems and six-role aliases, ordered categorical semantics, terminal banks and aliases, and canonical float/Hex8 sequential ramps. The underlying bg/fg subsystem remains independently locked at <code>{escape(data["frozen_system"]["sha256"][:12])}</code>. Commanded maturity stays in Oklab; transformed pair and foreground clearance use flare-aware CAM16-UCS; WCAG remains an independent legibility gate. The evidence-based six-role production mapping and remaining promotion gates are recorded in <a href="promotion-readiness.md">promotion readiness</a>.</p><div class="truth-grid"><article class="truth-card"><h3>Categorical identity survives profile changes</h3><p>The first three slots are consistently warm amber, cool blue/cyan, and rose/magenta across 3400K, 2000K, and 1200K. Later slots preserve green, teal, and earth families where profile capacity permits; transformed prefix separation breaks semantic ties.</p></article><article class="truth-card"><h3>Real surfaces map honestly to six roles</h3><p>N=5 makes rule and border/selection share the strongest surface. N=4 also makes low-emphasis/sidebar and ordinary panel share, preserving the active/raised and rule/selection boundaries required by six-role consumers.</p></article><article class="truth-card"><h3>Sequential optimization is profile-specific</h3><p>3400K and 2000K stop at perceptually sufficient transformed CV and spend the remaining freedom on commanded uniformity. 1200K minimizes worst sampled-gain CV. Every canonical float stays inside the approved chroma path; six Hex8 anchors are previews.</p></article></div><table class="status-table"><thead><tr><th>Profile</th><th>Current</th><th>Halfway</th></tr></thead><tbody>{statuses}</tbody></table></section>
<section class="metrics-section" id="dependent-frontiers"><p class="eyebrow">DEPENDENT-BANK OUTCOMES · SAMPLED-GRID CAM16-UCS</p><h2>Capacity, semantics, and scalar uniformity</h2><p class="metrics-note">Categorical counts report their sampled-gain minimum pair distance and pass/block state. Terminal columns show the selected bank's sampled-gain minimum pair and foreground clearance. Sequential CV is measured on canonical float samples, not the Hex8 preview anchors.</p>{dependent_frontiers_html(data)}</section>
<section class="metrics-section" id="metrics"><p class="eyebrow">FROZEN SYSTEM METRICS · BEST WITHIN EACH PROFILE ONLY</p><h2>The backgrounds and foregrounds did not move</h2><p class="metrics-note">Every value below is recomputed from the frozen system bytes. <u>Underline</u> marks the best-performing lane(s) per profile for that metric (bold in the README markdown); passing a floor alone is never underlined.</p>{metrics_html(data, computed)}</section>{"".join(sections)}</main><footer class="footer">Exact values: transformed-first-results.json · Reproducible search: search_transformed_first.py · Promotion requires a separate canonical pass.</footer>
<script>
const body=document.body,params=new URLSearchParams(location.search);
const canSync=location.protocol==='http:'||location.protocol==='https:';
function sync(){{if(!canSync)return;const u=new URL(location.href);u.searchParams.set('profile',body.dataset.profile);u.searchParams.set('state',body.dataset.state);u.searchParams.set('candidate',body.dataset.focus);history.replaceState(null,'',u)}}
function profile(v,w=true){{body.dataset.profile=v;document.querySelectorAll('[data-profile-button]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.profileButton===v)));if(w)sync()}}
function state(v,w=true){{body.dataset.state=v;document.querySelectorAll('[data-state-button]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.stateButton===v)));document.querySelectorAll('img[data-commanded]').forEach(i=>i.src=i.dataset[v]);if(w)sync()}}
function focus(v,w=true){{body.dataset.focus=v;document.querySelectorAll('[data-focus-button]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.focusButton===v)));if(w)sync()}}
document.querySelectorAll('[data-profile-button]').forEach(b=>b.addEventListener('click',()=>profile(b.dataset.profileButton)));document.querySelectorAll('[data-state-button]').forEach(b=>b.addEventListener('click',()=>state(b.dataset.stateButton)));document.querySelectorAll('[data-focus-button]').forEach(b=>b.addEventListener('click',()=>focus(b.dataset.focusButton)));
profile({json.dumps(PROFILE_SLUGS)}.includes(params.get('profile'))?params.get('profile'):'3400k-dark',false);state(params.get('state')==='simulated'?'simulated':'commanded',false);focus({json.dumps(list(LANES))}.includes(params.get('candidate'))?params.get('candidate'):'all',false);
</script></body></html>"""


def exact_values_markdown(data: dict[str, Any]) -> str:
    blocks = []
    for profile in PROFILE_SLUGS:
        profile_record = data["profiles"][profile]
        blocks.append(f"### {profile_record['name']}")
        for lane in LANES:
            record = profile_record["lanes"][lane]
            blocks.append(
                f"#### {LANE_LABELS[lane][0]} ({record['bg_count']} surfaces)\n\n"
                "```text\n"
                f"Surfaces:    {' '.join(value.removeprefix('#') for value in lane_surface_values(record))}\n"
                f"Foregrounds: {' '.join(value.removeprefix('#') for value in record['foregrounds'])}\n"
                f"Categorical: {' '.join(value.removeprefix('#') for value in record['categorical'])}\n"
                f"Terminal:    {' '.join(value.removeprefix('#') for value in record['terminal'])}\n"
                f"Sequential:  {' '.join(value.removeprefix('#') for value in record['sequential_anchors'])}\n"
                "```"
            )
    return "\n\n".join(blocks)


def badges_markdown(computed: dict[str, dict[str, dict[str, float]]]) -> str:
    rows = [
        "| Profile | Lane | Distinctness | Universal text |",
        "|---|---|:---:|:---:|",
    ]
    for profile in PROFILE_SLUGS:
        for lane in LANES:
            rows.append(
                f"| {profile} | {LANE_LABELS[lane][0]} | {distinctness_status(computed[profile][lane])} | {universal_status(profile, computed[profile][lane])} |"
            )
    return "\n".join(rows)


def surface_counts_markdown(data: dict[str, Any]) -> str:
    lines = [
        "| Profile | Current bg_count | Halfway bg_count | Halfway choice rule / note |",
        "|---|:---:|:---:|---|",
    ]
    for profile in PROFILE_SLUGS:
        lanes = data["profiles"][profile]["lanes"]
        halfway = lanes["halfway"]
        rule = halfway["search"].get("count_choice_rule") or halfway["search"].get("note", "")
        lines.append(
            f"| {data['profiles'][profile]['name']} | {lanes['current']['bg_count']} | {halfway['bg_count']} | {rule} |"
        )
    return "\n".join(lines)


def categorical_adoption_markdown(data: dict[str, Any]) -> str:
    lines = []
    for profile in PROFILE_SLUGS:
        for lane in LANES:
            record = data["profiles"][profile]["lanes"][lane]
            lines.append(
                f"- **{data['profiles'][profile]['name']} · {LANE_LABELS[lane][0]}:** "
                f"{record['categorical_adoption']}; shipped count is "
                f"{len(record['categorical'])} colors."
            )
    return "\n".join(lines)


def dependent_frontiers_markdown(data: dict[str, Any]) -> str:
    lines = [
        (
            "| Profile | Lane | Categorical frontier (N: sampled-grid CAM16 pair / status) | "
            "Terminal sampled-grid pair | Sequential transformed CV | Commanded CV | "
            "Sampled-gain CV max | Sampled-gain max:min |"
        ),
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for profile in PROFILE_SLUGS:
        for lane in LANES:
            record = data["profiles"][profile]["lanes"][lane]
            frontier_cells = []
            for row in record["categorical_frontier"]:
                rendered = (
                    f"{row['count']}: {row['sampled_grid_pair_cam16_ucs']:.2f} / "
                    f"{'PASS' if row['passes'] else 'FAIL'}"
                )
                if row.get("selected_bank"):
                    if row.get("selected_trial"):
                        rendered += " / selected"
                    else:
                        rendered += (
                            " / trial rejected; shipped selected at "
                            f"{row['selected_bank_sampled_grid_pair_cam16_ucs']:.2f} / PASS"
                        )
                frontier_cells.append(rendered)
            frontier = ", ".join(frontier_cells)
            lines.append(
                f"| {profile} | {LANE_LABELS[lane][0]} | {frontier} | "
                f"{record['terminal_metrics']['sampled_gain_pair_min_cam16_ucs']:.2f} | "
                f"{record['sequential_metrics']['transformed_cam16_cv']:.4f} | "
                f"{record['sequential_metrics']['normal_cv']:.4f} | "
                f"{record['sequential_metrics']['sampled_gain_cv_max']:.4f} | "
                f"{record['sequential_metrics']['sampled_gain_max_to_min_max']:.2f} |"
            )
    return "\n".join(lines)


def render_readme(data: dict[str, Any]) -> str:
    computed = computed_lane_metrics(data)
    return f"""# Dark foreground warmth exploration

> **Branch:** `exp/dark-foreground-warmth`<br>
> **Status:** isolated experiment; not a production palette update<br>
> **Live comparison:** [open `index.html`](index.html)<br>
> **Promotion contract:** [role/alias and remaining-work audit](promotion-readiness.md)

## Bottom line

Design the seen state first: even transformed distinctness binds before commanded warmth; leftover exact-Hex8 freedom buys the halfway hue step for ink and surfaces.

The complete approved artifact is freeze-locked at `{
        data["approved_artifact_freeze"]["sha256"]
    }`. It covers profile gains; current and halfway backgrounds/foregrounds; ordered categorical semantic slots; terminal banks and aliases; canonical float and Hex8 sequential ramps; and their metric/selection contracts. Transformed perceptual metrics use flare-aware CAM16-UCS (`L_A=8`, `Y_b=3`, flare `0.0075` of untransformed white); commanded identity remains in Oklab and WCAG contrast remains an independent hard gate.

## Methodology

- **Transformed-first gating.** Even the *transformed* (warm-display simulated) appearance must keep distinct surfaces and readable text before any commanded-warmth objective is scored. This is the pass's central discipline: the seen state is designed first.
- **Variable surface count.** The halfway lane searches background counts 3–6 per profile; each count gets a bounded exact-Hex8 search with deterministic seeds. Leftover byte freedom inside the ±24-byte radius is what buys the hue step.
- **Independent dependent banks.** Categorical count trials are validated only by categorical gates; terminal and sequential gates cannot veto them. The complete selected assembly receives one final combined validation.
- **Cross-profile categorical identity.** The first three category slots are consistently warm amber, cool blue/cyan, and rose/magenta across every profile. Green/mint, teal, and earth/brown occupy later slots where capacity permits; transformed prefix separation breaks semantic ties.
- **Sampled gain evidence.** Final candidates receive a unique 3×3 grid over nonzero gain axes (blue-zero duplicates are removed). These are sampled-grid diagnostics, not continuous worst-case claims; near-floor candidates receive a denser adaptive scan.
- **Profile-specific scalar construction.** 3400K and 2000K stop at transformed CV ≤ 0.05 and then minimize commanded CV. 1200K minimizes worst sampled-gain CV under nominal transformed CV ≤ 0.10 and commanded CV ≤ 0.18. The approved path/endpoints/chroma envelope remain fixed; 256 float samples are canonical and six Hex8 anchors are previews.
- **Recomputed evidence.** The renderer recomputes every published metric and both badge families from the serialized Hex8 values; no upstream release-status field exists in this schema to trust.

## Chosen surface counts

{surface_counts_markdown(data)}

## Categorical adoption notes

{categorical_adoption_markdown(data)}

## Dependent-bank frontiers

{dependent_frontiers_markdown(data)}

## Distinctness vs universal text badges

The third pass serialized a strict release status per lane; this schema does not. Instead the renderer computes two lightweight lenses from the Hex8 values themselves:

- **Distinctness** — transformed adjacent CAM16-UCS distance ≥ 2.5 on every step, uniformity ratio ≤ 1.6, and span ≥ 6.0;
- **Universal text** — transformed worst-surface contrast floors of `4.5 / 3.5 / 2.4` for `fg_0 / fg_1 / fg_2`, with `fg_0` raised to each family's own primary-text floor when stricter.

{badges_markdown(computed)}

## Combined metrics

Rows are Pareto-ranked: transformed usability first, then commanded warmth. Every value is recomputed from the serialized Hex8 records by the renderer. Underline marks only the best-performing lane(s) **within each profile for that metric** — shown underlined on the page and **bold** in this markdown. Values are not decorated merely for passing a floor. Directions compete; there is no aggregate winner.

{metrics_markdown(data, computed)}

## Reader-facing proof domains

The [live page](index.html) keeps both warmth lanes visible together by default for the selected profile and provides controls for:

- profile: 3400K / 2000K / 1200K;
- commanded vs exact signal simulation;
- optional single-lane focus (all / current / halfway).

It includes complete anatomy, a substantial editorial hierarchy, realistic code/terminal syntax and all semantic roles, a dense dashboard with categories/statuses/table/forms, sequential gradient and heatmap, real Mars MOLA scalar data, Mona Lisa photographic mapping, and a scientific propagation figure. Mars and Mona are candidate-specific commanded PNGs with separately generated exact-simulated PNGs; raster evidence is not a CSS-only transform.

## Static review captures

The interactive page is authoritative. These committed captures make the same comparison reviewable directly on GitHub:

{
        chr(10).join(
            f"- [`{name}`](review-captures/{name})"
            for name in (
                "3400k-dark-anatomy-commanded.png",
                "3400k-dark-anatomy-simulated.png",
                "2000k-dark-anatomy-commanded.png",
                "2000k-dark-anatomy-simulated.png",
                "1200k-dark-anatomy-commanded.png",
                "1200k-dark-anatomy-simulated.png",
                "3400k-dark-terminal-commanded.png",
                "3400k-dark-terminal-simulated.png",
                "3400k-dark-dashboard-commanded.png",
                "3400k-dark-dashboard-simulated.png",
                "3400k-dark-science-commanded.png",
                "3400k-dark-science-simulated.png",
                "metrics-table.png",
                "phone-metrics.png",
                "phone-2000k-halfway-simulated.png",
            )
        )
    }

![2000K Dark Halfway exact simulated at 390 px](review-captures/phone-2000k-halfway-simulated.png)

## Exact values

{exact_values_markdown(data)}

## Search provenance and reproducibility

- Exact selected data, per-count system searches with seeds, iterations, evaluated candidate counts, accepted moves, objectives, continuous float maps, Hex8 previews, categorical trials, and adoption notes: [`transformed-first-results.json`](transformed-first-results.json)
- Reproducible bounded search: [`search_transformed_first.py`](search_transformed_first.py)
- Deterministic renderer: [`../../../tools/render_dark_foreground_warmth_experiment.py`](../../../tools/render_dark_foreground_warmth_experiment.py)
- Independent verification: [`../../../tests/test_dark_foreground_warmth_experiment.py`](../../../tests/test_dark_foreground_warmth_experiment.py)

The simulated state applies each family's documented encoded-sRGB diagonal gain vector.

## Promotion boundary

Nothing here is canonical. If a warmth lane is chosen, promotion is a separate pass that must update authoritative definitions, transformed targets, generated exports, release invariants, public documentation, and downstream themes. Experimental prose, failed candidates, and comparison-only assets should not leak into the production reader path.
"""


def main() -> int:
    data = load_data()
    render_candidate_assets(data)
    (OUT / "index.html").write_text(render_html(data), encoding="utf-8")
    (OUT / "README.md").write_text(render_readme(data), encoding="utf-8")
    print(f"rendered dark foreground warmth comparison under {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
