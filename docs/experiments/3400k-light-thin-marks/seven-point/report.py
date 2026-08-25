#!/usr/bin/env python3
"""Generate the immutable fixed-fg0 seven-point human-review package."""

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
DEFAULT_OUTPUT = EXPERIMENT / "review/g2-seven-point"
ROLE_ORDER = ("reference", "benchmark-c", "a", "b", "c")
FINALIST_ROLES = ("a", "b", "c")
ROLE_LABELS = {
    "reference": "Current production",
    "benchmark-c": "Prior clean-sheet C",
    "a": "Candidate A",
    "b": "Candidate B",
    "c": "Candidate C",
}
EXPECTED_EVIDENCE_COUNT = 22
EXPECTED_OUTPUT_FILES = {"index.html", "report.md", "selection.json", "evidence"}


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seven = _load("seven_point_optimizer_for_report", "optimizer.py")
polish = _load("seven_point_polish_for_report", "polish.py")
browser = _load("seven_point_browser_for_report", "browser_evidence.py")
p3 = seven.p3


class ReportError(RuntimeError):
    """Raised when review evidence or output violates the closed report contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReportError(message)


def load_json(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def transformed_hex(value: str, gains: Sequence[float]) -> str:
    rgb = p3.parse_exact_hex8(value) * np.asarray(gains, dtype=float)
    return p3.srgb_to_hex(np.clip(rgb, 0.0, 1.0))


def gated_metric(result: Mapping[str, Any], width: str, state: str) -> float:
    rows = result["pair_metrics_by_family"]["seven_point"]["actual_by_width_state_background"][
        width
    ][state]
    return min(float(rows[name]["minimum_observed_delta_e_ok"]) for name in p3.GATE_BACKGROUNDS)


def pair_binding(
    request: Mapping[str, Any], pairs: Mapping[str, Any], width: float, state: str
) -> dict[str, Any]:
    plan = {row["id"]: row for row in request["requested_pairs"]}
    candidates = []
    for row in pairs["rows"]:
        item = plan[row["id"]]
        if (
            float(item["width_css_px"]) == width
            and item["state"] == state
            and item["background"] in p3.GATE_BACKGROUNDS
        ):
            candidates.append(
                (
                    float(row["observed_delta_e_ok"]),
                    tuple(item["roles"]),
                    item["background"],
                    item["id"],
                )
            )
    require(bool(candidates), f"no pair binding for {width:g}px {state}")
    value, roles, background, pair_id = min(candidates)
    return {
        "delta_e_ok": value,
        "roles": list(roles),
        "background": background,
        "pair_id": pair_id,
    }


def collect(
    search_dir: Path, request_dir: Path, browser_dir: Path, *, replay_search: bool
) -> dict[str, Any]:
    inputs = seven.load_inputs(replay=False)
    contract = seven.load_contract()
    if replay_search:
        polish.validate(search_dir, progress=True)
    search = load_json(Path(search_dir) / "results.json", "polished search results")
    require(
        search.get("artifact_kind") == "seven-point-bounded-full-catalog-polish",
        "search artifact kind differs",
    )
    gains = list(inputs.viewing["transform"]["gains"])
    rows = {}
    for role in ROLE_ORDER:
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
        require(verified["status"] == "PASS", f"browser verification failed for {role}")
        require(verified["observation_count"] == 30_240, f"observation count differs for {role}")
        require(verified["pair_count"] == 90_720, f"pair count differs for {role}")
        require(
            verified["family_counts"] == {"seven_point": 90_720},
            f"pair family count differs for {role}",
        )
        request = load_json(request_path, f"request {role}")
        result = load_json(result_path, f"result {role}")
        pairs = load_json(pairs_path, f"pairs {role}")
        bank = [request["fixed_fg0"], *request["serialized_bank"]]
        rows[role] = {
            "role": role,
            "label": ROLE_LABELS[role],
            "candidate_id": request["candidate_id"],
            "bank": bank,
            "transformed_bank": [transformed_hex(value, gains) for value in bank],
            "status": result["status"],
            "metrics": {
                state: {width: gated_metric(result, width, state) for width in ("1.5", "2", "3")}
                for state in ("commanded", "transformed")
            },
            "bindings": {
                state: {
                    width: pair_binding(request, pairs, float(width), state)
                    for width in ("1.5", "2", "3")
                }
                for state in ("commanded", "transformed")
            },
            "request_sha256": browser.sha256_file(request_path),
            "result_sha256": browser.sha256_file(result_path),
            "observations_sha256": browser.sha256_file(observations_path),
            "pairs_sha256": browser.sha256_file(pairs_path),
        }
    recommendation = max(
        FINALIST_ROLES,
        key=lambda role: (
            rows[role]["metrics"]["transformed"]["1.5"],
            rows[role]["metrics"]["transformed"]["2"],
            rows[role]["metrics"]["transformed"]["3"],
            role,
        ),
    )
    return {
        "inputs": inputs,
        "contract": contract,
        "search": search,
        "rows": rows,
        "recommendation": recommendation,
    }


def swatches(values: Sequence[str], *, labeled: bool = True) -> str:
    labels = ["fg₀", "one", "two", "three", "four", "five", "six"]
    return "".join(
        f'<div class="swatch" style="--swatch:{html.escape(value)}">'
        f'<span class="swatch-color"></span>'
        + (
            f'<span class="swatch-name">{html.escape(labels[index])}</span>'
            f"<code>{html.escape(value)}</code>"
            if labeled
            else ""
        )
        + "</div>"
        for index, value in enumerate(values)
    )


def line_specimen(values: Sequence[str], width: float, suffix: str) -> str:
    paths = [
        "M8 26 C58 2 110 50 160 26 S260 2 312 26",
        "M8 39 C58 15 110 63 160 39 S260 15 312 39",
        "M8 52 C58 28 110 76 160 52 S260 28 312 52",
        "M8 65 C58 41 110 89 160 65 S260 41 312 65",
        "M8 78 C58 54 110 102 160 78 S260 54 312 78",
        "M8 91 C58 67 110 115 160 91 S260 67 312 91",
        "M8 104 C58 80 110 128 160 104 S260 80 312 104",
    ]
    dashes = ("", "8 5", "2 5", "12 4 2 4", "5 3", "1 4", "10 5")
    return (
        f'<svg class="line-specimen" viewBox="0 0 320 132" role="img" '
        f'aria-label="Seven-point {width:g}px thin-mark specimen {html.escape(suffix)}">'
        + "".join(
            f'<path d="{paths[index]}" stroke="{value}" stroke-width="{width}" '
            f'stroke-dasharray="{dashes[index]}" fill="none" />'
            for index, value in enumerate(values)
        )
        + "</svg>"
    )


def finance_specimen(values: Sequence[str]) -> str:
    paths = [
        "M8 92 L54 79 L100 86 L146 54 L192 62 L238 29 L306 36",
        "M8 70 L54 63 L100 48 L146 67 L192 40 L238 53 L306 25",
        "M8 101 L54 84 L100 91 L146 78 L192 85 L238 66 L306 73",
        "M8 58 L54 75 L100 60 L146 44 L192 50 L238 35 L306 43",
        "M8 110 L54 102 L100 76 L146 83 L192 61 L238 68 L306 48",
        "M8 82 L54 91 L100 72 L146 90 L192 74 L238 46 L306 58",
    ]
    return (
        '<svg class="finance" viewBox="0 0 314 124" role="img" '
        'aria-label="Six categorical series with fixed foreground axes">'
        f'<path d="M8 8 V112 H306" stroke="{values[0]}" stroke-width="1.5" fill="none" />'
        + "".join(
            f'<path d="{path}" stroke="{values[index + 1]}" stroke-width="2" '
            f'fill="none" stroke-linecap="round" />'
            for index, path in enumerate(paths)
        )
        + "</svg>"
    )


def metric_table(row: Mapping[str, Any]) -> str:
    body = []
    for width in ("1.5", "2", "3"):
        binding = row["bindings"]["transformed"][width]
        body.append(
            "<tr>"
            f"<th>{width}px</th>"
            f"<td>{row['metrics']['transformed'][width]:.3f}</td>"
            f"<td>{html.escape(' ↔ '.join(binding['roles']))}</td>"
            f"<td>{html.escape(binding['background'])}</td>"
            "</tr>"
        )
    return (
        '<table class="metrics"><thead><tr><th>Width</th><th>Worst ΔEOK</th>'
        "<th>Binding pair</th><th>Canvas</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def candidate_card(row: Mapping[str, Any], recommendation: str) -> str:
    badge = '<span class="badge">Recommended</span>' if row["role"] == recommendation else ""
    return f"""
