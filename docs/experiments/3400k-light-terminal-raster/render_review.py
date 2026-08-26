#!/usr/bin/env python3
"""Render the immutable human-review package for the terminal experiment."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROLE_ORDER = ("red", "green", "yellow", "blue", "magenta", "cyan")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metric(evidence: dict[str, Any], bank: str, state: str, dpr: int, role: str) -> dict[str, Any]:
    return next(
        row
        for row in evidence["role_aggregates"]
        if row["bank"] == bank
        and row["state"] == state
        and row["dpr"] == dpr
        and row["role"] == role
    )


def terminal_pane(bank: dict[str, Any], *, transformed: bool, label: str) -> str:
    rows = []
    for role in ROLE_ORDER:
        rows.append(
            f"<div><span style='color:{bank['terminal'][role]}'>{html.escape(role.upper())}</span>"
            f"<code style='color:{bank['terminal'][role]}'>Ag0 ERROR ok []{{}} &lt;&gt; $ git</code></div>"
        )
    css_class = "terminal transformed" if transformed else "terminal commanded"
    return (
        f"<section class='{css_class}' style='--pane-bg:{bank['surfaces']['bg_0']};"
        f"--pane-fg:{bank['surfaces']['fg_0']}'><h4>{html.escape(label)}</h4>"
        f"<p class='reference' style='color:{bank['surfaces']['fg_0']}'>FG0 · Ag0 ordinary output []{{}} $ git</p>"
        + "".join(rows)
        + "</section>"
    )


def role_table(evidence: dict[str, Any], bank_id: str, bank: dict[str, Any]) -> str:
    rows = []
    for role in ROLE_ORDER:
        day = metric(evidence, bank_id, "commanded-normal-light", 1, role)
        night = metric(evidence, bank_id, "transformed-low-light", 1, role)
        rows.append(
            "<tr>"
            f"<th>{role}</th><td><code>{bank['terminal'][role]}</code></td>"
            f"<td>{day['active_min_p10']:.3f}</td><td>{night['active_min_p10']:.3f}</td>"
            f"<td>{night['edge_min_median']:.3f}</td>"
            f"<td>{night['active_max_near_fraction'] * 100:.1f}%</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Role</th><th>Hex</th><th>Day glyph p10</th>"
        "<th>Low-light glyph p10</th><th>Low-light edge median</th><th>Near tail</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def render(results: dict[str, Any], evidence: dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    acceptance = {row["bank"]: row for row in evidence["acceptance"]}
    cards = []
    order = ["current-light", *(row["id"] for row in results["finalists"]), "reference-dark"]
    names = {
        "current-light": "Current 3400K Light reference",
        "reference-dark": "Current 3400K Dark perceptual reference",
    }
    for candidate in results["finalists"]:
        names[candidate["id"]] = candidate["id"].replace("-", " ")
    for bank_id in order:
        bank = evidence["banks"][bank_id]
        if bank["kind"] == "finalist":
            gate = acceptance[bank_id]
            status = gate["status"]
            status_note = (
                "Eligible for human review"
                if status == "PASS"
                else f"Rejected by browser gate · {len(gate['failures'])} failures"
            )
        elif bank["kind"] == "baseline":
            status = "REFERENCE"
            status_note = "Shipped Light bank"
        else:
            status = "REFERENCE"
            status_note = "Working Dark reference · not a Light candidate"
        cards.append(
            f"<article class='candidate {status.lower()}' id='{html.escape(bank_id)}'>"
            f"<header><div><p class='status'>{status}</p><h2>{html.escape(names[bank_id])}</h2>"
            f"<p>{html.escape(status_note)}</p></div><code>{' '.join(bank['terminal'][role] for role in ROLE_ORDER)}</code></header>"
            "<div class='panes'>"
            + terminal_pane(bank, transformed=False, label="Commanded · normal daytime viewing")
            + terminal_pane(
                bank, transformed=True, label="Exact 3400K transform · low-light viewing"
            )
            + "</div>"
            + role_table(evidence, bank_id, bank)
            + "</article>"
        )
    gain = results["frozen"]["profile_gains"]
    matrix = " ".join(
        [
            f"{gain[0]} 0 0 0 0",
            f"0 {gain[1]} 0 0 0",
            f"0 0 {gain[2]} 0 0",
            "0 0 0 1 0",
        ]
    )
    page = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>3400K Light terminal accent review</title><style>
:root{{--canvas:#F9F9F8;--panel:#ECECEB;--rule:#CAC7C3;--text:#342F2C;--soft:#4D4540;--meta:#665C54;--action:#007672;--bad:#430000}}*{{box-sizing:border-box}}body{{margin:0;background:var(--canvas);color:var(--text);font:15px/1.45 system-ui,sans-serif}}main{{max-width:1480px;margin:auto;padding:34px 24px 72px}}h1,h2{{font-family:Georgia,serif}}h1{{font-size:38px;margin:0 0 8px}}.lede{{max-width:80ch;color:var(--soft)}}.contract{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;margin:24px 0 34px;background:var(--rule);border:1px solid var(--rule)}}.contract div{{background:var(--panel);padding:12px}}.contract span{{display:block;color:var(--meta);font-size:12px}}.candidate{{margin:0 0 28px;border:1px solid var(--rule);background:var(--panel);padding:18px}}.candidate>header{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}}.candidate h2{{margin:0;font-size:25px}}.candidate header p{{margin:3px 0;color:var(--soft)}}.candidate header>code{{max-width:55%;overflow-wrap:anywhere}}.status{{font:700 11px monospace!important;color:var(--meta)!important;letter-spacing:.08em}}.pass{{box-shadow:inset 0 3px var(--action)}}.fail{{box-shadow:inset 0 3px var(--bad)}}.panes{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:16px 0}}.terminal{{padding:14px 16px;background:var(--pane-bg);color:var(--pane-fg);font-family:Menlo,monospace;overflow:hidden}}.terminal.transformed{{filter:url(#warm)}}.terminal h4{{margin:0 0 10px;color:var(--pane-fg);font:600 12px system-ui,sans-serif}}.terminal .reference{{margin:0 0 8px;font-size:13px}}.terminal div{{display:grid;grid-template-columns:76px minmax(0,1fr);gap:8px;font-size:13px;line-height:1.6}}.terminal code{{font:inherit;white-space:nowrap}}table{{width:100%;border-collapse:collapse;background:var(--canvas)}}th,td{{padding:7px 9px;border-bottom:1px solid var(--rule);text-align:right;font-variant-numeric:tabular-nums}}th:first-child,td:first-child{{text-align:left}}thead th{{color:var(--soft);font-size:12px}}.gate{{margin-top:30px;padding:16px;border:1px solid var(--rule)}}@media(max-width:800px){{main{{padding:22px 12px 48px}}h1{{font-size:31px}}.contract{{grid-template-columns:1fr 1fr}}.candidate>header{{display:block}}.candidate header>code{{display:block;max-width:none;margin-top:10px}}.panes{{grid-template-columns:1fr}}.terminal div{{grid-template-columns:64px minmax(0,1fr);font-size:11px}}.candidate{{padding:12px}}table{{font-size:11px}}th,td{{padding:5px 4px}}}}
</style></head><body><svg width='0' height='0' aria-hidden='true'><filter id='warm' color-interpolation-filters='sRGB'><feColorMatrix type='matrix' values='{matrix}'/></filter></svg><main><h1>3400K Light terminal accent rebuild</h1><p class='lede'>Commanded colors are optimized under normal daytime CAM16 viewing (`L_A=64`, `Y_b=20`). Transformed colors are optimized under low-light CAM16 viewing (`L_A=8`, `Y_b=3`). Production remains unchanged until Michael selects.</p><section class='contract'><div><span>Frozen source</span><strong>{results["source"]["commit"][:10]}</strong></div><div><span>Contrast gate</span><strong>≥4.5 on terminal bg0</strong></div><div><span>Browser target</span><strong>red/green/blue p10 ↑</strong></div><div><span>Human selection</span><strong>None yet</strong></div></section>{"".join(cards)}<section class='gate'><h2>Gate</h2><p>Only <strong>A raster maximum</strong> currently passes the nominal commanded/low-light browser gate. Gain-corner browser rows are report-only diagnostics; analytical gain-corner contrast and pair gates are hard. B and C remain visible as rejected search evidence, not selectable finalists.</p></section></main></body></html>"""
    (output / "index.html").write_text(page)
    selection = {
        "schema_version": 1,
        "source_commit": results["source"]["commit"],
        "results_sha256": sha256(HERE / "results.json"),
        "browser_evidence_sha256": sha256(HERE / "browser-evidence.json"),
        "eligible_candidates": [
            row["bank"] for row in evidence["acceptance"] if row["status"] == "PASS"
        ],
        "selection": None,
        "automatic_recommendation": None,
        "production_promotion": False,
    }
    (output / "selection.json").write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n")
    report = f"""# 3400K Light terminal accent rebuild

## Verdict

Only **A-raster-maximum** passes the declared nominal browser gate. It remains an experimental human-review candidate, not a production selection.

## Viewing model

- Commanded/day: CAM16 `L_A=64`, `Y_b=20`, 0.75% flare.
- Transformed/low-light: CAM16 `L_A=8`, `Y_b=3`, 0.75% flare.
- Exact 3400K encoded-sRGB gains: `{results["frozen"]["profile_gains"]}`.

## Eligible candidate

`{" ".join(evidence["banks"]["A-raster-maximum"]["terminal"][role] for role in ROLE_ORDER)}`

The candidate removes the nominal accent→`fg_0` near-collision tail for every role and materially improves red, green, and blue active-pixel p10 at DPR1/2. Yellow is allowed at no worse than 85% of baseline p10; it retains zero nominal near-tail samples. Accent-pair browser p10 is nonregressive versus the current Light bank.

## Status

- Human selection: **none**
- Production promotion: **false**
- B/C: retained as rejected diagnostics
- Gain-corner browser rows: report-only sampled diagnostics
- Analytical contrast/pair gain-corner gates: hard
"""
    (output / "report.md").write_text(report)
    print(output / "index.html")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=HERE / "results.json")
    parser.add_argument("--evidence", type=Path, default=HERE / "browser-evidence.json")
    parser.add_argument("--output", type=Path, default=HERE / "review")
    args = parser.parse_args()
    render(json.loads(args.results.read_text()), json.loads(args.evidence.read_text()), args.output)


if __name__ == "__main__":
    main()
