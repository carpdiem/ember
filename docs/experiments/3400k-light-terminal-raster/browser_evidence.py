#!/usr/bin/env python3
"""Capture and measure Chromium terminal-glyph evidence for finalists."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import subprocess
import tempfile
from itertools import combinations, product
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ROLE_ORDER = ("fg_0", "red", "green", "yellow", "blue", "magenta", "cyan")
ACCENT_ROLES = ROLE_ORDER[1:]
BACKGROUNDS = ("bg_0", "bg_1")
FONT_SIZES = (11, 13, 15)
FONT_WEIGHTS = (400, 600)
DPRS = (1, 2)
TILE_WIDTH = 224
TILE_HEIGHT = 56
ROWS_PER_CHUNK = 12
TEXT = "Ag0 ERROR ok []{} <> $ git"
BANDS = {
    "core_75": (0.75, 1.01),
    "body_50": (0.50, 1.01),
    "edge_05_50": (0.05, 0.50),
    "active_05": (0.05, 1.01),
}
GAIN_STATES = {
    "commanded-normal-light": (1.0, 1.0, 1.0),
    "transformed-low-light": (1.0, 0.74, 0.53),
    "corner-g703-b5035": (1.0, 0.703, 0.5035),
    "corner-g703-b5565": (1.0, 0.703, 0.5565),
    "corner-g777-b5035": (1.0, 0.777, 0.5035),
    "corner-g777-b5565": (1.0, 0.777, 0.5565),
}


class EvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rgb(value: str) -> np.ndarray:
    value = value.lstrip("#")
    return np.asarray([int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=float)


def linearize(values: np.ndarray) -> np.ndarray:
    return np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)


def oklab(values: np.ndarray) -> np.ndarray:
    linear = linearize(np.asarray(values, dtype=float))
    m1 = np.asarray(
        [
            [0.4122214708, 0.5363325363, 0.0514459929],
            [0.2119034982, 0.6806995451, 0.1073969566],
            [0.0883024619, 0.2817188376, 0.6299787005],
        ]
    )
    m2 = np.asarray(
        [
            [0.2104542553, 0.7936177850, -0.0040720468],
            [1.9779984951, -2.4285922050, 0.4505937099],
            [0.0259040371, 0.7827717662, -0.8086757660],
        ]
    )
    return np.cbrt(linear @ m1.T) @ m2.T


def expected_color(
    bank: dict[str, Any], role: str, gains: tuple[float, float, float]
) -> np.ndarray:
    value = bank["surfaces"][role] if role == "fg_0" else bank["terminal"][role]
    return np.clip(rgb(value) * np.asarray(gains), 0.0, 1.0)


def coverage_mask(tile: np.ndarray, background: np.ndarray, foreground: np.ndarray) -> np.ndarray:
    vector = foreground - background
    denominator = float(np.dot(vector, vector))
    require(denominator > 1e-12, "foreground and background collapse")
    alpha = np.sum((tile - background) * vector, axis=2) / denominator
    return np.clip(alpha, 0.0, 1.0)


def browse_binary() -> Path:
    explicit = os.environ.get("GSTACK_BROWSE")
    candidates = [Path(explicit).expanduser()] if explicit else []
    candidates.extend(
        [
            Path.home() / ".hermes/skills/gstack/browse/dist/browse",
            Path.home() / "gstack/browse/dist/browse",
        ]
    )
    found = next((path for path in candidates if path.is_file() and os.access(path, os.X_OK)), None)
    if found is None:
        raise EvidenceError("GStack browse binary unavailable")
    return found


def run_browse(binary: Path, cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        [str(binary), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode:
        raise EvidenceError((completed.stderr or completed.stdout).strip())
    return completed.stdout


def banks(results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    light_surfaces = results["frozen"]["surfaces"]
    current = dict(zip(ACCENT_ROLES, results["baseline"]["values"], strict=True))
    output = {
        "current-light": {"surfaces": light_surfaces, "terminal": current, "kind": "baseline"}
    }
    for finalist in results["finalists"]:
        output[finalist["id"]] = {
            "surfaces": light_surfaces,
            "terminal": dict(zip(ACCENT_ROLES, finalist["values"], strict=True)),
            "kind": "finalist",
        }
    # Dark is a working perceptual reference, never a Light candidate.
    output["reference-dark"] = {
        "surfaces": {
            "bg_0": "#050404",
            "bg_1": "#13100F",
            "fg_0": "#DCD9BF",
        },
        "terminal": dict(
            zip(
                ACCENT_ROLES,
                ("#F7B7AA", "#7BB48F", "#BE8236", "#A4C0FC", "#D486C3", "#69EBD5"),
                strict=True,
            )
        ),
        "kind": "reference",
    }
    return output


def page(
    bank: dict[str, Any],
    gains: tuple[float, float, float],
    dpr: int,
    selected_rows: list[dict[str, Any]],
) -> str:
    tiles = []
    for metadata in selected_rows:
        for role in ROLE_ORDER:
            color = bank["surfaces"][role] if role == "fg_0" else bank["terminal"][role]
            tiles.append(
                "<div class='tile' "
                f"style='background:{bank['surfaces'][metadata['background']]};color:{color}'>"
                f"<span style='font-size:{metadata['font_size']}px;font-weight:{metadata['font_weight']};"
                f"left:{8 + metadata['phase'][0]}px;top:{18 + metadata['phase'][1]}px'>"
                f"{html.escape(TEXT)}</span></div>"
            )
    matrix = " ".join(
        [
            f"{gains[0]} 0 0 0 0",
            f"0 {gains[1]} 0 0 0",
            f"0 0 {gains[2]} 0 0",
            "0 0 0 1 0",
        ]
    )
    filter_css = "" if gains == (1.0, 1.0, 1.0) else "filter:url(#state-transform);"
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>*{{box-sizing:border-box}}html,body{{margin:0;padding:0;width:{TILE_WIDTH * len(ROLE_ORDER)}px;background:#000}}#grid{{display:grid;grid-template-columns:repeat({len(ROLE_ORDER)},{TILE_WIDTH}px);grid-auto-rows:{TILE_HEIGHT}px;width:{TILE_WIDTH * len(ROLE_ORDER)}px;height:{len(selected_rows) * TILE_HEIGHT}px;{filter_css}}}.tile{{position:relative;width:{TILE_WIDTH}px;height:{TILE_HEIGHT}px;overflow:hidden}}.tile span{{position:absolute;display:block;margin:0;padding:0;white-space:pre;font-family:Menlo,'SFMono-Regular',monospace;line-height:1;font-style:normal;font-variant-ligatures:none;text-rendering:auto}}svg{{position:absolute;width:0;height:0}}</style></head><body><svg><filter id='state-transform' color-interpolation-filters='sRGB'><feColorMatrix type='matrix' values='{matrix}'/></filter></svg><div id='grid'>{"".join(tiles)}</div></body></html>"""