<article class="candidate" id="candidate-{row["role"]}">
  <header><div><p class="eyebrow">Seven-point finalist</p><h2>{html.escape(row["label"])}</h2></div>{badge}</header>
  <p class="candidate-id">ID <code>{html.escape(row["candidate_id"][:16])}…</code></p>
  <section><h3>Commanded</h3><div class="swatches">{swatches(row["bank"])}</div>
  {line_specimen(row["bank"], 1.5, "commanded on bg0")}{finance_specimen(row["bank"])}</section>
  <section class="transformed"><h3>Exact 3400K transform</h3><div class="swatches">{swatches(row["transformed_bank"])}</div>
  {line_specimen(row["transformed_bank"], 1.5, "transformed on bg0")}
  {line_specimen(row["transformed_bank"], 2.0, "transformed on bg1")}</section>
  {metric_table(row)}
</article>"""


def build_html(data: Mapping[str, Any]) -> str:
    rows = data["rows"]
    recommendation = data["recommendation"]
    summary_rows = "".join(
        "<tr>"
        f"<th>{html.escape(rows[role]['label'])}</th>"
        f"<td>{rows[role]['metrics']['transformed']['1.5']:.3f}</td>"
        f"<td>{rows[role]['metrics']['transformed']['2']:.3f}</td>"
        f"<td>{rows[role]['metrics']['transformed']['3']:.3f}</td>"
        f"<td>{html.escape(' ↔ '.join(rows[role]['bindings']['transformed']['1.5']['roles']))}</td>"
        "</tr>"
        for role in ROLE_ORDER
    )
    baseline_cards = "".join(
        f'<article class="benchmark"><h3>{html.escape(rows[role]["label"])}</h3>'
        f'<div class="swatches compact">{swatches(rows[role]["transformed_bank"], labeled=False)}</div>'
        f"{line_specimen(rows[role]['transformed_bank'], 1.5, rows[role]['label'])}"
        f"<p>Worst transformed 1.5px: <strong>{rows[role]['metrics']['transformed']['1.5']:.3f}</strong></p></article>"
        for role in ("reference", "benchmark-c")
    )
    finalists = "".join(candidate_card(rows[role], recommendation) for role in FINALIST_ROLES)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ember 3400K Light — fixed-fg₀ seven-point review</title>
<style>
:root{{--bg:#f9f9f8;--panel:#ececeb;--ink:#342f2c;--muted:#665c54;--rule:#cac7c3;--accent:#8b4666}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 ui-sans-serif,system-ui,-apple-system,sans-serif}}
main{{max-width:1680px;margin:auto;padding:28px}} h1{{font:700 clamp(30px,5vw,64px)/.98 ui-serif,Georgia,serif;max-width:960px;margin:10px 0 18px}}
h2,h3,p{{margin-top:0}} .lede{{max-width:900px;font-size:18px;color:var(--muted)}} .eyebrow{{text-transform:uppercase;letter-spacing:.12em;font-size:11px;font-weight:750;color:var(--muted);margin-bottom:6px}}
.status{{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0 32px}} .status span,.badge{{border:1px solid var(--rule);padding:6px 10px;background:var(--panel);font-size:12px;font-weight:700}}
.summary-wrap{{overflow-x:auto;border-block:1px solid var(--rule);margin:28px 0}} table{{width:100%;border-collapse:collapse;white-space:nowrap}} th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid var(--rule)}} thead{{font-size:12px;color:var(--muted)}}
.benchmarks{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:28px 0}} .benchmark,.candidate{{border:1px solid var(--rule);background:#fff;padding:18px}}
.finalists{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;align-items:start}} .candidate header{{display:flex;justify-content:space-between;gap:12px}} .candidate-id{{font-size:12px;color:var(--muted)}}
.candidate section{{border-top:1px solid var(--rule);padding-top:14px;margin-top:14px}} .transformed{{background:#d8b08a22;padding:14px;margin-inline:-4px}} .swatches{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px;margin:8px 0 12px}} .swatch{{min-width:0}} .swatch-color{{display:block;height:46px;background:var(--swatch);border:1px solid #342f2c33}} .swatch-name,.swatch code{{display:block;font-size:10px;overflow:hidden;text-overflow:ellipsis}} .swatch-name{{font-weight:700;margin-top:4px}} .compact .swatch-color{{height:28px}}
.line-specimen,.finance{{display:block;width:100%;height:auto;background:#f9f9f8;border:1px solid var(--rule);margin:8px 0}} .transformed .line-specimen{{background:#d0aa84}} .metrics{{font-size:12px;margin-top:14px}} .metrics th,.metrics td{{padding:7px 5px}} code{{font-family:ui-monospace,SFMono-Regular,monospace}} footer{{margin-top:36px;border-top:1px solid var(--rule);padding-top:18px;color:var(--muted)}}
@media(max-width:1180px){{.finalists{{grid-template-columns:1fr}} .candidate{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}} .candidate>header,.candidate>.candidate-id,.candidate>.metrics{{grid-column:1/-1}}}}
@media(max-width:680px){{main{{padding:18px 12px}} .benchmarks{{grid-template-columns:1fr}} .candidate{{display:block;padding:14px}} .swatch-color{{height:38px}} .swatch-name{{display:none}} .swatch code{{font-size:8px;writing-mode:vertical-rl;height:56px}} th,td{{padding:8px}}}}
</style></head><body><main>
<p class="eyebrow">Ember palette experiment · 3400K Light</p><h1>One fixed ink. Six jointly optimized categorical colors.</h1>
<p class="lede">All 21 unordered pairs are evaluated symmetrically. <code>fg_0 #342F2C</code> and every non-categorical role remain frozen. Michael selects A, B, C, or rejects all.</p>
<div class="status"><span>AWAITING MICHAEL SELECTION</span><span>Human 1.5px capacity: UNKNOWN</span><span>Production promotion: FALSE</span><span>Evidence: 22 files</span></div>
<section><h2>Actual Chromium minima</h2><div class="summary-wrap"><table><thead><tr><th>Bank</th><th>1.5px</th><th>2px</th><th>3px</th><th>1.5px binding</th></tr></thead><tbody>{summary_rows}</tbody></table></div></section>
<section><h2>Anchors</h2><div class="benchmarks">{baseline_cards}</div></section>
<section><h2>Finalists</h2><div class="finalists">{finalists}</div></section>
<footer><p><strong>Recommendation: {html.escape(recommendation.upper())}</strong> — highest actual transformed minimum at 1.5px, then 2px and 3px. Recommendation is not selection.</p><p>Exact browser evidence: 30,240 observations and 90,720 symmetric pair rows per bank. No production values changed.</p></footer>
</main></body></html>"""


