# Ember 3400K Light thin-mark evidence harness

> **Scope:** Phase 0 + Phase 1 through Stop Gate G0 only<br>
> **Frozen source:** `c4c25e480912f8f54cbd8c992c0b6eb520dc0b8f`<br>
> **Production palette changes:** none<br>
> **Review:** [compact commanded/transformed index](review/index.html) · [G0 report](G0-REPORT.md) · [metrics](g0-metrics.json)

## What this proves

The frozen current schema-14 `3400k-light` payload reproduces a thin-mark identity problem under the exact encoded-sRGB gain `[1, 0.74, 0.53]`:

- categorical contract failure: `cat.five` vs `cat.six`;
- diagnostic/non-contract: `cat.two` vs `terminal.red`;
- diagnostic/non-contract: `cat.two` vs `fg_1`.

The review specimens cover actual `bg_0` and `bg_1`; `bg_2` is metrics/report-only. They include 1.5, 2, and 3 CSS px marks; DPR 1 and 2 validation; horizontal, diagonal, and curved geometry; solid, dashed, and dotted strokes; crossings; short legends; endpoint markers; sparklines; and deterministic fake Financial Cockpit and Thesis Baskets-style panels. No consumer repository or private data is imported.

This checkpoint does **not** optimize colors, alter a canonical source, claim a calibrated light-mode perceptual model, or reuse the dark CAM16-UCS `L_A=8, Y_b=3` conditions as a final light metric.

## Reproduce

```bash
# Re-freeze from the immutable source commit.
uv run python docs/experiments/3400k-light-thin-marks/freeze_baseline.py

# Rebuild deterministic metrics, report, SVGs, and review HTML.
uv run python docs/experiments/3400k-light-thin-marks/harness.py

# Focused deterministic tests (browser test skips unless explicitly enabled).
uv run pytest -q tests/test_3400k_light_thin_marks.py

# Optional local real-Chromium check via the supported GStack browser pattern.
uv run python docs/experiments/3400k-light-thin-marks/browser_validate.py
uv run python docs/experiments/3400k-light-thin-marks/harness.py  # bind report to browser result
EMBER_RUN_BROWSER_TESTS=1 uv run pytest -q tests/test_3400k_light_thin_marks.py
```

When GStack/Chromium is unavailable, the browser validator writes a clear `SKIP` result rather than failing deterministic CI. The committed current-baseline browser result compares sampled raster pixels and per-pixel Oklab distances; no full-image hash is a permanent metric.

## Files

- `baseline.json` — exact source commit, profile, whole 3400K Light family payload, source contracts, and production artifact hashes.
- `freeze_baseline.py` — deterministic immutable-commit freezer.
- `harness.py` — metric backend boundary, coverage proxy, commutation proof, fake data, and artifact renderer.
- `g0-metrics.json` — full rederived matrix for bg_0/bg_1/bg_2, widths, DPRs, and geometries.
- `browser_validate.py` / `browser-validation.json` — optional GStack/Chromium sampled-pixel comparison.
- `G0-REPORT.md` — compact stop-gate evidence and unresolved calibration questions.
- `review/` — commanded/transformed SVGs, compact index, and controlled browser probe.
