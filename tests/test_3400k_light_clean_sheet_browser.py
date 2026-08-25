from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "docs/experiments/3400k-light-thin-marks"
CLEAN_SHEET = EXPERIMENT / "clean-sheet"
sys.path[:0] = [str(CLEAN_SHEET), str(EXPERIMENT)]

import browser_evidence as browser
import optimizer as clean


@pytest.fixture(scope="module")
def inputs():
    return clean.load_authorized_inputs(EXPERIMENT, replay=False)


@pytest.fixture(scope="module")
def contract(inputs):
    value = clean.load_contract(CLEAN_SHEET / "search-contract.json")
    clean.validate_contract(value, inputs)
    return value


@pytest.fixture(scope="module")
def plans(inputs):
    return browser.build_observation_plan(inputs), browser.build_pair_plan(inputs)


def test_exact_fg0_extension_cardinality_formulas_and_closed_family_order(inputs, plans) -> None:
    observations, pairs = plans
    bases = browser._base_rows(inputs)
    masks = inputs.raster_masks["records"]
    state_count = 2
    background_count = 3
    category_count = 6
    lane_direction_count = 2

    assert len(bases) == 2_160
    assert len(masks) == 720
    assert len(observations) == len(masks) * state_count * background_count * (category_count + 1)
    assert sum(row["family"] == "categorical" for row in observations) == 25_920
    assert sum(row["family"] == "category_fg_0" for row in observations) == 4_320
    assert len(observations) == 30_240

    assert sum(row["family"] == "categorical" for row in pairs) == len(bases) * 15
    assert sum(row["family"] == "category_fg_0" for row in pairs) == (
        len(bases) * category_count * lane_direction_count
    )
    assert len(pairs) == 58_320
    assert [
        family for family, _ in __import__("itertools").groupby(row["family"] for row in pairs)
    ] == [
        "categorical",
        "category_fg_0",
    ]
    assert all(row["family"] in browser.PAIR_FAMILY_ORDER for row in pairs)


def test_fg0_pairs_cover_both_lane_directions(plans) -> None:
    observations, pairs = plans
    lane_by_id = {row["id"]: row["lane"] for row in observations}
    fg_pairs = [row for row in pairs if row["family"] == "category_fg_0"]
    directions = {
        (lane_by_id[row["left_observation_id"]], lane_by_id[row["right_observation_id"]])
        for row in fg_pairs
    }
    assert directions == {(0, 1), (1, 0)}
    assert all(row["roles"][1] == "fg_0" for row in fg_pairs)


def test_compact_raw_observation_fixture_rejects_tampering() -> None:
    values = np.asarray([[10, 20, 30], [30, 40, 50]], dtype=np.uint8)
    record = {
        "request_observation_id": "synthetic",
        "sample_count": 2,
        "observed_rgb8_median": [20.0, 30.0, 40.0],
        "observed_rgb8_base64": base64.b64encode(values.tobytes()).decode("ascii"),
    }
    mask = {"sample_count": 2}
    assert np.array_equal(browser._decode_observation(record, mask), values)

    changed = dict(record)
    changed["observed_rgb8_median"] = [21.0, 30.0, 40.0]
    with pytest.raises(browser.CleanSheetEvidenceError, match="median differs"):
        browser._decode_observation(changed, mask)

    changed = dict(record)
    changed["observed_rgb8_base64"] = changed["observed_rgb8_base64"][:-4]
    with pytest.raises(browser.CleanSheetEvidenceError, match="cardinality differs"):
        browser._decode_observation(changed, mask)

    changed = dict(record)
    changed["sample_count"] = 1
    with pytest.raises(browser.CleanSheetEvidenceError, match="exact mask"):
        browser._decode_observation(changed, mask)


def test_top_record_count_and_family_closure_uses_explicit_exceptions() -> None:
    with pytest.raises(browser.CleanSheetEvidenceError, match="keys are not closed"):
        browser.exact_keys({"allowed": 1, "extra": 2}, {"allowed"}, "synthetic")

    pair = {
        "id": "pair-1",
        "family": "categorical",
        "matched_station_count": 1,
        "observed_delta_e_ok": 1.0,
        "proxy_prediction_delta_e_ok": 1.0,
        "actual_residual_delta_e_ok": 0.0,
    }
    payload = {
        "schema_version": 1,
        "artifact_kind": "synthetic",
        "request_sha256": "0" * 64,
        "candidate_id": "1" * 64,
        "binding": {},
        "pair_count": 1,
        "pair_order_sha256": "2" * 64,
        "family_order": list(browser.PAIR_FAMILY_ORDER),
        "family_counts": {"categorical": 1, "category_fg_0": 0},
        "rows": [pair],
        "metrics_by_family": {},
    }
    browser._validate_pair_payload(payload)

    extra = deepcopy(payload)
    extra["rows"][0]["forged"] = True
    with pytest.raises(browser.CleanSheetEvidenceError, match="keys are not closed"):
        browser._validate_pair_payload(extra)

    bad_family = deepcopy(payload)
    bad_family["rows"][0]["family"] = "legacy_category_only"
    with pytest.raises(browser.CleanSheetEvidenceError, match="family is invalid"):
        browser._validate_pair_payload(bad_family)

    missing = dict(payload)
    missing.pop("pair_count")
    with pytest.raises(browser.CleanSheetEvidenceError, match="keys are not closed"):
        browser._validate_pair_payload(missing)


