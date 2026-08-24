#!/usr/bin/env python3
"""Phase 2B browser-calibration API for the G1 deterministic probe.

Phase 2A intentionally does not manufacture browser samples. A missing binary is
SKIP; an installed binary that fails is ERROR; a healthy prerequisite probe
remains PENDING_BROWSER_CALIBRATION until real pixel extraction is implemented.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


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


def _write_result(output_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "proxy-calibration.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def run_validation(output_dir: Path = HERE) -> dict[str, Any]:
    """Check browser prerequisites without claiming Phase 2B pixel evidence."""

    output_dir = Path(output_dir)
    browse = _browse_binary()
    if browse is None:
        return _write_result(
            output_dir,
            {
                "status": "SKIP",
                "reason": "gstack browse binary unavailable",
                "dependency": "real local GStack/Chromium browser",
                "samples": [],
            },
        )

    try:
        completed = subprocess.run(
            [str(browse), "status"],
            cwd=output_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return _write_result(
            output_dir,
            {
                "status": "ERROR",
                "reason": f"browser runtime/probe failure: {error}",
                "samples": [],
            },
        )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        return _write_result(
            output_dir,
            {
                "status": "ERROR",
                "reason": (
                    f"browser runtime/probe failure: status exited {completed.returncode}"
                    + (f": {detail}" if detail else "")
                ),
                "samples": [],
            },
        )

    return _write_result(
        output_dir,
        {
            "status": "PENDING_BROWSER_CALIBRATION",
            "reason": (
                "browser prerequisite responded, but Phase 2A does not collect or claim real "
                "pixel samples; run the Phase 2B extractor"
            ),
            "full_image_hash_used": False,
            "acceptance": {
                "minimum_global_pooled_correlation": 0.95,
                "maximum_pair_background_mae": 0.75,
                "observed_global_pooled_correlation": None,
                "observed_pair_background_mae_max": None,
                "status": "NOT_EVALUATED",
            },
            "provenance": {
                "gstack_browse_binary_sha256": _sha256(browse),
                "probe_sha256": _sha256(HERE / "review/g1-browser-probe.html"),
                "validator_sha256": _sha256(Path(__file__)),
                "chromium_version": None,
                "chromium_version_status": "pending-browser-calibration",
            },
            "samples": [],
            "coordinates": None,
        },
    )


if __name__ == "__main__":
    result = run_validation()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] in {"SKIP", "PENDING_BROWSER_CALIBRATION"} else 1)
