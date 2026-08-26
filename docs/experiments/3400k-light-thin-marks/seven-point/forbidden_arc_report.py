#!/usr/bin/env python3
"""Generate the final forbidden-hue A/B/C human review package."""

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
DEFAULT_OUTPUT = EXPERIMENT / "review/g2-seven-point-forbidden-arc"
FINALIST_ROLES = ("a", "b", "c")
BENCHMARK_ROLES = ("reference", "benchmark-c")
ALL_ROLES = (*BENCHMARK_ROLES, *FINALIST_ROLES)
LABELS = {
    "reference": "Candidate A benchmark",
    "benchmark-c": "Prior C benchmark",
    "a": "New A",
    "b": "New B",
    "c": "New C",
}
LANE_COPY = {
    "a": "De novo lane A: broad role-neutral six-color rebuild.",
    "b": "De novo lane B: broad role-neutral six-color rebuild.",
    "c": "De novo lane C: balanced 3+3 lightness geometry.",
}
EXPECTED_EVIDENCE_COUNT = 22
FORBIDDEN_ARC = (92.0, 118.0)


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base_report = _load("base_report_for_forbidden_review", "report.py")
seven = _load("seven_for_forbidden_review", "optimizer.py")
browser = _load("browser_for_forbidden_review", "browser_evidence.py")
forbidden = _load("forbidden_for_forbidden_review", "forbidden_arc.py")
p3 = seven.p3
contrast_ratio = seven.contrast_ratio
srgb_to_oklab = seven.srgb_to_oklab