def build_report_md(data: Mapping[str, Any]) -> str:
    rows = data["rows"]
    lines = [
        "# Fixed-fg₀ seven-point review",
        "",
        "**Status:** `AWAITING_MICHAEL_SELECTION`  ",
        "**Selection:** `null`  ",
        f"**Recommendation:** `{data['recommendation'].upper()}`  ",
        "**Human 1.5px capacity:** `UNKNOWN`  ",
        "**Production promotion:** `false`",
        "",
        "| Bank | Transformed 1.5px | 2px | 3px | 1.5px binding |",
        "|---|---:|---:|---:|---|",
    ]
    for role in ROLE_ORDER:
        row = rows[role]
        lines.append(
            f"| {row['label']} | {row['metrics']['transformed']['1.5']:.8f} | "
            f"{row['metrics']['transformed']['2']:.8f} | "
            f"{row['metrics']['transformed']['3']:.8f} | "
            f"{' ↔ '.join(row['bindings']['transformed']['1.5']['roles'])} |"
        )
    lines += [
        "",
        "All values are actual Chromium minima over the two gating backgrounds. `bg_2` remains report-only.",
        "All 21 pairs use both subpixel lane directions. `fg_0`, all other foregrounds, surfaces, terminal colors, sequential maps, dark palettes, and production exports are unchanged.",
        "",
    ]
    return "\n".join(lines)


