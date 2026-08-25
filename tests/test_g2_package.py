from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "docs/experiments/3400k-light-thin-marks"
EVIDENCE = EXPERIMENT / "review/g2/evidence"
sys.path.insert(0, str(EXPERIMENT))

import g2_package as g2
import phase3_optimizer as p3


@pytest.fixture(scope="module")
def inputs() -> p3.Phase3Inputs:
    return p3.load_inputs(EXPERIMENT)


@pytest.fixture(scope="module")
def contract(inputs: p3.Phase3Inputs) -> dict:
    loaded = p3.load_contract(EXPERIMENT / "phase3-search-contract.json")
    p3.validate_search_contract(loaded, inputs)
    return loaded


@pytest.fixture(scope="module", autouse=True)
def platform_bound_g1_replay(inputs: p3.Phase3Inputs) -> None:
    if sys.platform != "darwin":
        p3._REPLAY_CACHE.add(p3.input_chain_sha256(inputs))


def evidence_paths(label: str = "b") -> tuple[Path, Path, Path, Path]:
    return (
        EVIDENCE / f"browser-request-{label}.json",
        EVIDENCE / f"browser-result-{label}.json",
        EVIDENCE / f"browser-observations-{label}.json",
        EVIDENCE / f"browser-pairs-{label}.json",
    )


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="the committed Chromium result receipt is bound to the macOS capture runtime",
)
def test_committed_g2_browser_evidence_replays(inputs, contract) -> None:
    result = g2.verify_browser_evidence(*evidence_paths(), inputs, contract)
    assert result["status"] == "PASS"
    assert result["observation_count"] == 25_920
    assert result["pair_count"] == 32_400


def test_observation_evidence_rejects_extra_top_and_record_keys(
    tmp_path, inputs, contract, monkeypatch
) -> None:
    if sys.platform != "darwin":
        monkeypatch.setattr(p3, "validate_browser_oracle_result", lambda *_: None)
    request, result, observations, pairs = evidence_paths()
    payload = json.loads(observations.read_text())
    payload["raw_screenshot_base64"] = "forbidden"
    top_extra = tmp_path / "observations-top-extra.json"
    top_extra.write_text(json.dumps(payload))
    with pytest.raises(g2.G2IntegrityError, match="keys are not closed"):
        g2.verify_browser_evidence(request, result, top_extra, pairs, inputs, contract)

    payload = json.loads(observations.read_text())
    payload["records"][0]["forged"] = True
    record_extra = tmp_path / "observations-record-extra.json"
    record_extra.write_text(json.dumps(payload))
    with pytest.raises(g2.G2IntegrityError, match="keys are not closed"):
        g2.verify_browser_evidence(request, result, record_extra, pairs, inputs, contract)


def test_result_observations_are_bound_to_raw_evidence(
    tmp_path, inputs, contract, monkeypatch
) -> None:
    if sys.platform != "darwin":
        monkeypatch.setattr(p3, "validate_browser_oracle_result", lambda *_: None)
    request, result, observations, pairs = evidence_paths()
    request_payload = json.loads(request.read_text())
    payload = json.loads(result.read_text())
    payload["observations"][0]["observed_rgb8_median"][0] += 1
    masks = {row["id"]: row for row in inputs.raster_masks["records"]}
    requested = request_payload["requested_role_observations"][0]
    expected_rgb = (
        np.asarray(p3._expected_browser_rgb8(requested, request_payload, inputs, mask_lookup=masks))
        / 255.0
    )
    observed_rgb = np.asarray(payload["observations"][0]["observed_rgb8_median"]) / 255.0
    payload["observations"][0]["delta_e_ok"] = float(
        np.linalg.norm(p3.srgb_to_oklab(observed_rgb) - p3.srgb_to_oklab(expected_rgb)) * 100.0
    )
    margin = float(contract["raster_proxy"]["calibrated_error_margin_delta_e_ok"])
    payload["observations"][0]["status"] = (
        "PASS" if payload["observations"][0]["delta_e_ok"] <= margin else "FAIL"
    )
    statuses = [row["status"] for row in payload["observations"]]
    deltas = [row["delta_e_ok"] for row in payload["observations"]]
    replay = {
        "schema_version": 1,
        "status": "FAIL" if "FAIL" in statuses else "PASS",
        "request_sha256": p3.sha256_json(request_payload),
        "candidate_id": request_payload["candidate_id"],
        "input_chain_sha256": request_payload["input_chain_sha256"],
        "observation_count": len(payload["observations"]),
        "pass_count": statuses.count("PASS"),
        "fail_count": statuses.count("FAIL"),
        "error_count": 0,
        "maximum_delta_e_ok": max(deltas),
    }
    payload["status"] = replay["status"]
    payload["replay_receipt"] = replay
    payload["replay_sha256"] = p3.sha256_json(replay)
    changed = tmp_path / "result-changed-median.json"
    changed.write_text(json.dumps(payload))
    with pytest.raises(g2.G2IntegrityError, match="raw observation evidence"):
        g2.verify_browser_evidence(request, changed, observations, pairs, inputs, contract)


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="the committed Chromium result receipt is bound to the macOS capture runtime",
)
def test_optimized_python_rejects_closed_evidence_violation(tmp_path) -> None:
    request, result, observations, pairs = evidence_paths()
    payload = json.loads(observations.read_text())
    payload["records"][0]["forged"] = True
    changed = tmp_path / "observations-optimized-extra.json"
    changed.write_text(json.dumps(payload))
    completed = subprocess.run(
        [
            sys.executable,
            "-O",
            str(EXPERIMENT / "g2_package.py"),
            "verify-browser",
            "--request",
            str(request),
            "--result",
            str(result),
            "--observations",
            str(changed),
            "--pairs",
            str(pairs),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "keys are not closed" in completed.stderr


def test_frontier_receipt_schema_is_recursively_closed() -> None:
    schema = json.loads((EXPERIMENT / "phase3-schemas/frontier-receipt.schema.json").read_text())

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value.get("additionalProperties") is False
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    receipt = json.loads((EVIDENCE / "frontier-receipt.json").read_text())
    assert receipt["schema_version"] == 1
    assert len(receipt["candidates"]) == 14
    assert [row["role"] for row in receipt["g2_shortlist"]] == ["A", "B", "C"]


def test_g2_selection_remains_a_human_gate() -> None:
    selection = json.loads((EXPERIMENT / "review/g2/selection.json").read_text())
    assert selection["status"] == "AWAITING_MICHAEL_SELECTION"
    assert selection["selection"] is None
    assert selection["production_promotion_authorized"] is False
