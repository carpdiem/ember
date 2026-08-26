#!/usr/bin/env python3
"""Generate the final three-way Candidate A human review package."""

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

import numpy as np

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
ROOT = EXPERIMENT.parents[2]
DEFAULT_OUTPUT = EXPERIMENT / "review/g2-seven-point-final-three"
ROLE_ORDER = ("reference", "benchmark-c", "a")
LABELS = {
    "reference": "Original Candidate A",
    "benchmark-c": "Fixed-four de novo yellow",
    "a": "Pink-relaxed golden",
}
CHANGE_COPY = {
    "reference": "Original seven-point Candidate A. No roles changed.",
    "benchmark-c": "Changes only the two warm roles. Pink, green, teal, and blue-violet remain exact.",
    "a": "Changes three roles: warm red, golden hue-family color, and pink. Green, teal, and blue-violet remain exact.",
}
EXPECTED_EVIDENCE_COUNT = 14
PRIOR_C_ACTUAL_1_5 = 7.30273837


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base_report = _load("base_report_for_final_three", "report.py")
seven = _load("seven_for_final_three", "optimizer.py")
browser = _load("browser_for_final_three", "browser_evidence.py")
p3 = seven.p3
contrast_ratio = seven.contrast_ratio
srgb_to_oklab = seven.srgb_to_oklab


class FinalThreeError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalThreeError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    require(isinstance(value, dict), f"{path.name} must be an object")
    return value


def oklch(value: str, gains: Sequence[float] | None = None) -> list[float]:
    rgb = p3.parse_exact_hex8(value)
    if gains is not None:
        rgb = rgb * np.asarray(gains, dtype=float)
    lab = srgb_to_oklab(rgb)
    return [
        float(lab[0]),
        float(np.hypot(lab[1], lab[2])),
        float(np.degrees(np.arctan2(lab[2], lab[1])) % 360.0),
    ]


def contrast_rows(bank: Sequence[str], inputs: Any) -> list[dict[str, Any]]:
    gains = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    surfaces = inputs.baseline["family"]["surfaces"]
    rows = []
    for index, value in enumerate(bank[1:]):
        rgb = p3.parse_exact_hex8(value)
        rows.append(
            {
                "role": f"category-{index}",
                "hex8": value,
                "commanded": {
                    background: contrast_ratio(rgb, p3.parse_exact_hex8(surfaces[background]))
                    for background in ("bg_0", "bg_1")
                },
                "transformed": {
                    background: contrast_ratio(
                        rgb * gains,
                        p3.parse_exact_hex8(surfaces[background]) * gains,
                    )
                    for background in ("bg_0", "bg_1")
                },
            }
        )
    return rows


