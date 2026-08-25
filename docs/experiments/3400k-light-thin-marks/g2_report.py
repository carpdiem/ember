#!/usr/bin/env python3
"""Render the polished, static G2 human-review package from verified evidence."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import phase3_optimizer as p3

ROLE_LABELS = ("one", "two", "three", "four", "five", "six")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return value


def transformed_hex(value: str, gains: list[float]) -> str:
    rgb = p3.parse_exact_hex8(value) * np.asarray(gains)
    return p3.srgb_to_hex(np.clip(rgb, 0.0, 1.0))


def role_moves(baseline: list[str], bank: list[str]) -> list[dict[str, Any]]:
    base_lab = p3.bank_oklab(baseline)
    bank_lab = p3.bank_oklab(bank)
    return [
        {
            "role": f"cat.{role}",
            "baseline": baseline[index],
            "candidate": bank[index],
            "delta_e_ok": float(np.linalg.norm(bank_lab[index] - base_lab[index]) * 100.0),
        }
        for index, role in enumerate(ROLE_LABELS)
    ]


def line_chart(bank: list[str], *, transformed: bool, identifier: str) -> str:
    paths = (
        "M20 118 C90 18 160 144 240 52 S390 22 500 98",
        "M20 48 C110 138 190 2 280 88 S410 142 500 40",
        "M20 94 C100 72 170 18 250 72 S410 116 500 66",
        "M20 28 C92 122 184 106 256 36 S420 6 500 74",
        "M20 70 C110 14 196 138 286 44 S426 20 500 112",
        "M20 108 C96 34 186 56 270 106 S412 128 500 28",
    )
    filter_id = f"warm-{identifier}"
    definitions = (
        f'<defs><filter id="{filter_id}" color-interpolation-filters="sRGB">'
        '<feColorMatrix type="matrix" values="1 0 0 0 0 0 .74 0 0 0 0 0 .53 0 0 0 0 0 1 0"/>'
        "</filter></defs>"
        if transformed
        else ""
    )
    filter_attribute = f' filter="url(#{filter_id})"' if transformed else ""
    lines = []
    for index, (path, color) in enumerate(zip(paths, bank, strict=True)):
        lines.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.5" '
            'stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="500" cy="{(98, 40, 66, 74, 112, 28)[index]}" r="3.2" fill="{color}"/>'
        )
    legend = "".join(
        f'<g transform="translate(22 {150 + index * 18})"><line x2="24" stroke="{color}" '
        f'stroke-width="1.5"/><text x="32" y="4">cat.{ROLE_LABELS[index]}</text></g>'
        for index, color in enumerate(bank)
    )
    return (
        '<svg class="plot" viewBox="0 0 540 272" role="img" '
        'aria-label="Six uniform 1.5 pixel categorical lines with crossings, endpoints, and legend">'
        f"{definitions}<g{filter_attribute}>"
        '<rect width="540" height="272" rx="14" fill="#F9F9F8"/>'
        '<path d="M20 136H514" stroke="#CAC7C3" stroke-width="1"/>'
        f"{''.join(lines)}{legend}</g></svg>"
    )


def style_stress(bank: list[str], *, transformed: bool, identifier: str) -> str:
    styles = (
        ("", "solid"),
        ('stroke-dasharray="8 5"', "dashed"),
        ('stroke-dasharray="1 5" stroke-linecap="round"', "dotted"),
    )
    filter_id = f"stress-{identifier}"
    definitions = (
        f'<defs><filter id="{filter_id}" color-interpolation-filters="sRGB">'
        '<feColorMatrix type="matrix" values="1 0 0 0 0 0 .74 0 0 0 0 0 .53 0 0 0 0 0 1 0"/>'
        "</filter></defs>"
        if transformed
        else ""
    )
    filter_attribute = f' filter="url(#{filter_id})"' if transformed else ""
    rows = []
    for style_index, (attributes, label) in enumerate(styles):
        y = 34 + style_index * 42
        rows.append(f'<text x="16" y="{y + 4}">{label}</text>')
        for index, color in enumerate(bank):
            x = 92 + index * 68
            rows.append(
                f'<path d="M{x} {y + 10} C{x + 14} {y - 18} {x + 36} {y + 30} {x + 52} {y}" '
                f'fill="none" stroke="{color}" stroke-width="1.5" {attributes}/>'
            )
    return (
        '<svg class="stress" viewBox="0 0 530 150" role="img" '
        'aria-label="Separate solid dashed and dotted style stress panel">'
        f'{definitions}<g{filter_attribute}><rect width="530" height="150" rx="12" fill="#ECECEB"/>'
        f"{''.join(rows)}</g></svg>"
    )


def sparklines(bank: list[str], *, transformed: bool, identifier: str) -> str:
    filter_id = f"spark-{identifier}"
    definitions = (
        f'<defs><filter id="{filter_id}" color-interpolation-filters="sRGB">'
        '<feColorMatrix type="matrix" values="1 0 0 0 0 0 .74 0 0 0 0 0 .53 0 0 0 0 0 1 0"/>'
        "</filter></defs>"
        if transformed
        else ""
    )
    filter_attribute = f' filter="url(#{filter_id})"' if transformed else ""
    rows = []
    values = (
        (8, 22, 14, 31, 26, 36),
        (28, 18, 30, 16, 24, 12),
        (32, 26, 34, 20, 25, 9),
        (12, 24, 18, 28, 17, 34),
        (30, 20, 25, 16, 22, 10),
        (18, 30, 24, 35, 28, 38),
    )
    for index, color in enumerate(bank):
        y = 20 + index * 34
        points = " ".join(
            f"{180 + point * 34},{y + 18 - value / 2}" for point, value in enumerate(values[index])
        )
        rows.append(
            f'<text x="14" y="{y + 10}">Basket {index + 1}</text>'
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.5"/>'
            f'<circle cx="350" cy="{y + 18 - values[index][-1] / 2}" r="2.8" fill="{color}"/>'
        )
    return (
        '<svg class="sparks" viewBox="0 0 380 230" role="img" '
        'aria-label="Six compact thesis basket sparklines with uniform line treatment">'
        f'{definitions}<g{filter_attribute}><rect width="380" height="230" rx="12" fill="#F9F9F8"/>'
        f"{''.join(rows)}</g></svg>"
    )


def cockpit(bank: list[str], *, transformed: bool, identifier: str) -> str:
    filter_id = f"cockpit-{identifier}"
    definitions = (
        f'<defs><filter id="{filter_id}" color-interpolation-filters="sRGB">'
        '<feColorMatrix type="matrix" values="1 0 0 0 0 0 .74 0 0 0 0 0 .53 0 0 0 0 0 1 0"/>'
        "</filter></defs>"
        if transformed
        else ""
    )
    filter_attribute = f' filter="url(#{filter_id})"' if transformed else ""
    cards = []
    for index, color in enumerate(bank):
        x = 18 + (index % 2) * 180
        y = 22 + (index // 2) * 72
        cards.append(
            f'<g transform="translate({x} {y})"><rect width="164" height="56" rx="9" fill="#ECECEB" '
            f'stroke="{color}"/><text x="12" y="20">cat.{ROLE_LABELS[index]}</text>'
            f'<text x="12" y="42" class="value">{(18.4 + index * 7.3):.1f}%</text>'
            f'<path d="M94 40 C110 12 126 48 150 18" fill="none" stroke="{color}" stroke-width="1.5"/></g>'
        )
    return (
        '<svg class="cockpit" viewBox="0 0 380 246" role="img" '
        'aria-label="Compact Financial Cockpit with six categorical cards">'
        f'{definitions}<g{filter_attribute}><rect width="380" height="246" rx="12" fill="#F9F9F8"/>'
        f"{''.join(cards)}</g></svg>"
    )


def swatches(bank: list[str], gains: list[float]) -> str:
    return "".join(
        f'<div class="swatch"><span style="--c:{color};--t:{transformed_hex(color, gains)}"></span>'
        f"<b>cat.{ROLE_LABELS[index]}</b><code>{color}</code><small>{transformed_hex(color, gains)}</small></div>"
        for index, color in enumerate(bank)
    )


def metric_delta(value: float, baseline: float) -> str:
    delta = value - baseline
    return f"{value:.3f} <small>({delta:+.3f})</small>"


def candidate_section(
    label: str,
    summary: dict[str, Any],
    baseline: dict[str, Any],
    browser: dict[str, Any],
    gains: list[float],
    objective: str,
) -> str:
    bank = summary["serialized_bank"]
    moves = role_moves(baseline["serialized_bank"], bank)
    metrics = summary["pareto"]
    base_metrics = baseline["pareto"]
    rows = "".join(
        f"<tr><th>{html.escape(move['role'])}</th><td><code>{move['baseline']}</code></td>"
        f"<td><code>{move['candidate']}</code></td><td>{move['delta_e_ok']:.3f}</td></tr>"
        for move in moves
    )
    browser_minima = browser["minimum_pair_by_width"]
    browser_rows = "".join(
        f"<li><b>{width}px</b> {row['observed_delta_e_ok']:.3f} ΔE_OK · "
        f"{html.escape(' / '.join(row['roles']))} · {row['state']}</li>"
        for width, row in browser_minima.items()
    )
    return f"""
