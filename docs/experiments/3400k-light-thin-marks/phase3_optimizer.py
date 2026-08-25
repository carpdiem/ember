"""Deterministic, evidence-gated Phase 3 categorical optimizer engine.

This experiment-only module never writes production palette or export files. Proposal
floats cross an immediate canonical Hex8 boundary; every metric is then recomputed from
the reparsed consumer bytes. Phase 3B may call :func:`run_search`, but Phase 3A only
exercises the frozen baseline, synthetic fixtures, and tiny temporary smoke runs.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import math
import multiprocessing
import os
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import colour
import numpy as np

from ember.color import (
    contrast_ratio,
    hex_to_srgb,
    oklab_to_srgb,
    srgb_to_hex,
    srgb_to_oklab,
    wcag_luminance,
)

ROLES = ("cat.one", "cat.two", "cat.three", "cat.four", "cat.five", "cat.six")
ROLE_NAMES = ("one", "two", "three", "four", "five", "six")
GATE_BACKGROUNDS = ("bg_0", "bg_1")
REPORT_BACKGROUND = "bg_2"
FOREGROUNDS = ("fg_0", "fg_1", "fg_2")
APPROVED_G1_HEAD = "922ba7faa45ccdb56e95356750d353c7602da78a"
CAPTURE_SOURCE_HEAD = "98d7ff9183fa91112583fd6fe8a1ed16fa90e157"
BASELINE_SOURCE_HEAD = "c4c25e480912f8f54cbd8c992c0b6eb520dc0b8f"
INPUT_FILENAMES = {
    "baseline": "baseline.json",
    "viewing": "viewing-conditions.json",
    "gain_grid": "gain-grid.json",
    "neutral": "neutral-confusability.json",
    "proxy": "proxy-calibration.json",
    "raster_ledger": "raster-baseline.json",
    "raster_masks": "raster-masks.json",
    "raster_observations": "raster-observations.json",
    "replay_receipt": "raster-verification.json",
    "replay_verifier": "g1_evidence_verify.py",
    "browser_probe": "review/g1-browser-probe.html",
}
PARETO_DIMENSIONS = (
    "transformed_pair_min",
    "commanded_pair_min",
    "neutral_min",
    "graphics_contrast_min",
    "raster_1_5_min",
    "raster_2_min",
    "raster_3_min",
    "max_commanded_deviation",
    "mean_commanded_deviation",
)
_MAXIMIZE = PARETO_DIMENSIONS[:7]
_MINIMIZE = PARETO_DIMENSIONS[7:]
_CANONICAL_HEX = __import__("re").compile(r"^#[0-9A-F]{6}$")
_CANONICAL_HASH = __import__("re").compile(r"^[0-9a-f]{64}$")
_REPLAY_CACHE: set[str] = set()
SEARCH_ALGORITHM_VERSION = "phase3-survivor-driven-v2"
SEARCH_MANIFEST_SCHEMA_VERSION = 2
MAX_COARSE_SURVIVORS = 5_000
MIN_REFINE_CANDIDATES = 500

_BROWSER_REQUEST_KEYS = {
    "schema_version",
    "request_kind",
    "candidate_id",
    "bank_kind",
    "serialized_bank",
    "serialized_bank_sha256",
    "input_chain_sha256",
    "search_contract_sha256",
    "frontier_manifest_sha256",
    "frontier_rank",
    "mask_set",
    "requested_roles",
    "requested_role_observations",
    "full_image_hash_used",
    "cvd_policy",
    "human_width_capacity",
}
_BROWSER_RESULT_KEYS = {
    "schema_version",
    "request_sha256",
    "candidate_id",
    "serialized_bank_sha256",
    "input_chain_sha256",
    "status",
    "observations",
    "full_image_hash_used",
    "human_width_capacity",
}


class AuthorizationError(RuntimeError):
    """Raised before proposal generation when committed G1 evidence is not exact."""


class FrozenInputError(RuntimeError):
    """Raised when a candidate mutates anything except the canonical categorical bank."""


class StaleArtifactError(RuntimeError):
    """Raised when an oracle or approval artifact is stale or tampered."""


@dataclass(frozen=True)
class Phase3Inputs:
    experiment_dir: Path
    baseline: dict[str, Any]
    viewing: dict[str, Any]
    gain_grid: dict[str, Any]
    neutral: dict[str, Any]
    proxy: dict[str, Any]
    raster_ledger: dict[str, Any]
    raster_masks: dict[str, Any]
    raster_observations: dict[str, Any]
    replay_receipt: dict[str, Any]
    source_paths: dict[str, Path]
    source_sha256: dict[str, str]


@dataclass(frozen=True)
class SearchJob:
    index: int
    seed: int


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain a JSON object")
    return value


def load_inputs(experiment_dir: Path) -> Phase3Inputs:
    experiment_dir = Path(experiment_dir).resolve()
    paths = {key: experiment_dir / name for key, name in INPUT_FILENAMES.items()}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise AuthorizationError(f"Phase 3 input files are missing: {missing}")
    payloads = {
        key: _load_json(path)
        for key, path in paths.items()
        if key not in {"replay_verifier", "browser_probe"}
    }
    return Phase3Inputs(
        experiment_dir=experiment_dir,
        baseline=payloads["baseline"],
        viewing=payloads["viewing"],
        gain_grid=payloads["gain_grid"],
        neutral=payloads["neutral"],
        proxy=payloads["proxy"],
        raster_ledger=payloads["raster_ledger"],
        raster_masks=payloads["raster_masks"],
        raster_observations=payloads["raster_observations"],
        replay_receipt=payloads["replay_receipt"],
        source_paths=paths,
        source_sha256={key: _sha256(path) for key, path in paths.items()},
    )


def frozen_non_categorical(baseline: Mapping[str, Any]) -> dict[str, Any]:
    frozen = deepcopy(dict(baseline))
    family = frozen.get("family")
    if not isinstance(family, dict) or "categorical" not in family:
        raise FrozenInputError("baseline lacks the canonical categorical bank")
    del family["categorical"]
    return frozen


def assert_only_categorical_changed(
    approved_baseline: Mapping[str, Any], candidate_baseline: Mapping[str, Any]
) -> None:
    if frozen_non_categorical(approved_baseline) != frozen_non_categorical(candidate_baseline):
        raise FrozenInputError("candidate changed a frozen non-categorical byte/value")
    categorical = candidate_baseline["family"].get("categorical", {})
    if tuple(categorical) != ROLE_NAMES:
        raise FrozenInputError("candidate must contain exactly the six canonical categorical roles")
    canonical_bank(categorical.values())
    if "categorical_line" in json.dumps(candidate_baseline, sort_keys=True):
        raise FrozenInputError(
            "categorical_line is forbidden; one dependent categorical bank is required"
        )


def input_chain_sha256(inputs: Phase3Inputs) -> str:
    return sha256_json(inputs.source_sha256)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise AuthorizationError(message)


def _git_blob_sha256(inputs: Phase3Inputs, revision: str, relative_path: str) -> str:
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=inputs.experiment_dir,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        payload = subprocess.run(
            ["git", "show", f"{revision}:{relative_path}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise AuthorizationError("approved G1 Git input chain cannot be resolved") from error
    return hashlib.sha256(payload).hexdigest()


def _validate_authorization_chain(inputs: Phase3Inputs) -> None:
    for key, path in inputs.source_paths.items():
        _require(_sha256(path) == inputs.source_sha256[key], f"{key} changed after input loading")

    proxy = inputs.proxy
    acceptance = proxy.get("acceptance", {})
    _require(proxy.get("status") == "PASS", "committed G1 evidence status is not PASS")
    _require(proxy.get("phase3_search_authorized") is True, "phase3_search_authorized is not true")
    _require(acceptance.get("status") == "PASS", "G1 acceptance status is not PASS")
    _require(
        acceptance.get("global_pooled_correlation", -math.inf)
        >= acceptance.get("minimum_global_pooled_correlation", 0.95),
        "G1 pooled correlation is absent or below its committed floor",
    )
    _require(
        acceptance.get("observed_gate_pair_background_mae_max_delta_e_ok", math.inf)
        <= acceptance.get("maximum_gate_pair_background_mae_delta_e_ok", 0.75),
        "G1 pair/background MAE is absent or above its committed ceiling",
    )
    _require(proxy.get("approved_head") == APPROVED_G1_HEAD, "proxy approved_head is stale")
    _require(
        proxy.get("baseline_source_commit") == BASELINE_SOURCE_HEAD,
        "proxy baseline source is not the approved baseline",
    )
    _require(
        inputs.baseline.get("baseline_source_commit") == BASELINE_SOURCE_HEAD,
        "baseline input source commit is stale",
    )

    evidence = proxy.get("evidence", {})
    evidence_keys = {
        "raster_ledger": "raster_ledger",
        "raster_masks": "raster_masks",
        "raster_observations": "raster_observations",
        "independent_replay": "replay_receipt",
    }
    for record_key, source_key in evidence_keys.items():
        record = evidence.get(record_key, {})
        _require(
            record.get("sha256") == inputs.source_sha256[source_key], f"{record_key} hash mismatch"
        )
        _require(
            record.get("file") == INPUT_FILENAMES[source_key], f"{record_key} filename mismatch"
        )
    replay_provenance = evidence["independent_replay"]
    _require(
        replay_provenance.get("verifier_file") == INPUT_FILENAMES["replay_verifier"],
        "replay verifier filename mismatch",
    )
    _require(
        replay_provenance.get("verifier_sha256") == inputs.source_sha256["replay_verifier"],
        "replay verifier hash mismatch",
    )

    provenance = proxy.get("provenance", {})
    _require(provenance.get("approved_head") == APPROVED_G1_HEAD, "G1 provenance head is stale")
    _require(
        provenance.get("validator_source_commit") == CAPTURE_SOURCE_HEAD,
        "capture validator source commit is stale",
    )
    for key in ("probe_sha256", "validator_sha256", "gstack_browse_binary_sha256"):
        value = provenance.get(key)
        _require(
            isinstance(value, str)
            and len(value) == 64
            and all(c in "0123456789abcdef" for c in value),
            f"{key} is not a SHA-256 digest",
        )
    _require(
        provenance["probe_sha256"] == inputs.source_sha256["browser_probe"],
        "browser probe hash mismatch",
    )

    receipt = inputs.replay_receipt
    _require(receipt.get("status") == "PASS", "independent replay receipt is not PASS")
    _require(
        receipt.get("approved_head") == APPROVED_G1_HEAD, "independent replay receipt is stale"
    )
    expected_counts = {
        "mask_records_verified": 720,
        "role_observations_verified": 21_600,
        "pair_rows_replayed": 32_400,
        "planned_id_mapping_rows_verified": 32_400,
    }
    for key, expected in expected_counts.items():
        _require(receipt.get(key) == expected, f"independent replay receipt {key} is invalid")
    receipt_provenance = receipt.get("provenance", {})
    for key, source_key in (
        ("raster_ledger_sha256", "raster_ledger"),
        ("raster_masks_sha256", "raster_masks"),
        ("raster_observations_sha256", "raster_observations"),
        ("verifier_sha256", "replay_verifier"),
    ):
        _require(
            receipt_provenance.get(key) == inputs.source_sha256[source_key],
            f"independent replay receipt {key} mismatch",
        )

    ledger = inputs.raster_ledger
    _require(
        ledger.get("phase3_search_authorized") is True, "raster ledger does not authorize search"
    )
    _require(
        ledger.get("approved_head") == APPROVED_G1_HEAD, "raster ledger approved head is stale"
    )
    _require(ledger.get("matrix_status") == "PASS", "raster ledger is incomplete")
    _require(ledger.get("observed_case_count") == 32_400, "raster ledger row count is invalid")
    approved_path = "docs/experiments/3400k-light-thin-marks/raster-baseline.json"
    approved_blob = _git_blob_sha256(inputs, APPROVED_G1_HEAD, approved_path)
    _require(
        provenance.get("approved_ledger_sha256") == approved_blob,
        "approved G1 implementation input hash mismatch",
    )


def _run_independent_replay(inputs: Phase3Inputs) -> None:
    cache_key = input_chain_sha256(inputs)
    if cache_key in _REPLAY_CACHE:
        return
    path = inputs.source_paths["replay_verifier"]
    spec = importlib.util.spec_from_file_location("phase3_g1_evidence_verify", path)
    if spec is None or spec.loader is None:
        raise AuthorizationError("independent G1 replay verifier cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        replayed = module.verify_evidence(evidence_dir=inputs.experiment_dir)
    except Exception as error:
        raise AuthorizationError(f"independent G1 evidence replay failed: {error}") from error
    _require(replayed == inputs.replay_receipt, "independent replay result differs from receipt")
    _REPLAY_CACHE.add(cache_key)


def authorize_search(inputs: Phase3Inputs, *, replay: bool = True) -> dict[str, Any]:
    """Fail closed unless the exact committed G1 evidence and replay chain are valid."""
    _validate_authorization_chain(inputs)
    if replay:
        _run_independent_replay(inputs)
    return {
        "schema_version": 1,
        "status": "PASS",
        "phase3_search_authorized": True,
        "approved_head": APPROVED_G1_HEAD,
        "input_chain_sha256": input_chain_sha256(inputs),
        "frozen_non_categorical_sha256": sha256_json(frozen_non_categorical(inputs.baseline)),
        "independent_replay_verified": replay or input_chain_sha256(inputs) in _REPLAY_CACHE,
    }


def parse_exact_hex8(value: str) -> np.ndarray:
    if not isinstance(value, str) or _CANONICAL_HEX.fullmatch(value) is None:
        raise ValueError(f"non-canonical Hex8 value: {value!r}")
    rgb = hex_to_srgb(value)
    if srgb_to_hex(rgb) != value:
        raise ValueError(f"Hex8 round-trip failed: {value!r}")
    return rgb


def canonical_bank(values: Iterable[str]) -> tuple[str, ...]:
    bank = tuple(values)
    if len(bank) != 6:
        raise ValueError("categorical bank must contain exactly six values")
    for value in bank:
        parse_exact_hex8(value)
    if len(set(bank)) != 6:
        raise ValueError("categorical bank contains duplicate exact Hex8 values")
    return bank


def bank_rgb(values: Iterable[str]) -> np.ndarray:
    return np.asarray([parse_exact_hex8(value) for value in canonical_bank(values)])


def bank_oklab(values: Iterable[str]) -> np.ndarray:
    return srgb_to_oklab(bank_rgb(values))


def quantize_proposal(
    proposal_oklab: Sequence[Sequence[float]],
) -> tuple[tuple[str, ...], np.ndarray]:
    proposal = np.asarray(proposal_oklab, dtype=float)
    if proposal.shape != (6, 3) or not np.all(np.isfinite(proposal)):
        raise ValueError("proposal must be a finite 6x3 Oklab array")
    srgb = oklab_to_srgb(proposal)
    # The repository's inverse matrices round-trip exact sRGB with <1e-7 numerical
    # residue at gamut boundaries. Reject substantive out-of-gamut proposals, then
    # quantize through the repository's clipping Hex8 consumer boundary.
    if np.any(srgb < -1e-6) or np.any(srgb > 1.0 + 1e-6):
        raise ValueError("proposal is outside the exact sRGB gamut")
    bank = canonical_bank(srgb_to_hex(row) for row in srgb)
    reparsed = bank_rgb(bank)
    return bank, reparsed


def bank_hash(bank: Iterable[str]) -> str:
    return sha256_json(list(canonical_bank(bank)))


def load_contract(path: Path) -> dict[str, Any]:
    return _load_json(Path(path))


def validate_search_contract(contract: Mapping[str, Any], inputs: Phase3Inputs) -> None:
    required = {
        "schema_version",
        "authorization",
        "bank",
        "input_sha256",
        "seed",
        "proposal_bounds",
        "hard_gates",
        "evaluation_ladder",
        "pareto_dimensions",
        "raster_proxy",
        "local_gain_refinement",
        "cvd",
        "threshold_policy",
    }
    if set(contract) != required:
        raise ValueError(f"search contract keys differ: {sorted(set(contract) ^ required)}")
    bank = contract["bank"]
    if bank != {"kind": "categorical", "role_order": list(ROLES), "count": 6}:
        raise ValueError("search contract must define exactly one canonical categorical bank")
    if contract["authorization"]["approved_g1_head"] != APPROVED_G1_HEAD:
        raise ValueError("search contract approved G1 head is stale")
    if contract["input_sha256"] != inputs.source_sha256:
        raise ValueError("search contract does not bind the exact input chain")
    if contract["pareto_dimensions"] != list(PARETO_DIMENSIONS):
        raise ValueError("search contract Pareto dimensions differ")
    if contract["cvd"] != {"report_only": True, "used_as_gate": False}:
        raise ValueError("CVD must remain strictly report-only")
    if contract["proposal_bounds"]["global_oklab"]["per_role_chroma_min"] is not None:
        raise ValueError("a universal per-role chroma floor is forbidden")


def _pairs(points: np.ndarray) -> tuple[np.ndarray, list[tuple[str, str]]]:
    indices = list(itertools.combinations(range(6), 2))
    distances = np.asarray([np.linalg.norm(points[a] - points[b]) for a, b in indices])
    return distances, [(ROLES[a], ROLES[b]) for a, b in indices]


def _hue_degrees(lab: np.ndarray) -> np.ndarray:
    return np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360.0


def _hue_delta(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def _failure(
    gate: str,
    actual: float | str,
    relation: str,
    threshold: float | str,
    *,
    scenario: str | None = None,
    roles: Sequence[str] = (),
    width: float | None = None,
) -> dict[str, Any]:
    return {
        "gate": gate,
        "actual": actual,
        "relation": relation,
        "threshold": threshold,
        "scenario": scenario,
        "roles": list(roles),
        "width_css_px": width,
    }


def gate_every_row(
    rows: Iterable[Mapping[str, Any]], *, metric: str, floor: float, gate: str
) -> list[dict[str, Any]]:
    failures = []
    for row in rows:
        actual = float(row[metric])
        if actual + 1e-12 < floor:
            failures.append(_failure(gate, actual, ">=", floor, scenario=str(row["id"])))
    return failures


def sampled_minimum(rows: Iterable[Mapping[str, Any]], metric: str) -> tuple[float, str]:
    values = [(float(row[metric]), str(row["id"])) for row in rows]
    if not values:
        raise ValueError("sampled minimum requires at least one row")
    return min(values)


def evaluate_gain_samples(
    samples: Iterable[Mapping[str, Any]], metric: Callable[[dict[str, Any]], float]
) -> list[dict[str, Any]]:
    return [dict(row, value=float(metric(dict(row)))) for row in samples]


def _baseline_bank(inputs: Phase3Inputs) -> tuple[str, ...]:
    categorical = inputs.baseline["family"]["categorical"]
    return tuple(categorical[name] for name in ROLE_NAMES)


def evaluate_cheap(
    values: Iterable[str], inputs: Phase3Inputs, contract: Mapping[str, Any]
) -> dict[str, Any]:
    bank = canonical_bank(values)
    rgb = bank_rgb(bank)
    lab = srgb_to_oklab(rgb)
    pair_values, pair_roles = _pairs(lab * 100.0)
    pair_index = int(np.argmin(pair_values))
    family = inputs.baseline["family"]
    neutral_rgb = np.asarray([parse_exact_hex8(family["surfaces"][name]) for name in FOREGROUNDS])
    neutral_lab = srgb_to_oklab(neutral_rgb)
    neutral_matrix = np.linalg.norm(lab[:, None] - neutral_lab[None, :], axis=2) * 100.0
    neutral_index = np.unravel_index(int(np.argmin(neutral_matrix)), neutral_matrix.shape)
    backgrounds = {
        name: parse_exact_hex8(family["surfaces"][name])
        for name in (*GATE_BACKGROUNDS, REPORT_BACKGROUND)
    }
    contrast_by_background = {
        name: min(contrast_ratio(color, background) for color in rgb)
        for name, background in backgrounds.items()
    }
    chroma = np.linalg.norm(lab[:, 1:], axis=1)
    hues = _hue_degrees(lab)
    failures: list[dict[str, Any]] = []
    bounds = contract["proposal_bounds"]
    global_bounds = bounds["global_oklab"]
    for index, role_bound in enumerate(bounds["roles"]):
        role = ROLES[index]
        for gate, actual, relation, threshold in (
            ("oklab-lightness-floor", lab[index, 0], ">=", role_bound["l_min"]),
            ("oklab-lightness-ceiling", lab[index, 0], "<=", role_bound["l_max"]),
            ("oklab-chroma-ceiling", chroma[index], "<=", global_bounds["chroma_max"]),
            (
                "role-hue-neighborhood",
                _hue_delta(hues[index], role_bound["hue_center_degrees"]),
                "<=",
                role_bound["hue_half_width_degrees"],
            ),
        ):
            failed = actual < threshold - 1e-12 if relation == ">=" else actual > threshold + 1e-12
            if failed:
                failures.append(
                    _failure(gate, float(actual), relation, float(threshold), roles=(role,))
                )
    mean_chroma = float(np.mean(chroma))
    for gate, actual, relation, threshold in (
        ("bank-mean-chroma-floor", mean_chroma, ">=", global_bounds["bank_mean_chroma_min"]),
        ("bank-mean-chroma-ceiling", mean_chroma, "<=", global_bounds["bank_mean_chroma_max"]),
        (
            "commanded-pair-distance",
            pair_values[pair_index],
            ">=",
            contract["hard_gates"]["commanded_pair_delta_e_ok"],
        ),
        (
            "commanded-neutral-separation",
            neutral_matrix[neutral_index],
            ">=",
            contract["hard_gates"]["neutral_delta_e_ok"],
        ),
        (
            "commanded-graphics-contrast",
            min(contrast_by_background[name] for name in GATE_BACKGROUNDS),
            ">=",
            contract["hard_gates"]["graphics_contrast_ratio"],
        ),
    ):
        failed = actual < threshold - 1e-12 if relation == ">=" else actual > threshold + 1e-12
        if failed:
            roles: tuple[str, ...] = ()
            if gate == "commanded-pair-distance":
                roles = pair_roles[pair_index]
            elif gate == "commanded-neutral-separation":
                roles = (ROLES[neutral_index[0]], FOREGROUNDS[neutral_index[1]])
            failures.append(_failure(gate, float(actual), relation, float(threshold), roles=roles))
    return {
        "serialized_bank_sha256": bank_hash(bank),
        "commanded_oklab": lab.tolist(),
        "lightness_by_role": lab[:, 0].tolist(),
        "chroma_by_role": chroma.tolist(),
        "hue_by_role_degrees": hues.tolist(),
        "mean_chroma": mean_chroma,
        "pair_min_delta_e_ok": float(pair_values[pair_index]),
        "pair_roles": list(pair_roles[pair_index]),
        "neutral_min_delta_e_ok": float(neutral_matrix[neutral_index]),
        "neutral_roles": [ROLES[neutral_index[0]], FOREGROUNDS[neutral_index[1]]],
        "graphics_contrast_by_background": contrast_by_background,
        "graphics_contrast_gate_min": min(
            contrast_by_background[name] for name in GATE_BACKGROUNDS
        ),
        "bg_2_policy": "report-only",
        "failures": failures,
    }


def evaluate_commanded_batch(
    banks: Sequence[Sequence[str]], inputs: Phase3Inputs
) -> dict[str, np.ndarray]:
    """Vectorized exact-Hex8 commanded metrics for coarse Phase 3B rejection."""
    if not banks:
        return {
            "pair_min_delta_e_ok": np.asarray([], dtype=float),
            "neutral_min_delta_e_ok": np.asarray([], dtype=float),
            "graphics_contrast_min": np.asarray([], dtype=float),
        }
    rgb = np.asarray([bank_rgb(bank) for bank in banks])
    lab = srgb_to_oklab(rgb)
    pair_indices = np.asarray(list(itertools.combinations(range(6), 2)), dtype=int)
    pair_delta = lab[:, pair_indices[:, 0]] - lab[:, pair_indices[:, 1]]
    pair_min = np.min(np.linalg.norm(pair_delta, axis=2) * 100.0, axis=1)
    surfaces = inputs.baseline["family"]["surfaces"]
    neutral = srgb_to_oklab(np.asarray([parse_exact_hex8(surfaces[name]) for name in FOREGROUNDS]))
    neutral_min = np.min(
        np.linalg.norm(lab[:, :, None] - neutral[None, None], axis=3) * 100.0, axis=(1, 2)
    )
    backgrounds = [parse_exact_hex8(surfaces[name]) for name in GATE_BACKGROUNDS]
    bank_luminance = wcag_luminance(rgb)
    background_luminance = wcag_luminance(np.asarray(backgrounds))
    lighter = np.maximum(bank_luminance[:, :, None], background_luminance[None, None, :])
    darker = np.minimum(bank_luminance[:, :, None], background_luminance[None, None, :])
    contrast_min = np.min((lighter + 0.05) / (darker + 0.05), axis=(1, 2))
    return {
        "pair_min_delta_e_ok": pair_min,
        "neutral_min_delta_e_ok": neutral_min,
        "graphics_contrast_min": contrast_min,
    }


def _viewing_scenarios(viewing: Mapping[str, Any], *, primary_only: bool) -> list[dict[str, Any]]:
    rows = []
    primary = viewing["primary"]
    for background, y_b in primary["Y_b"].items():
        rows.append(
            {
                "id": f"primary-dim-{background}",
                "family": "primary",
                "background": background,
                "surround": primary["surround"],
                "flare": primary["flare_fraction_of_Yw"],
                "l_a": primary["L_A_cd_m2"],
                "y_b": y_b,
            }
        )
    if primary_only:
        return rows
    sensitivity = viewing["sensitivity"]
    for l_a in sensitivity["L_A_cd_m2"]:
        for background, y_b in sensitivity["transformed_white_adapted_Y_b"].items():
            rows.append(
                {
                    "id": f"sensitivity-average-la-{l_a:g}-{background}",
                    "family": "sensitivity",
                    "background": background,
                    "surround": sensitivity["surround"],
                    "flare": sensitivity["flare_fraction_of_Yw"],
                    "l_a": l_a,
                    "y_b": y_b,
                }
            )
    return rows


def _gain_samples(inputs: Phase3Inputs, *, nominal_only: bool) -> list[dict[str, Any]]:
    if nominal_only:
        gains = inputs.viewing["transform"]["gains"]
        return [
            {"id": "nominal", "red_gain": gains[0], "green_gain": gains[1], "blue_gain": gains[2]}
        ]
    dedup: dict[tuple[float, float, float], dict[str, Any]] = {}
    for row in inputs.gain_grid["grid"]["samples"]:
        key = (float(row["red_gain"]), float(row["green_gain"]), float(row["blue_gain"]))
        dedup.setdefault(key, dict(row, id=row["name"]))
    return [dedup[key] for key in sorted(dedup)]


def _cam16_ucs(rgb: np.ndarray, scenario: Mapping[str, Any]) -> np.ndarray:
    xyz = np.asarray(colour.sRGB_to_XYZ(np.asarray(rgb, dtype=float)))
    white = np.asarray(colour.sRGB_to_XYZ(np.ones(3, dtype=float)))
    return np.asarray(
        colour.XYZ_to_CAM16UCS(
            xyz + float(scenario["flare"]) * white,
            XYZ_w=white,
            L_A=float(scenario["l_a"]),
            Y_b=float(scenario["y_b"]),
            surround=colour.VIEWING_CONDITIONS_CAM16[str(scenario["surround"])],
        )
    )


def evaluate_transformed(
    values: Iterable[str],
    inputs: Phase3Inputs,
    contract: Mapping[str, Any],
    *,
    full_grid: bool,
) -> dict[str, Any]:
    bank = canonical_bank(values)
    rgb = bank_rgb(bank)
    family = inputs.baseline["family"]
    neutral_rgb = np.asarray([parse_exact_hex8(family["surfaces"][name]) for name in FOREGROUNDS])
    backgrounds = {
        name: parse_exact_hex8(family["surfaces"][name])
        for name in (*GATE_BACKGROUNDS, REPORT_BACKGROUND)
    }
    scenarios = _viewing_scenarios(inputs.viewing, primary_only=not full_grid)
    gains = _gain_samples(inputs, nominal_only=not full_grid)
    rows = []
    failures: list[dict[str, Any]] = []
    for scenario in scenarios:
        for gain in gains:
            gain_values = np.asarray(
                [gain["red_gain"], gain["green_gain"], gain["blue_gain"]], dtype=float
            )
            transformed = np.clip(rgb * gain_values, 0.0, 1.0)
            transformed_neutral = np.clip(neutral_rgb * gain_values, 0.0, 1.0)
            transformed_background = np.clip(
                backgrounds[scenario["background"]] * gain_values, 0.0, 1.0
            )
            ucs = _cam16_ucs(transformed, scenario)
            neutral_ucs = _cam16_ucs(transformed_neutral, scenario)
            pair_values, pair_roles = _pairs(ucs)
            pair_index = int(np.argmin(pair_values))
            neutral_matrix = np.linalg.norm(ucs[:, None] - neutral_ucs[None, :], axis=2)
            neutral_index = np.unravel_index(int(np.argmin(neutral_matrix)), neutral_matrix.shape)
            contrast = min(contrast_ratio(color, transformed_background) for color in transformed)
            row_id = f"{scenario['id']}/{gain['id']}"
            row = {
                "id": row_id,
                "scenario": scenario["id"],
                "scenario_family": scenario["family"],
                "background": scenario["background"],
                "background_policy": "gate"
                if scenario["background"] in GATE_BACKGROUNDS
                else "report-only",
                "gain_sample": gain["id"],
                "gains": gain_values.tolist(),
                "pair_min_cam16_ucs": float(pair_values[pair_index]),
                "pair_roles": list(pair_roles[pair_index]),
                "neutral_min_cam16_ucs": float(neutral_matrix[neutral_index]),
                "neutral_roles": [ROLES[neutral_index[0]], FOREGROUNDS[neutral_index[1]]],
                "graphics_contrast": float(contrast),
                "j_prime_min": float(np.min(ucs[:, 0])),
                "j_prime_max": float(np.max(ucs[:, 0])),
                "m_prime_max": float(np.max(np.linalg.norm(ucs[:, 1:], axis=1))),
            }
            rows.append(row)
            if (
                scenario["background"] in GATE_BACKGROUNDS
                and contrast + 1e-12 < contract["hard_gates"]["graphics_contrast_ratio"]
            ):
                failures.append(
                    _failure(
                        "transformed-graphics-contrast",
                        contrast,
                        ">=",
                        contract["hard_gates"]["graphics_contrast_ratio"],
                        scenario=row_id,
                    )
                )
    pair_min, pair_binding = sampled_minimum(rows, "pair_min_cam16_ucs")
    neutral_min, neutral_binding = sampled_minimum(rows, "neutral_min_cam16_ucs")
    contrast_min, contrast_binding = sampled_minimum(
        [row for row in rows if row["background_policy"] == "gate"], "graphics_contrast"
    )
    return {
        "grid_kind": "full-45-gain-all-viewing-sensitivities" if full_grid else "primary-nominal",
        "scenario_policy": "report separately; never average",
        "rows": rows,
        "summary": {
            "sampled_pair_min_cam16_ucs": pair_min,
            "pair_binding_row": pair_binding,
            "sampled_neutral_min_cam16_ucs": neutral_min,
            "neutral_binding_row": neutral_binding,
            "sampled_graphics_contrast_min": contrast_min,
            "graphics_contrast_binding_row": contrast_binding,
            "claim": "sampled minimum; not a continuous worst case",
        },
        "local_refinement": {"status": "NOT_TRIGGERED", "rows": []},
        "failures": failures,
    }


def _gate_transformed_against_baseline(
    transformed: dict[str, Any], baseline: Mapping[str, Any], contract: Mapping[str, Any]
) -> None:
    baseline_rows = {row["id"]: row for row in baseline["rows"]}
    pair_ratio = float(contract["hard_gates"]["transformed_pair_baseline_ratio"])
    neutral_ratio = float(contract["hard_gates"]["transformed_neutral_baseline_ratio"])
    for row in transformed["rows"]:
        base = baseline_rows[row["id"]]
        checks = (
            (
                "transformed-pair-baseline-floor",
                row["pair_min_cam16_ucs"],
                ">=",
                pair_ratio * base["pair_min_cam16_ucs"],
                row["pair_roles"],
            ),
            (
                "transformed-neutral-baseline-floor",
                row["neutral_min_cam16_ucs"],
                ">=",
                neutral_ratio * base["neutral_min_cam16_ucs"],
                row["neutral_roles"],
            ),
            ("cam16-j-prime-floor", row["j_prime_min"], ">=", base["j_prime_min"], ()),
            ("cam16-j-prime-ceiling", row["j_prime_max"], "<=", 1.05 * base["j_prime_max"], ()),
            ("cam16-m-prime-ceiling", row["m_prime_max"], "<=", 1.10 * base["m_prime_max"], ()),
        )
        for gate, actual, relation, threshold, roles in checks:
            failed = actual < threshold - 1e-12 if relation == ">=" else actual > threshold + 1e-12
            if failed:
                transformed["failures"].append(
                    _failure(
                        gate,
                        float(actual),
                        relation,
                        float(threshold),
                        scenario=row["id"],
                        roles=roles,
                    )
                )


def _one_transformed_pair_min(
    bank: tuple[str, ...], scenario: Mapping[str, Any], gains: Mapping[str, float]
) -> float:
    gain = np.asarray([gains["red_gain"], gains["green_gain"], gains["blue_gain"]], dtype=float)
    ucs = _cam16_ucs(np.clip(bank_rgb(bank) * gain, 0.0, 1.0), scenario)
    return float(np.min(_pairs(ucs)[0]))


def _maybe_refine_binding_gain(
    bank: tuple[str, ...],
    transformed: dict[str, Any],
    baseline: Mapping[str, Any],
    inputs: Phase3Inputs,
    contract: Mapping[str, Any],
) -> None:
    if transformed["grid_kind"] != "full-45-gain-all-viewing-sensitivities":
        return
    baseline_rows = {row["id"]: row for row in baseline["rows"]}
    ratio = float(contract["hard_gates"]["transformed_pair_baseline_ratio"])
    margins = []
    for row in transformed["rows"]:
        floor = ratio * baseline_rows[row["id"]]["pair_min_cam16_ucs"]
        margins.append(((row["pair_min_cam16_ucs"] - floor) / floor, row))
    margin, binding = min(margins, key=lambda item: (item[0], item[1]["id"]))
    trigger = float(contract["local_gain_refinement"]["trigger_fraction_above_floor"])
    if margin > trigger:
        transformed["local_refinement"] = {
            "status": "NOT_TRIGGERED",
            "binding_row": binding["id"],
            "margin_fraction": float(margin),
            "trigger_fraction": trigger,
            "rows": [],
        }
        return
    scenario = next(
        row
        for row in _viewing_scenarios(inputs.viewing, primary_only=False)
        if row["id"] == binding["scenario"]
    )
    gain_rows = _gain_samples(inputs, nominal_only=False)
    green_axis = sorted({float(row["green_gain"]) for row in gain_rows})
    blue_axis = sorted({float(row["blue_gain"]) for row in gain_rows})

    def adjacent(axis: list[float], value: float) -> tuple[float, float]:
        position = min(range(len(axis)), key=lambda index: (abs(axis[index] - value), index))
        left = axis[max(0, position - 1)]
        right = axis[min(len(axis) - 1, position + 1)]
        return left, right

    binding_gain = {
        "red_gain": binding["gains"][0],
        "green_gain": binding["gains"][1],
        "blue_gain": binding["gains"][2],
    }
    refinement = local_gain_refinement(
        binding_gain,
        {
            "green": adjacent(green_axis, binding_gain["green_gain"]),
            "blue": adjacent(blue_axis, binding_gain["blue_gain"]),
        },
        lambda gains: _one_transformed_pair_min(bank, scenario, gains),
    )
    refinement.update(
        {
            "status": "TRIGGERED",
            "binding_row": binding["id"],
            "margin_fraction": float(margin),
            "trigger_fraction": trigger,
        }
    )
    transformed["local_refinement"] = refinement


def _mask_summaries(inputs: Phase3Inputs) -> dict[tuple[Any, ...], dict[int, float]]:
    grouped: dict[tuple[Any, ...], dict[int, float]] = {}
    for record in inputs.raster_masks["records"]:
        key = record["key"]
        geometry = (
            float(key["width_css_px"]),
            key["style"],
            key["orientation"],
            int(key["dpr"]),
            tuple(float(value) for value in key["phase_css_px"]),
        )
        coverage = float(np.median([sample[5] for sample in record["samples"]]))
        grouped.setdefault(geometry, {})[int(key["lane"])] = coverage
    if len(inputs.raster_masks["records"]) != 720 or len(grouped) != 360:
        raise AuthorizationError(
            "G1 mask geometry count differs from the approved 720/360 contract"
        )
    if any(set(lanes) != {0, 1} for lanes in grouped.values()):
        raise AuthorizationError("G1 mask geometry is missing a lane")
    return grouped


def evaluate_raster_proxy(
    values: Iterable[str], inputs: Phase3Inputs, contract: Mapping[str, Any]
) -> dict[str, Any]:
    bank = canonical_bank(values)
    rgb = bank_rgb(bank)
    surfaces = inputs.baseline["family"]["surfaces"]
    backgrounds = {
        name: parse_exact_hex8(surfaces[name]) for name in (*GATE_BACKGROUNDS, REPORT_BACKGROUND)
    }
    nominal = np.asarray(inputs.viewing["transform"]["gains"], dtype=float)
    minima: dict[str, tuple[float, str] | None] = {"1.5": None, "2": None, "3": None}
    margin = float(contract["raster_proxy"]["calibrated_error_margin_delta_e_ok"])
    for geometry, lanes in sorted(_mask_summaries(inputs).items()):
        width, style, orientation, dpr, phase = geometry
        width_key = f"{width:g}"
        for state in ("commanded", "transformed"):
            gains = np.ones(3) if state == "commanded" else nominal
            for background_name, background in backgrounds.items():
                points = []
                for lane in (0, 1):
                    coverage = lanes[lane]
                    composite = coverage * rgb + (1.0 - coverage) * background
                    points.append(srgb_to_oklab(np.clip(composite * gains, 0.0, 1.0)))
                for left, right in itertools.combinations(range(6), 2):
                    distance = float(np.linalg.norm(points[0][left] - points[1][right]) * 100.0)
                    calibrated = distance - margin
                    binding = (
                        f"{state}/{background_name}/{style}/{orientation}/dpr-{dpr}/"
                        f"phase-{phase[0]:g}-{phase[1]:g}/{ROLES[left]}-{ROLES[right]}"
                    )
                    current = minima[width_key]
                    if current is None or (calibrated, binding) < current:
                        minima[width_key] = (calibrated, binding)
    return {
        "mask_source": INPUT_FILENAMES["raster_masks"],
        "mask_sha256": inputs.source_sha256["raster_masks"],
        "mask_count": len(inputs.raster_masks["records"]),
        "geometry_count": 360,
        "rerasterized": False,
        "calibrated_error_margin_delta_e_ok": margin,
        "minimum_pair_by_width": {
            key: {"calibrated_delta_e_ok": value[0], "binding_row": value[1]}
            for key, value in minima.items()
            if value is not None
        },
        "claim": "calibrated raster-proxy sampled minimum over every approved G1 mask geometry",
    }


def _deviation(bank: tuple[str, ...], inputs: Phase3Inputs) -> tuple[float, float]:
    values = np.linalg.norm(bank_oklab(bank) - bank_oklab(_baseline_bank(inputs)), axis=1) * 100.0
    return float(np.max(values)), float(np.mean(values))


def _candidate_id(bank: tuple[str, ...], inputs: Phase3Inputs, contract: Mapping[str, Any]) -> str:
    return sha256_json(
        {
            "schema_version": 1,
            "ordered_bank_sha256": bank_hash(bank),
            "search_contract_sha256": sha256_json(contract),
            "frozen_non_categorical_sha256": sha256_json(frozen_non_categorical(inputs.baseline)),
        }
    )


def evaluate_candidate(
    values: Iterable[str],
    inputs: Phase3Inputs,
    contract: Mapping[str, Any],
    *,
    stage: Literal["cheap", "primary", "full"] = "full",
    cvd_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validate_search_contract(contract, inputs)
    bank = canonical_bank(values)
    cheap = evaluate_cheap(bank, inputs, contract)
    primary = (
        evaluate_transformed(bank, inputs, contract, full_grid=False) if stage != "cheap" else None
    )
    full = evaluate_transformed(bank, inputs, contract, full_grid=True) if stage == "full" else None
    if primary is not None:
        baseline_primary = (
            primary
            if bank == _baseline_bank(inputs)
            else evaluate_transformed(_baseline_bank(inputs), inputs, contract, full_grid=False)
        )
        _gate_transformed_against_baseline(primary, baseline_primary, contract)
    if full is not None:
        baseline_full = (
            full
            if bank == _baseline_bank(inputs)
            else evaluate_transformed(_baseline_bank(inputs), inputs, contract, full_grid=True)
        )
        _gate_transformed_against_baseline(full, baseline_full, contract)
        _maybe_refine_binding_gain(bank, full, baseline_full, inputs, contract)
    raster = evaluate_raster_proxy(bank, inputs, contract) if stage == "full" else None
    transformed = full or primary
    max_deviation, mean_deviation = _deviation(bank, inputs)
    graphics = cheap["graphics_contrast_gate_min"]
    neutral = cheap["neutral_min_delta_e_ok"]
    transformed_pair = cheap["pair_min_delta_e_ok"]
    failures = list(cheap["failures"])
    if transformed is not None:
        transformed_pair = transformed["summary"]["sampled_pair_min_cam16_ucs"]
        neutral = min(neutral, transformed["summary"]["sampled_neutral_min_cam16_ucs"])
        graphics = min(graphics, transformed["summary"]["sampled_graphics_contrast_min"])
        failures.extend(transformed["failures"])
    raster_values: dict[str, float | None] = {"1.5": None, "2": None, "3": None}
    if raster is not None:
        raster_values = {
            key: row["calibrated_delta_e_ok"]
            for key, row in raster["minimum_pair_by_width"].items()
        }
    pareto = {
        "transformed_pair_min": transformed_pair,
        "commanded_pair_min": cheap["pair_min_delta_e_ok"],
        "neutral_min": neutral,
        "graphics_contrast_min": graphics,
        "raster_1_5_min": raster_values["1.5"],
        "raster_2_min": raster_values["2"],
        "raster_3_min": raster_values["3"],
        "max_commanded_deviation": max_deviation,
        "mean_commanded_deviation": mean_deviation,
    }
    baseline = bank == _baseline_bank(inputs)
    return {
        "schema_version": 1,
        "row_kind": "baseline" if baseline else "candidate",
        "candidate_id": _candidate_id(bank, inputs, contract),
        "bank_kind": "categorical",
        "role_order": list(ROLES),
        "serialized_bank": list(bank),
        "serialized_bank_sha256": bank_hash(bank),
        "input_chain_sha256": input_chain_sha256(inputs),
        "search_contract_sha256": sha256_json(contract),
        "evaluation_stage": stage,
        "cheap": cheap,
        "primary": primary,
        "full": full,
        "raster_proxy": raster,
        "pareto": pareto,
        "failures": failures,
        "strict_pareto_improvement": False,
        "cvd": {
            "report_only": True,
            "used_as_gate": False,
            "metrics": dict(cvd_report or {}),
        },
        "browser_oracle_status": "NOT_RUN",
    }


def is_strict_pareto_improvement(
    candidate: Mapping[str, float], baseline: Mapping[str, float]
) -> bool:
    no_regression = all(candidate[key] >= baseline[key] for key in _MAXIMIZE) and all(
        candidate[key] <= baseline[key] for key in _MINIMIZE
    )
    strict = any(candidate[key] > baseline[key] for key in _MAXIMIZE) or any(
        candidate[key] < baseline[key] for key in _MINIMIZE
    )
    return no_regression and strict


def dedupe_candidate_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    chosen: dict[str, dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        key = str(row["serialized_bank_sha256"])
        current = chosen.get(key)
        if current is None or str(row["candidate_id"]) < str(current["candidate_id"]):
            chosen[key] = row
    return sorted(chosen.values(), key=lambda row: str(row["candidate_id"]))


def _protected_hard_gates_nonregressed(
    candidate: Mapping[str, Any], baseline: Mapping[str, Any]
) -> bool:
    if candidate.get("evaluation_stage") != "full" or baseline.get("evaluation_stage") != "full":
        return False
    candidate_rows = {row["id"]: row for row in candidate["full"]["rows"]}
    baseline_rows = {row["id"]: row for row in baseline["full"]["rows"]}
    if candidate_rows.keys() != baseline_rows.keys():
        return False
    for identifier, base in baseline_rows.items():
        row = candidate_rows[identifier]
        for metric in ("pair_min_cam16_ucs", "neutral_min_cam16_ucs"):
            if row[metric] + 1e-12 < base[metric]:
                return False
        if (
            base["background_policy"] == "gate"
            and row["graphics_contrast"] + 1e-12 < base["graphics_contrast"]
        ):
            return False
    return True


def pareto_front(
    rows: Iterable[Mapping[str, Any]], baseline: Mapping[str, Any]
) -> list[dict[str, Any]]:
    feasible = [dict(row) for row in dedupe_candidate_rows(rows) if not row.get("failures")]
    baseline_metrics = baseline["pareto"]
    for row in feasible:
        row["strict_pareto_improvement"] = _protected_hard_gates_nonregressed(
            row, baseline
        ) and is_strict_pareto_improvement(row["pareto"], baseline_metrics)

    def dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        lm, rm = left["pareto"], right["pareto"]
        nonworse = all(lm[key] >= rm[key] for key in _MAXIMIZE) and all(
            lm[key] <= rm[key] for key in _MINIMIZE
        )
        better = any(lm[key] > rm[key] for key in _MAXIMIZE) or any(
            lm[key] < rm[key] for key in _MINIMIZE
        )
        return nonworse and better

    front = [
        row
        for row in feasible
        if not any(dominates(other, row) for other in feasible if other is not row)
    ]
    ranked = sorted(
        front,
        key=lambda row: (
            tuple(-row["pareto"][key] for key in _MAXIMIZE)
            + tuple(row["pareto"][key] for key in _MINIMIZE)
            + (row["candidate_id"],)
        ),
    )
    anchor = dict(baseline)
    anchor["strict_pareto_improvement"] = False
    return [anchor, *[row for row in ranked if row["candidate_id"] != anchor["candidate_id"]]]


def local_gain_refinement(
    binding_gain: Mapping[str, float],
    cell_bounds: Mapping[str, Sequence[float]],
    evaluator: Callable[[dict[str, float]], float],
) -> dict[str, Any]:
    """Evaluate the declared deterministic 5x5 subgrid around a sampled binding point."""
    green_bounds = cell_bounds["green"]
    blue_bounds = cell_bounds["blue"]
    if len(green_bounds) != 2 or len(blue_bounds) != 2:
        raise ValueError("local refinement requires two-value green/blue cell bounds")
    green = np.linspace(float(green_bounds[0]), float(green_bounds[1]), 5)
    blue = np.linspace(float(blue_bounds[0]), float(blue_bounds[1]), 5)
    rows = []
    for green_gain in green:
        for blue_gain in blue:
            sample = {
                "red_gain": float(binding_gain.get("red_gain", 1.0)),
                "green_gain": float(green_gain),
                "blue_gain": float(blue_gain),
            }
            rows.append(dict(sample, value=float(evaluator(sample))))
    binding = min(rows, key=lambda row: (row["value"], row["green_gain"], row["blue_gain"]))
    return {
        "design": "deterministic 5 x 5 local subgrid",
        "sample_count": 25,
        "sampled_minimum": binding,
        "continuous_worst_case_claim": False,
    }


def _browser_observations(inputs: Phase3Inputs) -> list[dict[str, str]]:
    observations = []
    for mask in sorted(inputs.raster_masks["records"], key=lambda row: row["id"]):
        for state in ("commanded", "transformed"):
            for background in (*GATE_BACKGROUNDS, REPORT_BACKGROUND):
                for role in ROLES:
                    observations.append(
                        {
                            "id": f"{mask['id']}/{state}/{background}/{role}",
                            "mask_id": mask["id"],
                            "state": state,
                            "background": background,
                            "role": role,
                        }
                    )
    return observations


def validate_browser_oracle_request(
    request: Mapping[str, Any], inputs: Phase3Inputs, contract: Mapping[str, Any]
) -> None:
    authorize_search(inputs, replay=True)
    if set(request) != _BROWSER_REQUEST_KEYS or request.get("schema_version") != 2:
        raise StaleArtifactError("browser request schema version/keys are invalid")
    if request.get("bank_kind") != "categorical" or request.get("requested_roles") != list(ROLES):
        raise StaleArtifactError("browser request bank/role contract is tampered")
    try:
        serialized_hash = bank_hash(request.get("serialized_bank", ()))
    except (TypeError, ValueError) as error:
        raise StaleArtifactError("browser request serialized bank is invalid") from error
    if request.get("serialized_bank_sha256") != serialized_hash:
        raise StaleArtifactError("browser request serialized bank hash is tampered")
    if request.get("input_chain_sha256") != input_chain_sha256(inputs):
        raise StaleArtifactError("browser request input chain is stale")
    if request.get("search_contract_sha256") != sha256_json(contract):
        raise StaleArtifactError("browser request search contract is stale")
    for key in ("frontier_manifest_sha256",):
        value = request.get(key)
        if not isinstance(value, str) or _CANONICAL_HASH.fullmatch(value) is None:
            raise StaleArtifactError(f"browser request {key} is invalid")
    request_kind = request.get("request_kind")
    rank = request.get("frontier_rank")
    if request_kind == "frontier-candidate":
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
            raise StaleArtifactError("browser request frontier rank is invalid")
    elif request_kind == "baseline-reference":
        if rank != 0:
            raise StaleArtifactError("baseline reference must use frontier rank zero")
    else:
        raise StaleArtifactError("browser request kind is invalid")
    mask_set = request.get("mask_set", {})
    if mask_set != {
        "file": INPUT_FILENAMES["raster_masks"],
        "sha256": inputs.source_sha256["raster_masks"],
        "count": 720,
        "rerasterize": False,
    }:
        raise StaleArtifactError("browser request G1 mask set is stale or requests rerasterization")
    if request.get("requested_role_observations") != _browser_observations(inputs):
        raise StaleArtifactError("browser request role-observation enumeration is tampered")
    if (
        request.get("full_image_hash_used") is not False
        or request.get("human_width_capacity") is not None
    ):
        raise StaleArtifactError("browser request makes a forbidden image/human-capacity claim")


def build_browser_oracle_request(
    candidate: Mapping[str, Any],
    inputs: Phase3Inputs,
    contract: Mapping[str, Any],
    *,
    finalist_rank: int,
    frontier: Mapping[str, Any],
    reference: bool = False,
) -> dict[str, Any]:
    authorize_search(inputs, replay=True)
    validate_frontier_manifest(frontier, inputs, contract)
    if candidate["input_chain_sha256"] != input_chain_sha256(inputs):
        raise StaleArtifactError("candidate input chain is stale")
    if candidate.get("search_contract_sha256") != sha256_json(contract):
        raise StaleArtifactError("candidate search contract is stale")
    if candidate["serialized_bank_sha256"] != bank_hash(candidate["serialized_bank"]):
        raise StaleArtifactError("candidate bank hash is tampered")
    if candidate.get("candidate_id") != _candidate_id(
        canonical_bank(candidate["serialized_bank"]), inputs, contract
    ):
        raise StaleArtifactError("candidate ID is stale or tampered")
    baseline_id = frontier["baseline_candidate_id"]
    if reference:
        if candidate.get("row_kind") != "baseline" or candidate["candidate_id"] != baseline_id:
            raise StaleArtifactError("only the exact frontier baseline may be a reference request")
        if finalist_rank != 0:
            raise ValueError("baseline reference rank must be zero")
        request_kind = "baseline-reference"
    else:
        ranked = frontier["ranked_candidate_ids"]
        if (
            candidate.get("row_kind") != "candidate"
            or candidate.get("evaluation_stage") != "full"
            or candidate.get("failures")
            or canonical_bank(candidate["serialized_bank"]) == _baseline_bank(inputs)
        ):
            raise StaleArtifactError("browser candidates must be failure-free full evaluations")
        if finalist_rank < 1 or finalist_rank > len(ranked):
            raise ValueError("finalist_rank is outside the exact frontier")
        if ranked[finalist_rank - 1] != candidate["candidate_id"]:
            raise StaleArtifactError("candidate/rank is not bound to the exact frontier")
        request_kind = "frontier-candidate"
    request = {
        "schema_version": 2,
        "request_kind": request_kind,
        "candidate_id": candidate["candidate_id"],
        "bank_kind": "categorical",
        "serialized_bank": candidate["serialized_bank"],
        "serialized_bank_sha256": candidate["serialized_bank_sha256"],
        "input_chain_sha256": input_chain_sha256(inputs),
        "search_contract_sha256": sha256_json(contract),
        "frontier_manifest_sha256": sha256_json(frontier),
        "frontier_rank": finalist_rank,
        "mask_set": {
            "file": INPUT_FILENAMES["raster_masks"],
            "sha256": inputs.source_sha256["raster_masks"],
            "count": 720,
            "rerasterize": False,
        },
        "requested_roles": list(ROLES),
        "requested_role_observations": _browser_observations(inputs),
        "full_image_hash_used": False,
        "cvd_policy": "report-only",
        "human_width_capacity": None,
    }
    validate_browser_oracle_request(request, inputs, contract)
    return request


def validate_browser_oracle_result(result: Mapping[str, Any], request: Mapping[str, Any]) -> None:
    if set(result) != _BROWSER_RESULT_KEYS or result.get("schema_version") != 2:
        raise StaleArtifactError("browser result schema version/keys are invalid")
    if result.get("request_sha256") != sha256_json(request):
        raise StaleArtifactError("browser result request hash is stale or tampered")
    for key in ("candidate_id", "serialized_bank_sha256", "input_chain_sha256"):
        if result.get(key) != request.get(key):
            raise StaleArtifactError(f"browser result {key} is stale or tampered")
    if result.get("full_image_hash_used") is not False:
        raise StaleArtifactError("browser result may not use full-image hashes as a metric")
    if result.get("human_width_capacity") is not None:
        raise StaleArtifactError("browser result cannot assign human width capacity")
    if result.get("status") not in {"PASS", "FAIL", "ERROR"}:
        raise StaleArtifactError("browser result status is invalid")
    observations = result.get("observations")
    requested = request.get("requested_role_observations")
    if not isinstance(observations, list) or not isinstance(requested, list):
        raise StaleArtifactError("browser result observations are invalid")
    expected_ids = [row["id"] for row in requested]
    observed_ids = [row.get("request_observation_id") for row in observations]
    if observed_ids != expected_ids:
        raise StaleArtifactError(
            "browser result observation enumeration is incomplete or reordered"
        )
    statuses = []
    for row in observations:
        if set(row) != {"request_observation_id", "status", "sample_count", "observed_rgb8_median"}:
            raise StaleArtifactError("browser result observation shape is invalid")
        status = row["status"]
        sample_count = row["sample_count"]
        rgb = row["observed_rgb8_median"]
        if status not in {"PASS", "FAIL", "ERROR"}:
            raise StaleArtifactError("browser result observation status is invalid")
        if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 0:
            raise StaleArtifactError("browser result observation sample count is invalid")
        if rgb is not None and (
            not isinstance(rgb, list)
            or len(rgb) != 3
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                or value > 255
                for value in rgb
            )
        ):
            raise StaleArtifactError("browser result observation RGB8 median is invalid")
        if status == "PASS" and (sample_count < 1 or rgb is None):
            raise StaleArtifactError("passing browser observation lacks sampled RGB8 evidence")
        statuses.append(status)
    expected_status = "ERROR" if "ERROR" in statuses else "FAIL" if "FAIL" in statuses else "PASS"
    if result["status"] != expected_status:
        raise StaleArtifactError("browser result aggregate status disagrees with observations")


def validate_approval_freeze(
    receipt: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
    frontier: Mapping[str, Any],
    browser_result: Mapping[str, Any],
    inputs: Phase3Inputs,
    contract: Mapping[str, Any],
) -> None:
    if (
        receipt.get("status") != "APPROVED"
        or receipt.get("production_promotion_authorized") is not False
    ):
        raise StaleArtifactError("G2 approval status/promotion boundary is invalid")
    expected = {
        "candidate_id": candidate["candidate_id"],
        "serialized_bank_sha256": candidate["serialized_bank_sha256"],
        "candidate_artifact_sha256": sha256_json(candidate),
        "frontier_manifest_sha256": sha256_json(frontier),
        "browser_result_sha256": sha256_json(browser_result),
        "input_chain_sha256": input_chain_sha256(inputs),
        "search_contract_sha256": sha256_json(contract),
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise StaleArtifactError(f"approval/hash-freeze receipt {key} is stale or tampered")
    for key in ("schema_bundle_sha256", "replay_sha256"):
        value = receipt.get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise StaleArtifactError(f"approval/hash-freeze receipt {key} is invalid")


def make_search_jobs(*, seed: int, count: int, chunk_size: int) -> list[SearchJob]:
    if seed < 0 or count < 0 or chunk_size < 1:
        raise ValueError("seed/count/chunk_size are out of range")
    jobs = []
    for index in range(count):
        digest = hashlib.sha256(f"phase3:{seed}:{index}".encode()).digest()
        jobs.append(SearchJob(index=index, seed=int.from_bytes(digest[:8], "big")))
    return jobs


def merge_chunk_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Merge deterministic shards without colliding equal job indices from different runs."""
    rows = [dict(row) for row in records]
    by_index: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        key = (int(row.get("run_seed", 0)), int(row["job_index"]))
        current = by_index.get(key)
        if current is None or str(row["candidate_id"]) < str(current["candidate_id"]):
            by_index[key] = row
    return [by_index[key] for key in sorted(by_index)]