def collect(search_dir: Path, request_dir: Path, browser_dir: Path) -> dict[str, Any]:
    inputs = seven.load_inputs(replay=False)
    contract = seven.load_contract()
    search = load_json(Path(search_dir) / "results.json")
    require(
        search["artifact_kind"] == "seven-point-minimal-relaxation-frontier",
        "minimal-relaxation search artifact differs",
    )
    gains = list(inputs.viewing["transform"]["gains"])
    rows = {}
    for role in ROLE_ORDER:
        print(f"[final-three] verify-start role={role}", file=sys.stderr, flush=True)
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
        require(verified["observation_count"] == 30_240, f"observation count differs for {role}")
        require(verified["pair_count"] == 90_720, f"pair count differs for {role}")
        request = load_json(request_path)
        result = load_json(result_path)
        pairs = load_json(pairs_path)
        bank = [request["fixed_fg0"], *request["serialized_bank"]]
        rows[role] = {
            "role": role,
            "label": LABELS[role],
            "change_copy": CHANGE_COPY[role],
            "candidate_id": request["candidate_id"],
            "bank": bank,
            "transformed_bank": [base_report.transformed_hex(value, gains) for value in bank],
            "oklch": [oklch(value) for value in bank],
            "transformed_oklch": [oklch(value, gains) for value in bank],
            "contrast": contrast_rows(bank, inputs),
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
        print(f"[final-three] verify-complete role={role}", file=sys.stderr, flush=True)
    require(
        rows["a"]["metrics"]["transformed"]["1.5"] > PRIOR_C_ACTUAL_1_5,
        "minimal-relaxation option falls below prior clean-sheet C",
    )
    return {"search": search, "rows": rows}


def identity_table(row: Mapping[str, Any]) -> str:
    labels = ("fg₀", "one", "two", "three", "four", "five", "six")
    body = []
    for index, label in enumerate(labels):
        source = row["oklch"][index]
        transformed = row["transformed_oklch"][index]
        body.append(
            f"<tr><th>{label}</th><td><code>{row['bank'][index]}</code></td>"
            f"<td>{source[0]:.3f} / {source[1]:.3f} / {source[2]:.1f}°</td>"
            f"<td><code>{row['transformed_bank'][index]}</code></td>"
            f"<td>{transformed[0]:.3f} / {transformed[1]:.3f} / {transformed[2]:.1f}°</td></tr>"
        )
    return (
        '<table class="identity-table"><thead><tr><th>Role</th><th>Commanded</th>'
        "<th>Oklch L/C/h</th><th>3400K</th><th>3400K Oklch</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def contrast_table(row: Mapping[str, Any]) -> str:
    changed = {
        "reference": {"category-0", "category-1"},
        "benchmark-c": {"category-0", "category-1"},
        "a": {"category-0", "category-1", "category-5"},
    }[row["role"]]
    body = []
    for item in row["contrast"]:
        if item["role"] not in changed:
            continue
        body.append(
            f"<tr><th>{item['role']} <code>{item['hex8']}</code></th>"
            f"<td>{item['commanded']['bg_0']:.3f}</td><td>{item['commanded']['bg_1']:.3f}</td>"
            f"<td>{item['transformed']['bg_0']:.3f}</td><td>{item['transformed']['bg_1']:.3f}</td></tr>"
        )
    return (
        '<table class="contrast-table"><thead><tr><th>Changed role</th><th>Cmd bg0</th>'
        "<th>Cmd bg1</th><th>3400K bg0</th><th>3400K bg1</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def terminal_specimen(values: Sequence[str]) -> str:
    return f"""<div class="terminal" style="--ink:{values[0]};--c1:{values[1]};--c2:{values[2]};--c3:{values[3]};--c4:{values[4]};--c5:{values[5]};--c6:{values[6]}"><div><span class="prompt">$</span> ember inspect --profile 3400k-light</div><div><span class="c1">series.one</span> <span class="c2">series.two</span> <span class="c3">series.three</span></div><div><span class="c4">INFO</span> transformed thin marks verified</div><div><span class="c5">TRACE</span> 21 symmetric pairs · <span class="c6">PASS</span></div></div>"""


def application_specimen(values: Sequence[str]) -> str:
    bars = "".join(
        f'<span style="height:{28 + index * 9}px;background:{values[index + 1]}"></span>'
        for index in range(6)
    )
    chips = "".join(
        f'<span style="border-color:{values[index + 1]};color:{values[index + 1]}">Series {index + 1}</span>'
        for index in range(6)
    )
    return f"""<div class="application" style="--ink:{values[0]}"><div class="app-head"><strong>Portfolio overview</strong><small>Exact palette identity</small></div><div class="bars">{bars}</div><div class="chips">{chips}</div></div>"""


def metric_strip(row: Mapping[str, Any]) -> str:
    binding = row["bindings"]["transformed"]["1.5"]
    return (
        '<div class="metric-strip"><strong>Actual transformed minima</strong>'
        f"<span>1.5px {row['metrics']['transformed']['1.5']:.3f}</span>"
        f"<span>2px {row['metrics']['transformed']['2']:.3f}</span>"
        f"<span>3px {row['metrics']['transformed']['3']:.3f}</span>"
        f"<span>Binding {html.escape(' ↔ '.join(binding['roles']))}</span></div>"
    )


def card(row: Mapping[str, Any]) -> str:
    return f"""<article class="option" id="option-{row["role"]}"><header><p class="eyebrow">Final human option</p><h2>{html.escape(row["label"])}</h2><p>{html.escape(row["change_copy"])}</p></header><section class="identity-first"><h3>Full commanded identity</h3><div class="swatches">{base_report.swatches(row["bank"])}</div>{base_report.line_specimen(row["bank"], 1.5, "commanded")}{base_report.finance_specimen(row["bank"])}{terminal_specimen(row["bank"])}{application_specimen(row["bank"])}</section><section class="transformed"><h3>Exact 3400K identity</h3><div class="swatches">{base_report.swatches(row["transformed_bank"])}</div>{base_report.line_specimen(row["transformed_bank"], 1.5, "transformed")}{base_report.line_specimen(row["transformed_bank"], 2.0, "transformed")}{terminal_specimen(row["transformed_bank"])}{application_specimen(row["transformed_bank"])}</section>{metric_strip(row)}{contrast_table(row)}<details><summary>Exact Hex and Oklch for all seven roles</summary>{identity_table(row)}</details></article>"""


def build_html(data: Mapping[str, Any]) -> str:
    rows = data["rows"]
    summary = "".join(
        f"<tr><th>{html.escape(rows[role]['label'])}</th>"
        f"<td>{rows[role]['metrics']['transformed']['1.5']:.3f}</td>"
        f"<td>{rows[role]['metrics']['transformed']['2']:.3f}</td>"
        f"<td>{rows[role]['metrics']['transformed']['3']:.3f}</td>"
        f"<td>{html.escape(rows[role]['change_copy'])}</td></tr>"
        for role in ROLE_ORDER
    )
    options = "".join(card(rows[role]) for role in ROLE_ORDER)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Candidate A final three-way review</title><style>
:root{{--bg:#f9f9f8;--ink:#342f2c;--muted:#665c54;--rule:#cac7c3;--panel:#ececeb}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 ui-sans-serif,system-ui,sans-serif}}main{{max-width:1720px;margin:auto;padding:28px}}h1{{font:700 clamp(34px,5vw,66px)/.98 ui-serif,Georgia,serif;max-width:1100px;margin:8px 0 16px}}h2,h3,p{{margin-top:0}}.lede{{font-size:18px;max-width:980px;color:var(--muted)}}.eyebrow{{font-size:11px;text-transform:uppercase;letter-spacing:.13em;font-weight:750;color:var(--muted);margin-bottom:6px}}.status{{display:flex;gap:10px;flex-wrap:wrap;margin:24px 0}}.status span{{border:1px solid var(--rule);background:var(--panel);padding:6px 9px;font-size:12px;font-weight:750}}.trade{{background:#fff9df;border-left:4px solid #8b6b12;padding:14px}}.summary-wrap{{overflow-x:auto;border-block:1px solid var(--rule);margin:26px 0}}table{{width:100%;border-collapse:collapse;white-space:nowrap}}th,td{{padding:9px;border-bottom:1px solid var(--rule);text-align:left}}.options{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;align-items:start}}.option{{border:1px solid var(--rule);background:#fff;padding:16px;min-width:0}}.option header{{min-height:142px}}.option section{{border-top:1px solid var(--rule);padding-top:12px;margin-top:12px}}.transformed{{background:#d8b08a22;padding:13px;margin-inline:-3px}}.swatches{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px}}.swatch{{min-width:0}}.swatch-color{{display:block;height:42px;background:var(--swatch);border:1px solid #342f2c33}}.swatch-name,.swatch code{{display:block;font-size:8px;overflow:hidden}}.line-specimen,.finance{{width:100%;height:auto;background:#f9f9f8;border:1px solid var(--rule);margin:8px 0}}.transformed .line-specimen{{background:#d0aa84}}.terminal{{background:#f2f0eb;color:var(--ink);border:1px solid var(--rule);padding:10px;font:11px/1.6 ui-monospace,monospace;margin:8px 0}}.terminal .prompt{{color:var(--c3)}}.terminal .c1{{color:var(--c1)}}.terminal .c2{{color:var(--c2)}}.terminal .c3{{color:var(--c3)}}.terminal .c4{{color:var(--c4)}}.terminal .c5{{color:var(--c5)}}.terminal .c6{{color:var(--c6)}}.application{{border:1px solid var(--rule);padding:10px;color:var(--ink);margin:8px 0}}.app-head{{display:flex;justify-content:space-between}}.app-head small{{color:var(--muted)}}.bars{{height:90px;display:flex;align-items:flex-end;gap:6px;margin:10px 0}}.bars span{{flex:1}}.chips{{display:flex;gap:4px;flex-wrap:wrap}}.chips span{{border:1px solid;padding:3px 5px;font-size:9px}}.metric-strip{{display:flex;gap:10px;flex-wrap:wrap;padding:12px 0;font-size:11px}}.contrast-table,.identity-table{{font-size:9px}}details{{margin-top:12px}}summary{{cursor:pointer;font-weight:700}}footer{{margin-top:30px;padding-top:16px;border-top:1px solid var(--rule);color:var(--muted)}}
@media(max-width:1180px){{.options{{grid-template-columns:1fr}}.option header{{min-height:0}}.summary-wrap{{overflow:visible}}.summary-wrap table{{table-layout:fixed;white-space:normal}}.summary-wrap th:nth-child(5),.summary-wrap td:nth-child(5){{display:none}}}}
@media(max-width:680px){{main{{padding:18px 12px}}.summary-wrap{{overflow:visible}}.summary-wrap table{{table-layout:fixed;white-space:normal;font-size:11px}}.summary-wrap th:nth-child(5),.summary-wrap td:nth-child(5){{display:none}}.option{{padding:13px;max-width:100%}}.swatch-name{{display:none}}.swatch code{{font-size:8px;writing-mode:vertical-rl;height:56px}}.contrast-table,.identity-table{{font-size:8px;white-space:normal;table-layout:fixed}}th,td{{padding:6px}}}}
</style></head><body><main><p class="eyebrow">Ember 3400K Light · final focused human review</p><h1>Three complete palette identities.</h1><p class="lede">The search phase is closed. This board compares only the original Candidate A, the strongest non-olive fixed-four frontier, and the smallest gate-clean relaxation that opens a cleaner golden region. No optimizer score chooses for Michael.</p><div class="status"><span>AWAITING MICHAEL FINAL-THREE SELECTION</span><span>Production: UNCHANGED</span><span>Automatic recommendation: NONE</span></div><p class="trade"><strong>Actual 1.5px trade:</strong> Original A 9.484 · Fixed-four yellow 9.137 · Pink-relaxed golden 7.725. All three are gate-clean; the pink-relaxed option remains above prior clean-sheet C at 7.303.</p><section><h2>Verified comparison</h2><div class="summary-wrap"><table><thead><tr><th>Option</th><th>1.5px</th><th>2px</th><th>3px</th><th>Role changes</th></tr></thead><tbody>{summary}</tbody></table></div></section><section><h2>Full visual identities</h2><div class="options">{options}</div></section><footer><p>Every option is backed by 30,240 fresh Chromium observations and 90,720 symmetric pair rows. Fixed <code>fg_0</code> and every noncategorical byte remain unchanged. Human selects; no automatic recommendation.</p></footer></main></body></html>"""


def selection_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    rows = data["rows"]
    return {
        "schema_version": 1,
        "artifact_kind": "seven-point-final-three-human-selection",
        "status": "AWAITING_MICHAEL_FINAL_THREE_SELECTION",
        "selection": None,
        "allowed_selections": ["ORIGINAL-A", "FIXED-FOUR-YELLOW", "PINK-RELAXED-GOLDEN"],
        "candidate_ids": {rows[role]["label"]: rows[role]["candidate_id"] for role in ROLE_ORDER},
        "automatic_recommendation": None,
        "production_promotion": False,
        "fixed_fg0": "#342F2C",
        "report_source": browser._source_binding("final_three_report.py"),
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
    require(len(sources) == EXPECTED_EVIDENCE_COUNT, "final-three evidence count differs")
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
        "# Candidate A final three-way review\n\nHuman selection board; see `index.html`.\n"
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
            {
                "status": "PASS",
                "output": str(args.output_dir),
                "evidence_file_count": EXPECTED_EVIDENCE_COUNT,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
