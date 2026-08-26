#!/usr/bin/env python3
"""Generate the fixed-four de novo hue-frontier review package."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
ROOT = EXPERIMENT.parents[2]
DEFAULT_OUTPUT = EXPERIMENT / "review/g2-seven-point-hue-frontier"
ROLE_ORDER = ("reference", "benchmark-c", "a", "b", "c")
LABELS = {
    "reference": "Candidate A baseline",
    "benchmark-c": "Amber / orange",
    "a": "Golden yellow",
    "b": "Yellow",
    "c": "Yellow-green edge",
}
EXPECTED_EVIDENCE_COUNT = 22


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base_report = _load("base_report_for_hue_review", "report.py")
seven = _load("seven_for_hue_review", "optimizer.py")
frontier = _load("frontier_for_hue_review", "hue_frontier.py")
browser = _load("browser_for_hue_review", "browser_evidence.py")
p3 = seven.p3


class HueReportError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HueReportError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    require(isinstance(value, dict), f"{path.name} must be an object")
    return value


def collect(search_dir: Path, request_dir: Path, browser_dir: Path) -> dict[str, Any]:
    inputs = seven.load_inputs(replay=False)
    contract = seven.load_contract()
    search = load_json(Path(search_dir) / "results.json")
    require(search["artifact_kind"] == "seven-point-hue-frontier", "hue search differs")
    rows = {}
    for role in ROLE_ORDER:
        print(f"[hue-report] verify-start role={role}", file=sys.stderr, flush=True)
        request_path = Path(request_dir) / f"browser-request-{role}.json"
        result_path = Path(browser_dir) / f"browser-result-{role}.json"
        observations_path = Path(browser_dir) / f"browser-observations-{role}.json"
        pairs_path = Path(browser_dir) / f"browser-pairs-{role}.json"
        verified = browser.verify(
            request_path,
            result_path,
            observations_path,
            pairs_path,
            search_dir,
            inputs,
            contract,
            validate_search=False,
        )
        require(verified["status"] == "PASS", f"browser evidence fails for {role}")
        require(verified["observation_count"] == 30_240, f"observations differ for {role}")
        require(verified["pair_count"] == 90_720, f"pairs differ for {role}")
        request = load_json(request_path)
        result = load_json(result_path)
        pairs = load_json(pairs_path)
        search_row = search["browser_roles"][role]
        bank = [request["fixed_fg0"], *request["serialized_bank"]]
        rows[role] = {
            "role": role,
            "label": LABELS[role],
            "candidate_id": request["candidate_id"],
            "bank": bank,
            "transformed_bank": [
                base_report.transformed_hex(value, inputs.viewing["transform"]["gains"])
                for value in bank
            ],
            "free_1": search_row["free_1"],
            "free_2": search_row["free_2"],
            "free_1_oklch": search_row.get("free_1_oklch"),
            "free_2_oklch": search_row.get("free_2_oklch"),
            "free_1_transformed_oklch": search_row.get("free_1_transformed_oklch"),
            "free_2_transformed_oklch": search_row.get("free_2_transformed_oklch"),
            "contrast": search_row["contrast"],
            "metrics": {
                state: {
                    width: base_report.gated_metric(result, width, state)
                    for width in ("1.5", "2", "3")
                }
                for state in ("commanded", "transformed")
            },
            "bindings": {
                state: {
                    width: base_report.pair_binding(request, pairs, float(width), state)
                    for width in ("1.5", "2", "3")
                }
                for state in ("commanded", "transformed")
            },
        }
        print(f"[hue-report] verify-complete role={role}", file=sys.stderr, flush=True)
    return {"search": search, "rows": rows}


def oklch_text(values: Sequence[float] | None) -> str:
    if values is None:
        return "baseline metadata"
    return f"L {values[0]:.3f} · C {values[1]:.3f} · h {values[2]:.1f}°"


def contrast_table(row: Mapping[str, Any]) -> str:
    body = []
    for role, label in (("free_1", "Free color 1"), ("free_2", "Hue-family color")):
        values = row["contrast"][role]
        body.append(
            f"<tr><th>{label}</th>"
            f"<td>{values['commanded']['bg_0']:.3f}</td><td>{values['commanded']['bg_1']:.3f}</td>"
            f"<td>{values['transformed']['bg_0']:.3f}</td><td>{values['transformed']['bg_1']:.3f}</td></tr>"
        )
    return (
        '<table class="contrast"><thead><tr><th>Role</th><th>Cmd bg0</th><th>Cmd bg1</th>'
        "<th>3400K bg0</th><th>3400K bg1</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def card(row: Mapping[str, Any]) -> str:
    binding = row["bindings"]["transformed"]["1.5"]
    return f"""
