from __future__ import annotations

import base64
import importlib.util
import itertools
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
SEVEN = EXPERIMENT / "seven-point"
SPEC = importlib.util.spec_from_file_location(
    "seven_point_browser_evidence", SEVEN / "browser_evidence.py"
)
assert SPEC and SPEC.loader
browser = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = browser
SPEC.loader.exec_module(browser)


@pytest.fixture(scope="module")
def inputs():
    return browser.seven.load_inputs(replay=False)


@pytest.fixture(scope="module")
def contract(inputs):
    value = browser.seven.load_contract()
    browser.seven.validate_contract(value, inputs)
    return value


@pytest.fixture(scope="module")
def plans(inputs):
    return browser.build_observation_plan(inputs), browser.build_pair_plan(inputs)


def _candidate(role: str, categories: tuple[str, ...], contract) -> dict[str, object]:
    return browser._special_candidate(role, categories, contract)


def _fake_search_artifacts(tmp_path: Path, inputs, contract) -> tuple[Path, dict[str, dict]]:
    production = browser.seven.canonical_categories(
        inputs.baseline["family"]["categorical"].values()
    )
    candidates = {role: _candidate(role, production, contract) for role in ("a", "b", "c")}
    artifacts = tmp_path / "search"
    artifacts.mkdir()
    (artifacts / "catalog-summary.json").write_text("{}\n")
    (artifacts / "results.json").write_text(
        json.dumps(
            {
                "artifact_kind": "seven-point-bounded-full-catalog-polish",
                "candidates": [candidates[role] for role in ("a", "b", "c")],
            }
        )
        + "\n"
    )
    return artifacts, candidates


def test_exact_symmetric_cardinality_formulas_and_one_closed_family(inputs, plans) -> None:
    observations, pairs = plans
    bases = browser._base_rows(inputs)
    masks = inputs.raster_masks["records"]

    assert len(bases) == 2_160
    assert len(masks) == 720
    assert len(browser.ROLE_ORDER) == 7
    assert len(observations) == len(masks) * 2 * 3 * 7 == 30_240
    assert {row["family"] for row in observations} == {"seven_point"}
    assert len(list(itertools.combinations(browser.ROLE_ORDER, 2))) == 21
    assert len(pairs) == len(bases) * 21 * 2 == 90_720
    assert {row["family"] for row in pairs} == {"seven_point"}
    assert browser.PAIR_FAMILY_ORDER == ("seven_point",)
    assert browser._counts() == {
        "bases": 2_160,
        "roles": 7,
        "observations": 30_240,
        "unordered_pairs": 21,
        "lane_directions": 2,
        "pairs": 90_720,
    }


def test_every_base_has_exact_21_pairs_in_both_immutable_lane_directions(plans) -> None:
    observations, pairs = plans
    lane_by_observation = {row["id"]: row["lane"] for row in observations}
    expected_pairs = list(itertools.combinations(browser.ROLE_ORDER, 2))
    for start in range(0, len(pairs), 42):
        chunk = pairs[start : start + 42]
        assert [tuple(row["roles"]) for row in chunk] == [
            pair for pair in expected_pairs for _ in range(2)
        ]
        assert [
            (
                lane_by_observation[row["left_observation_id"]],
                lane_by_observation[row["right_observation_id"]],
            )
            for row in chunk
        ] == [(0, 1), (1, 0)] * 21
    covered = {role for row in pairs[:42] for role in row["roles"]}
    assert covered == set(browser.ROLE_ORDER)
    assert browser.ROLE_ORDER[0] == "fg_0"


def test_requests_are_exactly_reference_benchmark_c_and_seven_point_abc(
    tmp_path, inputs, contract, plans, monkeypatch
) -> None:
    artifacts, candidates = _fake_search_artifacts(tmp_path, inputs, contract)
    production = browser.seven.canonical_categories(
        inputs.baseline["family"]["categorical"].values()
    )
    benchmark = tuple(reversed(production))
    calls: list[tuple[str, bool]] = []
    writes: list[str] = []

    monkeypatch.setattr(browser.seven, "benchmark_categories", lambda *args: benchmark)
    monkeypatch.setattr(
        browser.polish_search,
        "validate",
        lambda *args, **kwargs: calls.append(("full", kwargs["progress"])),
    )

    def validate(request, *args, **kwargs):
        calls.append((request["request_role"], kwargs["validate_search"]))

    monkeypatch.setattr(browser, "validate_request", validate)
    monkeypatch.setattr(browser, "_write_json", lambda path, value: writes.append(path.name))
    requests = browser.build_requests(artifacts, tmp_path / "requests", inputs, contract)

    assert list(requests) == ["reference", "benchmark-c", "a", "b", "c"]
    assert writes == [f"browser-request-{role}.json" for role in requests]
    assert calls == [("full", True), *[(role, False) for role in requests]]
    assert requests["reference"]["serialized_bank"] == list(production)
    assert requests["benchmark-c"]["serialized_bank"] == list(
        browser.seven.canonical_categories(benchmark)
    )
    assert [requests[role]["candidate_id"] for role in ("a", "b", "c")] == [
        candidates[role]["candidate_id"] for role in ("a", "b", "c")
    ]


