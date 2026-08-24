# Ember 3400K Light thin-mark evidence harness

> **Scope:** Phase 0/1 G0 evidence plus deterministic Phase 2A G1 core<br>
> **Frozen source:** `c4c25e480912f8f54cbd8c992c0b6eb520dc0b8f`<br>
> **Production palette changes:** none<br>
> **Status:** `CORE_READY_BROWSER_PENDING`; Phase 3 candidate search awaits the Phase 2B browser machinery gates<br>
> **Review:** [G1 commanded/transformed index](review/g1-index.html) · [G1 report](G1-REPORT.md) · [planned raster matrix](raster-baseline.json) · [G0 archive](review/index.html)

## What this proves

The frozen current schema-14 `3400k-light` payload reproduces a thin-mark identity problem under the exact encoded-sRGB gain `[1, 0.74, 0.53]`:

- categorical contract failure: `cat.five` vs `cat.six`;
- diagnostic/non-contract: `cat.two` vs `terminal.red`;
- diagnostic/non-contract: `cat.two` vs `fg_1`.

The review specimens cover actual `bg_0` and `bg_1`; `bg_2` is metrics/report-only. They include 1.5, 2, and 3 CSS px marks; DPR 1 and 2 validation; horizontal, diagonal, and curved geometry; solid, dashed, and dotted strokes; crossings; short legends; endpoint markers; sparklines; and deterministic fake Financial Cockpit and Thesis Baskets-style panels. No consumer repository or private data is imported.

This checkpoint does **not** optimize colors, alter a canonical source, claim device calibration, or reuse the dark CAM16-UCS `L_A=8, Y_b=3` conditions. G1 instead pins explicit light-surface CAM16-UCS engineering assumptions, a complete 32,400-case planned browser matrix, and a preregistered visibility protocol. Browser observations, proxy acceptance, human floors, and width capacity all remain pending. Passing Phase 2B browser machinery gates may authorize Phase 3 candidate search; the human study remains mandatory before a final visibility floor, width capacity, or production promotion, but is not required merely to begin candidate search.

## Reproduce

```bash
# Re-freeze from the immutable source commit.
uv run python docs/experiments/3400k-light-thin-marks/freeze_baseline.py

# Rebuild deterministic G0 and G1 core artifacts.
uv run python docs/experiments/3400k-light-thin-marks/harness.py
uv run --extra experiment python docs/experiments/3400k-light-thin-marks/g1_harness.py

# Focused deterministic tests (browser tests skip unless explicitly enabled).
uv run pytest -q tests/test_3400k_light_thin_marks.py

# Archived G0 browser check; Phase 2A's G1 command checks prerequisites only.
uv run python docs/experiments/3400k-light-thin-marks/browser_validate.py
uv run python docs/experiments/3400k-light-thin-marks/harness.py  # bind G0 report
uv run python docs/experiments/3400k-light-thin-marks/g1_browser_validate.py
EMBER_RUN_BROWSER_TESTS=1 uv run pytest -q tests/test_3400k_light_thin_marks.py
```

The G1 validator returns `SKIP` only when the browser binary is absent, `ERROR` for an installed browser runtime/probe failure, and `PENDING_BROWSER_CALIBRATION` after a healthy prerequisite check. It cannot return G1 `PASS` until Phase 2B implements and records real pixel extraction.

The archived G0 browser result compares sampled raster pixels and per-pixel Oklab distances. Its 0.95 correlation floor applies only to the global sample pool; local DPR/pair/background correlations are disclosed but not gated. Every local row, including the categorical contract pair, is separately gated at MAE ≤ 0.75 ΔE_OK. No full-image hash is a permanent metric. Provenance hashes bind the browser probe, validator source, and GStack browse binary; sanitized status/mode is recorded, while an unavailable Chromium version is not claimed.

## Files

- `baseline.json` — exact source commit, profile, whole 3400K Light family payload, source contracts, and production artifact hashes.
- `freeze_baseline.py` — deterministic immutable-commit freezer.
- `harness.py` — metric backend boundary, coverage proxy, commutation proof, fake data, and artifact renderer.
- `g0-metrics.json` — full rederived matrix for bg_0/bg_1/bg_2, widths, DPRs, and geometries.
- `browser_validate.py` / `browser-validation.json` — optional GStack/Chromium sampled-pixel comparison.
- `G0-REPORT.md` — archived compact G0 stop-gate evidence.
- `g1_harness.py` — Phase 2A contract, Oklab/CAM16-UCS analytical core, planned matrices, protocols, and deterministic renderers.
- `viewing-conditions.json` / `raster-baseline.json` / `neutral-confusability.json` / `gain-grid.json` — pinned G1 assumptions and planned/analytical reconnaissance.
- `visibility-trial-protocol.json` — preregistered 2AFC design with no results or capacity claims.
- `g1_browser_validate.py` / `proxy-calibration.json` — Phase 2B API/schema with explicit pending semantics and no fabricated browser evidence.
- `G1-REPORT.md` — `CORE_READY_BROWSER_PENDING` checkpoint and exact remaining work.
- `review/` — G0 archive plus tagged G1 desktop and 390×844 phone commanded/transformed SVGs, responsive index, and deterministic browser probe.
