#!/usr/bin/env python3
"""Generate the focused Candidate A warm-pair human review."""

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
DEFAULT_OUTPUT = EXPERIMENT / "review/g2-seven-point-warm-pair"
ROLE_ORDER = ("reference", "benchmark-c", "a", "b", "c")
LABELS = {
    "reference": "Candidate A baseline",
    "benchmark-c": "Lift only",
    "a": "Clean gold",
    "b": "Bright warm",
    "c": "Photopic 2.7 challenge",
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


base_report = _load("seven_report_for_warm_review", "report.py")
seven = _load("seven_optimizer_for_warm_review", "optimizer.py")
warm = _load("warm_search_for_warm_review", "warm_pair.py")
browser = _load("seven_browser_for_warm_review", "browser_evidence.py")
p3 = seven.p3


class WarmReportError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WarmReportError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    require(isinstance(value, dict), f"{path.name} must be an object")
    return value


def collect(search_dir: Path, request_dir: Path, browser_dir: Path) -> dict[str, Any]:
    inputs = seven.load_inputs(replay=False)
    contract = seven.load_contract()
    search = load_json(Path(search_dir) / "results.json")
    require(search["artifact_kind"] == "seven-point-warm-pair-refinement", "warm search differs")
    rows = {}
    for role in ROLE_ORDER:
        print(f"[warm-report] verify-start role={role}", file=sys.stderr, flush=True)
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
        transformed = [
            base_report.transformed_hex(value, inputs.viewing["transform"]["gains"])
            for value in bank
        ]
        rows[role] = {
            "role": role,
            "label": LABELS[role],
            "candidate_id": request["candidate_id"],
            "bank": bank,
            "transformed_bank": transformed,
            "compliance": search_row["compliance"],
            "warm_red": search_row.get("warm_red", request["serialized_bank"][0]),
            "warm_gold": search_row.get("warm_gold", request["serialized_bank"][1]),
            "contrast": search_row["contrast"],
            "hard_gate_failures": search_row["hard_gate_failures"],
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
        print(f"[warm-report] verify-complete role={role}", file=sys.stderr, flush=True)
    return {"search": search, "rows": rows}


def contrast_table(row: Mapping[str, Any]) -> str:
    body = []
    for role in ("warm_red", "warm_gold"):
        label = "Warm red" if role == "warm_red" else "Gold / olive"
        values = row["contrast"][role]
        body.append(
            "<tr>"
            f"<th>{label}</th>"
            f"<td>{values['commanded']['bg_0']:.3f}</td>"
            f"<td>{values['commanded']['bg_1']:.3f}</td>"
            f"<td>{values['transformed']['bg_0']:.3f}</td>"
            f"<td>{values['transformed']['bg_1']:.3f}</td>"
            "</tr>"
        )
    return (
        '<table class="contrast"><thead><tr><th>Warm role</th><th>Cmd bg0</th>'
        "<th>Cmd bg1</th><th>3400K bg0</th><th>3400K bg1</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def card(row: Mapping[str, Any]) -> str:
    challenge = row["compliance"] != "FULL_3_0"
    badge = (
        '<span class="badge exception">2.7 challenge · not PASS</span>'
        if challenge
        else '<span class="badge pass">Full 3.0 contract</span>'
    )
    note = (
        '<p class="exception-note"><strong>Sole exception:</strong> warm gold at exact 3400K on bg1 '
        f"is {row['contrast']['warm_gold']['transformed']['bg_1']:.3f}:1 versus the 3.0 target. "
        "This is a photopic-adaptation hypothesis test, not an automatic recommendation.</p>"
        if challenge
        else ""
    )
    binding = row["bindings"]["transformed"]["1.5"]
    return f"""
<article class="variant {"challenge" if challenge else "compliant"}" id="variant-{row["role"]}">
<header><div><p class="eyebrow">Focused warm-pair lane</p><h2>{html.escape(row["label"])}</h2></div>{badge}</header>
<p class="pair">Warm pair <code>{html.escape(row["warm_red"])}</code> + <code>{html.escape(row["warm_gold"])}</code></p>{note}
<section><h3>Commanded</h3><div class="swatches">{base_report.swatches(row["bank"])}</div>{base_report.line_specimen(row["bank"], 1.5, "commanded")}{base_report.finance_specimen(row["bank"])}</section>
<section class="transformed"><h3>Exact 3400K transform</h3><div class="swatches">{base_report.swatches(row["transformed_bank"])}</div>{base_report.line_specimen(row["transformed_bank"], 1.5, "transformed")}{base_report.line_specimen(row["transformed_bank"], 2.0, "transformed")}</section>
<div class="metric"><strong>Actual transformed minima</strong><span>1.5px {row["metrics"]["transformed"]["1.5"]:.3f}</span><span>2px {row["metrics"]["transformed"]["2"]:.3f}</span><span>3px {row["metrics"]["transformed"]["3"]:.3f}</span><span>Binding {html.escape(" ↔ ".join(binding["roles"]))}</span></div>
{contrast_table(row)}
</article>"""


def build_html(data: Mapping[str, Any]) -> str:
    rows = data["rows"]
    table_rows = "".join(
        "<tr>"
        f"<th>{html.escape(rows[role]['label'])}</th>"
        f"<td>{rows[role]['warm_red']}</td><td>{rows[role]['warm_gold']}</td>"
        f"<td>{rows[role]['metrics']['transformed']['1.5']:.3f}</td>"
        f"<td>{rows[role]['contrast']['warm_gold']['transformed']['bg_1']:.3f}</td>"
        f"<td>{'2.7 exception' if rows[role]['compliance'] != 'FULL_3_0' else 'Full 3.0'}</td>"
        "</tr>"
        for role in ROLE_ORDER
    )
    baseline = card(rows["reference"])
    variants = "".join(card(rows[role]) for role in ("benchmark-c", "a", "b", "c"))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Candidate A warm-pair refinement</title>
<style>
:root{{--bg:#f9f9f8;--panel:#ececeb;--ink:#342f2c;--muted:#665c54;--rule:#cac7c3;--warn:#8b3618}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 ui-sans-serif,system-ui,sans-serif}}main{{max-width:1600px;margin:auto;padding:28px}}h1{{font:700 clamp(32px,5vw,64px)/1 ui-serif,Georgia,serif;max-width:1050px;margin:8px 0 16px}}h2,h3,p{{margin-top:0}}.lede{{max-width:920px;font-size:18px;color:var(--muted)}}.eyebrow{{font-size:11px;text-transform:uppercase;letter-spacing:.13em;font-weight:750;color:var(--muted);margin-bottom:6px}}.status{{display:flex;gap:10px;flex-wrap:wrap;margin:24px 0}}.status span,.badge{{border:1px solid var(--rule);padding:6px 9px;background:var(--panel);font-size:12px;font-weight:750}}.badge.exception{{border-color:var(--warn);color:var(--warn);background:#fff2e8}}.badge.pass{{color:#285c36}}.summary{{overflow-x:auto;margin:26px 0;border-block:1px solid var(--rule)}}table{{width:100%;border-collapse:collapse;white-space:nowrap}}th,td{{padding:9px;border-bottom:1px solid var(--rule);text-align:left}}.baseline{{max-width:780px;margin:24px auto}}.variants{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}.variant{{background:#fff;border:1px solid var(--rule);padding:18px;min-width:0}}.variant.challenge{{border:2px solid var(--warn)}}.variant header{{display:flex;justify-content:space-between;gap:12px}}.pair{{color:var(--muted);font-size:13px}}.exception-note{{border-left:4px solid var(--warn);padding:10px;background:#fff2e8}}.variant section{{border-top:1px solid var(--rule);padding-top:12px;margin-top:14px}}.transformed{{background:#d8b08a22;padding:14px;margin-inline:-4px}}.swatches{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px}}.swatch{{min-width:0}}.swatch-color{{display:block;height:44px;background:var(--swatch);border:1px solid #342f2c33}}.swatch-name,.swatch code{{display:block;font-size:9px;overflow:hidden}}.line-specimen,.finance{{width:100%;height:auto;background:#f9f9f8;border:1px solid var(--rule);margin:8px 0}}.transformed .line-specimen{{background:#d0aa84}}.metric{{display:flex;gap:12px;flex-wrap:wrap;padding:12px 0;font-size:12px}}.contrast{{font-size:11px}}footer{{margin-top:30px;padding-top:18px;border-top:1px solid var(--rule);color:var(--muted)}}
@media(max-width:1100px){{.variants{{grid-template-columns:1fr}}}}
@media(max-width:680px){{main{{padding:18px 12px}}.summary{{overflow:visible}}.summary table{{table-layout:fixed;white-space:normal;font-size:11px}}.summary th:nth-child(2),.summary td:nth-child(2),.summary th:nth-child(3),.summary td:nth-child(3){{display:none}}.variant{{padding:13px;max-width:100%}}.variant header{{display:block}}.badge{{display:inline-block;margin-bottom:10px}}.swatch-name{{display:none}}.swatch code{{font-size:8px;writing-mode:vertical-rl;height:56px}}.contrast{{font-size:9px;white-space:normal;table-layout:fixed}}th,td{{padding:7px}}}}
</style></head><body><main><p class="eyebrow">Ember 3400K Light · focused human correction</p><h1>Candidate A, without the ugly olive.</h1><p class="lede">Michael likes Candidate A but rejected <code>#857D0B</code> as “ugly as sin.” This experiment changes only the two warm colors. Fixed <code>fg_0</code> and the green, teal, blue-violet, and pink colors remain byte-identical. Human taste—not scalar optimization—motivates this pass.</p><div class="status"><span>AWAITING MICHAEL WARM-PAIR SELECTION</span><span>Production: UNCHANGED</span><span>Human 1.5px capacity: UNKNOWN</span></div><section><h2>Actual Chromium and contrast</h2><div class="summary"><table><thead><tr><th>Lane</th><th>Warm red</th><th>Gold</th><th>1.5px ΔEOK</th><th>Gold 3400K/bg1</th><th>Contract</th></tr></thead><tbody>{table_rows}</tbody></table></div></section><section><h2>Baseline A</h2><div class="baseline">{baseline}</div></section><section><h2>Focused alternatives</h2><div class="variants">{variants}</div></section><footer><p>The Photopic 2.7 lane is visibly flagged and is not a PASS or automatic recommendation. No 2.5 lane was generated. Every bank was captured in Chromium with 30,240 observations and 90,720 symmetric pair rows.</p></footer></main></body></html>"""


def selection_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    rows = data["rows"]
    return {
        "schema_version": 1,
        "artifact_kind": "seven-point-warm-pair-human-selection",
        "status": "AWAITING_MICHAEL_WARM_PAIR_SELECTION",
        "selection": None,
        "allowed_selections": ["KEEP-A", "LIFT-ONLY", "CLEAN-GOLD", "BRIGHT-WARM", "PHOTOPIC-2.7"],
        "candidate_ids": {rows[role]["label"]: rows[role]["candidate_id"] for role in ROLE_ORDER},
        "automatic_recommendation": None,
        "photopic_lane_status": "HUMAN_CHALLENGE_NOT_PASS",
        "production_promotion": False,
        "fixed_fg0": "#342F2C",
        "report_source": browser._source_binding("warm_pair_report.py"),
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
    require(len(sources) == EXPECTED_EVIDENCE_COUNT, "warm evidence count differs")
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
        "# Candidate A warm-pair review\n\nHuman aesthetic correction; see `index.html`.\n"
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