def selection_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    rows = data["rows"]
    return {
        "schema_version": 1,
        "artifact_kind": "seven-point-human-selection",
        "status": "AWAITING_MICHAEL_SELECTION",
        "selection": None,
        "allowed_selections": ["A", "B", "C"],
        "candidate_ids": {role.upper(): rows[role]["candidate_id"] for role in FINALIST_ROLES},
        "recommendation": data["recommendation"].upper(),
        "human_1_5px_capacity": "UNKNOWN",
        "production_promotion": False,
        "fixed_fg0": "#342F2C",
        "evidence_file_count": EXPECTED_EVIDENCE_COUNT,
        "report_source": browser._source_binding("report.py"),
    }


def copy_evidence(
    search_dir: Path, request_dir: Path, browser_dir: Path, evidence_dir: Path
) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sources = [
        Path(search_dir) / "catalog-summary.json",
        Path(search_dir) / "results.json",
    ]
    sources += [Path(request_dir) / f"browser-request-{role}.json" for role in ROLE_ORDER]
    for role in ROLE_ORDER:
        sources += [
            Path(browser_dir) / f"browser-result-{role}.json",
            Path(browser_dir) / f"browser-observations-{role}.json",
            Path(browser_dir) / f"browser-pairs-{role}.json",
        ]
    require(len(sources) == EXPECTED_EVIDENCE_COUNT, "evidence source count differs")
    for source in sources:
        require(source.is_file(), f"missing evidence source: {source.name}")
        require(source.stat().st_size < 50_000_000, f"evidence file exceeds 50 MB: {source.name}")
        target = evidence_dir / source.name
        shutil.copyfile(source, target)
        require(source.read_bytes() == target.read_bytes(), f"evidence copy differs: {source.name}")
    require(
        len([path for path in evidence_dir.iterdir() if path.is_file()]) == EXPECTED_EVIDENCE_COUNT,
        "tracked evidence count differs",
    )