class ForbiddenReviewError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ForbiddenReviewError(message)


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
    for index, value in enumerate(bank):
        rgb = p3.parse_exact_hex8(value)
        rows.append(
            {
                "role": "fg₀" if index == 0 else f"category-{index - 1}",
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
        search["artifact_kind"] == "seven-point-forbidden-hue-arc-rebuild",
        "forbidden-arc search artifact differs",
    )
    require(search["forbidden_arc"]["closed_interval_degrees"] == [92.0, 118.0], "arc differs")
    require(search["pair_accounting"]["total_unordered_pairs"] == 21, "pair accounting differs")
    gains = list(inputs.viewing["transform"]["gains"])
    rows = {}
    for role in ALL_ROLES:
        print(f"[forbidden-review] verify-start role={role}", file=sys.stderr, flush=True)
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
        commanded_oklch = [oklch(value) for value in bank]
        rows[role] = {
            "role": role,
            "label": LABELS[role],
            "candidate_id": request["candidate_id"],
            "bank": bank,
            "transformed_bank": [base_report.transformed_hex(value, gains) for value in bank],
            "oklch": commanded_oklch,
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
            "forbidden_hues": [
                item[2]
                for item in commanded_oklch[1:]
                if FORBIDDEN_ARC[0] <= item[2] <= FORBIDDEN_ARC[1]
            ],
        }
        print(f"[forbidden-review] verify-complete role={role}", file=sys.stderr, flush=True)
    require(
        all(rows[role]["forbidden_hues"] == [] for role in FINALIST_ROLES),
        "finalist contains forbidden commanded hue",
    )
    require(
        len({tuple(rows[role]["bank"]) for role in FINALIST_ROLES}) == 3,
        "finalist identities collapsed",
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
            f"<td>{source[0]:.3f} / {source[1]:.3f} / {source[2]:.2f}°</td>"
            f"<td><code>{row['transformed_bank'][index]}</code></td>"
            f"<td>{transformed[0]:.3f} / {transformed[1]:.3f} / {transformed[2]:.2f}°</td></tr>"
        )
    return (
        '<table class="identity-table"><thead><tr><th>Role</th><th>Commanded</th>'
        "<th>Oklch L/C/h</th><th>Exact 3400K</th><th>3400K Oklch</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def contrast_table(row: Mapping[str, Any]) -> str:
    body = []
    for item in row["contrast"]:
        body.append(
            f"<tr><th>{item['role']} <code>{item['hex8']}</code></th>"
            f"<td>{item['commanded']['bg_0']:.3f}</td><td>{item['commanded']['bg_1']:.3f}</td>"
            f"<td>{item['transformed']['bg_0']:.3f}</td>"
            f"<td>{item['transformed']['bg_1']:.3f}</td></tr>"
        )
    return (
        '<table class="contrast-table"><thead><tr><th>Role</th><th>Cmd bg0</th>'
        "<th>Cmd bg1</th><th>3400K bg0</th><th>3400K bg1</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def terminal_specimen(values: Sequence[str]) -> str:
    return f"""<div class="terminal" style="--ink:{values[0]};--c1:{values[1]};--c2:{values[2]};--c3:{values[3]};--c4:{values[4]};--c5:{values[5]};--c6:{values[6]}"><div><span class="prompt">$</span> ember inspect --profile 3400k-light</div><div><span class="c1">series.one</span> <span class="c2">series.two</span> <span class="c3">series.three</span></div><div><span class="c4">INFO</span> forbidden arc excluded</div><div><span class="c5">TRACE</span> 21 pairs · two directions · <span class="c6">PASS</span></div></div>"""


def application_specimen(values: Sequence[str]) -> str:
    bars = "".join(
        f'<span style="height:{31 + index * 8}px;background:{values[index + 1]}"></span>'
        for index in range(6)
    )
    chips = "".join(
        f'<span style="border-color:{values[index + 1]};color:{values[index + 1]}">S{index + 1}</span>'
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


def exclusion_proof(row: Mapping[str, Any]) -> str:
    hues = [item[2] for item in row["oklch"][1:]]
    values = " · ".join(f"{value:.2f}°" for value in hues)
    return (
        '<div class="proof"><strong>Closed-arc proof: PASS</strong>'
        f"<span>Commanded categorical hues: {values}</span>"
        "<span>Zero lie within 92.0°–118.0°.</span></div>"
    )


def state_specimens(values: Sequence[str], state: str) -> str:
    widths = (1.5, 2.0, 3.0) if state == "transformed" else (1.5,)
    marks = "".join(base_report.line_specimen(values, width, state) for width in widths)
    return (
        f'<div class="swatches">{base_report.swatches(values)}</div>'
        + marks
        + base_report.finance_specimen(values)
        + terminal_specimen(values)
        + application_specimen(values)
    )


def card(row: Mapping[str, Any]) -> str:
    return f"""<article class="option" id="option-{row["role"]}"><header><p class="eyebrow">Forbidden-arc finalist</p><h2>{html.escape(row["label"])}</h2><p>{html.escape(LANE_COPY[row["role"]])}</p></header><section class="identity-first"><h3>Full commanded identity</h3>{state_specimens(row["bank"], "commanded")}</section><section class="transformed"><h3>Exact 3400K identity</h3>{state_specimens(row["transformed_bank"], "transformed")}</section>{metric_strip(row)}{exclusion_proof(row)}<details open><summary>Contrast on both backgrounds · both states</summary>{contrast_table(row)}</details><details><summary>Exact Hex and Oklch for all seven roles</summary>{identity_table(row)}</details></article>"""


def benchmark_strip(rows: Mapping[str, Any]) -> str:
    body = []
    for role in BENCHMARK_ROLES:
        row = rows[role]
        body.append(
            f'<article class="benchmark"><h3>{html.escape(row["label"])}</h3>'
            f'<div class="compact-swatches">{base_report.swatches(row["bank"])}</div>'
            f"<p><strong>Actual transformed:</strong> 1.5px {row['metrics']['transformed']['1.5']:.3f} · "
            f"2px {row['metrics']['transformed']['2']:.3f} · "
            f"3px {row['metrics']['transformed']['3']:.3f}</p></article>"
        )
    return '<div class="benchmarks">' + "".join(body) + "</div>"


def build_html(data: Mapping[str, Any]) -> str:
    rows = data["rows"]
    search = data["search"]
    summary = "".join(
        f"<tr><th>{rows[role]['label']}</th>"
        f"<td>{rows[role]['metrics']['transformed']['1.5']:.3f}</td>"
        f"<td>{rows[role]['metrics']['transformed']['2']:.3f}</td>"
        f"<td>{rows[role]['metrics']['transformed']['3']:.3f}</td>"
        f"<td>{' / '.join(rows[role]['bank'][1:])}</td></tr>"
        for role in FINALIST_ROLES
    )
    options = "".join(card(rows[role]) for role in FINALIST_ROLES)
    catalog = search["catalog"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Forbidden-arc A/B/C review</title><style>
:root{{--bg:#f9f9f8;--ink:#342f2c;--muted:#665c54;--rule:#cac7c3;--panel:#ececeb;--warm:#fff6e9}}*{{box-sizing:border-box}}html,body{{max-width:100%;overflow-x:hidden}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 ui-sans-serif,system-ui,sans-serif}}main{{max-width:1720px;margin:auto;padding:28px}}h1{{font:700 clamp(34px,5vw,66px)/.98 ui-serif,Georgia,serif;max-width:1120px;margin:8px 0 16px}}h2,h3,p{{margin-top:0}}.lede{{font-size:18px;max-width:1040px;color:var(--muted)}}.eyebrow{{font-size:11px;text-transform:uppercase;letter-spacing:.13em;font-weight:750;color:var(--muted);margin-bottom:6px}}.status{{display:flex;gap:10px;flex-wrap:wrap;margin:24px 0}}.status span{{border:1px solid var(--rule);background:var(--panel);padding:6px 9px;font-size:12px;font-weight:750}}.method{{background:var(--warm);border-left:4px solid #8b6b12;padding:14px;max-width:1180px}}.summary-wrap{{overflow-x:auto;border-block:1px solid var(--rule);margin:26px 0}}table{{width:100%;border-collapse:collapse;white-space:nowrap}}th,td{{padding:8px;border-bottom:1px solid var(--rule);text-align:left}}.summary-wrap td:last-child{{font:10px/1.35 ui-monospace,monospace}}.options{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;align-items:start}}.option{{border:1px solid var(--rule);background:#fff;padding:15px;min-width:0}}.option header{{min-height:126px}}.option section{{border-top:1px solid var(--rule);padding-top:11px;margin-top:11px}}.transformed{{background:#d8b08a22;padding:12px;margin-inline:-3px}}.swatches{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px}}.swatch{{min-width:0}}.swatch-color{{display:block;height:42px;background:var(--swatch);border:1px solid #342f2c33}}.swatch-name,.swatch code{{display:block;font-size:8px;overflow:hidden}}.line-specimen,.finance{{width:100%;height:auto;background:#f9f9f8;border:1px solid var(--rule);margin:8px 0}}.transformed .line-specimen,.transformed .finance{{background:#d0aa84}}.terminal{{background:#f2f0eb;color:var(--ink);border:1px solid var(--rule);padding:10px;font:11px/1.6 ui-monospace,monospace;margin:8px 0}}.terminal .prompt{{color:var(--c3)}}.terminal .c1{{color:var(--c1)}}.terminal .c2{{color:var(--c2)}}.terminal .c3{{color:var(--c3)}}.terminal .c4{{color:var(--c4)}}.terminal .c5{{color:var(--c5)}}.terminal .c6{{color:var(--c6)}}.application{{border:1px solid var(--rule);padding:10px;margin:8px 0;color:var(--ink);background:#f8f7f4}}.app-head{{display:flex;justify-content:space-between;gap:8px}}.app-head small{{color:var(--ink);opacity:.72}}.bars{{height:86px;display:flex;align-items:end;gap:7px;margin:12px 0}}.bars span{{flex:1;min-width:0}}.chips{{display:flex;flex-wrap:wrap;gap:4px}}.chips span{{border:1px solid;padding:2px 5px;font-size:9px;font-weight:700}}.metric-strip,.proof{{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0;padding:9px;background:var(--panel)}}.metric-strip span,.proof span{{font-size:11px}}.proof{{background:#eef4e9;border-left:3px solid #35672f}}details{{margin-top:10px}}summary{{font-weight:750;cursor:pointer}}.contrast-table,.identity-table{{font-size:9px;margin-top:8px}}.benchmarks{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:16px 0 30px}}.benchmark{{border:1px solid var(--rule);background:var(--panel);padding:12px}}.benchmark h3{{margin-bottom:8px}}.benchmark p{{margin:8px 0 0;font-size:12px}}.compact-swatches .swatch-color{{height:20px}}.compact-swatches .swatch-name,.compact-swatches code{{display:none}}.compact-swatches{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:3px}}footer{{margin:26px 0;color:var(--muted)}}
@media(max-width:1180px){{.options{{grid-template-columns:1fr}}.option header{{min-height:0}}.summary-wrap{{overflow:visible}}.summary-wrap table{{table-layout:fixed;white-space:normal}}.summary-wrap th:nth-child(5),.summary-wrap td:nth-child(5){{display:none}}}}
@media(max-width:680px){{main{{padding:18px 12px}}.summary-wrap table{{font-size:11px}}.benchmarks{{grid-template-columns:1fr}}.option{{padding:12px}}.swatch-name{{display:none}}.swatch code{{font-size:8px;writing-mode:vertical-rl;height:56px}}.contrast-table,.identity-table{{font-size:8px;white-space:normal;table-layout:fixed}}th,td{{padding:5px}}.app-head{{font-size:11px}}}}
</style></head><body><main><p class="eyebrow">Ember 3400K Light · forbidden-hue final review</p><h1>Three de novo six-color systems.</h1><p class="lede">The categorical bank was rebuilt from scratch after role-neutrally excluding every exact Hex whose commanded Oklch hue lies in the closed 92.0°–118.0° arc. Higher actual minima mean stronger worst-case thin-mark separation. Attractiveness remains a human judgment.</p><div class="status"><span>AWAITING MICHAEL A/B/C SELECTION</span><span>Production: UNCHANGED</span><span>Automatic recommendation: NONE</span></div><p class="method"><strong>Eligibility and accounting.</strong> Full catalog {catalog["full_before"]:,} → {catalog["full_after"]:,}; {catalog["full_rejected"]:,} forbidden colors removed. Every finalist proves zero categorical hues in the forbidden arc. Fixed <code>fg_0 #342F2C</code> participates in exactly 21 unordered pairs: 15 category↔category plus 6 fg₀↔category, with both lane directions.</p><section><h2>Actual Chromium comparison</h2><div class="summary-wrap"><table><thead><tr><th>Finalist</th><th>1.5px</th><th>2px</th><th>3px</th><th>Exact categorical bank</th></tr></thead><tbody>{summary}</tbody></table></div>{benchmark_strip(rows)}<p class="lede">Candidate A and prior C are compact evidence controls only. They did not affect eligibility or ranking.</p></section><section><h2>Full commanded and 3400K identities</h2><div class="options">{options}</div></section><footer><p>Each of the five banks is independently backed by 30,240 Chromium observations and 90,720 symmetric pair rows. The three finalists pass all hard gates. Selection is intentionally null.</p></footer></main></body></html>"""


def selection_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    rows = data["rows"]
    return {
        "schema_version": 1,
        "artifact_kind": "seven-point-forbidden-arc-human-selection",
        "status": "AWAITING_MICHAEL_FORBIDDEN_ARC_SELECTION",
        "selection": None,
        "allowed_selections": ["NEW-A", "NEW-B", "NEW-C"],
        "candidate_ids": {
            rows[role]["label"]: rows[role]["candidate_id"] for role in FINALIST_ROLES
        },
        "benchmark_ids": {
            rows[role]["label"]: rows[role]["candidate_id"] for role in BENCHMARK_ROLES
        },
        "automatic_recommendation": None,
        "production_promotion": False,
        "fixed_fg0": "#342F2C",
        "forbidden_commanded_oklch_hue_arc_closed": [92.0, 118.0],
        "total_unordered_pairs": 21,
        "report_source": browser._source_binding("forbidden_arc_report.py"),
    }


def copy_evidence(search_dir: Path, request_dir: Path, browser_dir: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    sources = [Path(search_dir) / name for name in ("catalog-summary.json", "results.json")]
    sources += [Path(request_dir) / f"browser-request-{role}.json" for role in ALL_ROLES]
    for role in ALL_ROLES:
        sources += [
            Path(browser_dir) / f"browser-{kind}-{role}.json"
            for kind in ("result", "observations", "pairs")
        ]
    require(len(sources) == EXPECTED_EVIDENCE_COUNT, "forbidden review evidence count differs")
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
        "# Forbidden-hue A/B/C review\n\nHuman selection board; see `index.html`.\n"
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