def _git_root(experiment_dir: Path) -> Path:
    try:
        value = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=experiment_dir,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise AuthorizationError("Git root cannot be resolved for the output guard") from error
    return Path(value).resolve()


def validate_external_output_path(output_dir: Path, inputs: Phase3Inputs) -> Path:
    """Reject lexical or symlink-resolved output anywhere inside the repository."""
    root = _git_root(inputs.experiment_dir)
    raw = Path(output_dir).expanduser()
    lexical = Path(os.path.abspath(raw))
    resolved = raw.resolve(strict=False)
    if root == lexical or root in lexical.parents or root == resolved or root in resolved.parents:
        raise ValueError("search output must be external to the entire Git repository")
    return resolved


def _proposal_context(inputs: Phase3Inputs, contract: Mapping[str, Any]) -> dict[str, Any]:
    baseline = _baseline_bank(inputs)
    cheap = evaluate_cheap(baseline, inputs, contract)
    role_index = {role: index for index, role in enumerate(ROLES)}
    pair = tuple(role_index[role] for role in cheap["pair_roles"])
    neutral = role_index[cheap["neutral_roles"][0]]
    rgb = bank_rgb(baseline)
    surfaces = inputs.baseline["family"]["surfaces"]
    backgrounds = [parse_exact_hex8(surfaces[name]) for name in GATE_BACKGROUNDS]
    contrast_by_role = np.asarray(
        [min(contrast_ratio(color, background) for background in backgrounds) for color in rgb]
    )
    return {
        "baseline_bank": baseline,
        "baseline_lab": bank_oklab(baseline),
        "binding_pair": pair,
        "binding_neutral": neutral,
        "binding_contrast": int(np.argmin(contrast_by_role)),
    }