<article class="frontier" id="frontier-{row["role"]}"><header><p class="eyebrow">De novo hue-family frontier</p><h2>{html.escape(row["label"])}</h2></header>
<div class="identity"><div><strong>Free color 1</strong><code>{row["free_1"]}</code><span>{oklch_text(row["free_1_oklch"])}</span><span>3400K {oklch_text(row["free_1_transformed_oklch"])}</span></div><div><strong>Hue-family color</strong><code>{row["free_2"]}</code><span>{oklch_text(row["free_2_oklch"])}</span><span>3400K {oklch_text(row["free_2_transformed_oklch"])}</span></div></div>
<section><h3>Commanded</h3><div class="swatches">{base_report.swatches(row["bank"])}</div>{base_report.line_specimen(row["bank"], 1.5, "commanded")}{base_report.finance_specimen(row["bank"])}</section>
<section class="transformed"><h3>Exact 3400K transform</h3><div class="swatches">{base_report.swatches(row["transformed_bank"])}</div>{base_report.line_specimen(row["transformed_bank"], 1.5, "transformed")}{base_report.line_specimen(row["transformed_bank"], 2.0, "transformed")}</section>
<div class="metric"><strong>Actual transformed minima</strong><span>1.5px {row["metrics"]["transformed"]["1.5"]:.3f}</span><span>2px {row["metrics"]["transformed"]["2"]:.3f}</span><span>3px {row["metrics"]["transformed"]["3"]:.3f}</span><span>Binding {html.escape(" ↔ ".join(binding["roles"]))}</span></div>{contrast_table(row)}</article>"""


def build_html(data: Mapping[str, Any]) -> str:
    rows = data["rows"]
    support = data["search"]["feasible_hue_support"]
    intervals = ", ".join(f"{low:.1f}–{high:.1f}°" for low, high in support["intervals_degrees"])
    summary = "".join(
        f"<tr><th>{html.escape(rows[role]['label'])}</th><td>{rows[role]['free_1']}</td><td>{rows[role]['free_2']}</td>"
        f"<td>{oklch_text(rows[role]['free_2_oklch'])}</td><td>{rows[role]['metrics']['transformed']['1.5']:.3f}</td></tr>"
        for role in ROLE_ORDER
    )
    baseline = card(rows["reference"])
    variants = "".join(card(rows[role]) for role in ("benchmark-c", "a", "b", "c"))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Candidate A de novo hue frontier</title><style>
:root{{--bg:#f9f9f8;--ink:#342f2c;--muted:#665c54;--rule:#cac7c3;--panel:#ececeb}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 ui-sans-serif,system-ui,sans-serif}}main{{max-width:1600px;margin:auto;padding:28px}}h1{{font:700 clamp(32px,5vw,64px)/1 ui-serif,Georgia,serif;max-width:1080px;margin:8px 0 16px}}h2,h3,p{{margin-top:0}}.lede{{max-width:940px;font-size:18px;color:var(--muted)}}.eyebrow{{font-size:11px;text-transform:uppercase;letter-spacing:.13em;font-weight:750;color:var(--muted);margin-bottom:6px}}.status{{display:flex;gap:10px;flex-wrap:wrap;margin:24px 0}}.status span{{border:1px solid var(--rule);background:var(--panel);padding:6px 9px;font-size:12px;font-weight:750}}.support{{padding:14px;border-left:4px solid #8b6b12;background:#fff9df}}.summary{{overflow-x:auto;border-block:1px solid var(--rule);margin:26px 0}}table{{width:100%;border-collapse:collapse;white-space:nowrap}}th,td{{padding:9px;border-bottom:1px solid var(--rule);text-align:left}}.baseline{{max-width:790px;margin:24px auto}}.variants{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}.frontier{{background:#fff;border:1px solid var(--rule);padding:18px;min-width:0}}.identity{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.identity>div{{background:var(--panel);padding:10px}}.identity strong,.identity code,.identity span{{display:block}}.identity span{{font-size:11px;color:var(--muted)}}.frontier section{{border-top:1px solid var(--rule);padding-top:12px;margin-top:14px}}.transformed{{background:#d8b08a22;padding:14px;margin-inline:-4px}}.swatches{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px}}.swatch{{min-width:0}}.swatch-color{{display:block;height:44px;background:var(--swatch);border:1px solid #342f2c33}}.swatch-name,.swatch code{{display:block;font-size:9px;overflow:hidden}}.line-specimen,.finance{{width:100%;height:auto;background:#f9f9f8;border:1px solid var(--rule);margin:8px 0}}.transformed .line-specimen{{background:#d0aa84}}.metric{{display:flex;gap:12px;flex-wrap:wrap;padding:12px 0;font-size:12px}}.contrast{{font-size:11px}}footer{{margin-top:30px;padding-top:18px;border-top:1px solid var(--rule);color:var(--muted)}}
@media(max-width:1100px){{.variants{{grid-template-columns:1fr}}}}
@media(max-width:680px){{main{{padding:18px 12px}}.summary{{overflow:visible}}.summary table{{table-layout:fixed;white-space:normal;font-size:11px}}.summary th:nth-child(2),.summary td:nth-child(2),.summary th:nth-child(4),.summary td:nth-child(4){{display:none}}.frontier{{padding:13px;max-width:100%}}.identity{{grid-template-columns:1fr}}.swatch-name{{display:none}}.swatch code{{font-size:8px;writing-mode:vertical-rl;height:56px}}.contrast{{font-size:9px;white-space:normal;table-layout:fixed}}th,td{{padding:7px}}}}
</style></head><body><main><p class="eyebrow">Ember 3400K Light · de novo fixed-four diagnostic</p><h1>Hue first. No olive anchor.</h1><p class="lede">Both warm slots were re-searched from the full exact-Hex hard-gate-feasible space. Ranking contains no baseline hue, chroma, churn, target-distance, or “gold” preference. Fixed <code>fg_0</code> and the green, teal, blue-violet, and pink colors remain byte-identical.</p><div class="status"><span>AWAITING MICHAEL HUE-FRONTIER SELECTION</span><span>Production: UNCHANGED</span><span>Automatic recommendation: NONE</span></div><p class="support"><strong>Actual feasible hue support:</strong> {support["exact_color_count"]} exact colors across {html.escape(intervals)}. The 60.2–82.1° gap is a measured consequence of the fixed-four geometry, not a hidden search corridor.</p><section><h2>Appearance-led frontier</h2><div class="summary"><table><thead><tr><th>Hue family</th><th>Free 1</th><th>Family color</th><th>Commanded Oklch</th><th>1.5px ΔEOK</th></tr></thead><tbody>{summary}</tbody></table></div></section><section><h2>Baseline A</h2><div class="baseline">{baseline}</div></section><section><h2>Fixed-four hue frontier</h2><div class="variants">{variants}</div></section><footer><p>This is the controlled fixed-four diagnostic. Human appearance judgment—not optimizer score—selects the next direction. Every bank preserves the complete 3.0 graphics contract and has 30,240 Chromium observations plus 90,720 symmetric pair rows.</p></footer></main></body></html>"""


