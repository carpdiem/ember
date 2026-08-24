#!/usr/bin/env python3
"""Capture and calibrate the G1 thin-mark ledger with real Chromium raster pixels.

The release oracle is a GStack screenshot of eager same-origin ``srcdoc`` iframes.
Each iframe rasterizes one exact 160x128 SVG tile at local origin. Monochrome masks
factor geometry/coverage from role-colour observations; those facts reconstruct all
32,400 canonical planned pair rows without treating canvas or inline atlases as an
oracle.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import itertools
import json
import math
import os
import re
import statistics
import subprocess
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
APPROVED_HEAD = "922ba7faa45ccdb56e95356750d353c7602da78a"
TILE_WIDTH = 160
TILE_HEIGHT = 128
ATLAS_COLUMNS = 8
CHUNK_TILES = 128
DEFAULT_STANDALONE_SENTINELS = 48
MAX_STANDALONE_SENTINELS = 21_600
GAINS = np.array([1.0, 0.74, 0.53], dtype=float)
PATHS = {
    "horizontal": "M16 64 L144 64",
    "vertical": "M80 16 L80 112",
    "diagonal_45": "M24 104 L120 8",
    "shallow_1_2": "M16 88 L144 40",
    "curved": "M16 96 C48 18 108 116 144 28",
}
ROLE_LANES = (
    ("cat.one", 0),
    ("cat.two", 0),
    ("cat.two", 1),
    ("cat.three", 0),
    ("cat.three", 1),
    ("cat.four", 0),
    ("cat.four", 1),
    ("cat.five", 0),
    ("cat.five", 1),
    ("cat.six", 1),
)
BASE_FIELDS = (
    "state",
    "background",
    "width_css_px",
    "style",
    "orientation",
    "dpr",
    "phase_css_px",
)


def _browse_binary() -> Path | None:
    explicit = os.environ.get("GSTACK_BROWSE")
    if explicit is not None:
        candidate = Path(explicit).expanduser()
        return candidate if candidate.is_file() and os.access(candidate, os.X_OK) else None
    candidates = (
        ROOT / ".hermes/skills/gstack/browse/dist/browse",
        Path.home() / ".hermes/skills/gstack/browse/dist/browse",
    )
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.is_file() and os.access(candidate, os.X_OK)
        ),
        None,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _run(
    arguments: list[str],
    *,
    cwd: Path,
    stdin: str | None = None,
    timeout: int = 240,
) -> str:
    completed = subprocess.run(
        arguments,
        cwd=cwd,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"command exited {completed.returncode}" + (f": {detail}" if detail else "")
        )
    return completed.stdout.strip()


def _browse(browse: Path, cwd: Path, *arguments: str, timeout: int = 240) -> str:
    return _run([str(browse), *arguments], cwd=cwd, timeout=timeout)


def _parse_jsonish(text: str) -> Any:
    candidates = [text.strip()]
    for opening, closing in (("{", "}"), ("[", "]")):
        first, last = text.find(opening), text.rfind(closing)
        if first >= 0 and last > first:
            candidates.append(text[first : last + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            return json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError:
            continue
    raise RuntimeError("browser returned invalid JSON")


def _sanitize_status(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"\s*(Status|Mode):\s*([A-Za-z0-9_-]+)\s*", line)
        if match:
            result[match.group(1).lower()] = match.group(2).lower()
    return result or {"status": "responded", "mode": "unreported"}


def _rgb(value: str) -> np.ndarray:
    value = value.removeprefix("#")
    return np.array([int(value[index : index + 2], 16) for index in (0, 2, 4)]) / 255.0


def _oklab(values: np.ndarray) -> np.ndarray:
    encoded = np.asarray(values, dtype=float)
    linear = np.where(
        encoded <= 0.04045,
        encoded / 12.92,
        ((encoded + 0.055) / 1.055) ** 2.4,
    )
    first = np.array(
        [
            [0.4122214708, 0.5363325363, 0.0514459929],
            [0.2119034982, 0.6806995451, 0.1073969566],
            [0.0883024619, 0.2817188376, 0.6299787005],
        ]
    )
    second = np.array(
        [
            [0.2104542553, 0.7936177850, -0.0040720468],
            [1.9779984951, -2.428592205, 0.4505937099],
            [0.0259040371, 0.7827717662, -0.808675766],
        ]
    )
    return np.cbrt(linear @ first.T) @ second.T


def _correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 2 or statistics.pstdev(left) == 0 or statistics.pstdev(right) == 0:
        return 1.0 if left == right else 0.0
    return float(np.corrcoef(np.asarray(left), np.asarray(right))[0, 1])


def _base_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        tuple(row[field]) if field == "phase_css_px" else row[field] for field in BASE_FIELDS
    )


def _mask_key(base: tuple[Any, ...], lane: int) -> tuple[Any, ...]:
    _, _, width, style, orientation, dpr, phase = base
    return width, style, orientation, dpr, phase, lane


def _expected_planned_rows(contract: dict[str, Any]) -> list[dict[str, Any]]:
    pairs = list(itertools.combinations(contract["category_order"], 2))
    rows = []
    dimensions = itertools.product(
        contract["state_order"],
        contract["background_order"],
        contract["widths_css_px"],
        contract["style_order"],
        contract["orientations"],
        contract["device_pixel_ratios"],
        contract["phases_css_px"],
        pairs,
    )
    for index, (state, background, width, style, orientation, dpr, phase, pair) in enumerate(
        dimensions, start=1
    ):
        rows.append(
            {
                "id": f"planned-{index:05d}",
                "state": state,
                "background": background,
                "background_policy": "gate" if background in ("bg_0", "bg_1") else "report-only",
                "width_css_px": width,
                "style": style,
                "orientation": orientation,
                "dpr": dpr,
                "phase_css_px": list(phase),
                "roles": [f"cat.{pair[0]}", f"cat.{pair[1]}"],
            }
        )
    return rows


def _validate_ledger(raster: dict[str, Any]) -> list[dict[str, Any]]:
    expected = _expected_planned_rows(raster["specimen_contract"])
    if len(raster["matrix"]) != len(expected) or len(expected) != 32_400:
        raise RuntimeError("approved ledger cardinality is not exactly 32,400")
    for actual, planned in zip(raster["matrix"], expected, strict=True):
        projection = {key: actual[key] for key in planned}
        if projection != planned:
            raise RuntimeError(f"approved ledger mapping mismatch at {planned['id']}")
    return expected


def _geometry_metadata(browse: Path, workspace: Path) -> dict[str, Any]:
    path = workspace / "geometry.html"
    svg_paths = "".join(f'<path id="p-{name}" d="{data}"/>' for name, data in PATHS.items())
    path.write_text(
        f"""<!doctype html><meta charset=utf-8><style>html,body{{margin:0}}</style>
