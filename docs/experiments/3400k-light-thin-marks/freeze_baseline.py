#!/usr/bin/env python3
"""Freeze the Ember 3400K Light G0 baseline from one immutable Git commit."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

BASELINE_COMMIT = "c4c25e480912f8f54cbd8c992c0b6eb520dc0b8f"
ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).with_name("baseline.json")
ARTIFACTS = (
    "src/ember/definitions.py",
    "src/ember/sequential_data.py",
    "src/ember/palettes.json",
    "palettes/ember.json",
    "palettes/ember.css",
    "docs/swatches/3400k-light.svg",
    "index.html",
)


def git_bytes(relative_path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{BASELINE_COMMIT}:{relative_path}"], cwd=ROOT)


def main() -> None:
    manifest = json.loads(git_bytes("palettes/ember.json"))
    family = manifest["families"]["3400k-light"]
    contract_fields = {
        key: value
        for key, value in family.items()
        if key.endswith("_target")
        or key
        in {
            "background_surface_count",
            "background_surface_values",
            "background_role_indices",
            "categorical_semantic_slots",
            "foreground_chroma_direction",
            "foreground_chroma_order_tolerance",
            "terminal_ansi_indices",
            "terminal_night_groups",
            "terminal_semantic_color_count",
            "terminal_daylight_color_count",
        }
    }
    payload = {
        "baseline_source_commit": BASELINE_COMMIT,
        "schema_version": manifest["schema_version"],
        "profile_gains": [1.0, 0.74, 0.53],
        "family": family,
        "source_contracts": {
            "manifest_quality_targets": manifest["quality_targets"],
            "profile_contract": manifest["profiles"]["3400k"],
            "family_contract_fields": contract_fields,
            "experiment_scope": {
                "required_render_backgrounds": ["bg_0", "bg_1"],
                "report_only_backgrounds": ["bg_2"],
                "categorical_bank_is_contract_scope": True,
                "cross_bank_checks_are_diagnostic_non_contract": True,
                "production_values_may_change": False,
            },
        },
        "production_artifacts": {
            path: {
                "sha256": hashlib.sha256(content := git_bytes(path)).hexdigest(),
                "bytes": len(content),
            }
            for path in ARTIFACTS
        },
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
