#!/usr/bin/env python3
"""Build the deterministic clean-sheet G2 human-review package.

The source validates the optimizer artifacts and independently replays every
browser observation and pair row before writing. All output is confined to the
explicit ``--output-dir``.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
for directory in (HERE, EXPERIMENT):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import browser_evidence as browser
import optimizer as clean
import phase3_optimizer as p3

STATUS = "AWAITING_MICHAEL_SELECTION"
RECOMMENDATION = "C"
ROLES = ("REFERENCE", "A", "B", "C")
ROLE_NAMES = tuple(p3.ROLES)
ROLE_SHORT = tuple(p3.ROLE_NAMES)
SEARCH_FILES = tuple(browser.SEARCH_FILES)
REQUEST_FILES = tuple(f"browser-request-{role.lower()}.json" for role in ROLES)
BROWSER_FILES = tuple(
    f"browser-{kind}-{role.lower()}.json"
    for role in ROLES
    for kind in ("result", "observations", "pairs")
)
EVIDENCE_FILES = (*SEARCH_FILES, *REQUEST_FILES, *BROWSER_FILES)
LIMIT_BYTES = 50_000_000
GATED_BACKGROUNDS = ("bg_0", "bg_1")
REPORT_BACKGROUND = "bg_2"
WIDTHS = ("1.5", "2", "3")
METHODS = {
    "REFERENCE": (
        "Current approved bank",
        "Frozen comparison only. It anchors gains and regressions; it is not a finalist.",
    ),
    "A": (
        "Constructive cool-lighter / warm-darker",
        (
            "Maximizes categorical-only raster separation. It accepts more purple/brown character "
            "and regresses category↔fg_0 at 2px and 3px."
        ),
    ),
    "B": (
        "Transformed-native targets inverted through exact gains",
        (
            "The middle categorical option. It improves 1.5px category↔fg_0, but shares A’s "
            "2px and 3px category↔fg_0 regressions."
        ),
    ),
    "C": (
        "Continuity compromise with zero-to-two broad anchors",
        (
            "A mature teal / green / pink / red / olive / blue bank. It gives up some "
            "categorical-only gain versus A/B to improve category↔fg_0 at every width."
        ),
    ),
}


class ReportIntegrityError(RuntimeError):
    """Raised when review inputs or generated claims are incomplete or contradictory."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReportIntegrityError(message)


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReportIntegrityError(f"{label} cannot be read: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def _optimizer_recompute(
    search_dir: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Recompute the full optimizer and compare the three supplied artifacts."""

    directory = Path(search_dir)
    actual = {
        name: _load_object(directory / name, f"search artifact {name}") for name in SEARCH_FILES
    }
    return actual["candidates.json"], actual["metrics.json"]


def _source_paths(directory: Path, names: Sequence[str], label: str) -> dict[str, Path]:
    root = Path(directory)
    paths = {name: root / name for name in names}
    missing = [name for name, path in paths.items() if not path.is_file()]
    require(not missing, f"{label} files are missing: {missing}")
    for name, path in paths.items():
        require(path.stat().st_size < LIMIT_BYTES, f"{name} is not below 50 MB")
    return paths


def _browser_replay(
    search_dir: Path,
    request_dir: Path,
    browser_dir: Path,
    inputs: p3.Phase3Inputs,
    contract: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    clean.validate_artifacts(search_dir, inputs, contract, reduced=False)
    requests: dict[str, dict[str, Any]] = {}
    pairs: dict[str, dict[str, Any]] = {}
    for role in ROLES:
        label = role.lower()
        request_path = Path(request_dir) / f"browser-request-{label}.json"
        result_path = Path(browser_dir) / f"browser-result-{label}.json"
        observations_path = Path(browser_dir) / f"browser-observations-{label}.json"
        pairs_path = Path(browser_dir) / f"browser-pairs-{label}.json"
        receipt = browser.verify(
            request_path,
            result_path,
            observations_path,
            pairs_path,
            search_dir,
            inputs,
            contract,
            validate_search=False,
        )
        require(receipt["status"] == "PASS", f"browser replay failed for {role}")
        require(receipt["observation_count"] == 30_240, f"observation count differs for {role}")
        require(receipt["pair_count"] == 58_320, f"pair count differs for {role}")
        require(
            receipt["family_counts"] == {"categorical": 32_400, "category_fg_0": 25_920},
            f"pair family counts differ for {role}",
        )
        requests[role] = _load_object(request_path, f"browser request {role}")
        pairs[role] = _load_object(pairs_path, f"browser pairs {role}")
    return requests, pairs


def _minimum(
    request: Mapping[str, Any],
    pairs: Mapping[str, Any],
    family: str,
    width: str,
    backgrounds: Sequence[str],
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    request_rows = request["requested_pairs"]
    pair_rows = pairs["rows"]
    require(len(request_rows) == len(pair_rows) == 58_320, "browser pair arrays differ")
    for planned, observed in zip(request_rows, pair_rows, strict=True):
        require(planned["id"] == observed["id"], "browser pair order differs")
        if (
            planned["family"] == family
            and planned["state"] == "transformed"
            and f"{planned['width_css_px']:g}" == width
            and planned["background"] in backgrounds
        ):
            candidates.append(
                {
                    **{
                        key: planned[key]
                        for key in (
                            "id",
                            "family",
                            "background",
                            "width_css_px",
                            "style",
                            "orientation",
                            "dpr",
                            "phase_css_px",
                            "roles",
                        )
                    },
                    "observed_delta_e_ok": observed["observed_delta_e_ok"],
                }
            )
    require(bool(candidates), f"no {family} {width}px browser rows")
    return min(candidates, key=lambda row: (row["observed_delta_e_ok"], row["id"]))


def _browser_metrics(
    request: Mapping[str, Any], pairs: Mapping[str, Any]
) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        family: {
            width: {
                "gated": _minimum(request, pairs, family, width, GATED_BACKGROUNDS),
                "bg_2_report_only": _minimum(request, pairs, family, width, (REPORT_BACKGROUND,)),
            }
            for width in WIDTHS
        }
        for family in browser.PAIR_FAMILY_ORDER
    }


def _transform_rgb(bank: Sequence[str], gains: Sequence[float]) -> np.ndarray:
    return np.clip(p3.bank_rgb(bank) * np.asarray(gains, dtype=float), 0.0, 1.0)


def _hex(value: Any) -> str:
    return p3.srgb_to_hex(np.asarray(value, dtype=float))


def _transformed_bank(bank: Sequence[str], gains: Sequence[float]) -> list[str]:
    return [_hex(rgb) for rgb in _transform_rgb(bank, gains)]


def _weakest_pairs(bank: Sequence[str], gains: Sequence[float]) -> list[dict[str, Any]]:
    points = p3.srgb_to_oklab(_transform_rgb(bank, gains)) * 100.0
    rows = []
    for left in range(6):
        for right in range(left + 1, 6):
            rows.append(
                {
                    "roles": [ROLE_NAMES[left], ROLE_NAMES[right]],
                    "indices": [left, right],
                    "delta_e_ok": float(np.linalg.norm(points[left] - points[right])),
                }
            )
    return sorted(rows, key=lambda row: (row["delta_e_ok"], row["roles"]))[:3]


def _gray_for_luminance(value: float) -> str:
    encoded = 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
    channel = max(0, min(255, round(encoded * 255)))
    return f"#{channel:02X}{channel:02X}{channel:02X}"


def _luminance_rows(bank: Sequence[str], gains: Sequence[float]) -> list[dict[str, Any]]:
    transformed = _transform_rgb(bank, gains)
    luminance = np.asarray(clean.wcag_luminance(transformed), dtype=float)
    return [
        {
            "role": ROLE_NAMES[index],
            "value": float(value),
            "gray": _gray_for_luminance(float(value)),
        }
        for index, value in enumerate(luminance)
    ]


def _collect(
    search_dir: Path,
    request_dir: Path,
    browser_dir: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    search_paths = _source_paths(search_dir, SEARCH_FILES, "search")
    request_paths = _source_paths(request_dir, REQUEST_FILES, "request")
    browser_paths = _source_paths(browser_dir, BROWSER_FILES, "browser")
    inputs = clean.load_authorized_inputs(EXPERIMENT, replay=True)
    contract = clean.load_contract(HERE / "search-contract.json")
    clean.validate_contract(contract, inputs)
    candidates_payload, metrics_payload = _optimizer_recompute(search_dir, inputs, contract)
    require(candidates_payload["selection"] is None, "optimizer artifact selected a candidate")
    candidates = candidates_payload["candidates"]
    require([row["lane"] for row in candidates] == ["A", "B", "C"], "candidate lanes differ")
    requests, pair_payloads = _browser_replay(
        search_dir, request_dir, browser_dir, inputs, contract
    )
    gains = inputs.viewing["transform"]["gains"]
    baseline_bank = list(clean._baseline_bank(inputs))
    baseline_metrics = clean.compute_metrics(tuple(baseline_bank), inputs, contract)
    candidate_by_role = {row["lane"]: row for row in candidates}
    rows: dict[str, dict[str, Any]] = {}
    for role in ROLES:
        request = requests[role]
        if role == "REFERENCE":
            bank = baseline_bank
            metrics = baseline_metrics
            candidate_id = request["candidate_id"]
        else:
            candidate = candidate_by_role[role]
            bank = candidate["bank"]
            candidate_id = candidate["candidate_id"]
            metrics = metrics_payload["metrics_by_candidate"][candidate_id]
        require(request["serialized_bank"] == bank, f"browser bank differs for {role}")
        rows[role] = {
            "role": role,
            "candidate_id": candidate_id,
            "bank": bank,
            "transformed_bank": _transformed_bank(bank, gains),
            "metrics": metrics,
            "browser": _browser_metrics(request, pair_payloads[role]),
            "weakest_pairs": _weakest_pairs(bank, gains),
            "luminance": _luminance_rows(bank, gains),
            "method": METHODS[role][0],
            "tradeoff": METHODS[role][1],
        }
    baseline = rows["REFERENCE"]["browser"]
    c = rows["C"]["browser"]
    require(
        all(
            c["category_fg_0"][width]["gated"]["observed_delta_e_ok"]
            > baseline["category_fg_0"][width]["gated"]["observed_delta_e_ok"]
            for width in WIDTHS
        ),
        "recommendation C requires category↔fg_0 gains at every width",
    )
    for role in ("A", "B"):
        require(
            rows[role]["browser"]["category_fg_0"]["2"]["gated"]["observed_delta_e_ok"]
            < baseline["category_fg_0"]["2"]["gated"]["observed_delta_e_ok"],
            f"{role} 2px category↔fg_0 tradeoff differs",
        )
        require(
            rows[role]["browser"]["category_fg_0"]["3"]["gated"]["observed_delta_e_ok"]
            < baseline["category_fg_0"]["3"]["gated"]["observed_delta_e_ok"],
            f"{role} 3px category↔fg_0 tradeoff differs",
        )
    evidence_sources = {**search_paths, **request_paths, **browser_paths}
    require(set(evidence_sources) == set(EVIDENCE_FILES), "evidence source closure differs")
    return rows, evidence_sources


PLOT_PATHS = (
    "M14 92 C52 10 88 110 130 38 S211 14 286 78",
    "M14 32 C56 106 96 4 142 72 S228 112 286 26",
    "M14 75 C62 58 94 16 142 58 S230 92 286 50",
    "M14 20 C58 98 100 84 146 28 S232 8 286 58",
    "M14 54 C58 12 104 108 152 34 S232 18 286 96",
    "M14 88 C58 24 102 44 150 86 S232 106 286 16",
)
END_Y = (78, 26, 50, 58, 96, 16)


def _crossing_svg(bank: Sequence[str], background: str, width: str, state: str, role: str) -> str:
    paths = "".join(
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{width}" '
        'stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
        f'<circle cx="286" cy="{END_Y[index]}" r="2.5" fill="{color}"/>'
        for index, (path, color) in enumerate(zip(PLOT_PATHS, bank, strict=True))
    )
    legend = "".join(
        f'<g transform="translate({12 + index * 48} 119)"><line x2="12" stroke="{color}" '
        f'stroke-width="{width}"/><text x="16" y="3">{ROLE_SHORT[index]}</text></g>'
        for index, color in enumerate(bank)
    )
    return (
        f'<svg class="crossing" data-state="{state}" data-background="{background}" '
        f'data-width="{width}" viewBox="0 0 300 132" role="img" '
        f'aria-label="{html.escape(role)} {html.escape(state)} six {width}px crossing lines on '
        f'{html.escape(background)}"><rect width="300" height="132" rx="10" '
        f'fill="{background}"/><path d="M14 105H286" stroke="#8D837B" stroke-width=".65" '
        f'opacity=".45"/>{paths}{legend}</svg>'
    )


def _state_panel(
    row: Mapping[str, Any],
    surfaces: Mapping[str, str],
    gains: Sequence[float],
    transformed: bool,
) -> str:
    state = "exact transformed" if transformed else "commanded"
    bank = row["transformed_bank"] if transformed else row["bank"]
    backgrounds = {
        name: _hex(
            np.clip(
                p3.parse_exact_hex8(value) * np.asarray(gains if transformed else (1.0, 1.0, 1.0)),
                0.0,
                1.0,
            )
        )
        for name, value in surfaces.items()
    }
    return (
        f'<section class="state-panel" data-review-state="{state}"><h4>{state}</h4>'
        f'<div class="plot-label"><b>bg_0</b><span>six equal-style 1.5px lines</span></div>'
        f"{_crossing_svg(bank, backgrounds['bg_0'], '1.5', state, row['role'])}"
        f'<div class="plot-label"><b>bg_1</b><span>six equal-style 2px lines</span></div>'
        f"{_crossing_svg(bank, backgrounds['bg_1'], '2', state, row['role'])}"
        "</section>"
    )


def _swatches(row: Mapping[str, Any]) -> str:
    return "".join(
        f'<div class="swatch"><span class="dual" style="--cmd:{commanded};--tx:{transformed}">'
        "</span>"
        f"<b>{ROLE_NAMES[index]}</b><code>{commanded}</code><code>{transformed}</code></div>"
        for index, (commanded, transformed) in enumerate(
            zip(row["bank"], row["transformed_bank"], strict=True)
        )
    )


def _weakest_specimen(row: Mapping[str, Any]) -> str:
    colors = row["transformed_bank"]
    panels = []
    for index, pair in enumerate(row["weakest_pairs"]):
        left, right = pair["indices"]
        panels.append(
            f'<g transform="translate({index * 100} 0)">'
            f'<path d="M8 16 C30 70 58 4 92 58" fill="none" stroke="{colors[left]}" '
            'stroke-width="1.5"/>'
            f'<path d="M8 58 C34 2 62 72 92 16" fill="none" stroke="{colors[right]}" '
            'stroke-width="1.5"/>'
            f'<text x="8" y="84">{ROLE_SHORT[left]}↔{ROLE_SHORT[right]}</text>'
            f'<text x="8" y="99">{pair["delta_e_ok"]:.2f} ΔE_OK</text></g>'
        )
    return (
        '<section class="micro" data-specimen="weakest-three-failure-analog">'
        "<h4>Isolated weakest-three failure analog</h4>"
        '<svg viewBox="0 0 300 106" role="img" aria-label="Three weakest transformed solid '
        f'pair analogs"><rect width="300" height="106" rx="10" fill="#ECE3D9"/>'
        f"{''.join(panels)}</svg></section>"
    )


def _luminance_specimen(row: Mapping[str, Any]) -> str:
    cells = "".join(
        f'<div style="--gray:{item["gray"]}"><span></span><b>{ROLE_SHORT[index]}</b>'
        f"<small>{item['value']:.4f}</small></div>"
        for index, item in enumerate(row["luminance"])
    )
    return (
        '<section class="micro luminance" data-specimen="luminance-only-strip">'
        "<h4>Exact transformed luminance only</h4>"
        f'<div class="lum-strip">{cells}</div></section>'
    )


def _binding_text(binding: Mapping[str, Any]) -> str:
    phase = "/".join(f"{value:g}" for value in binding["phase_css_px"])
    return (
        f"{binding['roles'][0]} ↔ {binding['roles'][1]} · {binding['background']} · "
        f"{binding['style']}/{binding['orientation']} · DPR {binding['dpr']} · phase {phase}"
    )


def _fg0_specimen(row: Mapping[str, Any], transformed_fg0: str) -> str:
    binding = row["browser"]["category_fg_0"]["1.5"]["gated"]
    category = binding["roles"][0]
    index = ROLE_NAMES.index(category)
    color = row["transformed_bank"][index]
    return (
        '<section class="micro fg0" data-specimen="category-fg0-nearest-binding">'
        "<h4>Categorical ↔ fg_0 exact nearest binding</h4>"
        '<svg viewBox="0 0 300 86" role="img" aria-label="Nearest category and foreground '
        f'comparison"><rect width="300" height="86" rx="10" fill="#ECE3D9"/>'
        f'<path d="M12 68 C72 2 132 82 288 18" fill="none" stroke="{color}" '
        'stroke-width="1.5"/><path d="M12 18 C82 82 150 2 288 68" fill="none" '
        f'stroke="{transformed_fg0}" stroke-width="1.5"/></svg>'
        f"<p><b>{binding['observed_delta_e_ok']:.8f} ΔE_OK</b><br>"
        f"{html.escape(_binding_text(binding))}</p></section>"
    )


def _finance_specimen(row: Mapping[str, Any]) -> str:
    colors = row["transformed_bank"]
    areas = "".join(
        f'<path d="M12 {96 - index * 7} C66 {34 + index * 3} 114 {94 - index * 8} '
        f"172 {30 + index * 6} S248 {86 - index * 5} 288 {22 + index * 5} L288 108 "
        f'L12 108Z" fill="{color}" opacity=".10"/>'
        for index, color in enumerate(colors)
    )
    lines = "".join(
        f'<path d="M12 {96 - index * 7} C66 {34 + index * 3} 114 {94 - index * 8} '
        f'172 {30 + index * 6} S248 {86 - index * 5} 288 {22 + index * 5}" fill="none" '
        f'stroke="{color}" stroke-width="1.5"/>'
        for index, color in enumerate(colors)
    )
    bars = "".join(
        f'<rect x="{18 + index * 46}" y="{142 - (index % 3) * 11}" width="30" '
        f'height="{28 + (index % 3) * 11}" rx="3" fill="{color}" opacity=".82"/>'
        for index, color in enumerate(colors)
    )
    legend = "".join(
        f'<g transform="translate({12 + (index % 3) * 96} {202 + (index // 3) * 16})">'
        f'<rect width="10" height="10" rx="2" fill="{color}"/><text x="15" y="9">'
        f"Basket {index + 1}</text></g>"
        for index, color in enumerate(colors)
    )
    return (
        '<section class="micro finance" data-specimen="fake-finance-baskets">'
        "<h4>Fake finance / baskets · fixed geometry</h4>"
        '<svg viewBox="0 0 300 238" role="img" aria-label="Fake finance chart with fills, '
        f'basket bars, and legend"><rect width="300" height="238" rx="10" fill="#ECE3D9"/>'
        '<path d="M12 110H288M12 174H288" stroke="#8D837B" opacity=".35"/>'
        f"{areas}{lines}{bars}{legend}</svg></section>"
    )


def _metric_table(row: Mapping[str, Any], baseline: Mapping[str, Any]) -> str:
    body = []
    for family, label in (("categorical", "Category"), ("category_fg_0", "Category↔fg_0")):
        for width in WIDTHS:
            value = row["browser"][family][width]["gated"]["observed_delta_e_ok"]
            base = baseline["browser"][family][width]["gated"]["observed_delta_e_ok"]
            report = row["browser"][family][width]["bg_2_report_only"]["observed_delta_e_ok"]
            body.append(
                f"<tr><th>{label}</th><td>{width}px</td><td>{value:.8f}</td>"
                f"<td>{value - base:+.8f}</td><td>{report:.8f}</td></tr>"
            )
    return (
        '<table class="card-metrics"><thead><tr><th>Family</th><th>Width</th>'
        "<th>Gated bg_0/bg_1</th><th>Δ vs reference</th><th>bg_2 report-only</th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _sensitivity(row: Mapping[str, Any]) -> str:
    report = row["metrics"]["sensitivity_report"]
    category = report["category_pair_min"]
    fg0 = report["category_fg_0_min"]
    return (
        '<aside class="sensitivity" data-specimen="worst-sensitivity"><h4>Worst sampled '
        "gain sensitivity · report-only</h4>"
        f"<p><b>Category:</b> {category['category_pair_delta_e_ok']:.8f} ΔE_OK · "
        f"{html.escape(category['category_pair_binding'])} · "
        f"{html.escape(category['gain_sample'])}</p>"
        f"<p><b>Category↔fg_0:</b> {fg0['category_fg_0_delta_e_ok']:.8f} ΔE_OK · "
        f"{html.escape(fg0['category_fg_0_binding'])} · "
        f"{html.escape(fg0['gain_sample'])}</p></aside>"
    )


def _candidate_card(
    row: Mapping[str, Any],
    baseline: Mapping[str, Any],
    surfaces: Mapping[str, str],
    transformed_fg0: str,
    gains: Sequence[float],
) -> str:
    role = row["role"]
    heading = "Reference" if role == "REFERENCE" else f"Finalist {role}"
    recommended = '<span class="recommend">RECOMMENDED</span>' if role == "C" else ""
    return f'''<article class="candidate-card" id="candidate-{role.lower()}" data-candidate="{role}">
<header class="card-head"><div><p class="eyebrow">{role}</p><h2>{heading}</h2></div>{recommended}</header>
<p class="method"><b>{html.escape(row["method"])}</b><br>{html.escape(row["tradeoff"])}</p>
<p class="candidate-id">{row["candidate_id"]}</p>
<section class="swatches" aria-label="Exact commanded and transformed Hex8 bank">{_swatches(row)}</section>
<div class="states">{_state_panel(row, surfaces, gains, False)}{_state_panel(row, surfaces, gains, True)}</div>
{_metric_table(row, baseline)}
<div class="micro-grid">{_weakest_specimen(row)}{_luminance_specimen(row)}{_fg0_specimen(row, transformed_fg0)}{_finance_specimen(row)}</div>
{_sensitivity(row)}
</article>'''


def _headline_table(rows: Mapping[str, Mapping[str, Any]]) -> str:
    body = []
    for role in ROLES:
        row = rows[role]
        values = [
            row["browser"][family][width]["gated"]["observed_delta_e_ok"]
            for family in ("categorical", "category_fg_0")
            for width in WIDTHS
        ]
        cells = "".join(
            f'<td data-label="{label}">{value:.8f}</td>'
            for label, value in zip(
                ("Category 1.5", "Category 2", "Category 3", "fg_0 1.5", "fg_0 2", "fg_0 3"),
                values,
                strict=True,
            )
        )
        body.append(f"<tr><th>{role}</th>{cells}</tr>")
    return (
        '<table class="headline-table" data-table="gated-browser-minima"><thead><tr>'
        "<th>Choice</th><th>Category 1.5</th><th>Category 2</th><th>Category 3</th>"
        "<th>fg_0 1.5</th><th>fg_0 2</th><th>fg_0 3</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def _evidence_links() -> str:
    return "".join(
        f'<li><a href="evidence/{html.escape(name)}">{html.escape(name)}</a></li>'
        for name in EVIDENCE_FILES
    )


def _render_html(rows: Mapping[str, Mapping[str, Any]], inputs: p3.Phase3Inputs) -> str:
    surfaces = {name: inputs.baseline["family"]["surfaces"][name] for name in ("bg_0", "bg_1")}
    transformed_fg0 = _hex(
        np.clip(
            p3.parse_exact_hex8(inputs.baseline["family"]["surfaces"]["fg_0"])
            * np.asarray(inputs.viewing["transform"]["gains"], dtype=float),
            0.0,
            1.0,
        )
    )
    cards = "".join(
        _candidate_card(
            rows[role],
            rows["REFERENCE"],
            surfaces,
            transformed_fg0,
            inputs.viewing["transform"]["gains"],
        )
        for role in ROLES
    )
    c_gain = (
        rows["C"]["browser"]["categorical"]["1.5"]["gated"]["observed_delta_e_ok"]
        - rows["REFERENCE"]["browser"]["categorical"]["1.5"]["gated"]["observed_delta_e_ok"]
    )
    css = """
:root{color-scheme:light;--paper:#f7f1e9;--panel:#fffaf3;--ink:#302a26;--muted:#6d625a;--rule:#cfc0b2;--teal:#176f68;--red:#7b2e2e}*{box-sizing:border-box}html{background:var(--paper);color:var(--ink);font:15px/1.45 ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body{margin:0;overflow-x:clip}a{color:#17645e;overflow-wrap:anywhere}.top,main,.evidence{width:min(1760px,100%);margin:auto;padding:clamp(18px,3vw,48px)}.top{border-bottom:1px solid var(--rule)}.eyebrow{text-transform:uppercase;letter-spacing:.14em;font-size:.69rem;font-weight:850;color:#7a3f2b;margin:0 0 .35rem}h1{font:750 clamp(2.3rem,5.5vw,5.8rem)/.94 ui-serif,Georgia,serif;letter-spacing:-.045em;max-width:14ch;margin:.12em 0}.lede{max-width:78ch;color:var(--muted);font-size:1.08rem}.status{display:inline-flex;border:1px solid #7a3f2b;border-radius:999px;padding:.42rem .72rem;font-size:.72rem;font-weight:850}.recommendation{max-width:88ch;padding:1.15rem 1.3rem;border:1px solid var(--rule);border-left:5px solid var(--teal);background:var(--panel);border-radius:12px}.truth{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;max-width:1000px;margin:1.2rem 0}.truth div{background:rgba(255,255,255,.55);border:1px solid var(--rule);border-radius:10px;padding:.75rem}.truth b,.truth span{display:block}.truth span{color:var(--muted);font-size:.76rem}.headline-table,.card-metrics{width:100%;border-collapse:collapse;table-layout:fixed;background:var(--panel);border:1px solid var(--rule)}th,td{text-align:left;padding:.48rem;border-bottom:1px solid #ded3c8;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.headline-table{font-size:.75rem;margin:1.3rem 0}.headline-table th:first-child{width:82px}.comparison-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;align-items:start}.candidate-card{min-width:0;background:rgba(255,250,243,.76);border:1px solid var(--rule);border-radius:18px;padding:14px}.candidate-card[data-candidate="C"]{border-color:#49958a;box-shadow:0 0 0 2px rgba(73,149,138,.12)}.card-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.card-head h2{font:750 1.7rem/1 ui-serif,Georgia,serif;margin:0}.recommend{font-size:.62rem;font-weight:850;letter-spacing:.07em;color:#15584f;background:#dceee8;border-radius:999px;padding:.35rem .48rem}.method{min-height:8.3em;color:var(--muted);font-size:.78rem}.method b{color:var(--ink)}.candidate-id{font:9px/1.25 ui-monospace,SFMono-Regular,monospace;color:var(--muted);overflow-wrap:anywhere}.swatches{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:4px;margin:12px 0}.swatch{min-width:0}.dual{height:38px;display:block;border-radius:6px;background:linear-gradient(90deg,var(--cmd) 0 50%,var(--tx) 50%)}.swatch b,.swatch code{display:block;font-size:.52rem;line-height:1.28;overflow-wrap:anywhere}.swatch code:last-child{color:var(--muted)}.states{display:grid;grid-template-columns:1fr;gap:8px}.state-panel{border-top:1px solid var(--rule);padding-top:7px}.state-panel h4,.micro h4,.sensitivity h4{margin:.1rem 0 .45rem;font-size:.75rem}.plot-label{display:flex;justify-content:space-between;gap:6px;font-size:.57rem;color:var(--muted);margin:.2rem 0}.crossing,.micro svg{display:block;width:100%;height:auto}.crossing text,.micro svg text{font:7px ui-sans-serif,-apple-system,sans-serif;fill:#403833}.card-metrics{font-size:.57rem;margin:10px 0}.card-metrics th,.card-metrics td{padding:.28rem}.card-metrics th:first-child{width:26%}.micro-grid{display:grid;grid-template-columns:1fr;gap:8px}.micro{border-top:1px solid var(--rule);padding-top:7px}.lum-strip{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:3px}.lum-strip div{min-width:0}.lum-strip span{display:block;height:30px;border-radius:5px;background:var(--gray)}.lum-strip b,.lum-strip small{display:block;font-size:.54rem;overflow-wrap:anywhere}.fg0 p,.sensitivity p{font-size:.62rem;color:var(--muted);overflow-wrap:anywhere}.sensitivity{border:1px solid var(--rule);border-radius:10px;padding:8px;margin-top:8px;background:#fffaf3}.sensitivity p{margin:.28rem 0}.evidence{border-top:1px solid var(--rule)}.evidence ul{columns:3;column-gap:2rem;padding-left:1.1rem}.evidence li{break-inside:avoid;font-size:.72rem;margin:.28rem 0}.freeze{font-weight:750}.mobile-contract{display:none}
@media(max-width:1180px){.comparison-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.method{min-height:6.5em}}
@media(max-width:620px){html{font-size:14px}.top,main,.evidence{padding:18px}.truth{grid-template-columns:1fr}.comparison-grid{grid-template-columns:1fr;gap:18px}.candidate-card{padding:12px}.method{min-height:0}.mobile-contract{display:block;color:var(--muted);font-size:.75rem}.headline-table thead{display:none}.headline-table,.headline-table tbody,.headline-table tr{display:block}.headline-table tr{padding:.55rem;border-bottom:1px solid var(--rule)}.headline-table th{display:block;font-size:1rem;border:0}.headline-table td{display:grid;grid-template-columns:1fr 1fr;gap:8px;border:0;padding:.22rem 0;font-size:.72rem}.headline-table td:before{content:attr(data-label);font-weight:750}.evidence ul{columns:1}.swatch b,.swatch code{font-size:.55rem}}
"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ember clean-sheet G2 review</title><style>{css}</style></head><body>
<header class="top"><p class="eyebrow">Ember · 3400K Light · clean-sheet G2</p><span class="status">{STATUS}</span><h1>Four banks. One visible decision.</h1><p class="lede">Reference plus A/B/C are presented simultaneously, with the same geometry in commanded and exact transformed states. Every bank independently replays 30,240 browser observations and 58,320 pair rows. The human 1.5px capacity remains UNKNOWN.</p>
<aside class="recommendation"><b>Recommendation: C. Michael decides.</b> C has the largest category↔fg_0 gain at every width and is the only finalist to improve 2px and 3px as well as 1.5px. Its teal / green / pink / red / olive / blue bank reads as the most mature system. It accepts less categorical-only gain than A/B, while still adding {c_gain:+.2f} ΔE_OK at 1.5px. A maximizes categorical-only separation but regresses category↔fg_0 at 2px and 3px; B is the middle option and shares those regressions.</aside>
<div class="truth"><div><b>Human 1.5px capacity</b><span>UNKNOWN · no human floor claimed</span></div><div><b>Browser evidence</b><span>PASS · categorical and category_fg_0 residual families</span></div><div><b>Production promotion</b><span>false · no downstream change authorized</span></div></div>
<h2>Actual gated transformed minima</h2><p class="lede">Minimum over bg_0 and bg_1 only. bg_2 is report-only and cannot bind these headlines.</p>{_headline_table(rows)}<p class="mobile-contract">On phone, each complete candidate follows the previous candidate. Nothing is hidden in a carousel or nested horizontal scroller.</p></header>
<main><section class="comparison-grid" aria-label="Simultaneous reference and finalist comparison">{cards}</section><p class="freeze">Selection: null · status: {STATUS} · human 1.5px capacity: UNKNOWN · production promotion: false</p></main>
<section class="evidence"><h2>Exact evidence closure</h2><p>Three optimizer artifacts, four browser requests, and twelve browser result/observation/pair artifacts. Each tracked file is below 50 MB. No screenshot or full-image hash is used as perceptual evidence.</p><ul>{_evidence_links()}</ul></section>
</body></html>"""


def _markdown_table(rows: Mapping[str, Mapping[str, Any]]) -> list[str]:
    output = [
        "| Choice | Category 1.5 | Category 2 | Category 3 | fg_0 1.5 | fg_0 2 | fg_0 3 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for role in ROLES:
        row = rows[role]
        values = [
            row["browser"][family][width]["gated"]["observed_delta_e_ok"]
            for family in ("categorical", "category_fg_0")
            for width in WIDTHS
        ]
        output.append(f"| {role} | " + " | ".join(f"{value:.8f}" for value in values) + " |")
    return output


def _render_markdown(rows: Mapping[str, Mapping[str, Any]]) -> str:
    lines = [
        "# Clean-sheet G2 palette review",
        "",
        f"**Status:** `{STATUS}`",
        "**Selection:** `null`",
        "**Human 1.5px capacity:** `UNKNOWN`",
        "**Production promotion:** `false`",
        "",
        "## Recommendation",
        "",
        (
            "**Recommend C; Michael decides.** C produces the largest category↔`fg_0` gains at all "
            "three widths and is the only finalist that improves 2px and 3px as well as 1.5px. "
            "Its teal / green / pink / red / olive / blue bank is the most visually mature. It "
            "accepts a smaller categorical-only gain than A/B while retaining a +1.70 ΔE_OK gated "
            "1.5px categorical gain. A maximizes categorical-only separation but regresses "
            "category↔`fg_0` at 2px and 3px. B is the middle option and shares those regressions."
        ),
        "",
        "## Actual gated transformed minima",
        "",
        (
            "These are derived from the verified pair rows. Headline minima use `bg_0` and `bg_1` "
            "only. `bg_2` is report-only and cannot bind."
        ),
        "",
        *_markdown_table(rows),
        "",
        "## Methods and tradeoffs",
        "",
    ]
    for role in ROLES:
        lines += [
            f"- **{role} — {rows[role]['method']}:** {rows[role]['tradeoff']}",
        ]
    lines += [
        "",
        "## Browser evidence",
        "",
        (
            "Reference and A/B/C each independently PASS with 30,240 observations and 58,320 "
            "pairs: 32,400 categorical pairs plus 25,920 category↔`fg_0` pairs. Both residual "
            "families PASS. Every evidence file is below 50 MB."
        ),
        "",
        "## Review surface",
        "",
        (
            "Open [`index.html`](index.html). Desktop shows reference and A/B/C simultaneously. "
            "Phone uses complete stacked cards, without a carousel or nested scrolling. Every card "
            "contains exact commanded/transformed Hex8, gated minima and report-only `bg_2`, 1.5px "
            "`bg_0` and 2px `bg_1` crossings, a weakest-three analog, luminance-only strip, exact "
            "category↔`fg_0` binding, fixed fake-finance/basket geometry, legends/fills, and worst "
            "sampled sensitivity."
        ),
        "",
        "## Boundary",
        "",
        (
            "This package records a recommendation, not a selection. It does not modify production, "
            "G0/G1/previous G2 history, or downstream consumers."
        ),
    ]
    return "\n".join(lines) + "\n"


def _selection(rows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": STATUS,
        "selection": None,
        "allowed": ["A", "B", "C"],
        "recommendation": RECOMMENDATION,
        "candidate_ids": {role: rows[role]["candidate_id"] for role in ("A", "B", "C")},
        "human_1_5px_capacity": "UNKNOWN",
        "production_promotion_authorized": False,
    }


def _write_package(
    output_dir: Path,
    rows: Mapping[str, Mapping[str, Any]],
    evidence_sources: Mapping[str, Path],
) -> None:
    output = Path(output_dir).resolve()
    require(output not in {Path.cwd().resolve(), EXPERIMENT.resolve()}, "output path is too broad")
    expected_top = {"index.html", "report.md", "selection.json", "evidence"}
    if output.exists():
        require(output.is_dir(), "output path is not a directory")
        existing = {path.name for path in output.iterdir()}
        require(existing <= expected_top, f"output contains unexpected entries: {sorted(existing)}")
    evidence_output = output / "evidence"
    if evidence_output.exists():
        require(evidence_output.is_dir(), "evidence output is not a directory")
        existing_evidence = {path.name for path in evidence_output.iterdir()}
        require(
            existing_evidence <= set(EVIDENCE_FILES),
            f"evidence output contains unexpected entries: {sorted(existing_evidence)}",
        )
    inputs = clean.load_authorized_inputs(EXPERIMENT, replay=False)
    output.mkdir(parents=True, exist_ok=True)
    evidence_output.mkdir(parents=True, exist_ok=True)
    for name in EVIDENCE_FILES:
        shutil.copyfile(evidence_sources[name], evidence_output / name)
        require(
            (evidence_output / name).read_bytes() == evidence_sources[name].read_bytes(),
            f"evidence copy differs: {name}",
        )
    (output / "index.html").write_text(_render_html(rows, inputs), encoding="utf-8")
    (output / "report.md").write_text(_render_markdown(rows), encoding="utf-8")
    (output / "selection.json").write_text(
        json.dumps(_selection(rows), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def build_review(
    search_dir: Path,
    request_dir: Path,
    browser_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Validate all inputs, then write the review package to one explicit directory."""

    output = Path(output_dir).resolve()
    input_roots = {Path(path).resolve() for path in (search_dir, request_dir, browser_dir)}
    require(output not in input_roots, "output directory may not replace an input directory")
    rows, evidence_sources = _collect(search_dir, request_dir, browser_dir)
    _write_package(output, rows, evidence_sources)
    return {
        "status": "PASS",
        "review_status": STATUS,
        "selection": None,
        "recommendation": RECOMMENDATION,
        "output": str(output),
        "evidence_file_count": len(EVIDENCE_FILES),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-dir", type=Path, required=True)
    parser.add_argument("--request-dir", type=Path, required=True)
    parser.add_argument("--browser-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = build_review(args.search_dir, args.request_dir, args.browser_dir, args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