def metric_summary(values: np.ndarray, exact: np.ndarray) -> dict[str, float]:
    return {
        "sample_count": len(values),
        "delta_e_ok_p10": float(np.quantile(values, 0.10)),
        "delta_e_ok_median": float(np.quantile(values, 0.50)),
        "delta_e_ok_p90": float(np.quantile(values, 0.90)),
        "exact_rgb8_fraction": float(np.mean(exact)),
        "near_fraction_delta_e_below_0_5": float(np.mean(values < 0.5)),
    }


def analyze_tile_pair(
    left: np.ndarray, right: np.ndarray, selected: np.ndarray
) -> dict[str, float]:
    left_lab = oklab(left.reshape(-1, 3)).reshape(left.shape)
    right_lab = oklab(right.reshape(-1, 3)).reshape(right.shape)
    distance = np.linalg.norm(left_lab - right_lab, axis=2)[selected] * 100.0
    exact = np.all(
        np.rint(left * 255).astype(np.uint8) == np.rint(right * 255).astype(np.uint8), axis=2
    )[selected]
    return metric_summary(distance, exact)


def capture_and_measure(results: dict[str, Any], output: Path) -> dict[str, Any]:
    binary = browse_binary()
    bank_map = banks(results)
    role_rows = []
    pair_rows = []
    mask_rows = []
    screenshot_count = 0
    with tempfile.TemporaryDirectory(prefix="ember-terminal-browser-") as directory:
        temp = Path(directory)
        for dpr in DPRS:
            phases = tuple(
                (x / dpr, y / dpr) for x, y in ((0.0, 0.0), (0.0, 0.5), (0.5, 0.0), (0.5, 0.5))
            )
            rows = [
                {
                    "background": background,
                    "font_size": size,
                    "font_weight": weight,
                    "phase": phase,
                }
                for background, size, weight, phase in product(
                    BACKGROUNDS, FONT_SIZES, FONT_WEIGHTS, phases
                )
            ]
            run_browse(
                binary,
                temp,
                "viewport",
                f"{TILE_WIDTH * len(ROLE_ORDER)}x{TILE_HEIGHT * ROWS_PER_CHUNK}",
                "--scale",
                str(dpr),
            )
            for bank_id, bank in bank_map.items():
                for state, gains in GAIN_STATES.items():
                    for chunk_start in range(0, len(rows), ROWS_PER_CHUNK):
                        selected_rows = rows[chunk_start : chunk_start + ROWS_PER_CHUNK]
                        html_path = temp / "probe.html"
                        html_path.write_text(page(bank, gains, dpr, selected_rows))
                        png_path = temp / "probe.png"
                        run_browse(binary, temp, "goto", f"file://{html_path}")
                        run_browse(binary, temp, "wait", "--load")
                        run_browse(binary, temp, "screenshot", str(png_path), "--viewport")
                        screenshot_count += 1
                        with Image.open(png_path) as image:
                            pixels = np.asarray(image.convert("RGB"), dtype=float) / 255.0
                        expected_shape = (
                            len(selected_rows) * TILE_HEIGHT * dpr,
                            len(ROLE_ORDER) * TILE_WIDTH * dpr,
                            3,
                        )
                        require(
                            pixels.shape == expected_shape, f"bad screenshot shape {pixels.shape}"
                        )
                        for local_row, metadata in enumerate(selected_rows):
                            y0 = local_row * TILE_HEIGHT * dpr
                            y1 = y0 + TILE_HEIGHT * dpr
                            tiles = {}
                            for role_index, role in enumerate(ROLE_ORDER):
                                x0 = role_index * TILE_WIDTH * dpr
                                x1 = x0 + TILE_WIDTH * dpr
                                tiles[role] = pixels[y0:y1, x0:x1]
                            background = np.median(
                                tiles["fg_0"][: 5 * dpr, : 5 * dpr].reshape(-1, 3), axis=0
                            )
                            fg_expected = expected_color(bank, "fg_0", gains)
                            alpha = coverage_mask(tiles["fg_0"], background, fg_expected)
                            masks = {
                                "core_75": alpha >= 0.75,
                                "body_50": alpha >= 0.50,
                                "edge_05_50": (alpha >= 0.05) & (alpha < 0.50),
                                "active_05": alpha >= 0.05,
                            }
                            global_row = chunk_start + local_row
                            mask_rows.append(
                                {
                                    "bank": bank_id,
                                    "state": state,
                                    "dpr": dpr,
                                    "row": global_row,
                                    **metadata,
                                    "active_samples": int(masks["active_05"].sum()),
                                    "core_samples": int(masks["core_75"].sum()),
                                    "maximum_coverage": float(alpha.max()),
                                }
                            )
                            for role in ACCENT_ROLES:
                                for band, selected in masks.items():
                                    metrics = analyze_tile_pair(
                                        tiles[role], tiles["fg_0"], selected
                                    )
                                    role_rows.append(
                                        {
                                            "bank": bank_id,
                                            "kind": bank["kind"],
                                            "state": state,
                                            "dpr": dpr,
                                            "row": global_row,
                                            **metadata,
                                            "role": role,
                                            "band": band,
                                            **metrics,
                                        }
                                    )
                            for left, right in combinations(ACCENT_ROLES, 2):
                                metrics = analyze_tile_pair(
                                    tiles[left], tiles[right], masks["active_05"]
                                )
                                pair_rows.append(
                                    {
                                        "bank": bank_id,
                                        "kind": bank["kind"],
                                        "state": state,
                                        "dpr": dpr,
                                        "row": global_row,
                                        **metadata,
                                        "roles": [left, right],
                                        **metrics,
                                    }
                                )
    aggregates = []
    for bank_id, bank in bank_map.items():
        for state in GAIN_STATES:
            for dpr in DPRS:
                for role in ACCENT_ROLES:
                    selected = [
                        row
                        for row in role_rows
                        if row["bank"] == bank_id
                        and row["state"] == state
                        and row["dpr"] == dpr
                        and row["role"] == role
                        and row["band"] == "active_05"
                    ]
                    edge = [
                        row
                        for row in role_rows
                        if row["bank"] == bank_id
                        and row["state"] == state
                        and row["dpr"] == dpr
                        and row["role"] == role
                        and row["band"] == "edge_05_50"
                    ]
                    aggregates.append(
                        {
                            "bank": bank_id,
                            "kind": bank["kind"],
                            "state": state,
                            "dpr": dpr,
                            "role": role,
                            "active_min_p10": min(row["delta_e_ok_p10"] for row in selected),
                            "active_min_median": min(row["delta_e_ok_median"] for row in selected),
                            "active_max_near_fraction": max(
                                row["near_fraction_delta_e_below_0_5"] for row in selected
                            ),
                            "active_max_exact_fraction": max(
                                row["exact_rgb8_fraction"] for row in selected
                            ),
                            "edge_min_p10": min(row["delta_e_ok_p10"] for row in edge),
                            "edge_min_median": min(row["delta_e_ok_median"] for row in edge),
                            "edge_max_near_fraction": max(
                                row["near_fraction_delta_e_below_0_5"] for row in edge
                            ),
                        }
                    )
    pair_aggregates = []
    for bank_id, bank in bank_map.items():
        for state in GAIN_STATES:
            for dpr in DPRS:
                selected = [
                    row
                    for row in pair_rows
                    if row["bank"] == bank_id and row["state"] == state and row["dpr"] == dpr
                ]
                binding = min(selected, key=lambda row: row["delta_e_ok_p10"])
                pair_aggregates.append(
                    {
                        "bank": bank_id,
                        "kind": bank["kind"],
                        "state": state,
                        "dpr": dpr,
                        "minimum_active_p10": binding,
                    }
                )
    baseline_lookup = {
        (row["state"], row["dpr"], row["role"]): row
        for row in aggregates
        if row["bank"] == "current-light"
    }
    baseline_pair_lookup = {
        (row["state"], row["dpr"]): row for row in pair_aggregates if row["bank"] == "current-light"
    }
    primary_states = ("commanded-normal-light", "transformed-low-light")
    target_roles = ("red", "green", "blue")
    acceptance = []
    for bank_id, bank in bank_map.items():
        if bank["kind"] != "finalist":
            continue
        failures = []
        selected = [
            row for row in aggregates if row["bank"] == bank_id and row["state"] in primary_states
        ]
        for row in selected:
            baseline = baseline_lookup[(row["state"], row["dpr"], row["role"])]
            required_ratio = 1.0 if row["role"] in target_roles else 0.85
            if row["active_min_p10"] <= required_ratio * baseline["active_min_p10"] + 1e-9:
                failures.append(
                    f"{row['state']} dpr{row['dpr']} {row['role']} active p10 missed ratio {required_ratio}"
                )
            if row["active_max_near_fraction"] > 0.0:
                failures.append(
                    f"{row['state']} dpr{row['dpr']} {row['role']} retained near-tail samples"
                )
            if row["active_max_exact_fraction"] > 0.0:
                failures.append(
                    f"{row['state']} dpr{row['dpr']} {row['role']} has exact RGB8 collisions"
                )
        selected_pairs = [
            row
            for row in pair_aggregates
            if row["bank"] == bank_id and row["state"] in primary_states
        ]
        for row in selected_pairs:
            baseline = baseline_pair_lookup[(row["state"], row["dpr"])]
            if (
                row["minimum_active_p10"]["delta_e_ok_p10"]
                < baseline["minimum_active_p10"]["delta_e_ok_p10"] - 1e-9
            ):
                failures.append(f"{row['state']} dpr{row['dpr']} accent-pair p10 regressed")
        acceptance.append(
            {
                "bank": bank_id,
                "status": "PASS" if not failures else "FAIL",
                "failures": failures,
                "gain_corner_browser_status": "report-only-sampled-diagnostic",
            }
        )
    payload = {
        "schema_version": 1,
        "artifact_kind": "3400k-light-terminal-browser-evidence",
        "source": results["source"],
        "results_sha256": sha256_file(HERE / "results.json"),
        "script_sha256": sha256_file(Path(__file__)),
        "gstack_browse_sha256": sha256_file(binary),
        "browser_matrix": {
            "fonts": ["Menlo"],
            "font_sizes": list(FONT_SIZES),
            "font_weights": list(FONT_WEIGHTS),
            "dprs": list(DPRS),
            "backgrounds": list(BACKGROUNDS),
            "states": {key: list(value) for key, value in GAIN_STATES.items()},
            "phases": "0 or 0.5/DPR CSS px on each axis",
            "text": TEXT,
            "screenshot_count": screenshot_count,
        },
        "banks": bank_map,
        "role_aggregates": aggregates,
        "pair_aggregates": pair_aggregates,
        "acceptance": acceptance,
        "human_visibility_floor": None,
        "production_promotion_authorized": False,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=HERE / "results.json")
    parser.add_argument("--output", type=Path, default=HERE / "browser-evidence.json")
    args = parser.parse_args()
    results = json.loads(args.results.read_text())
    payload = capture_and_measure(results, args.output)
    print(args.output)
    for row in payload["acceptance"]:
        print(row["bank"], row["status"], len(row["failures"]))


if __name__ == "__main__":
    main()
