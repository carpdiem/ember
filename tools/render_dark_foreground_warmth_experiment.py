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

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TOOLS = ROOT / "tools"
for path in (SRC, TOOLS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_all import _mars_topography_colormap_image, _mona_lisa_colormap_image

from ember.color import hex_to_srgb, srgb_to_hex, warm_transform
from ember.definitions import FAMILIES
from ember.generate import generate_family

OUT = ROOT / "docs/experiments/dark-foreground-warmth"
SEARCH = OUT / "search-results.json"
SEARCH_SCRIPT = OUT / "search_full_palette.py"
ASSETS = OUT / "candidate-assets"
PROFILE_SLUGS = ("3400k-dark", "2000k-dark", "1200k-dark")
LANES = ("current", "halfway", "full")
LANE_LABELS = {
    "current": ("Current warmth", "Shipped dark warmth target; relaxed foreground lightness"),
    "halfway": ("Halfway", "50% of the Light Mid-Depth hue step for ink and surfaces"),
    "full": ("Full step", "Light Mid-Depth hue level for ink and surfaces, dark hierarchy kept"),
}
TERM_NAMES = ("red", "green", "yellow", "blue", "magenta", "cyan")
UNIVERSAL_FOREGROUND_FLOORS = (4.5, 3.5, 2.4)

METRICS = (
    (
        "Strict release status",
        "strict_status",
        "higher",
        lambda c: 1.0 if c["release_status"] == "PASS" else 0.0,
        ".0f",
    ),
    (
        "FG-0 worst-surface transformed contrast",
        "fg0_contrast",
        "higher",
        lambda c: c["metrics"]["foreground"]["worst_surface_shifted_contrast"][0],
        ".2f",
    ),
    (
        "FG-1 worst-surface transformed contrast",
        "fg1_contrast",
        "higher",
        lambda c: c["metrics"]["foreground"]["worst_surface_shifted_contrast"][1],
        ".2f",
    ),
    (
        "FG-2 worst-surface transformed contrast",
        "fg2_contrast",
        "higher",
        lambda c: c["metrics"]["foreground"]["worst_surface_shifted_contrast"][2],
        ".2f",
    ),
    (
        "Foreground mean +b",
        "fg_mean_b",
        "lower",
        lambda c: c["metrics"]["foreground"]["normal_mean_plus_b"],
        ".4f",
    ),
    (
        "Foreground mean chroma",
        "fg_mean_chroma",
        "lower",
        lambda c: c["metrics"]["foreground"]["normal_mean_chroma"],
        ".4f",
    ),
    (
        "Foreground chroma reduction vs current",
        "fg_reduction",
        "higher",
        lambda c: c["metrics"]["foreground"]["chroma_reduction_vs_current_percent"],
        ".1f",
    ),
    *(
        (
            f"FG-{index} absolute L movement from shipped",
            f"fg{index}_dl",
            "lower",
            lambda c, index=index: abs(c["foreground_lightness_deltas_vs_shipped"][index]),
            ".4f",
        )
        for index in range(3)
    ),
    (
        "Foreground adjacent ΔEOK, transformed minimum",
        "fg_night_adj",
        "higher",
        lambda c: min(c["metrics"]["foreground"]["shifted_adjacent_delta_e_ok"]),
        ".2f",
    ),
    (
        "Foreground adjacent ΔEOK, day minimum",
        "fg_day_adj",
        "higher",
        lambda c: min(c["metrics"]["foreground"]["normal_adjacent_delta_e_ok"]),
        ".2f",
    ),
    (
        "Terminal foreground clearance, transformed",
        "term_night_fg",
        "higher",
        lambda c: c["metrics"]["terminal"]["shifted_foreground_clearance_min"],
        ".2f",
    ),
    (
        "Terminal foreground clearance, day",
        "term_day_fg",
        "higher",
        lambda c: c["metrics"]["terminal"]["normal_foreground_clearance_min"],
        ".2f",
    ),
    (
        "Categorical foreground clearance, transformed",
        "cat_night_fg",
        "higher",
        lambda c: c["metrics"]["categorical"]["shifted_foreground_clearance_min"],
        ".2f",
    ),
    (
        "Categorical foreground clearance, day",
        "cat_day_fg",
        "higher",
        lambda c: c["metrics"]["categorical"]["normal_foreground_clearance_min"],
        ".2f",
    ),
    *(
        (
            f"FG-{index} commanded Oklab L",
            f"fg{index}_l",
            "higher",
            lambda c, index=index: c["metrics"]["foreground"]["normal_lightness"][index],
            ".4f",
        )
        for index in range(3)
    ),
    (
        "Surface mean movement ΔEOK",
        "surface_move",
        "lower",
        lambda c: c["surface_movement_mean_delta_e_ok"],
        ".3f",
    ),
    (
        "Surface transformed adjacent ΔEOK minimum",
        "surface_step",
        "higher",
        lambda c: min(c["metrics"]["surface"]["shifted_adjacent_delta_e_ok"]),
        ".2f",
    ),
    (
        "Surface transformed span ΔEOK",
        "surface_span",
        "higher",
        lambda c: c["metrics"]["surface"]["shifted_span_delta_e_ok"],
        ".2f",
    ),
    (
        "Categorical pair separation, transformed",
        "cat_night_pair",
        "higher",
        lambda c: c["metrics"]["categorical"]["shifted_pair_delta_e_ok"],
        ".2f",
    ),
    (
        "Categorical pair separation, day",
        "cat_day_pair",
        "higher",
        lambda c: c["metrics"]["categorical"]["normal_pair_delta_e_ok"],
        ".2f",
    ),
    (
        "Categorical BG-0 transformed contrast",
        "cat_bg",
        "higher",
        lambda c: c["metrics"]["categorical"]["shifted_background_contrast_bg0_min"],
        ".2f",
    ),
    (
        "Terminal pair separation, transformed",
        "term_night_pair",
        "higher",
        lambda c: c["metrics"]["terminal"]["shifted_pair_delta_e_ok"],
        ".2f",
    ),
    (
        "Terminal group separation, day",
        "term_day_pair",
        "higher",
        lambda c: c["metrics"]["terminal"]["normal_pair_delta_e_ok"],
        ".2f",
    ),
    (
        "Terminal BG-0 transformed contrast",
        "term_bg",
        "higher",
        lambda c: c["metrics"]["terminal"]["shifted_background_contrast_bg0_min"],
        ".2f",
    ),
    (
        "Sequential transformed CV",
        "seq_night_cv",
        "lower",
        lambda c: c["metrics"]["sequential"]["shifted_cv"],
        ".4f",
    ),
    (
        "Sequential day CV",
        "seq_day_cv",
        "lower",
        lambda c: c["metrics"]["sequential"]["normal_cv"],
        ".4f",
    ),
    (
        "Sequential transformed max:min",
        "seq_night_ratio",
        "lower",
        lambda c: c["metrics"]["sequential"]["shifted_max_to_min"],
        ".3f",
    ),
    (
        "Sequential day max:min",
        "seq_day_ratio",
        "lower",
        lambda c: c["metrics"]["sequential"]["normal_max_to_min"],
        ".3f",
    ),
    (
        "Sequential transformed lightness range",
        "seq_night_l",
        "higher",
        lambda c: c["metrics"]["sequential"]["shifted_lightness_range"],
        ".4f",
    ),
    (
        "Sequential day lightness range",
        "seq_day_l",
        "higher",
        lambda c: c["metrics"]["sequential"]["normal_lightness_range"],
        ".4f",
    ),
    (
        "Sampled categorical gain-corner pair minimum",
        "corner_cat",
        "higher",
        lambda c: c["metrics"]["categorical"]["gain_corner_pair_min"],
        ".2f",
    ),
    (
        "Sampled terminal gain-corner pair minimum",
        "corner_term",
        "higher",
        lambda c: c["metrics"]["terminal"]["gain_corner_pair_min"],
        ".2f",
    ),
    (
        "Sampled sequential gain-corner CV maximum",
        "corner_seq",
        "lower",
        lambda c: c["metrics"]["sequential"]["gain_corner_cv_max"],
        ".4f",
    ),
)


def family(slug: str):
    return next(item for item in FAMILIES if item.slug == slug)


def load_data() -> dict[str, Any]:
    return json.loads(SEARCH.read_text(encoding="utf-8"))


def candidate_definition(slug: str, record: dict[str, Any]):
    base = family(slug)
    surfaces = dict(base.surfaces)
    surfaces.update(record["surfaces"])
    surfaces.update({f"fg_{index}": value for index, value in enumerate(record["foregrounds"])})
    return replace(
        base,
        surfaces=surfaces,
        categorical_colors=tuple(record["categorical"]),
        categorical_transformed_targets=tuple(record["categorical_transformed_targets"]),
        terminal_colors=tuple(record["terminal"]),
        terminal_transformed_targets=tuple(record["terminal_transformed_targets"]),
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
            record = data["profiles"][profile]["candidates"][lane]
            generated = generate_family(candidate_definition(profile, record))
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
    for index in range(6):
        variables.append(f"--bg-{index}:{state(record['surfaces'][f'bg_{index}'])}")
    for index, value in enumerate(record["foregrounds"]):
        variables.append(f"--fg-{index}:{state(value)}")
    for index, value in enumerate(record["categorical"]):
        variables.append(f"--cat-{index + 1}:{state(value)}")
    expanded_terminal = [record["terminal"][index] for index in record["terminal_ansi_indices"]]
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


def universal_status(record: dict[str, Any]) -> str:
    contrasts = record["metrics"]["foreground"]["worst_surface_shifted_contrast"]
    return (
        "PASS"
        if all(
            value + 1e-12 >= floor
            for value, floor in zip(contrasts, UNIVERSAL_FOREGROUND_FLOORS, strict=True)
        )
        else "FAIL"
    )


def best_lanes(profile_record: dict[str, Any], extractor, direction: str) -> set[str]:
    values = {lane: float(extractor(profile_record["candidates"][lane])) for lane in LANES}
    best = min(values.values()) if direction == "lower" else max(values.values())
    return {lane for lane, value in values.items() if abs(value - best) <= 1e-12}


def format_metric(value: float, spec: str, key: str) -> str:
    if key == "strict_status":
        return "PASS" if value >= 1.0 else "FAIL"
    text = format(value, spec)
    return f"{text}%" if key == "fg_reduction" else text


def metrics_html(data: dict[str, Any]) -> str:
    headers = "".join(
        f'<th colspan="3">{escape(data["profiles"][profile]["name"])}</th>'
        for profile in PROFILE_SLUGS
    )
    lanes = "".join(f"<th>{LANE_LABELS[lane][0]}</th>" for _ in PROFILE_SLUGS for lane in LANES)
    rows = []
    for label, key, direction, extractor, spec in METRICS:
        cells = []
        for profile in PROFILE_SLUGS:
            profile_record = data["profiles"][profile]
            best = best_lanes(profile_record, extractor, direction)
            for lane in LANES:
                value = float(extractor(profile_record["candidates"][lane]))
                rendered = format_metric(value, spec, key)
                cells.append(
                    f"<td>{'<strong>' + rendered + '</strong>' if lane in best else rendered}</td>"
                )
        arrow = "↓ lower" if direction == "lower" else "↑ higher"
        rows.append(
            f'<tr data-metric="{key}"><th>{escape(label)}</th><td class="direction">{arrow}</td>{"".join(cells)}</tr>'
        )
    return (
        '<div class="table-scroll"><table class="metrics"><thead><tr><th rowspan="2">Metric</th>'
        f'<th rowspan="2">Direction</th>{headers}</tr><tr>{lanes}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def metrics_markdown(data: dict[str, Any]) -> str:
    columns = [
        f"{data['profiles'][profile]['name']} {LANE_LABELS[lane][0]}"
        for profile in PROFILE_SLUGS
        for lane in LANES
    ]
    lines = [
        "| Metric | Direction | " + " | ".join(columns) + " |",
        "|---|:---:|" + "|".join("---:" for _ in columns) + "|",
    ]
    for label, key, direction, extractor, spec in METRICS:
        cells = []
        for profile in PROFILE_SLUGS:
            profile_record = data["profiles"][profile]
            best = best_lanes(profile_record, extractor, direction)
            for lane in LANES:
                value = float(extractor(profile_record["candidates"][lane]))
                rendered = format_metric(value, spec, key)
                cells.append(f"**{rendered}**" if lane in best else rendered)
        arrow = "↓ lower" if direction == "lower" else "↑ higher"
        lines.append(f"| {label} | {arrow} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def swatches(values: list[str], kind: str) -> str:
    return "".join(
        f'<span class="swatch {kind}-{index + 1}"><code>{value}</code></span>'
        for index, value in enumerate(values)
    )


def anatomy(profile: str, lane: str, record: dict[str, Any]) -> str:
    surfaces = "".join(
        f'<span class="surface bg-{index}"><b>BG-{index}</b><code>{record["surfaces"][f"bg_{index}"]}</code></span>'
        for index in range(6)
    )
    foregrounds = "".join(
        f'<p class="fg-{index}"><b>FG-{index}</b> {record["foregrounds"][index]} · hierarchy sample</p>'
        for index in range(3)
    )
    strict = record["release_status"]
    universal = universal_status(record)
    failures = "".join(f"<li>{escape(item)}</li>" for item in record["release_failures"])
    search_summary = ", ".join(
        f"{bank}: {'changed' if record['search'][bank]['changed_from_shipped'] else 'reselected shipped exact'}"
        for bank in ("full_system", "categorical", "terminal", "sequential")
    )
    return f"""
<header class="card-head"><div><p>{LANE_LABELS[lane][1]}</p><h3>{LANE_LABELS[lane][0]}</h3></div><div class="status"><span class="status-{strict.lower()}">Strict {strict}</span><span class="status-{universal.lower()}">Universal text {universal}</span></div></header>
<div class="surface-strip">{surfaces}</div><div class="foregrounds">{foregrounds}</div>
<div class="bank"><b>Categorical · {len(record["categorical"])}</b><div class="swatches">{swatches(record["categorical"], "cat")}</div></div>
<div class="bank"><b>Terminal authored · {len(record["terminal"])}</b><div class="swatches">{swatches(record["terminal"], "term")}</div></div>
<div class="gradient"></div><p class="search-summary">Fresh controlled search: {search_summary}. Every bank uses the same profile-specific seed pair in every lane. Sequential dependencies are recorded from the selected exact surfaces, so identical maps are evidence of identical inputs rather than seed noise.</p>
<details><summary>{len(record["release_failures"])} strict release-contract failure(s)</summary><ul>{failures or "<li>None.</li>"}</ul></details>
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


def candidate_card(profile: str, lane: str, record: dict[str, Any], domain: str) -> str:
    content = {
        "anatomy": anatomy(profile, lane, record),
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
    candidate_css = "\n".join(
        css_variables(
            profile,
            lane,
            data["profiles"][profile]["candidates"][lane],
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
            candidate_card(profile, lane, data["profiles"][profile]["candidates"][lane], domain)
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
            f'<td><b class="status-{data["profiles"][profile]["candidates"][lane]["release_status"].lower()}">Strict {data["profiles"][profile]["candidates"][lane]["release_status"]}</b><br><span>Universal text {universal_status(data["profiles"][profile]["candidates"][lane])}</span></td>'
            for lane in LANES
        )
        + "</tr>"
        for profile in PROFILE_SLUGS
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ember dark foreground warmth experiment</title><style>
:root{{--wrap-0:{wrapper["bg_0"]};--wrap-1:{wrapper["bg_1"]};--wrap-2:{wrapper["bg_2"]};--wrap-3:{wrapper["bg_3"]};--wrap-4:{wrapper["bg_4"]};--wrap-5:{wrapper["bg_5"]};--wrap-fg-0:{wrapper["fg_0"]};--wrap-fg-1:{wrapper["fg_1"]};--wrap-fg-2:{wrapper["fg_2"]};color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif}}*{{box-sizing:border-box}}html,body{{margin:0;max-width:100%;background:var(--wrap-0);color:var(--wrap-fg-0)}}button,input,select{{font:inherit}}.topbar{{position:sticky;top:0;z-index:50;display:grid;grid-template-columns:minmax(16rem,1fr) auto auto auto;gap:.65rem;align-items:center;padding:.65rem clamp(.65rem,2vw,1.4rem);background:rgba(16,14,12,.97);border-bottom:1px solid var(--wrap-4)}}.brand h1{{font-size:.85rem;letter-spacing:.08em;margin:0}}.brand p{{font-size:.62rem;color:var(--wrap-fg-2);margin:.2rem 0 0}}.control{{display:flex;gap:2px;padding:2px;background:var(--wrap-2);border:1px solid var(--wrap-4)}}.control button{{min-height:44px;padding:.35rem .65rem;border:0;background:transparent;color:var(--wrap-fg-1);cursor:pointer;white-space:nowrap}}.control button[aria-pressed="true"]{{background:var(--wrap-5);color:var(--wrap-fg-0)}}.intro,.proof,.metrics-section{{max-width:118rem;margin:0 auto;padding:clamp(1rem,3vw,2.8rem) clamp(.65rem,2vw,1.5rem)}}.eyebrow,.proof>header p{{font:700 .58rem ui-monospace,monospace;letter-spacing:.16em;color:var(--wrap-fg-2);margin:0}}.intro h2{{font:500 clamp(2rem,5vw,5rem)/.95 Georgia,serif;max-width:18ch;margin:.5rem 0 1rem}}.intro>p{{max-width:72rem;color:var(--wrap-fg-1);line-height:1.55}}.truth-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.6rem;margin-top:1.2rem}}.truth-card{{padding:1rem;background:var(--wrap-1);border:1px solid var(--wrap-4)}}.truth-card h3{{font-size:.8rem;margin:0 0 .4rem}}.truth-card p{{font-size:.7rem;line-height:1.5;color:var(--wrap-fg-1);margin:0}}.status-table{{margin-top:1rem;border-collapse:collapse;font-size:.68rem}}.status-table th,.status-table td{{padding:.5rem;border:1px solid var(--wrap-4);text-align:left}}.status-pass{{color:#7EB798}}.status-fail{{color:#F5AD9A}}.metrics-section,.proof{{border-top:1px solid var(--wrap-4);scroll-margin-top:4.5rem}}.metrics-section h2,.proof>header h2{{font-size:1rem;margin:.25rem 0}}.metrics-note,.proof>header span{{font-size:.68rem;color:var(--wrap-fg-2)}}.table-scroll{{overflow-x:auto;margin-top:1rem;border:1px solid var(--wrap-4)}}.metrics{{border-collapse:collapse;min-width:118rem;width:100%;font:500 .58rem ui-monospace,monospace}}.metrics th,.metrics td{{padding:.42rem .5rem;border:1px solid var(--wrap-4);text-align:right}}.metrics thead th{{background:var(--wrap-2);color:var(--wrap-fg-1);text-align:center}}.metrics tbody th{{position:sticky;left:0;background:var(--wrap-1);text-align:left;min-width:18rem}}.metrics .direction{{color:var(--wrap-fg-2);white-space:nowrap}}.metrics strong{{color:var(--wrap-fg-0);font-weight:inherit;text-decoration:underline 2px;text-underline-offset:3px}}.proof>header{{margin-bottom:.8rem}}.domain-head{{display:flex;align-items:baseline;justify-content:space-between;gap:.5rem;padding:.55rem .7rem;background:var(--bg-1);border-bottom:1px solid var(--bg-4)}}.domain-head p{{margin:0;font:.48rem ui-monospace,monospace;color:var(--fg-2)}}.domain-head h3{{margin:0;font-size:.72rem}}.candidate-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.65rem}}.candidate-card{{min-width:0;background:var(--bg-0);color:var(--fg-0);border:1px solid var(--bg-5);overflow:hidden}}body:not([data-profile="3400k-dark"]) [data-profile="3400k-dark"],body:not([data-profile="2000k-dark"]) [data-profile="2000k-dark"],body:not([data-profile="1200k-dark"]) [data-profile="1200k-dark"]{{display:none}}body[data-focus="current"] [data-candidate]:not([data-candidate="current"]),body[data-focus="halfway"] [data-candidate]:not([data-candidate="halfway"]),body[data-focus="full"] [data-candidate]:not([data-candidate="full"]){{display:none}}body[data-focus]:not([data-focus="all"]) .candidate-grid{{grid-template-columns:minmax(0,38rem);justify-content:center}}.card-head{{display:flex;justify-content:space-between;gap:.5rem;align-items:end;padding:.7rem;background:var(--bg-1);border-bottom:1px solid var(--bg-4)}}.card-head p{{font:.5rem ui-monospace,monospace;color:var(--fg-2);margin:0}}.card-head h3{{font-size:.9rem;margin:.15rem 0 0}}.status{{display:flex;gap:.25rem;flex-wrap:wrap;justify-content:flex-end}}.status span{{font:700 .46rem ui-monospace,monospace;padding:.2rem .3rem;border:1px solid currentColor}}.surface-strip{{display:grid;grid-template-columns:repeat(6,1fr);margin:.7rem;border:1px solid var(--bg-5)}}.surface{{height:64px;display:flex;flex-direction:column;justify-content:end;padding:.3rem;min-width:0}}.surface b,.surface code{{font:.43rem ui-monospace,monospace;overflow:hidden}}.surface code{{color:var(--fg-2)}}.bg-0{{background:var(--bg-0)}}.bg-1{{background:var(--bg-1)}}.bg-2{{background:var(--bg-2)}}.bg-3{{background:var(--bg-3)}}.bg-4{{background:var(--bg-4)}}.bg-5{{background:var(--bg-5)}}.foregrounds,.bank{{padding:0 .7rem}}.foregrounds p{{font:.58rem ui-monospace,monospace;margin:.28rem 0}}.fg-0{{color:var(--fg-0)}}.fg-1{{color:var(--fg-1)}}.fg-2{{color:var(--fg-2)}}.bank{{display:grid;grid-template-columns:7rem 1fr;align-items:center;gap:.4rem;margin-top:.65rem;font:.52rem ui-monospace,monospace}}.swatches{{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:2px}}.swatch{{height:30px;display:block}}.swatch code{{display:none}}.cat-1{{background:var(--cat-1)}}.cat-2{{background:var(--cat-2)}}.cat-3{{background:var(--cat-3)}}.cat-4{{background:var(--cat-4)}}.cat-5{{background:var(--cat-5)}}.cat-6{{background:var(--cat-6)}}.term-1{{background:var(--term-red)}}.term-2{{background:var(--term-green)}}.term-3{{background:var(--term-yellow)}}.term-4{{background:var(--term-blue)}}.term-5{{background:var(--term-magenta)}}.term-6{{background:var(--term-cyan)}}.gradient{{height:20px;margin:.7rem;background:var(--seq);border:1px solid var(--bg-4)}}.search-summary,details{{font:.5rem/1.4 ui-monospace,monospace;color:var(--fg-2);margin:.5rem .7rem}}details ul{{padding-left:1.2rem}}.editorial,.terminal,.dashboard,.sequence-proof,figure{{margin:.7rem}}.editorial{{padding:clamp(1rem,3vw,2rem);background:var(--bg-1);min-height:31rem}}.editorial .kicker,.editorial .caption{{font:.54rem ui-monospace,monospace;color:var(--fg-2)}}.editorial h3{{font:500 1.55rem/1.05 Georgia,serif;margin:.65rem 0}}.editorial h4{{font:.8rem ui-sans-serif,sans-serif;margin:1.2rem 0 .25rem}}.editorial p,.editorial blockquote{{font:.76rem/1.6 Georgia,serif}}.editorial .standfirst,.editorial .support{{color:var(--fg-1)}}.editorial a{{color:var(--cat-1)}}.editorial mark{{background:var(--bg-5);color:var(--fg-0)}}.editorial blockquote{{margin:1rem 0;padding:.7rem;border-left:3px solid var(--cat-3);background:var(--bg-2)}}.terminal{{background:var(--bg-1);border:1px solid var(--bg-4);min-height:22rem}}.terminal header{{display:flex;gap:.3rem;align-items:center;padding:.55rem;background:var(--bg-2);border-bottom:1px solid var(--bg-4);font:.5rem ui-monospace,monospace}}.terminal header i{{width:7px;height:7px;border-radius:50%;background:var(--bg-5)}}.terminal pre{{padding:.85rem;margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:.57rem/1.75 ui-monospace,monospace}}.prompt,.comment{{color:var(--fg-2)}}.keyword{{color:var(--term-magenta)}}.function{{color:var(--term-cyan)}}.string{{color:var(--term-green)}}.selection{{background:var(--bg-5)}}.terminal-status{{display:grid;grid-template-columns:repeat(3,1fr);gap:.25rem;padding:.7rem;border-top:1px solid var(--bg-4);font:700 .48rem ui-monospace,monospace}}.terminal-status span{{background:var(--bg-2);padding:.35rem}}.term-red{{color:var(--term-red)}}.term-green{{color:var(--term-green)}}.term-yellow{{color:var(--term-yellow)}}.term-blue{{color:var(--term-blue)}}.term-magenta{{color:var(--term-magenta)}}.term-cyan{{color:var(--term-cyan)}}.dashboard{{border:1px solid var(--bg-4);background:var(--bg-1);font-family:ui-monospace,monospace}}.dashboard>header{{display:flex;justify-content:space-between;align-items:center;padding:.6rem;background:var(--bg-2);font-size:.52rem}}.dashboard header small{{display:block;color:var(--fg-2);margin-top:.2rem}}.dashboard button,.dashboard input,.dashboard select{{background:var(--bg-2);color:var(--fg-0);border:1px solid var(--bg-5);min-height:32px}}.dash-grid{{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--bg-4)}}.dash-grid section{{min-width:0;padding:.65rem;background:var(--bg-1)}}.dash-grid section>b{{font-size:.5rem;letter-spacing:.06em}}.summary strong{{display:block;font-size:1.6rem;margin:.5rem 0}}progress{{width:100%;accent-color:var(--cat-1)}}.summary p{{display:flex;gap:.3rem;flex-wrap:wrap;font-size:.42rem}}dl{{display:grid;grid-template-columns:repeat(3,1fr);gap:.2rem}}dl div{{padding:.35rem;background:var(--bg-2)}}dt{{font-size:.42rem;color:var(--fg-2)}}dd{{font-size:.62rem;margin:.1rem 0 0}}.chart,.events,.controls{{grid-column:1/-1}}.chart svg{{display:block;width:100%;height:130px;background:var(--bg-0);margin-top:.45rem}}.grid{{stroke:var(--bg-4);fill:none}}.series,.wave{{fill:none;stroke-width:2}}.cat-stroke-1{{stroke:var(--cat-1)}}.cat-stroke-2{{stroke:var(--cat-2)}}.cat-stroke-3{{stroke:var(--cat-3)}}.cat-stroke-4{{stroke:var(--cat-4)}}.cat-stroke-5{{stroke:var(--cat-5)}}.cat-stroke-6{{stroke:var(--cat-6)}}.cat-fill-1{{fill:var(--cat-1)}}.cat-fill-2{{fill:var(--cat-2)}}.heat>div,.heatmap{{display:grid;grid-template-columns:repeat(5,1fr);gap:2px;margin-top:.5rem}}.heat i,.heatmap i{{height:32px;background:var(--seq);background-size:1100% 100%;background-position:calc(var(--n) * -10%) 0}}.events table{{width:100%;border-collapse:collapse;margin-top:.4rem;font-size:.48rem}}.events th,.events td{{padding:.35rem;border:1px solid var(--bg-4);text-align:left}}.events .selected{{background:var(--bg-5)}}form{{display:grid;grid-template-columns:1fr 1fr;gap:.5rem;margin-top:.5rem;font-size:.5rem}}form label{{display:grid;gap:.25rem}}form label:nth-child(3){{display:flex;align-items:center}}form button{{grid-column:1/-1}}.sequence-proof{{padding:.2rem;background:var(--bg-1);border:1px solid var(--bg-4)}}figure{{padding:.55rem;background:var(--bg-1);border:1px solid var(--bg-4)}}figure img,figure svg{{display:block;width:100%;height:auto}}figcaption{{display:grid;gap:.15rem;margin-top:.4rem;font-size:.5rem}}figcaption span{{color:var(--fg-2)}}.scientific svg{{background:var(--bg-0)}}.axis{{fill:none;stroke:var(--fg-2)}}.wave{{stroke-width:3}}.dashed{{stroke-dasharray:9 5}}.marker{{stroke-dasharray:4 4}}.footer{{padding:2rem;text-align:center;color:var(--wrap-fg-2);font:.58rem ui-monospace,monospace}}{candidate_css}
@media(max-width:1100px){{.topbar{{grid-template-columns:1fr 1fr}}.brand{{grid-column:1/-1}}.candidate-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(max-width:680px){{.topbar{{position:static;display:flex;flex-direction:column;align-items:stretch}}.control{{display:grid;overflow:visible}}.control[aria-label="Profile"]{{grid-template-columns:repeat(3,1fr)}}.control[aria-label="Display state"]{{grid-template-columns:repeat(2,1fr)}}.control[aria-label="Candidate focus"]{{grid-template-columns:repeat(2,1fr)}}.control button{{min-width:0;white-space:normal}}.truth-grid,.candidate-grid{{grid-template-columns:1fr}}.intro h2{{font-size:2.4rem}}.proof{{padding:.9rem .55rem}}.metrics-section{{padding:1rem .55rem}}.card-head{{align-items:start;flex-direction:column}}.status{{justify-content:flex-start}}.surface{{height:56px}}.surface code{{font-size:.38rem}}.bank{{grid-template-columns:1fr}}.editorial,.terminal,.dashboard,.sequence-proof,figure{{margin:.45rem}}.dash-grid{{grid-template-columns:1fr}}.chart,.events,.controls{{grid-column:auto}}form{{grid-template-columns:1fr}}form button{{grid-column:auto}}.status-table{{width:100%;font-size:.58rem}}.status-table th,.status-table td{{padding:.3rem}}}}
@media(prefers-reduced-motion:reduce){{*{{animation:none!important;scroll-behavior:auto!important}}}}
</style></head><body data-profile="3400k-dark" data-state="commanded" data-focus="all">
<header class="topbar"><div class="brand"><h1>EMBER · DARK FOREGROUND WARMTH</h1><p>Transformed-first relaxed-L · full-system exact search</p></div><div class="control" role="group" aria-label="Profile">{profile_buttons}</div><div class="control" role="group" aria-label="Display state"><button type="button" data-state-button="commanded" aria-pressed="true">Commanded</button><button type="button" data-state-button="simulated" aria-pressed="false">Exact simulated</button></div><div class="control" role="group" aria-label="Candidate focus">{focus_buttons}</div></header>
<main><section class="intro"><p class="eyebrow">BRANCH EXPERIMENT · NOT CANONICAL · NO SINGLE SCALAR WINNER</p><h2>How much hue can Ember's dark system lose?</h2><p>This third pass steps both ink <em>and</em> surfaces toward the 3400K Light Mid-Depth hue philosophy: current keeps every shipped a/b vector; halfway interpolates all nine roles 50% of the way; full reaches the Light Mid-Depth hue level while keeping each role's shipped Oklab lightness and the dark palettes' decreasing-chroma hierarchy. Foreground lightness stays free within an explicit bound so transformed usability is never traded away, and categorical, terminal, and sequential banks are re-searched against each lane's exact selected system. Every value is scored only after exact Hex8 quantization.</p><div class="truth-grid"><article class="truth-card"><h3>Transformed usability first</h3><p>Current release floors are hard penalties. Hue targets, chroma, and movement are softer competing objectives after usability.</p></article><article class="truth-card"><h3>Hue step, not lightness step</h3><p>Surfaces move in hue (a/b) only; their dark lightness ladder, luminance ceilings, spacing, span, and text contrast gates still bind exactly.</p></article><article class="truth-card"><h3>Controlled dependencies</h3><p>Identical seed pairs are reused across lanes. Sequential searches record a surface dependency fingerprint, so map invariance or change follows actual inputs rather than seed noise.</p></article></div><table class="status-table"><thead><tr><th>Profile</th><th>Current</th><th>Halfway</th><th>Full</th></tr></thead><tbody>{statuses}</tbody></table></section>
<section class="metrics-section" id="metrics"><p class="eyebrow">COMBINED METRICS · BEST WITHIN EACH PROFILE ONLY</p><h2>Competing directions, no scalar winner</h2><p class="metrics-note">Rows are Pareto-ranked: usability and warmth first, provenance and secondary detail below. <u>Underline</u> marks the best-performing lane(s) per profile for that metric; passing a floor alone is never underlined. Gain-corner extrema are observations at four sampled ±5% G/B corners, not box-wide guarantees.</p>{metrics_html(data)}</section>{"".join(sections)}</main><footer class="footer">Exact values: search-results.json · Reproducible search: search_full_palette.py · Promotion requires a separate canonical pass.</footer>
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
            record = profile_record["candidates"][lane]
            blocks.append(
                f"#### {LANE_LABELS[lane][0]}\n\n"
                "```text\n"
                f"Surfaces:    {' '.join(value.removeprefix('#') for value in record['surfaces'].values())}\n"
                f"Foregrounds: {' '.join(value.removeprefix('#') for value in record['foregrounds'])}\n"
                f"Categorical: {' '.join(value.removeprefix('#') for value in record['categorical'])}\n"
                f"Terminal:    {' '.join(value.removeprefix('#') for value in record['terminal'])}\n"
                f"Sequential:  {' '.join(value.removeprefix('#') for value in record['sequential_anchors'])}\n"
                "```"
            )
    return "\n\n".join(blocks)


def failures_markdown(data: dict[str, Any]) -> str:
    rows = [
        "| Profile | Lane | Strict contract | Universal text roles | Exact failed gates |",
        "|---|---|:---:|:---:|---|",
    ]
    for profile in PROFILE_SLUGS:
        for lane in LANES:
            record = data["profiles"][profile]["candidates"][lane]
            failures = "<br>".join(f"`{item}`" for item in record["release_failures"]) or "None"
            rows.append(
                f"| {data['profiles'][profile]['name']} | {LANE_LABELS[lane][0]} | {record['release_status']} | {universal_status(record)} | {failures} |"
            )
    return "\n".join(rows)


def current_lane_summary(data: dict[str, Any]) -> str:
    lines = []
    for profile in PROFILE_SLUGS:
        record = data["profiles"][profile]["candidates"]["current"]
        outcomes = []
        for bank in ("full_system", "categorical", "terminal", "sequential"):
            changed = record["search"][bank]["changed_from_shipped"]
            outcomes.append(f"{bank} {'changed' if changed else 'reselected shipped exact values'}")
        lines.append(f"- **{data['profiles'][profile]['name']}:** " + "; ".join(outcomes) + ".")
    return "\n".join(lines)


def render_readme(data: dict[str, Any]) -> str:
    return f"""# Dark foreground warmth exploration

> **Branch:** `exp/dark-foreground-warmth`<br>
> **Status:** isolated experiment; not a production palette update<br>
> **Live comparison:** [open `index.html`](index.html)

## Bottom line

This third pass compares all three shipped dark profiles under three commanded warmth philosophies: current, halfway, and full — applied to **both ink and surfaces**. Foreground roles keep the Light Mid-Depth mean-warmth pattern from the previous pass (decreasing `1.2 / 1.0 / 0.8` dark-role chroma). Each background role now also interpolates its Oklab `a/b` toward its **3400K Light Mid-Depth** counterpart: halfway covers half that hue step, full reaches it completely. These are aesthetic penalties, not fixed colors.

The optimizer chooses a usable transformed foreground hierarchy first. Foreground Oklab `L` may move inside an explicit bound; surfaces move only in hue (`a/b`) within restrained ±24-byte bounds and must keep their dark lightness ladder exactly. Dependent categorical, terminal, and sequential banks are then rerun against each lane's selected exact system, including a deterministic terminal/foreground lightness feedback loop where needed.

There is **no single scalar winner**. Lower warmth/chroma competes with transformed contrast, hierarchy, semantic clearance, and sequential regularity.

## Why this pass exists

The [first fixed-lightness diagnostic](https://github.com/carpdiem/ember/tree/e99f9db7daa84e678d00d6796e2ffc2eff543f90/docs/experiments/dark-foreground-warmth) found transformed contrast breaches as warmth fell. Those breaches described the imposed fixed-`L` substitution, not the best achievable cooler system. The [second pass](https://github.com/carpdiem/ember/blob/e99f9db7daa84e678d00d6796e2ffc2eff543f90/docs/experiments/dark-foreground-warmth/README.md) freed foreground lightness but left backgrounds fixed. This pass extends the same hue step to surfaces as well, so dependent accent banks are re-optimized against genuinely cooler surroundings rather than warm ones held fixed by assumption.

## What remains controlled

- Surface and foreground bounds, seeds, objectives, selected exact values, movement, and failed gates are serialized for every lane.
- Surface movement is hue-only: dark lightness values are pinned per role while `a/b` interpolates toward the Mid-Depth counterpart under hard spacing/luminance gates.
- Semantic counts, `terminal_ansi_indices`, and `terminal_night_groups` are preserved per family.
- Canonical definitions, public manifests, CSS, package exports, and generated release themes are untouched.

## Fresh dependent searches

For **each profile × lane**, the joint surface/foreground system and every dependent bank receive fresh bounded exact-Hex8 searches with two deterministic seeds. Every lane within a profile uses the same controlled pair. Sequential search includes the selected surface system in its dependency fingerprint; byte-identical dependencies should produce byte-identical maps, while changed dependencies are recomputed rather than explained by seed noise. This is bounded-search evidence, not a global-optimum or infeasibility claim.

- full system: restrained surface bytes plus relaxed foreground bytes and explicit Oklab-L bounds;
- categorical: each shipped byte ±18;
- terminal: profile-specific exact byte bounds (±16 for 3400K, ±36 for 2000K/1200K), broadened for the severe transforms;
- sequential anchors: each shipped byte ±10;
- hard penalties: the complete current surface, foreground, categorical, terminal, sequential, maturity, contrast, and sampled-corner release contracts;
- soft objective: transformed clarity and hierarchy, restrained movement, then commanded warmth/chroma and lane-target closeness.
- terminal/foreground feedback: one deterministic focused `±0.018` Oklab-L refinement grid, followed by fresh dependent searches and authoritative final full-system gates.

### Current-lane result

The current lane was not copied. It went through the same fresh two-seed searches. Exact outcomes:

{current_lane_summary(data)}

## Strict release status vs universal text usability

“Strict” means every current family-specific surface, foreground, categorical, terminal, sequential, maturity, contrast, and sampled-corner gate. “Universal text” separately isolates transformed `fg_0 / fg_1 / fg_2` floors of `4.5 / 3.5 / 2.4`. All nine relaxed candidates clear both lenses; the distinction remains visible so later experiments cannot hide a family-specific miss behind the universal floor.

{failures_markdown(data)}

## Combined metrics

Rows are Pareto-ranked: usability and warmth first, provenance and secondary detail below. Underline marks only the best-performing lane(s) **within each profile for that metric**; values are not underlined merely for passing. Directions compete; there is no aggregate winner. Gain-corner values are extrema observed at four sampled corners, not continuous-box guarantees.

{metrics_markdown(data)}

## Reader-facing proof domains

The [live page](index.html) keeps all three warmth lanes visible together by default for the selected profile and provides controls for:

- profile: 3400K / 2000K / 1200K;
- commanded vs exact signal simulation;
- optional single-candidate focus.

It includes complete anatomy, a substantial editorial hierarchy, realistic code/terminal syntax and all semantic roles, a dense dashboard with categories/statuses/table/forms, sequential gradient and heatmap, real Mars MOLA scalar data, Mona Lisa photographic mapping, and a scientific propagation figure. Mars and Mona are candidate-specific commanded PNGs with separately generated exact-simulated PNGs; raster evidence is not a CSS-only transform.

## Static review captures

The interactive page is authoritative. These committed captures make the same comparison reviewable directly on GitHub.

### Complete anatomy across all dark profiles

| Profile | Commanded | Exact simulated |
|---|---|---|
| 3400K Dark | ![3400K Dark commanded anatomy](review-captures/3400k-dark-anatomy-commanded.png) | ![3400K Dark exact simulated anatomy](review-captures/3400k-dark-anatomy-simulated.png) |
| 2000K Dark | ![2000K Dark commanded anatomy](review-captures/2000k-dark-anatomy-commanded.png) | ![2000K Dark exact simulated anatomy](review-captures/2000k-dark-anatomy-simulated.png) |
| 1200K Dark | ![1200K Dark commanded anatomy](review-captures/1200k-dark-anatomy-commanded.png) | ![1200K Dark exact simulated anatomy](review-captures/1200k-dark-anatomy-simulated.png) |

### Full proof domains in 3400K Dark

| Domain | Commanded | Exact simulated |
|---|---|---|
| Terminal | ![Terminal commanded](review-captures/3400k-dark-terminal-commanded.png) | ![Terminal exact simulated](review-captures/3400k-dark-terminal-simulated.png) |
| Dashboard | ![Dashboard commanded](review-captures/3400k-dark-dashboard-commanded.png) | ![Dashboard exact simulated](review-captures/3400k-dark-dashboard-simulated.png) |
| Science and images | ![Science commanded](review-captures/3400k-dark-science-commanded.png) | ![Science exact simulated](review-captures/3400k-dark-science-simulated.png) |

### Phone-width focused state

![2000K Dark Full Step exact simulated at 390 px](review-captures/phone-2000k-full-simulated.png)

## Exact values

{exact_values_markdown(data)}

## Search provenance and reproducibility

- Exact selected data, unrounded metrics, per-seed objectives, bounds, changed/reselected flags, continuous float maps, Hex8 previews, and sampled gain corners: [`search-results.json`](search-results.json)
- Reproducible bounded search: [`search_full_palette.py`](search_full_palette.py)
- Deterministic renderer: [`../../../tools/render_dark_foreground_warmth_experiment.py`](../../../tools/render_dark_foreground_warmth_experiment.py)
- Independent verification: [`../../../tests/test_dark_foreground_warmth_experiment.py`](../../../tests/test_dark_foreground_warmth_experiment.py)

The simulated state applies each family's documented encoded-sRGB diagonal gain vector. The ±5% samples scale nonzero G/B gains only; exact zero blue remains zero.

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