def test_fg0_candidate_and_search_artifact_binding_rejects_tampering(
    tmp_path, inputs, contract, plans, monkeypatch
) -> None:
    observations, pairs = plans
    artifacts, candidates = _fake_search_artifacts(tmp_path, inputs, contract)
    production = browser.seven.canonical_categories(
        inputs.baseline["family"]["categorical"].values()
    )
    monkeypatch.setattr(browser.seven, "benchmark_categories", lambda *args: production)
    binding = browser._artifact_binding(artifacts, inputs, contract)
    request = browser._request_for("a", candidates["a"], binding, observations, pairs, inputs)
    browser.validate_request(request, artifacts, inputs, contract, validate_search=False)

    assert request["fixed_fg0"] == binding["fixed_fg0"] == "#342F2C"
    assert request["category_set_sha256"] == browser.p3.bank_hash(production)

    changed = deepcopy(request)
    changed["fixed_fg0"] = "#000000"
    with pytest.raises(browser.SevenPointEvidenceError, match="fixed fg0"):
        browser.validate_request(changed, artifacts, inputs, contract, validate_search=False)

    changed = deepcopy(request)
    changed["candidate_id"] = "f" * 64
    with pytest.raises(browser.SevenPointEvidenceError, match="candidate ID"):
        browser.validate_request(changed, artifacts, inputs, contract, validate_search=False)

    changed = deepcopy(request)
    changed["category_set_sha256"] = "e" * 64
    with pytest.raises(browser.SevenPointEvidenceError, match="set hash"):
        browser.validate_request(changed, artifacts, inputs, contract, validate_search=False)

    (artifacts / "catalog-summary.json").write_text('{"tampered":true}\n')
    with pytest.raises(browser.SevenPointEvidenceError, match="binding is stale"):
        browser.validate_request(request, artifacts, inputs, contract, validate_search=False)


def test_compact_raw_observation_rejects_corruption() -> None:
    values = np.asarray([[10, 20, 30], [30, 40, 50]], dtype=np.uint8)
    record = {
        "request_observation_id": "synthetic",
        "sample_count": 2,
        "observed_rgb8_median": [20.0, 30.0, 40.0],
        "observed_rgb8_base64": base64.b64encode(values.tobytes()).decode("ascii"),
    }
    assert np.array_equal(browser._decode_observation(record, {"sample_count": 2}), values)

    changed = dict(record)
    changed["observed_rgb8_median"] = [21.0, 30.0, 40.0]
    with pytest.raises(browser.SevenPointEvidenceError, match="median differs"):
        browser._decode_observation(changed, {"sample_count": 2})

    changed = dict(record)
    changed["observed_rgb8_base64"] = changed["observed_rgb8_base64"][:-4]
    with pytest.raises(browser.SevenPointEvidenceError, match="cardinality differs"):
        browser._decode_observation(changed, {"sample_count": 2})


def test_pair_and_result_schemas_are_closed_and_explicit() -> None:
    pair = {
        "id": "seven-point-00001",
        "family": "seven_point",
        "matched_station_count": 1,
        "observed_delta_e_ok": 1.0,
        "proxy_prediction_delta_e_ok": 1.0,
        "actual_residual_delta_e_ok": 0.0,
    }
    pair_payload = {
        "schema_version": 1,
        "artifact_kind": "seven-point-complete-symmetric-browser-pairs",
        "request_sha256": "0" * 64,
        "candidate_id": "1" * 64,
        "binding": {},
        "pair_count": 1,
        "pair_order_sha256": "2" * 64,
        "family_order": ["seven_point"],
        "family_counts": {"seven_point": 1},
        "rows": [pair],
        "metrics_by_family": {},
    }
    browser._validate_pair_payload(pair_payload)
    changed = deepcopy(pair_payload)
    changed["rows"][0]["forged"] = True
    with pytest.raises(browser.SevenPointEvidenceError, match="keys are not closed"):
        browser._validate_pair_payload(changed)
    changed = deepcopy(pair_payload)
    changed["rows"][0]["family"] = "category_only"
    with pytest.raises(browser.SevenPointEvidenceError, match="family is invalid"):
        browser._validate_pair_payload(changed)

    result = {
        "schema_version": 1,
        "artifact_kind": "seven-point-symmetric-browser-result",
        "status": "PASS",
        "request_sha256": "0" * 64,
        "candidate_id": "1" * 64,
        "serialized_bank_sha256": "2" * 64,
        "category_set_sha256": "2" * 64,
        "fixed_fg0": "#342F2C",
        "binding": {},
        "counts": browser._counts(),
        "observation_residuals_by_family": {},
        "pair_metrics_by_family": {},
        "source_provenance": {
            "browser": "Chromium via gstack browse",
            "browser_version": "synthetic",
            "browser_status": {},
        },
        "full_image_hash_used": False,
        "human_width_capacity": None,
        "production_promotion_authorized": False,
    }
    browser._validate_result_payload(result)
    changed = dict(result)
    changed["forged"] = True
    with pytest.raises(browser.SevenPointEvidenceError, match="keys are not closed"):
        browser._validate_result_payload(changed)
    changed = dict(result)
    changed["artifact_kind"] = "legacy"
    with pytest.raises(browser.SevenPointEvidenceError, match="schema is invalid"):
        browser._validate_result_payload(changed)