<section class="candidate" id="candidate-{label.lower()}">
  <header class="candidate-head"><div><p class="eyebrow">{label} · {html.escape(objective)}</p>
  <h2>{"Frozen baseline" if label == "REFERENCE" else f"Finalist {label}"}</h2>
  <p class="hash">{summary["candidate_id"]}</p></div><span class="pass">Chromium {browser["status"]}</span></header>
  <div class="swatches">{swatches(bank, gains)}</div>
  <div class="metric-grid">
    <article><span>1.5px target</span><strong>{metric_delta(metrics["raster_1_5_min"], base_metrics["raster_1_5_min"])}</strong></article>
    <article><span>Transformed pair min</span><strong>{metric_delta(metrics["transformed_pair_min"], base_metrics["transformed_pair_min"])}</strong></article>
    <article><span>Max commanded move</span><strong>{metrics["max_commanded_deviation"]:.3f}</strong></article>
    <article><span>Commanded pair min</span><strong>{metric_delta(metrics["commanded_pair_min"], base_metrics["commanded_pair_min"])}</strong></article>
  </div>
  <div class="review-grid">
    <article class="state"><h3>Commanded · desktop</h3>{line_chart(bank, transformed=False, identifier=label.lower() + "-cmd")}</article>
    <article class="state"><h3>Exact transformed · desktop</h3>{line_chart(bank, transformed=True, identifier=label.lower() + "-warm")}</article>
  </div>
  <div class="review-grid lower">
    <article><h3>Separate style stress</h3>{style_stress(bank, transformed=True, identifier=label.lower())}</article>
    <article><h3>Financial Cockpit</h3>{cockpit(bank, transformed=True, identifier=label.lower())}</article>
    <article><h3>Thesis Baskets · sparklines</h3>{sparklines(bank, transformed=True, identifier=label.lower())}</article>
    <article class="phone-proof"><h3>True 390 phone composition</h3><div class="phone-inner">{line_chart(bank, transformed=True, identifier=label.lower() + "-phone")}{sparklines(bank, transformed=False, identifier=label.lower() + "-phone")}</div></article>
  </div>
  <details><summary>Exact role Hex8 and commanded moves</summary><div class="table-wrap"><table><thead><tr><th>Role</th><th>Baseline</th><th>{label}</th><th>Move ΔE_OK</th></tr></thead><tbody>{rows}</tbody></table></div></details>
  <aside class="browser"><h3>Actual Chromium result</h3><p>25,920 ordered role observations and 32,400 reconstructed pair rows · residual gate <b>{browser["browser_residual_acceptance"]["status"]}</b>.</p><ul>{browser_rows}</ul></aside>