@pytest.mark.parametrize("python_flags", [[], ["-O"]], ids=["normal", "optimized"])
def test_closed_schema_rejection_survives_optimized_python(python_flags: list[str]) -> None:
    script = f"""
import sys
sys.path[:0] = [{str(CLEAN_SHEET)!r}, {str(EXPERIMENT)!r}]
import browser_evidence as b
b.exact_keys({{'allowed': 1, 'extra': 2}}, {{'allowed'}}, 'optimized fixture')
"""
    completed = subprocess.run(
        [sys.executable, *python_flags, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "keys are not closed" in completed.stderr


def test_detached_capture_request_recomputes_candidate_id_and_rejects_plan_corruption(
    inputs, contract, plans, monkeypatch
) -> None:
    observations, pairs = plans
    bank = clean._baseline_bank(inputs)
    candidate = {
        "lane": "A",
        "bank": list(bank),
        "candidate_id": browser.sha256_json(
            {"lane": "A", "bank": list(bank), "contract": browser.sha256_json(contract)}
        ),
    }
    binding = {
        "input_chain_sha256": clean.p3.input_chain_sha256(inputs),
        "search_contract_sha256": browser.sha256_json(contract),
        "search_artifacts": [
            {"file": name, "sha256": "0" * 64, "canonical_sha256": "1" * 64}
            for name in browser.SEARCH_FILES
        ],
        "optimizer_source": browser._optimizer_source(),
    }
    request = browser._request_for("A", candidate, binding, observations, pairs, inputs)
    browser.validate_request(request, None, inputs, contract, validate_search=False)

    tampered = dict(request)
    tampered["candidate_id"] = "f" * 64
    with pytest.raises(browser.CleanSheetEvidenceError, match="candidate ID"):
        browser.validate_request(tampered, None, inputs, contract, validate_search=False)

    reordered = dict(request)
    reordered["requested_pairs"] = [
        request["requested_pairs"][1],
        request["requested_pairs"][0],
        *request["requested_pairs"][2:],
    ]
    with pytest.raises(browser.CleanSheetEvidenceError, match="incomplete or reordered"):
        browser.validate_request(reordered, None, inputs, contract, validate_search=False)

    extra_record = dict(request)
    extra_record["requested_observations"] = [
        {**request["requested_observations"][0], "forged": True},
        *request["requested_observations"][1:],
    ]
    with pytest.raises(browser.CleanSheetEvidenceError, match="keys are not closed"):
        browser.validate_request(extra_record, None, inputs, contract, validate_search=False)

    missing = dict(request)
    missing["requested_observations"] = request["requested_observations"][:-1]
    with pytest.raises(browser.CleanSheetEvidenceError, match="incomplete or reordered"):
        browser.validate_request(missing, None, inputs, contract, validate_search=False)

    family = dict(request)
    family["requested_pairs"] = [
        {**request["requested_pairs"][0], "family": "category_only"},
        *request["requested_pairs"][1:],
    ]
    with pytest.raises(browser.CleanSheetEvidenceError, match="incomplete or reordered"):
        browser.validate_request(family, None, inputs, contract, validate_search=False)


def test_request_contract_contains_no_implicit_output_or_environment_metadata(
    inputs, contract, plans
) -> None:
    observations, pairs = plans
    bank = clean._baseline_bank(inputs)
    candidate = {
        "lane": "REFERENCE",
        "bank": list(bank),
        "candidate_id": browser.sha256_json(
            {
                "lane": "REFERENCE",
                "bank": list(bank),
                "contract": browser.sha256_json(contract),
            }
        ),
    }
    binding = {
        "input_chain_sha256": clean.p3.input_chain_sha256(inputs),
        "search_contract_sha256": browser.sha256_json(contract),
        "search_artifacts": [
            {"file": name, "sha256": "0" * 64, "canonical_sha256": "1" * 64}
            for name in browser.SEARCH_FILES
        ],
        "optimizer_source": browser._optimizer_source(),
    }
    request = browser._request_for("REFERENCE", candidate, binding, observations, pairs, inputs)
    serialized = json.dumps(request, sort_keys=True)
    assert str(ROOT) not in serialized
    assert not any(term in serialized.lower() for term in ("timestamp", "screenshot", "secret"))
    assert len(browser.canonical_json(request)) < browser.EVIDENCE_LIMIT_BYTES


def test_verify_can_reuse_one_prior_search_validation(
    tmp_path, inputs, contract, monkeypatch
) -> None:
    paths = []
    for name in ("request", "result", "observations", "pairs"):
        path = tmp_path / f"{name}.json"
        path.write_text("{}")
        paths.append(path)
    calls = []

    def record_validate(*args, **kwargs):
        calls.append(kwargs["validate_search"])

    monkeypatch.setattr(browser, "validate_request", record_validate)
    with pytest.raises(browser.CleanSheetEvidenceError):
        browser.verify(*paths, tmp_path, inputs, contract, validate_search=False)
    assert calls == [False]


@pytest.mark.skipif(
    sys.platform != "darwin"
    or not os.environ.get("CLEAN_SHEET_CHROMIUM_REQUEST")
    or not os.environ.get("CLEAN_SHEET_SEARCH_ARTIFACTS"),
    reason="real Chromium is Darwin-only and requires explicit request/search artifact opt-in",
)
def test_real_chromium_capture_and_independent_verification(tmp_path, inputs, contract) -> None:
    request_path = Path(os.environ["CLEAN_SHEET_CHROMIUM_REQUEST"])
    search_artifacts = Path(os.environ["CLEAN_SHEET_SEARCH_ARTIFACTS"])
    result = browser.run_browser(request_path, tmp_path, inputs, contract)
    label = json.loads(request_path.read_text())["request_role"].lower()
    verified = browser.verify(
        request_path,
        tmp_path / f"browser-result-{label}.json",
        tmp_path / f"browser-observations-{label}.json",
        tmp_path / f"browser-pairs-{label}.json",
        search_artifacts,
        inputs,
        contract,
    )
    assert result["status"] == "PASS"
    assert verified["observation_count"] == 30_240
    assert verified["pair_count"] == 58_320