def selection_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    rows = data["rows"]
    return {
        "schema_version": 1,
        "artifact_kind": "seven-point-hue-frontier-human-selection",
        "status": "AWAITING_MICHAEL_HUE_FRONTIER_SELECTION",
        "selection": None,
        "allowed_selections": [
            "KEEP-A",
            "AMBER-ORANGE",
            "GOLDEN-YELLOW",
            "YELLOW",
            "YELLOW-GREEN-EDGE",
        ],
        "candidate_ids": {rows[role]["label"]: rows[role]["candidate_id"] for role in ROLE_ORDER},
        "automatic_recommendation": None,
        "production_promotion": False,
        "fixed_fg0": "#342F2C",
        "report_source": browser._source_binding("hue_frontier_report.py"),
    }


def copy_evidence(search_dir: Path, request_dir: Path, browser_dir: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    sources = [Path(search_dir) / name for name in ("catalog-summary.json", "results.json")]
    sources += [Path(request_dir) / f"browser-request-{role}.json" for role in ROLE_ORDER]
    for role in ROLE_ORDER:
        sources += [
            Path(browser_dir) / f"browser-{kind}-{role}.json"
            for kind in ("result", "observations", "pairs")
        ]
    require(len(sources) == EXPECTED_EVIDENCE_COUNT, "hue evidence count differs")
    for source in sources:
        require(
            source.is_file() and source.stat().st_size < 50_000_000, f"bad evidence {source.name}"
        )
        target = output / source.name
        shutil.copyfile(source, target)
        require(source.read_bytes() == target.read_bytes(), f"copy differs {source.name}")


def generate(search_dir: Path, request_dir: Path, browser_dir: Path, output_dir: Path) -> None:
    output = Path(output_dir).resolve()
    if output.exists():
        shutil.rmtree(output)
    data = collect(search_dir, request_dir, browser_dir)
    output.mkdir(parents=True)
    copy_evidence(search_dir, request_dir, browser_dir, output / "evidence")
    (output / "index.html").write_text(build_html(data))
    (output / "selection.json").write_text(
        json.dumps(selection_payload(data), indent=2, sort_keys=True) + "\n"
    )
    (output / "report.md").write_text(
        "# Candidate A de novo hue frontier\n\nFixed-four controlled diagnostic; see `index.html`.\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-dir", type=Path, required=True)
    parser.add_argument("--request-dir", type=Path, required=True)
    parser.add_argument("--browser-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    generate(args.search_dir, args.request_dir, args.browser_dir, args.output_dir)
    print(
        json.dumps(
            {"status": "PASS", "output": str(args.output_dir), "evidence_file_count": 22}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