<svg width=160 height=128 xmlns="http://www.w3.org/2000/svg">{svg_paths}</svg>
<script>
const styles={{solid:null,dashed:[8,5],dotted:[1,5]}};
function stations(style,total,width,dpr){{
 const margin=Math.max(2,width), intervals=[];
 if(style==='solid') intervals.push([margin,total-margin]);
 else {{const pattern=styles[style],period=pattern[0]+pattern[1];
  for(let base=0;base<total;base+=period){{let a=Math.max(base,margin),b=Math.min(base+pattern[0],total-margin);const trim=Math.min(1,Math.max(0,b-a)*.25);if(b-a>2*trim)intervals.push([a+trim,b-trim]);}}
 }}
 const step=1/dpr, values=[];
 for(const [a,b] of intervals){{values.push((a+b)/2);for(let s=Math.ceil((a-1e-9)/step)*step;s<=b+1e-9;s+=step)values.push(s);}}
 return [...new Set(values.map(x=>Number(x.toFixed(6))))].sort((a,b)=>a-b);
}}
const meta={{}};
for(const name of {json.dumps(list(PATHS))}){{const p=document.getElementById('p-'+name),total=p.getTotalLength(),all={{}};
 for(const width of [1.5,2,3])for(const style of ['solid','dashed','dotted'])for(const dpr of [1,2]){{const rows=[];
  for(const s of stations(style,total,width,dpr)){{const q=p.getPointAtLength(s),a=p.getPointAtLength(Math.max(0,s-.01)),b=p.getPointAtLength(Math.min(total,s+.01)),n=Math.hypot(b.x-a.x,b.y-a.y)||1;rows.push({{s,x:q.x,y:q.y,tx:(b.x-a.x)/n,ty:(b.y-a.y)/n}});}}
  all[`${{width}}|${{style}}|${{dpr}}`]=rows;
 }}meta[name]={{total_length:total,stations:all}};
}}window.__g1Geometry=meta;
</script>""",
        encoding="utf-8",
    )
    _browse(browse, workspace, "viewport", "320x200", "--scale", "1")
    _browse(browse, workspace, "goto", path.as_uri())
    return _parse_jsonish(_browse(browse, workspace, "js", "JSON.stringify(window.__g1Geometry)"))


def _tile_svg(tile: dict[str, Any], index: int, baseline: dict[str, Any]) -> str:
    base = tuple(
        tuple(value) if position == 6 else value for position, value in enumerate(tile["base"])
    )
    state, background, width, style_name, orientation, _, phase = base
    style = baseline["contract"]["styles"][style_name]
    dash = (
        ""
        if style["dasharray"] is None
        else f' stroke-dasharray="{" ".join(map(str, style["dasharray"]))}"'
    )
    lane = tile["lane"]
    common = (
        f'd="{PATHS[orientation]}" fill="none" stroke-width="{width}" '
        f'stroke-linecap="{style["linecap"]}" stroke-dashoffset="{style["dashoffset"]}" '
        f'transform="translate({phase[0]} {phase[1] + lane * 8})"{dash}'
    )
    if tile["kind"] == "mask":
        body = f'<rect width="160" height="128" fill="#fff"/><path {common} stroke="#000"/>'
    else:
        role_name = tile["role"].split(".", 1)[1]
        definitions = ""
        filter_attribute = ""
        if state == "transformed":
            filter_id = f"warm-{index}"
            definitions = (
                f'<defs><filter id="{filter_id}" x="0" y="0" width="100%" height="100%" '
                'color-interpolation-filters="sRGB"><feColorMatrix type="matrix" '
                'values="1 0 0 0 0 0 .74 0 0 0 0 0 .53 0 0 0 0 0 1 0"/></filter></defs>'
            )
            filter_attribute = f' filter="url(#{filter_id})"'
        body = (
            f"{definitions}<g{filter_attribute}>"
            f'<rect width="160" height="128" fill="{baseline["surfaces"][background]}"/>'
            f'<path {common} stroke="{baseline["categorical"][role_name]}"/></g>'
        )
    return (
        f'<svg data-tile="{index}" width="160" height="128" viewBox="0 0 160 128" '
        f'xmlns="http://www.w3.org/2000/svg">{body}</svg>'
    )


def _write_atlas(path: Path, tiles: list[dict[str, Any]], baseline: dict[str, Any]) -> None:
    frames = []
    for index, tile in enumerate(tiles):
        source = "<!doctype html><style>html,body{margin:0}</style>" + _tile_svg(
            tile, index, baseline
        )
        frames.append(
            f'<iframe loading="eager" srcdoc="{html.escape(source, quote=True)}"></iframe>'
        )
    path.write_text(
        "<!doctype html><meta charset=utf-8>"
        f"<style>*{{box-sizing:border-box}}html,body{{margin:0;background:#fff}}#atlas{{display:grid;grid-template-columns:repeat({ATLAS_COLUMNS},{TILE_WIDTH}px);width:{ATLAS_COLUMNS * TILE_WIDTH}px}}iframe{{display:block;border:0;width:{TILE_WIDTH}px;height:{TILE_HEIGHT}px}}</style>"
        f'<div id="atlas">{"".join(frames)}</div>',
        encoding="utf-8",
    )


def _render_tiles(
    browse: Path,
    workspace: Path,
    kind: str,
    dpr: int,
    tiles: list[dict[str, Any]],
    baseline: dict[str, Any],
) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    images: dict[str, np.ndarray] = {}
    elapsed = 0.0
    _browse(
        browse,
        workspace,
        "viewport",
        f"{ATLAS_COLUMNS * TILE_WIDTH}x720",
        "--scale",
        str(dpr),
    )
    for start in range(0, len(tiles), CHUNK_TILES):
        chunk = tiles[start : start + CHUNK_TILES]
        stem = f"{kind}-dpr{dpr}-{start // CHUNK_TILES:03d}"
        html_path, png_path = workspace / f"{stem}.html", workspace / f"{stem}.png"
        _write_atlas(html_path, chunk, baseline)
        commands = json.dumps(
            [["goto", html_path.as_uri()], ["screenshot", str(png_path), "--selector", "#atlas"]]
        )
        began = time.perf_counter()
        _run([str(browse), "chain"], cwd=workspace, stdin=commands)
        elapsed += time.perf_counter() - began
        with Image.open(png_path) as opened:
            image = np.asarray(opened.convert("RGB"), dtype=np.uint8)
        expected_rows = math.ceil(len(chunk) / ATLAS_COLUMNS)
        expected_size = (
            expected_rows * TILE_HEIGHT * dpr,
            ATLAS_COLUMNS * TILE_WIDTH * dpr,
            3,
        )
        if image.shape != expected_size:
            raise RuntimeError(f"wrong screenshot dimensions for {stem}: {image.shape}")
        for index, tile in enumerate(chunk):
            row, column = divmod(index, ATLAS_COLUMNS)
            images[tile["id"]] = image[
                row * TILE_HEIGHT * dpr : (row + 1) * TILE_HEIGHT * dpr,
                column * TILE_WIDTH * dpr : (column + 1) * TILE_WIDTH * dpr,
            ].copy()
        png_path.unlink()
        html_path.unlink()
    return images, {
        "tiles": len(tiles),
        "chunks": math.ceil(len(tiles) / CHUNK_TILES),
        "browser_seconds": elapsed,
    }


def select_line_core(
    mask: np.ndarray,
    station_rows: list[dict[str, float]],
    width: float,
    dpr: int,
    phase: tuple[float, float],
    lane: int,
) -> list[list[float | int]]:
    """Select exact max-coverage line-core pixels using mask darkness as coverage."""

    coverage = 1.0 - mask.astype(float).mean(axis=2) / 255.0
    selected: list[list[float | int]] = []
    radius = width / 2 + 2 / dpr
    for station in station_rows:
        x = station["x"] + phase[0]
        y = station["y"] + phase[1] + lane * 8
        tx, ty = station["tx"], station["ty"]
        candidates = []
        for pixel_y in range(
            max(0, math.floor((y - radius) * dpr)),
            min(mask.shape[0] - 1, math.ceil((y + radius) * dpr)) + 1,
        ):
            for pixel_x in range(
                max(0, math.floor((x - radius) * dpr)),
                min(mask.shape[1] - 1, math.ceil((x + radius) * dpr)) + 1,
            ):
                center_x, center_y = (pixel_x + 0.5) / dpr, (pixel_y + 0.5) / dpr
                delta_x, delta_y = center_x - x, center_y - y
                if abs(delta_x * tx + delta_y * ty) <= 0.5 / dpr + 1e-9:
                    amount = float(coverage[pixel_y, pixel_x])
                    distance = math.hypot(delta_x, delta_y)
                    candidates.append((-amount, distance, pixel_y, pixel_x))
        if not candidates:
            continue
        negative_coverage, distance, pixel_y, pixel_x = min(candidates)
        amount = -negative_coverage
        if amount + 1e-12 < 0.5:
            continue
        selected.append(
            [
                round(station["s"], 6),
                round(x, 6),
                round(y, 6),
                pixel_x,
                pixel_y,
                round(amount, 8),
                round(distance, 8),
            ]
        )
    return selected


def _encode_rgb8(values: np.ndarray) -> str:
    return base64.b64encode(np.asarray(values, dtype=np.uint8).tobytes()).decode("ascii")


def _decode_rgb8(value: str, count: int) -> np.ndarray:
    decoded = np.frombuffer(base64.b64decode(value), dtype=np.uint8)
    if decoded.size != count * 3:
        raise ValueError("RGB8 observation cardinality mismatch")
    return decoded.reshape(count, 3)


def _predict_rgb8(
    mask_record: dict[str, Any],
    role: str,
    base: dict[str, Any],
    baseline: dict[str, Any],
) -> np.ndarray:
    coverage = np.array([sample[5] for sample in mask_record["samples"]])[:, None]
    foreground = _rgb(baseline["categorical"][role.split(".", 1)[1]])
    background = _rgb(baseline["surfaces"][base["background"]])
    gains = GAINS if base["state"] == "transformed" else np.ones(3)
    predicted = gains * (coverage * foreground + (1 - coverage) * background)
    return np.rint(np.clip(predicted, 0, 1) * 255).astype(np.uint8)


def reconstruct_pair_metrics(
    left: dict[str, Any],
    right: dict[str, Any],
    left_mask: dict[str, Any],
    right_mask: dict[str, Any],
    base: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    left_stations = [sample[0] for sample in left_mask["samples"]]
    right_stations = [sample[0] for sample in right_mask["samples"]]
    left_indices = {station: index for index, station in enumerate(left_stations)}
    right_indices = {station: index for index, station in enumerate(right_stations)}
    common = sorted(set(left_indices) & set(right_indices))
    if not common:
        return {"status": "UNSUPPORTED", "reason": "NO_MATCHED_STATIONS"}
    left_observed = _decode_rgb8(left["observed_rgb8_base64"], left["sample_count"])
    right_observed = _decode_rgb8(right["observed_rgb8_base64"], right["sample_count"])
    left_predicted = _predict_rgb8(left_mask, left["role"], base, baseline)
    right_predicted = _predict_rgb8(right_mask, right["role"], base, baseline)
    li = [left_indices[station] for station in common]
    ri = [right_indices[station] for station in common]
    observed_distance = (
        np.linalg.norm(
            _oklab(left_observed[li] / 255.0) - _oklab(right_observed[ri] / 255.0), axis=1
        )
        * 100
    )
    predicted_distance = (
        np.linalg.norm(
            _oklab(left_predicted[li] / 255.0) - _oklab(right_predicted[ri] / 255.0), axis=1
        )
        * 100
    )
    residual = np.abs(observed_distance - predicted_distance)
    return {
        "status": "PASS",
        "matched_station_count": len(common),
        "observed_distance": float(np.median(observed_distance)),
        "proxy_prediction": float(np.median(predicted_distance)),
        "proxy_error": float(np.mean(residual)),
        "observed_by_station": observed_distance,
        "predicted_by_station": predicted_distance,
        "absolute_residual_by_station": residual,
    }


def evaluate_acceptance(pair_rows: list[dict[str, Any]]) -> dict[str, Any]:
    observed: list[float] = []
    predicted: list[float] = []
    residual: list[float] = []
    grouped: dict[tuple[str, tuple[str, str]], list[float]] = defaultdict(list)
    diagnostics: dict[tuple[str, str, int, tuple[str, str]], dict[str, list[float]]] = defaultdict(
        lambda: {"observed": [], "predicted": []}
    )
    for row in pair_rows:
        if row["status"] != "PASS":
            continue
        obs = row.pop("_observed_by_station")
        pred = row.pop("_predicted_by_station")
        errors = row.pop("_absolute_residual_by_station")
        observed.extend(obs)
        predicted.extend(pred)
        residual.extend(errors)
        grouped[(row["background"], tuple(row["roles"]))].extend(errors)
        key = (row["state"], row["background"], row["dpr"], tuple(row["roles"]))
        diagnostics[key]["observed"].extend(obs)
        diagnostics[key]["predicted"].extend(pred)
    if not observed:
        return {"status": "FAIL", "reason": "no observed pair-distance samples"}
    local_gates = []
    for (background, roles), errors in sorted(grouped.items()):
        mae = float(np.mean(errors))
        local_gates.append(
            {
                "background": background,
                "background_policy": "gate" if background in ("bg_0", "bg_1") else "report-only",
                "roles": list(roles),
                "mae_delta_e_ok": round(mae, 8),
                "status": "PASS" if background == "bg_2" or mae <= 0.75 else "FAIL",
            }
        )
    local_diagnostics = []
    for (state, background, dpr, roles), values in sorted(diagnostics.items()):
        local_diagnostics.append(
            {
                "state": state,
                "background": background,
                "dpr": dpr,
                "roles": list(roles),
                "correlation": round(_correlation(values["observed"], values["predicted"]), 8),
                "mae_delta_e_ok": round(
                    float(np.mean(np.abs(np.asarray(values["observed"]) - values["predicted"]))), 8
                ),
            }
        )
    global_correlation = _correlation(observed, predicted)
    values = np.asarray(residual)
    maximum_gate_mae = max(
        row["mae_delta_e_ok"] for row in local_gates if row["background_policy"] == "gate"
    )
    passed = (
        global_correlation >= 0.95
        and float(np.mean(values)) <= 0.75
        and maximum_gate_mae <= 0.75
        and all(row["status"] == "PASS" for row in local_gates)
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "engineering_metric": "Oklab Euclidean distance x100 (Delta E OK)",
        "minimum_global_pooled_correlation": 0.95,
        "maximum_global_pooled_mae_delta_e_ok": 0.75,
        "maximum_gate_pair_background_mae_delta_e_ok": 0.75,
        "global_pooled_correlation": round(global_correlation, 8),
        "global_pooled_mae_delta_e_ok": round(float(np.mean(values)), 8),
        "global_pooled_p95_delta_e_ok": round(float(np.quantile(values, 0.95)), 8),
        "global_pooled_max_delta_e_ok": round(float(np.max(values)), 8),
        "observed_gate_pair_background_mae_max_delta_e_ok": round(maximum_gate_mae, 8),
        "pair_background": local_gates,
        "local_correlations_diagnostic_only": local_diagnostics,
    }


def _compact_matrix_json(payload: dict[str, Any]) -> str:
    metadata = [(key, payload[key]) for key in sorted(payload) if key != "matrix"]
    lines = ["{"]
    for key, value in metadata:
        lines.append(
            f"  {json.dumps(key)}: {json.dumps(value, sort_keys=True, separators=(',', ':'))},"
        )
    lines.append('  "matrix": [')
    for index, row in enumerate(payload["matrix"]):
        comma = "," if index + 1 < len(payload["matrix"]) else ""
        lines.append(f"    {json.dumps(row, sort_keys=True, separators=(',', ':'))}{comma}")
    lines.extend(["  ]", "}"])
    return "\n".join(lines) + "\n"


def _write_error(output_dir: Path, status: str, reason: str) -> dict[str, Any]:
    result = {"status": status, "reason": reason, "samples": []}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "proxy-calibration.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def _standalone_sentinel_error(value: object) -> str | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_STANDALONE_SENTINELS
    ):
        return (
            "standalone_sentinels must be an integer in range "
            f"1..{MAX_STANDALONE_SENTINELS}; got {value!r}"
        )
    return None


def run_validation(
    output_dir: Path = HERE, *, standalone_sentinels: int = DEFAULT_STANDALONE_SENTINELS
) -> dict[str, Any]:
    """Capture the complete approved ledger and write compact factored evidence."""

    output_dir = Path(output_dir)
    sentinel_error = _standalone_sentinel_error(standalone_sentinels)
    if sentinel_error is not None:
        return _write_error(output_dir, "ERROR", sentinel_error)
    browse = _browse_binary()
    if browse is None:
        return _write_error(output_dir, "SKIP", "gstack browse binary unavailable")
    try:
        status_text = _browse(browse, output_dir, "status", timeout=60)
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        return _write_error(output_dir, "ERROR", f"browser runtime/probe failure: {error}")

    started = time.perf_counter()
    try:
        raster_path = HERE / "raster-baseline.json"
        raster = json.loads(raster_path.read_text(encoding="utf-8"))
        planned_rows = _validate_ledger(raster)
        approved_ledger_hash = raster.get("provenance", {}).get(
            "approved_ledger_sha256", _sha256(raster_path)
        )
        baseline_payload = json.loads((HERE / "baseline.json").read_text(encoding="utf-8"))
        contract = raster["specimen_contract"]
        baseline = {
            "contract": contract,
            "categorical": baseline_payload["family"]["categorical"],
            "surfaces": {
                name: baseline_payload["family"]["surfaces"][name]
                for name in contract["background_order"]
            },
        }
        bases: list[tuple[Any, ...]] = []
        seen_bases = set()
        for row in planned_rows:
            key = _base_key(row)
            if key not in seen_bases:
                seen_bases.add(key)
                bases.append(key)
        if len(bases) != 2_160:
            raise RuntimeError(f"base factorization mismatch: {len(bases)}")

        with tempfile.TemporaryDirectory(prefix="ember-g1-phase2b-") as temporary:
            workspace = Path(temporary)
            geometry = _geometry_metadata(browse, workspace)
            mask_images: dict[str, np.ndarray] = {}
            color_images: dict[str, np.ndarray] = {}
            performance = defaultdict(float)
            mask_tiles_by_dpr: dict[int, list[dict[str, Any]]] = {}
            color_tiles_by_dpr: dict[int, list[dict[str, Any]]] = {}
            for dpr in contract["device_pixel_ratios"]:
                dpr_bases = [base for base in bases if base[5] == dpr]
                mask_keys = sorted(
                    {_mask_key(base, lane) for base in dpr_bases for lane in (0, 1)}, key=str
                )
                mask_tiles = []
                for key in mask_keys:
                    representative = next(
                        base for base in dpr_bases if _mask_key(base, key[-1]) == key
                    )
                    identifier = "mask|" + json.dumps(key, separators=(",", ":"))
                    mask_tiles.append(
                        {
                            "id": identifier,
                            "kind": "mask",
                            "base": list(representative),
                            "lane": key[-1],
                        }
                    )
                color_tiles = []
                for base in dpr_bases:
                    for role, lane in ROLE_LANES:
                        identifier = "color|" + json.dumps(
                            [*base, role, lane], separators=(",", ":")
                        )
                        color_tiles.append(
                            {
                                "id": identifier,
                                "kind": "color",
                                "base": list(base),
                                "role": role,
                                "lane": lane,
                            }
                        )
                mask_tiles_by_dpr[dpr] = mask_tiles
                color_tiles_by_dpr[dpr] = color_tiles
                for kind, tiles, target in (
                    ("mask", mask_tiles, mask_images),
                    ("color", color_tiles, color_images),
                ):
                    captured, measures = _render_tiles(
                        browse, workspace, kind, dpr, tiles, baseline
                    )
                    target.update(captured)
                    for name, value in measures.items():
                        performance[f"{kind}_{name}"] += value

            mask_records = []
            mask_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
            for index, key in enumerate(
                sorted({_mask_key(base, lane) for base in bases for lane in (0, 1)}, key=str),
                start=1,
            ):
                width, style, orientation, dpr, phase, lane = key
                identifier = "mask|" + json.dumps(key, separators=(",", ":"))
                width_key = f"{width:g}"
                samples = select_line_core(
                    mask_images[identifier],
                    geometry[orientation]["stations"][f"{width_key}|{style}|{dpr}"],
                    width,
                    dpr,
                    phase,
                    lane,
                )
                record = {
                    "id": f"mask-{index:04d}",
                    "key": {
                        "width_css_px": width,
                        "style": style,
                        "orientation": orientation,
                        "dpr": dpr,
                        "phase_css_px": list(phase),
                        "lane": lane,
                    },
                    "status": "PASS" if samples else "UNSUPPORTED",
                    "reason": None if samples else "NO_LINE_CORE_SAMPLES",
                    "sample_count": len(samples),
                    "samples": samples,
                }
                mask_records.append(record)
                mask_by_key[key] = record

            base_records = [
                {"id": f"base-{index:04d}", **dict(zip(BASE_FIELDS, base, strict=True))}
                for index, base in enumerate(bases, start=1)
            ]
            base_by_key = {base: record for base, record in zip(bases, base_records, strict=True)}
            observations = []
            observation_by_key: dict[tuple[tuple[Any, ...], str, int], dict[str, Any]] = {}
            rgb_residuals = []
            for index, base in enumerate(bases):
                base_record = base_records[index]
                for role, lane in ROLE_LANES:
                    mask = mask_by_key[_mask_key(base, lane)]
                    identifier = "color|" + json.dumps([*base, role, lane], separators=(",", ":"))
                    if mask["status"] != "PASS":
                        record = {
                            "id": f"obs-{len(observations) + 1:05d}",
                            "base_id": base_record["id"],
                            "role": role,
                            "lane": lane,
                            "mask_id": mask["id"],
                            "status": "UNSUPPORTED",
                            "reason": mask["reason"],
                            "sample_count": 0,
                        }
                    else:
                        image = color_images[identifier]
                        observed = np.array(
                            [image[int(sample[4]), int(sample[3])] for sample in mask["samples"]],
                            dtype=np.uint8,
                        )
                        predicted = _predict_rgb8(mask, role, base_record, baseline)
                        residual = observed.astype(int) - predicted.astype(int)
                        rgb_residuals.append(residual)
                        record = {
                            "id": f"obs-{len(observations) + 1:05d}",
                            "base_id": base_record["id"],
                            "role": role,
                            "lane": lane,
                            "mask_id": mask["id"],
                            "status": "PASS",
                            "reason": None,
                            "sample_count": len(observed),
                            "observed_rgb8_base64": _encode_rgb8(observed),
                            "observed_rgb8_median": np.median(observed, axis=0).tolist(),
                            "predicted_rgb8_median": np.median(predicted, axis=0).tolist(),
                            "residual_rgb8_median": np.median(residual, axis=0).tolist(),
                            "channel_mae_rgb8": np.mean(np.abs(residual), axis=0).tolist(),
                        }
                    observations.append(record)
                    observation_by_key[(base, role, lane)] = record

            pair_rows = []
            worst_cases = []
            for planned in planned_rows:
                base = _base_key(planned)
                left = observation_by_key[(base, planned["roles"][0], 0)]
                right = observation_by_key[(base, planned["roles"][1], 1)]
                left_mask = mask_by_key[_mask_key(base, 0)]
                right_mask = mask_by_key[_mask_key(base, 1)]
                row = dict(planned)
                if left["status"] != "PASS" or right["status"] != "PASS":
                    row.update(
                        {
                            "status": "UNSUPPORTED",
                            "reason": "NO_LINE_CORE_SAMPLES",
                            "observed_line_core_rgb8": None,
                            "observed_distance": None,
                            "proxy_prediction": None,
                            "proxy_error": None,
                            "evidence": {
                                "left_observation_id": left["id"],
                                "right_observation_id": right["id"],
                            },
                        }
                    )
                else:
                    metrics = reconstruct_pair_metrics(
                        left, right, left_mask, right_mask, base_by_key[base], baseline
                    )
                    if metrics["status"] != "PASS":
                        row.update(
                            {
                                "status": "UNSUPPORTED",
                                "reason": metrics["reason"],
                                "observed_line_core_rgb8": None,
                                "observed_distance": None,
                                "proxy_prediction": None,
                                "proxy_error": None,
                                "evidence": {
                                    "left_observation_id": left["id"],
                                    "right_observation_id": right["id"],
                                },
                            }
                        )
                    else:
                        row.update(
                            {
                                "status": "PASS",
                                "reason": None,
                                "observed_line_core_rgb8": [
                                    left["observed_rgb8_median"],
                                    right["observed_rgb8_median"],
                                ],
                                "observed_distance": round(metrics["observed_distance"], 8),
                                "proxy_prediction": round(metrics["proxy_prediction"], 8),
                                "proxy_error": round(metrics["proxy_error"], 8),
                                "evidence": {
                                    "left_observation_id": left["id"],
                                    "right_observation_id": right["id"],
                                    "matched_station_count": metrics["matched_station_count"],
                                },
                                "_observed_by_station": metrics["observed_by_station"].tolist(),
                                "_predicted_by_station": metrics["predicted_by_station"].tolist(),
                                "_absolute_residual_by_station": metrics[
                                    "absolute_residual_by_station"
                                ].tolist(),
                            }
                        )
                        worst_cases.append(
                            {
                                "id": row["id"],
                                "roles": row["roles"],
                                "background": row["background"],
                                "state": row["state"],
                                "width_css_px": row["width_css_px"],
                                "style": row["style"],
                                "orientation": row["orientation"],
                                "dpr": row["dpr"],
                                "phase_css_px": row["phase_css_px"],
                                "mae_delta_e_ok": row["proxy_error"],
                            }
                        )
                pair_rows.append(row)

            acceptance = evaluate_acceptance(pair_rows)
            unsupported = [row for row in pair_rows if row["status"] == "UNSUPPORTED"]
            supported_gate_rows = [row for row in pair_rows if row["background_policy"] == "gate"]
            coverage_sufficient = not unsupported and all(
                row["status"] == "PASS" for row in supported_gate_rows
            )
            phase3_authorized = acceptance["status"] == "PASS" and coverage_sufficient
            rgb_values = np.concatenate(rgb_residuals, axis=0).astype(float)

            # Compare retained station pixels from a deterministic spread with each tile alone.
            sentinel_mismatches = []
            sentinel_records = [
                observations[index]
                for index in np.linspace(
                    0,
                    len(observations) - 1,
                    min(standalone_sentinels, len(observations)),
                    dtype=int,
                )
                if observations[index]["status"] == "PASS"
            ]
            base_lookup = {record["id"]: record for record in base_records}
            mask_lookup = {record["id"]: record for record in mask_records}
            for observation in sentinel_records:
                base_record = base_lookup[observation["base_id"]]
                tile = {
                    "id": observation["id"],
                    "kind": "color",
                    "base": [base_record[field] for field in BASE_FIELDS],
                    "role": observation["role"],
                    "lane": observation["lane"],
                }
                html_path, png_path = workspace / "standalone.html", workspace / "standalone.png"
                _write_atlas(html_path, [tile], baseline)
                _browse(
                    browse,
                    workspace,
                    "viewport",
                    f"{TILE_WIDTH}x{TILE_HEIGHT}",
                    "--scale",
                    str(base_record["dpr"]),
                )
                commands = json.dumps(
                    [
                        ["goto", html_path.as_uri()],
                        ["screenshot", str(png_path), "--selector", "iframe"],
                    ]
                )
                _run([str(browse), "chain"], cwd=workspace, stdin=commands)
                with Image.open(png_path) as opened:
                    standalone = np.asarray(opened.convert("RGB"), dtype=np.uint8)
                mask = mask_lookup[observation["mask_id"]]
                expected = _decode_rgb8(
                    observation["observed_rgb8_base64"], observation["sample_count"]
                )
                actual = np.array(
                    [standalone[int(sample[4]), int(sample[3])] for sample in mask["samples"]]
                )
                if not np.array_equal(actual, expected):
                    sentinel_mismatches.append(observation["id"])
                html_path.unlink(missing_ok=True)
                png_path.unlink(missing_ok=True)
            if sentinel_mismatches:
                raise RuntimeError(
                    f"standalone-vs-batch sentinel mismatch: {sentinel_mismatches[:3]}"
                )

        mask_payload = {
            "schema": "ember-g1-raster-masks-v1",
            "description": (
                "Reusable monochrome line-core masks. Sample tuple fields are "
                "[arc_length_css_px, centerline_x_css_px, centerline_y_css_px, "
                "device_x, device_y, encoded_srgb_coverage, centerline_distance_css_px]."
            ),
            "coverage_polarity": "coverage = 1 - mean(mask_rgb8)/255; black stroke on white",
            "minimum_coverage": 0.5,
            "geometry_source": "Chromium SVG getTotalLength/getPointAtLength",
            "geometry_metadata_sha256": _json_bytes_sha256(geometry),
            "record_count": len(mask_records),
            "records": mask_records,
        }
        mask_path = output_dir / "raster-masks.json"
        mask_path.write_text(
            json.dumps(mask_payload, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        observation_payload = {
            "schema": "ember-g1-raster-observations-v1",
            "description": (
                "Factored real-Chromium role/lane RGB8 observations. RGB station triples are "
                "uint8 bytes encoded as base64 and align exactly with the referenced mask samples."
            ),
            "approved_head": APPROVED_HEAD,
            "role_lane_factorization": [list(value) for value in ROLE_LANES],
            "base_count": len(base_records),
            "observation_count": len(observations),
            "bases": base_records,
            "observations": observations,
        }
        observation_path = output_dir / "raster-observations.json"
        observation_path.write_text(
            json.dumps(observation_payload, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        mask_hash, observation_hash = _sha256(mask_path), _sha256(observation_path)

        width_capacity = {}
        for width in contract["widths_css_px"]:
            rows = [
                row
                for row in pair_rows
                if row["width_css_px"] == width and row["background_policy"] == "gate"
            ]
            passed_rows = [row for row in rows if row["status"] == "PASS"]
            worst = min(passed_rows, key=lambda row: row["observed_distance"])
            width_capacity[f"{width:.1f}"] = {
                "human_capacity_status": "UNKNOWN/UNPROVEN",
                "capacity": None,
                "pass_fail": None,
                "browser_numerical_reconnaissance": {
                    "gate_rows_observed": len(passed_rows),
                    "gate_rows_planned": len(rows),
                    "unique_pairs_observed": len({tuple(row["roles"]) for row in passed_rows}),
                    "minimum_observed_delta_e_ok": worst["observed_distance"],
                    "minimum_observed_pair": worst["roles"],
                    "minimum_observed_case_id": worst["id"],
                    "proxy_calibration_gate": acceptance["status"],
                    "not_a_visibility_floor_or_human_capacity": True,
                },
            }

        raster_output = {
            **{
                key: value
                for key, value in raster.items()
                if key not in {"matrix", "width_capacity"}
            },
            "approved_head": APPROVED_HEAD,
            "matrix_kind": "complete real-Chromium observed pair ledger reconstructed from factored evidence",
            "matrix_status": "PASS" if not unsupported else "PASS_WITH_UNSUPPORTED",
            "observed_case_count": len(pair_rows) - len(unsupported),
            "unsupported_case_count": len(unsupported),
            "phase3_search_authorized": phase3_authorized,
            "production_promotion_blocked": True,
            "human_requirements": (
                "Preregistered multi-observer 2AFC study, held-out floor calibration, and G2/G3 "
                "promotion gates remain required."
            ),
            "evidence": {
                "raster_masks": "raster-masks.json",
                "raster_masks_sha256": mask_hash,
                "raster_observations": "raster-observations.json",
                "raster_observations_sha256": observation_hash,
            },
            "provenance": {
                "approved_head": APPROVED_HEAD,
                "approved_ledger_sha256": approved_ledger_hash,
            },
            "width_capacity": width_capacity,
            "matrix": pair_rows,
        }
        raster_path_out = output_dir / "raster-baseline.json"
        raster_path_out.write_text(_compact_matrix_json(raster_output), encoding="utf-8")

        elapsed = time.perf_counter() - started
        total_tiles = int(performance["mask_tiles"] + performance["color_tiles"])
        browser_seconds = performance["mask_browser_seconds"] + performance["color_browser_seconds"]
        result = {
            "status": "PASS" if phase3_authorized else "FAIL",
            "baseline_source_commit": baseline_payload["baseline_source_commit"],
            "approved_head": APPROVED_HEAD,
            "evidence_kind": "real Chromium screenshot pixels with deterministic mask/role factoring",
            "full_image_hash_used": False,
            "phase3_search_authorized": phase3_authorized,
            "production_promotion_blocked": True,
            "operation_order_pin": {
                "order": "ancestor sRGB feColorMatrix after SVG raster/compositing",
                "structure": (
                    "source-coloured background and stroke share one ancestor filtered group; no "
                    "pre-transformed literals"
                ),
                "proof_boundary": (
                    "DOM/source structure is normative. Linear unclipped diagonal gains commute "
                    "with alpha compositing, so pixel equality alone cannot prove operation order."
                ),
            },
            "capture": {
                "tile_css_px": [TILE_WIDTH, TILE_HEIGHT],
                "chunk_tiles": CHUNK_TILES,
                "atlas_columns": ATLAS_COLUMNS,
                "transport": "eager same-origin srcdoc iframes; one GStack chain goto+screenshot per chunk",
                "screenshot_scale": "clip scale equals declared DPR",
                "dpr": contract["device_pixel_ratios"],
                "mask_tiles": int(performance["mask_tiles"]),
                "color_tiles": int(performance["color_tiles"]),
                "total_tiles": total_tiles,
                "chunks": int(performance["mask_chunks"] + performance["color_chunks"]),
                "browser_seconds": round(browser_seconds, 3),
                "total_runtime_seconds": round(elapsed, 3),
                "tiles_per_browser_second": round(total_tiles / browser_seconds, 3),
                "effective_pair_rows_per_second": round(len(pair_rows) / elapsed, 3),
                "standalone_vs_batch": {
                    "status": "PASS",
                    "observation_tiles_checked": len(sentinel_records),
                    "mismatch_count": 0,
                },
            },
            "counts": {
                "planned_pair_rows": len(pair_rows),
                "observed_pair_rows": len(pair_rows) - len(unsupported),
                "unsupported_pair_rows": len(unsupported),
                "errored_pair_rows": 0,
                "bases": len(base_records),
                "mask_records": len(mask_records),
                "role_lane_observations": len(observations),
                "line_core_samples": sum(record["sample_count"] for record in observations),
                "matched_pair_station_samples": sum(
                    row["evidence"].get("matched_station_count", 0) for row in pair_rows
                ),
            },
            "unsupported_geometry": {
                "count": len(unsupported),
                "reasons": dict(
                    sorted(
                        {
                            reason: sum(row.get("reason") == reason for row in unsupported)
                            for reason in {row.get("reason") for row in unsupported}
                        }.items()
                    )
                ),
                "supported_scope": list(PATHS),
                "excluded_by_policy": "endpoints, joins, markers, crossings, dash transitions",
            },
            "acceptance": acceptance,
            "rgb8_residuals": {
                "sample_channel_values": int(rgb_values.size),
                "mae": round(float(np.mean(np.abs(rgb_values))), 8),
                "p95": round(float(np.quantile(np.abs(rgb_values), 0.95)), 8),
                "max": int(np.max(np.abs(rgb_values))),
                "per_channel_mae": [
                    round(float(value), 8) for value in np.mean(np.abs(rgb_values), axis=0)
                ],
            },
            "worst_cases": sorted(worst_cases, key=lambda row: (-row["mae_delta_e_ok"], row["id"]))[
                :20
            ],
            "evidence": {
                "raster_masks": {"file": "raster-masks.json", "sha256": mask_hash},
                "raster_observations": {
                    "file": "raster-observations.json",
                    "sha256": observation_hash,
                },
                "raster_ledger": {
                    "file": "raster-baseline.json",
                    "sha256": _sha256(raster_path_out),
                },
            },
            "provenance": {
                "approved_head": APPROVED_HEAD,
                "approved_ledger_sha256": approved_ledger_hash,
                "probe_sha256": _sha256(HERE / "review/g1-browser-probe.html"),
                "validator_sha256": _sha256(Path(__file__)),
                "gstack_browse_binary_sha256": _sha256(browse),
                "browser_status": _sanitize_status(status_text),
                "chromium_version": None,
                "chromium_version_status": "unavailable-unclaimed",
            },
            "human_requirements_remaining": [
                "run the preregistered multi-observer 2AFC visibility study",
                "calibrate the final visibility floor on held-out responses",
                "pass G2 and G3 before any production promotion",
            ],
        }
        (output_dir / "proxy-calibration.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return result
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        return _write_error(output_dir, "ERROR", f"browser runtime/probe failure: {error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=HERE)
    parser.add_argument(
        "--standalone-sentinels",
        type=int,
        default=DEFAULT_STANDALONE_SENTINELS,
        help=(
            "standalone-vs-batch observations to verify "
            f"(integer 1..{MAX_STANDALONE_SENTINELS}; default: "
            f"{DEFAULT_STANDALONE_SENTINELS})"
        ),
    )
    arguments = parser.parse_args()
    result = run_validation(
        output_dir=arguments.output_dir, standalone_sentinels=arguments.standalone_sentinels
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"PASS", "SKIP"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