@pytest.mark.parametrize("python_flags", [[], ["-O"]], ids=["normal", "optimized"])
def test_closed_schema_rejection_survives_optimized_python(python_flags: list[str]) -> None:
    script = f"""
import importlib.util, sys
p = {str(SEVEN / "browser_evidence.py")!r}
s = importlib.util.spec_from_file_location('seven_browser_optimized', p)
m = importlib.util.module_from_spec(s); sys.modules[s.name] = m; s.loader.exec_module(m)
m.exact_keys({{'allowed': 1, 'extra': 2}}, {{'allowed'}}, 'optimized fixture')
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


def test_request_is_external_compact_and_contains_no_environment_metadata(
    tmp_path, inputs, contract, plans
) -> None:
    observations, pairs = plans
    production = browser.seven.canonical_categories(
        inputs.baseline["family"]["categorical"].values()
    )
    binding = {
        "input_chain_sha256": browser.p3.input_chain_sha256(inputs),
        "fixed_fg0": "#342F2C",
        "search_contract_sha256": browser.sha256_json(contract),
        "search_artifacts": [
            {"file": name, "sha256": "0" * 64, "canonical_sha256": "1" * 64}
            for name in browser.SEARCH_FILES
        ],
        "optimizer_source": browser._source_binding("optimizer.py"),
        "polish_source": browser._source_binding("polish.py"),
    }
    request = browser._request_for(
        "reference",
        _candidate("reference", production, contract),
        binding,
        observations,
        pairs,
        inputs,
    )
    serialized = browser.canonical_json(request)
    assert len(serialized) < browser.EVIDENCE_LIMIT_BYTES
    assert str(ROOT).encode() not in serialized
    assert not any(term in serialized.lower() for term in (b"timestamp", b"screenshot", b"secret"))
    with pytest.raises(ValueError, match="entire Git repository"):
        browser.p3.validate_external_output_path(ROOT / "scratch", inputs)
    browser._write_json(tmp_path / "request.json", request)
    assert (tmp_path / "request.json").stat().st_size < 50_000_000


def test_verify_can_skip_replay_only_after_a_prior_full_prevalidation(
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
    with pytest.raises(browser.SevenPointEvidenceError):
        browser.verify(*paths, tmp_path, inputs, contract, validate_search=False)
    assert calls == [False]


def test_committed_original_full_polish_binding_remains_valid(inputs, contract) -> None:
    review = EXPERIMENT / "review/g2-seven-point/evidence"
    request = json.loads((review / "browser-request-reference.json").read_text())
    browser.validate_request(
        request,
        SEVEN / "full-polish",
        inputs,
        contract,
        validate_search=False,
    )
    assert set(request["binding"]) == browser._BASE_BINDING_KEYS


def test_warm_binding_requires_exact_warm_source(inputs, contract) -> None:
    artifacts = SEVEN / "warm-pair"
    binding = browser._artifact_binding(artifacts, inputs, contract)
    assert set(binding) == browser._WARM_BINDING_KEYS
    browser._validate_binding(binding, artifacts, inputs, contract)

    missing = deepcopy(binding)
    del missing["warm_pair_source"]
    with pytest.raises(browser.SevenPointEvidenceError, match="keys are not closed"):
        browser._validate_binding(missing, artifacts, inputs, contract)

    tampered = deepcopy(binding)
    tampered["warm_pair_source"]["sha256"] = "f" * 64
    with pytest.raises(browser.SevenPointEvidenceError, match="binding is stale"):
        browser._validate_binding(tampered, artifacts, inputs, contract)


@pytest.mark.skipif(
    sys.platform != "darwin"
    or not os.environ.get("SEVEN_POINT_CHROMIUM_REQUEST")
    or not os.environ.get("SEVEN_POINT_SEARCH_ARTIFACTS"),
    reason="real Chromium is Darwin-only and requires explicit seven-point request/search opt-in",
)
def test_real_chromium_capture_and_independent_verification(tmp_path, inputs, contract) -> None:
    request_path = Path(os.environ["SEVEN_POINT_CHROMIUM_REQUEST"])
    search_artifacts = Path(os.environ["SEVEN_POINT_SEARCH_ARTIFACTS"])
    result = browser.run_browser(request_path, tmp_path, search_artifacts, inputs, contract)
    label = json.loads(request_path.read_text())["request_role"]
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
    assert verified["pair_count"] == 90_720
    assert verified["family_counts"] == {"seven_point": 90_720}