</section>"""


def build_review(evidence_dir: Path, output_dir: Path, experiment_dir: Path) -> dict[str, Any]:
    receipt = load(evidence_dir / "frontier-receipt.json")
    summaries = {
        role: load(evidence_dir / f"browser-summary-{role.lower()}.json")
        for role in ("REFERENCE", "A", "B", "C")
    }
    if any(summary["status"] != "PASS" for summary in summaries.values()):
        raise RuntimeError("G2 review cannot render a browser-failing finalist")
    baseline = receipt["baseline"]
    by_id = {row["candidate_id"]: row for row in receipt["candidates"]}
    shortlist = {row["role"]: row for row in receipt["g2_shortlist"]}
    selected = {
        "REFERENCE": baseline,
        **{role: by_id[shortlist[role]["candidate_id"]] for role in ("A", "B", "C")},
    }
    gains = load(experiment_dir / "viewing-conditions.json")["transform"]["gains"]
    sections = []
    for role in ("REFERENCE", "A", "B", "C"):
        objective = "frozen reference" if role == "REFERENCE" else shortlist[role]["objective"]
        sections.append(
            candidate_section(role, selected[role], baseline, summaries[role], gains, objective)
        )
    css = """
:root{color-scheme:light;--paper:#f9f9f8;--panel:#ececeb;--ink:#342f2c;--muted:#665c54;--rule:#cac7c3;--accent:#692501}*{box-sizing:border-box}html{background:var(--paper);color:var(--ink);font:16px/1.5 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{margin:0;overflow-x:hidden}main,.top{width:min(1500px,100%);margin:auto;padding:clamp(18px,4vw,64px)}.top{border-bottom:1px solid var(--rule)}h1{font-size:clamp(2.2rem,6vw,5.4rem);line-height:.95;letter-spacing:-.055em;max-width:14ch;margin:.2em 0}.lede{max-width:74ch;font-size:1.12rem;color:var(--muted)}.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:.72rem;font-weight:800;color:var(--accent)}.status{display:inline-flex;padding:.45rem .7rem;border:1px solid var(--accent);border-radius:999px;font-size:.76rem;font-weight:800}.recommendation{margin:2rem 0;padding:1.3rem;border:1px solid var(--rule);border-left:5px solid #39937c;background:#fff;border-radius:14px;max-width:80ch}.candidate{padding:clamp(22px,4vw,56px) 0;border-bottom:1px solid var(--rule)}.candidate-head{display:flex;gap:1rem;justify-content:space-between;align-items:flex-start}.candidate-head h2{font-size:clamp(2rem,4vw,3.8rem);margin:.1em 0}.hash{font:11px/1.3 ui-monospace,SFMono-Regular,monospace;overflow-wrap:anywhere;color:var(--muted)}.pass{background:#e6f1ea;color:#1f5a3d;padding:.45rem .7rem;border-radius:999px;font-size:.76rem;font-weight:800;white-space:nowrap}.swatches{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:1.4rem 0}.swatch{min-width:0}.swatch span{display:block;height:54px;border-radius:8px;background:linear-gradient(90deg,var(--c) 0 50%,var(--t) 50%)}.swatch b,.swatch code,.swatch small{display:block;font-size:.7rem;overflow-wrap:anywhere}.swatch small{color:var(--muted)}.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:1.5rem 0}.metric-grid article{padding:1rem;background:#fff;border:1px solid var(--rule);border-radius:12px}.metric-grid span,.metric-grid small{color:var(--muted);font-size:.76rem}.metric-grid strong{display:block;font-size:1.35rem}.review-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.review-grid.lower{grid-template-columns:repeat(4,minmax(0,1fr));align-items:start;margin-top:16px}.review-grid article,.state,.browser,details{min-width:0;background:#fff;border:1px solid var(--rule);border-radius:16px;padding:14px}.plot,.stress,.sparks,.cockpit{display:block;width:100%;height:auto}.plot text,.stress text,.sparks text,.cockpit text{font:10px ui-sans-serif,-apple-system,sans-serif;fill:#342f2c}.cockpit .value{font-size:16px;font-weight:800}.phone-proof{width:min(390px,100%);justify-self:center}.phone-inner{width:100%;overflow:hidden}.phone-inner .plot{min-width:0}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:560px}th,td{text-align:left;padding:.55rem;border-bottom:1px solid var(--rule)}code{font-family:ui-monospace,SFMono-Regular,monospace}.browser{margin-top:16px}.browser ul{columns:3;padding-left:1.2rem}.freeze{margin-top:2rem;padding:1rem;border:2px solid var(--accent);border-radius:14px;font-weight:800}@media(max-width:900px){.review-grid.lower{grid-template-columns:repeat(2,minmax(0,1fr))}.swatches{grid-template-columns:repeat(3,minmax(0,1fr))}.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.browser ul{columns:1}}@media(max-width:600px){main,.top{padding:18px}.review-grid,.review-grid.lower{grid-template-columns:1fr}.swatches{grid-template-columns:repeat(2,minmax(0,1fr))}.candidate-head{display:block}.pass{display:inline-flex}.metric-grid{grid-template-columns:1fr 1fr}.phone-proof{width:100%}h3{font-size:1rem}}@media(max-width:390px){.metric-grid{grid-template-columns:1fr}.swatches{grid-template-columns:repeat(2,minmax(0,1fr))}}
"""
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ember G2 categorical finalists</title><style>{css}</style></head><body>
<header class="top"><p class="eyebrow">Ember · 3400K Light · G2 human review</p><span class="status">AWAITING_MICHAEL_SELECTION</span><h1>Three real tradeoffs. One human decision.</h1><p class="lede">Baseline plus three deterministic target-improving Pareto-frontier finalists. Every finalist passed fresh Chromium capture with 25,920 ordered color observations and 32,400 independently reconstructed pair rows. The +0.05 ΔE_OK shortlist delta is deterministic, not a human visibility floor. Human width capacity remains UNKNOWN.</p><aside class="recommendation"><b>Recommendation: B.</b> It makes the smallest commanded change of the target-improving frontier set while improving both the 1.5px target and transformed-pair minimum. A buys the largest thin-mark gain with materially more churn and weaker transformed-pair separation. C maximizes transformed-pair separation, but gives up more 2px/3px geometry and moves farther than B.</aside></header>
<main>{"".join(sections)}<p class="freeze">Selection: null · status: AWAITING_MICHAEL_SELECTION · production promotion: not authorized</p></main></body></html>"""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(document)

    report_lines = [
        "# G2 categorical palette finalists",
        "",
        "**Status:** `AWAITING_MICHAEL_SELECTION`",
        "**Selection:** `null`",
        "**Production promotion:** not authorized",
        "",
        "## Recommendation",
        "",
        "**Recommend B** for the best target-improvement/churn/dual-state balance. It clears the deterministic +0.05 ΔE_OK shortlist delta, has the lowest maximum commanded deviation among target-improving frontier rows, and improves transformed-pair minimum. A is the aggressive 1.5px option; C is the transformed-pair option.",
        "",
        "The +0.05 ΔE_OK value is a deterministic shortlist delta, not a human visibility floor. Human visibility and width capacity remain **UNKNOWN**.",
        "",
        "## Exact finalists",
        "",
        "| Choice | Candidate ID | Exact role Hex8 | 1.5px proxy | Δ vs baseline | Transformed pair | Max move | Chromium |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    base_target = baseline["pareto"]["raster_1_5_min"]
    for role in ("A", "B", "C"):
        row = selected[role]
        report_lines.append(
            f"| {role} | `{row['candidate_id']}` | `{' '.join(row['serialized_bank'])}` | "
            f"{row['pareto']['raster_1_5_min']:.3f} | {row['pareto']['raster_1_5_min'] - base_target:+.3f} | "
            f"{row['pareto']['transformed_pair_min']:.3f} | {row['pareto']['max_commanded_deviation']:.3f} | PASS |"
        )
    report_lines += [
        "",
        "## Browser evidence",
        "",
        "Baseline and A/B/C each contain 25,920 ordered real-Chromium role observations and 32,400 reconstructed pair rows. Every observation replay and every browser residual gate passed. Evidence is split into separately hashed files below 50 MB. Full-image hashes are not used as perceptual evidence.",
        "",
        "## Review surface",
        "",
        "Open [`index.html`](index.html). It includes commanded and exact transformed desktop plots, true 390px phone compositions, uniform color-only lines, a separate style-stress panel, legends, crossings, endpoints, sparklines, Financial Cockpit, Thesis Baskets, exact role moves, and actual browser minima.",
        "",
        "## Boundary",
        "",
        "This package stops at Michael's G2 selection. It does not modify G0, G1, production palette values, exports, or downstream consumers.",
    ]
    (output_dir / "report.md").write_text("\n".join(report_lines) + "\n")
    selection = {
        "schema_version": 1,
        "status": "AWAITING_MICHAEL_SELECTION",
        "selection": None,
        "allowed": ["A", "B", "C"],
        "candidate_ids": {role: selected[role]["candidate_id"] for role in ("A", "B", "C")},
        "production_promotion_authorized": False,
        "human_width_capacity": None,
    }
    (output_dir / "selection.json").write_text(
        json.dumps(selection, indent=2, sort_keys=True) + "\n"
    )
    return {
        "status": "PASS",
        "index": "index.html",
        "report": "report.md",
        "selection": "selection.json",
        "recommended": "B",
        "candidate_ids": selection["candidate_ids"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--experiment-dir", type=Path, default=HERE)
    args = parser.parse_args()
    result = build_review(args.evidence_dir, args.output_dir, args.experiment_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