def _repair_proposal(lab: np.ndarray, contract: Mapping[str, Any]) -> np.ndarray:
    """Project a proposal into declared L/hue/chroma bounds and exact sRGB gamut."""
    repaired = np.asarray(lab, dtype=float).copy()
    bounds = contract["proposal_bounds"]
    global_bounds = bounds["global_oklab"]
    margin = 0.0025
    for index, role in enumerate(bounds["roles"]):
        repaired[index, 0] = np.clip(
            repaired[index, 0], role["l_min"] + margin, role["l_max"] - margin
        )
        chroma = float(np.linalg.norm(repaired[index, 1:]))
        hue = math.degrees(math.atan2(repaired[index, 2], repaired[index, 1])) % 360.0
        delta = (hue - role["hue_center_degrees"] + 180.0) % 360.0 - 180.0
        delta = float(
            np.clip(
                delta,
                -role["hue_half_width_degrees"] + 0.25,
                role["hue_half_width_degrees"] - 0.25,
            )
        )
        hue = math.radians(role["hue_center_degrees"] + delta)
        chroma = min(chroma, global_bounds["chroma_max"] - margin)
        repaired[index, 1:] = [chroma * math.cos(hue), chroma * math.sin(hue)]
    chroma = np.linalg.norm(repaired[:, 1:], axis=1)
    mean = float(np.mean(chroma))
    target = float(
        np.clip(
            mean,
            global_bounds["bank_mean_chroma_min"] + margin,
            global_bounds["bank_mean_chroma_max"] - margin,
        )
    )
    if mean > 0:
        repaired[:, 1:] *= target / mean
    # Preserve L and hue while shrinking chroma only as much as exact sRGB gamut requires.
    for _ in range(16):
        rgb = oklab_to_srgb(repaired)
        invalid = np.any((rgb < -1e-7) | (rgb > 1.0 + 1e-7), axis=1)
        if not np.any(invalid):
            break
        repaired[invalid, 1:] *= 0.96
    return repaired