def generate(
    search_dir: Path,
    request_dir: Path,
    browser_dir: Path,
    output_dir: Path,
    *,
    replay_search: bool,
) -> dict[str, Any]:
    output = Path(output_dir).resolve()
    if output.exists():
        unexpected = {path.name for path in output.iterdir()} - EXPECTED_OUTPUT_FILES
        require(not unexpected, f"review output contains unexpected entries: {sorted(unexpected)}")
        shutil.rmtree(output)
    data = collect(search_dir, request_dir, browser_dir, replay_search=replay_search)
    output.mkdir(parents=True)
    copy_evidence(search_dir, request_dir, browser_dir, output / "evidence")
    (output / "index.html").write_text(build_html(data))
    (output / "report.md").write_text(build_report_md(data))
    (output / "selection.json").write_text(
        json.dumps(selection_payload(data), indent=2, sort_keys=True) + "\n"
    )
    return {
        "status": "PASS",
        "output": str(output),
        "recommendation": data["recommendation"].upper(),
        "evidence_file_count": EXPECTED_EVIDENCE_COUNT,
        "review_status": "AWAITING_MICHAEL_SELECTION",
        "selection": None,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-dir", type=Path, required=True)
    parser.add_argument("--request-dir", type=Path, required=True)
    parser.add_argument("--browser-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-search-replay", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = generate(
        args.search_dir,
        args.request_dir,
        args.browser_dir,
        args.output_dir,
        replay_search=not args.skip_search_replay,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