def _propose_batch(
    jobs: Sequence[SearchJob], inputs: Phase3Inputs, contract: Mapping[str, Any]
) -> tuple[list[tuple[str, ...] | None], list[str]]:
    """Generate a deterministic baseline-anchored constrained NumPy proposal batch."""
    context = _proposal_context(inputs, contract)
    baseline = context["baseline_lab"]
    proposals = np.repeat(baseline[None, :, :], len(jobs), axis=0)
    modes: list[str] = []
    pair_left, pair_right = context["binding_pair"]
    priority = [pair_left, pair_right, context["binding_neutral"], context["binding_contrast"]]
    for offset, job in enumerate(jobs):
        if job.index == 0:
            modes.append("baseline-reference")
            continue
        rng = np.random.Generator(np.random.PCG64(job.seed))
        selector = job.index % 10
        if selector in {0, 8}:
            sigma = 0.0025 if selector == 0 else 0.006
            proposals[offset] += rng.normal(0.0, sigma, size=(6, 3))
            modes.append("local-all-role-small" if selector == 0 else "local-all-role-medium")
        elif selector in {1, 2, 3, 4, 5, 6}:
            count = 1 if selector in {1, 2, 3} else 2
            weights = np.ones(6)
            weights[priority] += 4.0
            chosen = rng.choice(6, size=count, replace=False, p=weights / np.sum(weights))
            proposals[offset, chosen] += rng.normal(0.0, 0.007, size=(count, 3))
            modes.append(f"targeted-{count}-role")
        elif selector == 7:
            direction = baseline[pair_left] - baseline[pair_right]
            direction /= max(float(np.linalg.norm(direction)), 1e-12)
            step = rng.uniform(0.0015, 0.006)
            proposals[offset, pair_left] += step * direction
            proposals[offset, pair_right] -= step * direction
            modes.append("baseline-binding-pair-emphasis")
        else:
            broader = baseline.copy()
            for index, role in enumerate(contract["proposal_bounds"]["roles"]):
                lightness = rng.uniform(role["l_min"], role["l_max"])
                chroma = rng.uniform(
                    0.075, contract["proposal_bounds"]["global_oklab"]["chroma_max"]
                )
                hue = math.radians(
                    role["hue_center_degrees"]
                    + rng.uniform(-role["hue_half_width_degrees"], role["hue_half_width_degrees"])
                )
                broader[index] = [lightness, chroma * math.cos(hue), chroma * math.sin(hue)]
            blend = rng.uniform(0.15, 0.40)
            proposals[offset] = (1.0 - blend) * baseline + blend * broader
            modes.append("bounded-broader-oklab")

        # The worst commanded contrast role is derived from the baseline and nudged inward;
        # this is a proposal prior, not a changed gate.
        proposals[offset, context["binding_contrast"], 0] -= rng.uniform(0.004, 0.010)
        # Likewise, separate the measured binding pair rather than hard-coding role identities.
        direction = baseline[pair_left] - baseline[pair_right]
        direction /= max(float(np.linalg.norm(direction)), 1e-12)
        pair_step = rng.uniform(0.0005, 0.0025)
        proposals[offset, pair_left] += pair_step * direction
        proposals[offset, pair_right] -= pair_step * direction
        proposals[offset] = _repair_proposal(proposals[offset], contract)

    banks: list[tuple[str, ...] | None] = []
    for proposal in proposals:
        try:
            bank, _ = quantize_proposal(proposal)
        except ValueError:
            banks.append(None)
        else:
            banks.append(bank)
    return banks, modes


def _batch_gate_results(
    banks: Sequence[tuple[str, ...]], inputs: Phase3Inputs, contract: Mapping[str, Any]
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    metrics = evaluate_commanded_batch(banks, inputs)
    rgb = np.asarray([bank_rgb(bank) for bank in banks])
    lab = srgb_to_oklab(rgb)
    chroma = np.linalg.norm(lab[:, :, 1:], axis=2)
    hues = np.degrees(np.arctan2(lab[:, :, 2], lab[:, :, 1])) % 360.0
    bounds = contract["proposal_bounds"]
    failures: dict[str, np.ndarray] = {}
    role_l_floor = np.zeros(len(banks), dtype=bool)
    role_l_ceiling = np.zeros(len(banks), dtype=bool)
    role_hue = np.zeros(len(banks), dtype=bool)
    for index, role in enumerate(bounds["roles"]):
        role_l_floor |= lab[:, index, 0] < role["l_min"] - 1e-12
        role_l_ceiling |= lab[:, index, 0] > role["l_max"] + 1e-12
        delta = np.abs((hues[:, index] - role["hue_center_degrees"] + 180.0) % 360.0 - 180.0)
        role_hue |= delta > role["hue_half_width_degrees"] + 1e-12
    global_bounds = bounds["global_oklab"]
    failures["oklab-lightness-floor"] = role_l_floor
    failures["oklab-lightness-ceiling"] = role_l_ceiling
    failures["oklab-chroma-ceiling"] = np.any(chroma > global_bounds["chroma_max"] + 1e-12, axis=1)
    failures["role-hue-neighborhood"] = role_hue
    mean_chroma = np.mean(chroma, axis=1)
    failures["bank-mean-chroma-floor"] = mean_chroma < global_bounds["bank_mean_chroma_min"] - 1e-12
    failures["bank-mean-chroma-ceiling"] = (
        mean_chroma > global_bounds["bank_mean_chroma_max"] + 1e-12
    )
    failures["commanded-pair-distance"] = (
        metrics["pair_min_delta_e_ok"] < contract["hard_gates"]["commanded_pair_delta_e_ok"] - 1e-12
    )
    failures["commanded-neutral-separation"] = (
        metrics["neutral_min_delta_e_ok"] < contract["hard_gates"]["neutral_delta_e_ok"] - 1e-12
    )
    failures["commanded-graphics-contrast"] = (
        metrics["graphics_contrast_min"] < contract["hard_gates"]["graphics_contrast_ratio"] - 1e-12
    )
    return metrics, failures


def _coarse_chunk(
    jobs: Sequence[SearchJob], inputs: Phase3Inputs, contract: Mapping[str, Any], run_seed: int
) -> tuple[list[dict[str, Any]], Counter[str], int]:
    banks, modes = _propose_batch(jobs, inputs, contract)
    rejected = Counter()
    valid_positions = [index for index, bank in enumerate(banks) if bank is not None]
    valid_banks = [banks[index] for index in valid_positions]
    if not valid_banks:
        rejected["proposal-quantization"] = len(jobs)
        return [], rejected, len(jobs)
    metrics, failure_masks = _batch_gate_results(valid_banks, inputs, contract)
    for gate, mask in failure_masks.items():
        rejected[gate] += int(np.count_nonzero(mask))
    failed_any = np.logical_or.reduce(list(failure_masks.values()))
    records = []
    for local_index, original_position in enumerate(valid_positions):
        job = jobs[original_position]
        bank = valid_banks[local_index]
        is_baseline = job.index == 0
        if failed_any[local_index] and not is_baseline:
            continue
        records.append(
            {
                "run_seed": run_seed,
                "job_index": job.index,
                "job_seed": job.seed,
                "proposal_mode": modes[original_position],
                "candidate_id": _candidate_id(bank, inputs, contract),
                "serialized_bank_sha256": bank_hash(bank),
                "serialized_bank": list(bank),
                "cheap_pass": bool(not failed_any[local_index]),
                "baseline_reference": is_baseline,
                "cheap_metrics": {
                    "pair_min_delta_e_ok": float(metrics["pair_min_delta_e_ok"][local_index]),
                    "neutral_min_delta_e_ok": float(metrics["neutral_min_delta_e_ok"][local_index]),
                    "graphics_contrast_min": float(metrics["graphics_contrast_min"][local_index]),
                },
            }
        )
    rejected["proposal-quantization"] += len(jobs) - len(valid_positions)
    return records, rejected, len(jobs)


def _survivor_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    metrics = row["cheap_metrics"]
    margins = (
        metrics["pair_min_delta_e_ok"] / 16.0,
        metrics["neutral_min_delta_e_ok"] / 8.0,
        metrics["graphics_contrast_min"] / 3.0,
    )
    return (-min(margins), -sum(margins), str(row["candidate_id"]))


def select_diverse_survivors(
    rows: Iterable[Mapping[str, Any]], *, limit: int = MAX_COARSE_SURVIVORS
) -> list[dict[str, Any]]:
    """Dedupe exact banks, then deterministically interleave proposal modes by quality."""
    exact: dict[str, dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        if not row.get("cheap_pass") or row.get("baseline_reference"):
            continue
        key = str(row["serialized_bank_sha256"])
        current = exact.get(key)
        identity = (int(row["run_seed"]), int(row["job_index"]), str(row["candidate_id"]))
        if current is None or identity < (
            int(current["run_seed"]),
            int(current["job_index"]),
            str(current["candidate_id"]),
        ):
            exact[key] = row
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in exact.values():
        buckets.setdefault(str(row["proposal_mode"]), []).append(row)
    for values in buckets.values():
        values.sort(key=_survivor_sort_key)
    selected = []
    names = sorted(buckets)
    position = 0
    while len(selected) < limit:
        added = False
        for name in names:
            if position < len(buckets[name]):
                selected.append(buckets[name][position])
                added = True
                if len(selected) == limit:
                    break
        if not added:
            break
        position += 1
    return selected


def _atomic_json(path: Path, payload: Any, *, immutable: bool = False) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical_json(payload) + b"\n"
    if path.exists():
        if immutable and path.read_bytes() == encoded:
            return 0
        if immutable:
            raise StaleArtifactError(
                f"immutable shard already exists with different bytes: {path.name}"
            )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, path)
    return len(encoded)


def _shard_layout(budget: int, chunk_size: int) -> list[dict[str, int]]:
    return [
        {"index": index, "start": start, "stop": min(start + chunk_size, budget)}
        for index, start in enumerate(range(0, budget, chunk_size))
    ]


def _load_and_validate_survivor_artifact(
    artifact: Path | Mapping[str, Any], inputs: Phase3Inputs, contract: Mapping[str, Any]
) -> tuple[dict[str, Any], str]:
    payload = (
        _load_json(Path(artifact))
        if isinstance(artifact, (str, os.PathLike, Path))
        else dict(artifact)
    )
    required = {
        "schema_version",
        "artifact_kind",
        "algorithm_version",
        "input_chain_sha256",
        "search_contract_sha256",
        "seed_runs",
        "proposal_count",
        "cheap_survivor_count",
        "deduped_survivor_count",
        "failure_histogram",
        "survivor_rows",
        "source_manifest_hashes",
    }
    if set(payload) != required or payload.get("schema_version") != 2:
        raise StaleArtifactError("coarse survivor artifact schema/keys are invalid")
    if payload.get("artifact_kind") != "coarse-survivors":
        raise StaleArtifactError("refine parent is not a coarse survivor artifact")
    if payload.get("algorithm_version") != SEARCH_ALGORITHM_VERSION:
        raise StaleArtifactError("coarse survivor artifact algorithm is stale")
    if payload.get("input_chain_sha256") != input_chain_sha256(inputs):
        raise StaleArtifactError("coarse survivor artifact input chain is stale")
    if payload.get("search_contract_sha256") != sha256_json(contract):
        raise StaleArtifactError("coarse survivor artifact search contract is stale")
    seed_runs = payload.get("seed_runs")
    if (
        not isinstance(seed_runs, list)
        or len(seed_runs) < contract["seed"]["minimum_independent_runs"]
        or len(set(seed_runs)) != len(seed_runs)
    ):
        raise StaleArtifactError("refine requires at least four unique coarse seed runs")
    rows = payload.get("survivor_rows")
    if not isinstance(rows, list) or any(not row.get("cheap_pass") for row in rows):
        raise StaleArtifactError("coarse survivor rows are invalid")
    if len({row["serialized_bank_sha256"] for row in rows}) != len(rows):
        raise StaleArtifactError("coarse survivor artifact contains duplicate exact banks")
    for row in rows:
        if row["serialized_bank_sha256"] != bank_hash(row["serialized_bank"]):
            raise StaleArtifactError("coarse survivor bank/hash is tampered")
    return payload, sha256_json(payload)


def combine_coarse_artifacts(
    artifacts: Sequence[Path | Mapping[str, Any]],
    *,
    output_path: Path,
    inputs: Phase3Inputs,
    contract: Mapping[str, Any],
    limit: int = MAX_COARSE_SURVIVORS,
) -> dict[str, Any]:
    if len(artifacts) < contract["seed"]["minimum_independent_runs"]:
        raise ValueError("at least four coarse run artifacts are required")
    output_path = validate_external_output_path(output_path, inputs)
    all_rows: list[dict[str, Any]] = []
    runs: list[int] = []
    source_hashes: list[str] = []
    histogram: Counter[str] = Counter()
    proposal_count = 0
    cheap_count = 0
    for artifact in artifacts:
        payload = (
            _load_json(Path(artifact))
            if isinstance(artifact, (str, os.PathLike, Path))
            else dict(artifact)
        )
        if payload.get("artifact_kind") != "coarse-run-survivors":
            raise StaleArtifactError("combine input is not a single-run coarse artifact")
        if payload.get("algorithm_version") != SEARCH_ALGORITHM_VERSION:
            raise StaleArtifactError("combine input algorithm is stale")
        if payload.get("input_chain_sha256") != input_chain_sha256(inputs):
            raise StaleArtifactError("combine input chain is stale")
        if payload.get("search_contract_sha256") != sha256_json(contract):
            raise StaleArtifactError("combine search contract is stale")
        run_seed = int(payload["run_seed"])
        if run_seed in runs:
            raise StaleArtifactError("coarse seed run is duplicated")
        runs.append(run_seed)
        source_hashes.append(sha256_json(payload))
        proposal_count += int(payload["proposal_count"])
        cheap_count += int(payload["cheap_survivor_count"])
        histogram.update(payload["failure_histogram"])
        all_rows.extend(dict(row) for row in payload["survivor_rows"])
    merged = merge_chunk_records(all_rows)
    selected = select_diverse_survivors(merged, limit=limit)
    result = {
        "schema_version": 2,
        "artifact_kind": "coarse-survivors",
        "algorithm_version": SEARCH_ALGORITHM_VERSION,
        "input_chain_sha256": input_chain_sha256(inputs),
        "search_contract_sha256": sha256_json(contract),
        "seed_runs": sorted(runs),
        "proposal_count": proposal_count,
        "cheap_survivor_count": cheap_count,
        "deduped_survivor_count": len(selected),
        "failure_histogram": dict(sorted(histogram.items())),
        "survivor_rows": selected,
        "source_manifest_hashes": sorted(source_hashes),
    }
    _atomic_json(output_path, result)
    return result


_FULL_WORKER_INPUTS: Phase3Inputs | None = None
_FULL_WORKER_CONTRACT: Mapping[str, Any] | None = None


def _initialize_full_worker(inputs: Phase3Inputs, contract: Mapping[str, Any]) -> None:
    global _FULL_WORKER_INPUTS, _FULL_WORKER_CONTRACT
    _FULL_WORKER_INPUTS = inputs
    _FULL_WORKER_CONTRACT = contract


def _evaluate_full_worker(task: Mapping[str, Any]) -> dict[str, Any]:
    if _FULL_WORKER_INPUTS is None or _FULL_WORKER_CONTRACT is None:
        raise RuntimeError("full-evaluation worker is not initialized")
    row = evaluate_candidate(
        task["serialized_bank"], _FULL_WORKER_INPUTS, _FULL_WORKER_CONTRACT, stage="full"
    )
    row.update(
        {
            "run_seed": task["run_seed"],
            "job_index": task["job_index"],
            "job_seed": task["job_seed"],
            "proposal_mode": task["proposal_mode"],
            "parent_artifact_sha256": task["parent_artifact_sha256"],
            "parent_candidate_ids": task["parent_candidate_ids"],
        }
    )
    return row


def validate_frontier_manifest(
    frontier: Mapping[str, Any], inputs: Phase3Inputs, contract: Mapping[str, Any]
) -> None:
    required = {
        "schema_version",
        "artifact_kind",
        "algorithm_version",
        "input_chain_sha256",
        "search_contract_sha256",
        "parent_artifact_sha256",
        "baseline_candidate_id",
        "candidate_ids",
        "ranked_candidate_ids",
        "frontier_rows_sha256",
        "pareto_dimensions",
        "rank_policy",
        "strict_pareto_requires_no_protected_regression",
        "sampled_not_continuous",
        "seed_runs",
        "browser_oracle_status",
        "human_width_capacity",
    }
    if set(frontier) != required or frontier.get("schema_version") != 2:
        raise StaleArtifactError("frontier manifest schema version/keys are invalid")
    if frontier.get("artifact_kind") != "full-evaluated-frontier":
        raise StaleArtifactError("frontier artifact kind is invalid")
    if frontier.get("algorithm_version") != SEARCH_ALGORITHM_VERSION:
        raise StaleArtifactError("frontier algorithm is stale")
    if frontier.get("input_chain_sha256") != input_chain_sha256(inputs):
        raise StaleArtifactError("frontier input chain is stale")
    if frontier.get("search_contract_sha256") != sha256_json(contract):
        raise StaleArtifactError("frontier search contract is stale")
    if frontier.get("pareto_dimensions") != list(PARETO_DIMENSIONS):
        raise StaleArtifactError("frontier Pareto contract is invalid")
    ranked = frontier.get("ranked_candidate_ids")
    candidate_ids = frontier.get("candidate_ids")
    if not isinstance(ranked, list) or not isinstance(candidate_ids, list):
        raise StaleArtifactError("frontier candidate enumeration is invalid")
    if candidate_ids != [frontier.get("baseline_candidate_id"), *ranked]:
        raise StaleArtifactError("frontier must be ordered and anchored by the baseline")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise StaleArtifactError("frontier candidate IDs are duplicated")


def _run_binding(
    inputs: Phase3Inputs,
    contract: Mapping[str, Any],
    *,
    stage: str,
    seed: int,
    budget: int,
    chunk_size: int,
    proposal_mode: str,
    workers: int,
    parent_artifact_sha256: str | None,
) -> dict[str, Any]:
    return {
        "algorithm_version": SEARCH_ALGORITHM_VERSION,
        "input_chain_sha256": input_chain_sha256(inputs),
        "search_contract_sha256": sha256_json(contract),
        "root_run_seed": seed,
        "stage": stage,
        "budget": budget,
        "chunk_size": chunk_size,
        "proposal_mode": proposal_mode,
        "worker_count": workers,
        "shard_layout": _shard_layout(budget, chunk_size),
        "parent_artifact_sha256": parent_artifact_sha256,
    }


def _validate_saved_shards(output_dir: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = []
    for expected_index, descriptor in enumerate(manifest.get("shards", [])):
        if descriptor.get("index") != expected_index:
            raise StaleArtifactError("checkpoint shard order is invalid")
        path = output_dir / descriptor["file"]
        if not path.is_file() or _sha256(path) != descriptor["sha256"]:
            raise StaleArtifactError(f"checkpoint shard {expected_index} is missing or corrupt")
        shard = _load_json(path)
        if shard.get("run_binding_sha256") != manifest["run_binding_sha256"]:
            raise StaleArtifactError("checkpoint shard run binding is stale")
        records.extend(dict(row) for row in shard["records"])
    return records


def run_search(
    inputs: Phase3Inputs,
    contract: Mapping[str, Any],
    *,
    output_dir: Path,
    stage: Literal["coarse", "refine"],
    seed: int,
    budget: int,
    chunk_size: int,
    max_seconds: float,
    workers: int,
    final_selection: bool,
    resume: bool = False,
    proposal_mode: str | None = None,
    survivor_artifact: Path | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run immutable deterministic shards and materialize bounded survivor/frontier artifacts."""
    authorize_search(inputs, replay=True)
    validate_search_contract(contract, inputs)
    if final_selection:
        raise ValueError("final selection is forbidden; browser/G2 selection remains separate")
    if stage not in {"coarse", "refine"} or budget < 0 or chunk_size < 1 or workers < 1:
        raise ValueError("invalid bounded search settings")
    if max_seconds <= 0:
        raise ValueError("max_seconds must be positive")
    output_dir = validate_external_output_path(output_dir, inputs)
    output_dir.mkdir(parents=True, exist_ok=True)

    parent_payload: dict[str, Any] | None = None
    parent_hash: str | None = None
    if stage == "refine":
        if survivor_artifact is None:
            raise ValueError("refine requires the exact combined coarse survivor artifact")
        parent_payload, parent_hash = _load_and_validate_survivor_artifact(
            survivor_artifact, inputs, contract
        )
        if not parent_payload["survivor_rows"]:
            raise ValueError("refine parent contains no cheap survivors")
    elif survivor_artifact is not None:
        raise ValueError("coarse search cannot consume a survivor artifact")
    proposal_mode = proposal_mode or (
        "baseline-anchored-mixture" if stage == "coarse" else "coarse-survivor-local"
    )
    binding = _run_binding(
        inputs,
        contract,
        stage=stage,
        seed=seed,
        budget=budget,
        chunk_size=chunk_size,
        proposal_mode=proposal_mode,
        workers=workers,
        parent_artifact_sha256=parent_hash,
    )
    binding_hash = sha256_json(binding)
    manifest_path = output_dir / "search-manifest.json"
    if resume:
        if not manifest_path.is_file():
            raise StaleArtifactError("resume requested but search manifest is missing")
        manifest = _load_json(manifest_path)
        if (
            manifest.get("run_binding") != binding
            or manifest.get("run_binding_sha256") != binding_hash
        ):
            raise StaleArtifactError("checkpoint run binding is stale")
        records = _validate_saved_shards(output_dir, manifest)
    else:
        if manifest_path.exists() or any(output_dir.glob("shard-*.json")):
            raise StaleArtifactError("output directory already contains search state; use resume")
        records = []
        manifest = {
            "schema_version": SEARCH_MANIFEST_SCHEMA_VERSION,
            "artifact_kind": "phase3-search-shard-manifest",
            "run_binding": binding,
            "run_binding_sha256": binding_hash,
            "shards": [],
            "completed_jobs": 0,
            "shard_bytes_written": 0,
            "selected_candidate_id": None,
            "final_selection_performed": False,
            "browser_oracle_run": False,
        }
        _atomic_json(manifest_path, manifest)

    completed_shards = len(manifest["shards"])
    started = time.monotonic()
    executor: ProcessPoolExecutor | None = None
    if stage == "refine" and workers > 1:
        executor = ProcessPoolExecutor(
            max_workers=workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_initialize_full_worker,
            initargs=(inputs, contract),
        )
    try:
        for layout in binding["shard_layout"][completed_shards:]:
            if time.monotonic() - started > max_seconds:
                break
            jobs = make_search_jobs(seed=seed, count=budget, chunk_size=chunk_size)[
                layout["start"] : layout["stop"]
            ]
            if stage == "coarse":
                chunk_records, histogram, proposal_count = _coarse_chunk(
                    jobs, inputs, contract, seed
                )
            else:
                assert parent_payload is not None and parent_hash is not None
                parents = parent_payload["survivor_rows"]
                tasks = []
                for job in jobs:
                    parent = parents[job.index % len(parents)]
                    if job.index < len(parents):
                        bank = parent["serialized_bank"]
                        mode = "exact-coarse-survivor"
                    else:
                        local_inputs = deepcopy(inputs)
                        categorical = local_inputs.baseline["family"]["categorical"]
                        for name, value in zip(ROLE_NAMES, parent["serialized_bank"], strict=True):
                            categorical[name] = value
                        bank = next(
                            candidate
                            for candidate in _propose_batch([job], local_inputs, contract)[0]
                            if candidate is not None
                        )
                        mode = "local-mutation-around-coarse-survivor"
                    tasks.append(
                        {
                            "run_seed": seed,
                            "job_index": job.index,
                            "job_seed": job.seed,
                            "proposal_mode": mode,
                            "serialized_bank": list(bank),
                            "parent_artifact_sha256": parent_hash,
                            "parent_candidate_ids": [parent["candidate_id"]],
                        }
                    )
                if executor is None:
                    _initialize_full_worker(inputs, contract)
                    chunk_records = [_evaluate_full_worker(task) for task in tasks]
                else:
                    chunk_records = list(executor.map(_evaluate_full_worker, tasks))
                histogram = Counter(
                    failure["gate"] for row in chunk_records for failure in row["failures"]
                )
                proposal_count = len(tasks)
            chunk_records = merge_chunk_records(chunk_records)
            shard_payload = {
                "schema_version": SEARCH_MANIFEST_SCHEMA_VERSION,
                "artifact_kind": f"phase3-{stage}-shard",
                "algorithm_version": SEARCH_ALGORITHM_VERSION,
                "run_binding_sha256": binding_hash,
                "chunk": layout,
                "proposal_count": proposal_count,
                "failure_histogram": dict(sorted(histogram.items())),
                "records": chunk_records,
            }
            shard_path = output_dir / f"shard-{layout['index']:06d}.json"
            written = _atomic_json(shard_path, shard_payload, immutable=True)
            descriptor = {
                **layout,
                "file": shard_path.name,
                "sha256": _sha256(shard_path),
                "record_count": len(chunk_records),
            }
            manifest["shards"].append(descriptor)
            manifest["completed_jobs"] += proposal_count
            manifest["shard_bytes_written"] += written
            _atomic_json(manifest_path, manifest)
            records.extend(chunk_records)
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)

    records = merge_chunk_records(records)
    histogram: Counter[str] = Counter()
    proposal_count = 0
    for descriptor in manifest["shards"]:
        shard = _load_json(output_dir / descriptor["file"])
        histogram.update(shard["failure_histogram"])
        proposal_count += int(shard["proposal_count"])
    manifest["completed_jobs"] = proposal_count
    manifest["records_sha256"] = sha256_json(records)

    if stage == "coarse":
        survivors = select_diverse_survivors(records)
        artifact = {
            "schema_version": 2,
            "artifact_kind": "coarse-run-survivors",
            "algorithm_version": SEARCH_ALGORITHM_VERSION,
            "input_chain_sha256": input_chain_sha256(inputs),
            "search_contract_sha256": sha256_json(contract),
            "run_seed": seed,
            "proposal_count": proposal_count,
            "cheap_survivor_count": sum(
                1 for row in records if row.get("cheap_pass") and not row.get("baseline_reference")
            ),
            "failure_histogram": dict(sorted(histogram.items())),
            "survivor_rows": survivors,
            "source_search_manifest_sha256": sha256_json(
                {"run_binding": binding, "shards": manifest["shards"]}
            ),
        }
        artifact_path = output_dir / "coarse-survivors.json"
        _atomic_json(artifact_path, artifact)
        manifest["result_artifact"] = {
            "file": artifact_path.name,
            "sha256": _sha256(artifact_path),
            "survivor_count": len(survivors),
        }
    else:
        baseline = evaluate_candidate(_baseline_bank(inputs), inputs, contract, stage="full")
        frontier_rows = pareto_front(records, baseline)
        rows_path = output_dir / "frontier-rows.json"
        _atomic_json(rows_path, frontier_rows)
        ranked_ids = [row["candidate_id"] for row in frontier_rows[1:]]
        assert parent_payload is not None and parent_hash is not None
        frontier = {
            "schema_version": 2,
            "artifact_kind": "full-evaluated-frontier",
            "algorithm_version": SEARCH_ALGORITHM_VERSION,
            "input_chain_sha256": input_chain_sha256(inputs),
            "search_contract_sha256": sha256_json(contract),
            "parent_artifact_sha256": parent_hash,
            "baseline_candidate_id": baseline["candidate_id"],
            "candidate_ids": [baseline["candidate_id"], *ranked_ids],
            "ranked_candidate_ids": ranked_ids,
            "frontier_rows_sha256": _sha256(rows_path),
            "pareto_dimensions": list(PARETO_DIMENSIONS),
            "rank_policy": "worst-state/pair/geometry, then aggregate, then commanded deviation",
            "strict_pareto_requires_no_protected_regression": True,
            "sampled_not_continuous": True,
            "seed_runs": parent_payload["seed_runs"],
            "browser_oracle_status": "NOT_RUN",
            "human_width_capacity": None,
        }
        validate_frontier_manifest(frontier, inputs, contract)
        frontier_path = output_dir / "frontier-manifest.json"
        _atomic_json(frontier_path, frontier)
        manifest["result_artifact"] = {
            "file": frontier_path.name,
            "sha256": _sha256(frontier_path),
            "frontier_count": len(frontier_rows),
        }
    _atomic_json(manifest_path, manifest)
    # Compatibility name for existing Phase 3A smoke consumers; bytes remain small.
    _atomic_json(output_dir / "smoke-manifest.json", manifest)
    return manifest


def generate_report_specimen(
    rows: Sequence[Mapping[str, Any]], *, output_dir: Path, selection: str | None
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted((dict(row) for row in rows), key=lambda row: row["candidate_id"])
    circles = []
    x = 30
    for row in ordered:
        for index, value in enumerate(row["serialized_bank"]):
            circles.append(
                f'<circle cx="{x + index * 24}" cy="30" r="9" fill="{value}" '
                f'data-candidate="{row["candidate_id"]}" data-role="{ROLES[index]}"/>'
            )
        x += 170
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="60" viewBox="0 0 1200 60">'
        '<rect width="1200" height="60" fill="#F9F9F8"/>' + "".join(circles) + "</svg>\n"
    ).encode()
    (output_dir / "phase3-specimen.svg").write_bytes(svg)
    report = {
        "schema_version": 1,
        "candidate_ids": [row["candidate_id"] for row in ordered],
        "selection": selection,
        "specimen_sha256": hashlib.sha256(svg).hexdigest(),
        "claims": {
            "gain": "sampled minima, never continuous worst case",
            "cvd": "report-only",
            "human_width_capacity": None,
        },
    }
    _atomic_json(output_dir / "phase3-report.json", report)
    return report


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Phase 3 survivor-driven categorical search")
    parser.add_argument("--experiment", type=Path, default=Path(__file__).resolve().parent)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("coarse", "refine"):
        command = subparsers.add_parser(name)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--seed", type=int, required=True)
        command.add_argument("--budget", type=int, required=True)
        command.add_argument("--chunk-size", type=int, required=True)
        command.add_argument("--workers", type=int, default=1 if name == "coarse" else 4)
        command.add_argument("--max-seconds", type=float, default=86_400.0)
        command.add_argument("--resume", action="store_true")
        if name == "refine":
            command.add_argument("--survivor-artifact", type=Path, required=True)
    combine = subparsers.add_parser("combine")
    combine.add_argument("--output", type=Path, required=True)
    combine.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args()
    inputs = load_inputs(args.experiment)
    contract = load_contract(args.experiment / "phase3-search-contract.json")
    if args.command == "combine":
        result = combine_coarse_artifacts(
            args.artifacts, output_path=args.output, inputs=inputs, contract=contract
        )
    else:
        result = run_search(
            inputs,
            contract,
            output_dir=args.output,
            stage=args.command,
            seed=args.seed,
            budget=args.budget,
            chunk_size=args.chunk_size,
            max_seconds=args.max_seconds,
            workers=args.workers,
            final_selection=False,
            resume=args.resume,
            survivor_artifact=getattr(args, "survivor_artifact", None),
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    _cli()
