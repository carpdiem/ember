# Pareto Palette Pass Implementation Plan

> **For Hermes:** Use subagent-driven-development discipline to implement this plan task-by-task.

**Goal:** Produce a fully generated experimental Ember branch that improves categorical/text separation, reports and improves ±5% gain sensitivity, and improves deep sequential-map commanded uniformity without weakening any existing nominal release gate.

**Architecture:** Keep authoritative palette values in `src/ember/definitions.py`, derive all published metrics in `src/ember/generate.py`, and keep generated outputs deterministic through `tools/build_all.py`. Add exact regression tests before each implementation. Compare every experimental result to the `main` manifest at commit `59c91c6`, preserving exact current quality thresholds and recording any visual or numerical tradeoff in the README.

**Tech Stack:** Python 3.10–3.13, NumPy, SciPy for offline optimization, Matplotlib/Pillow for deterministic specimens, pytest, Ruff, uv/hatchling.

---

### Task 1: Publish the experimental branch

**Objective:** Create a remotely visible branch anchored to the verified baseline.

**Files:** None.

1. Verify clean `main` equals `origin/main`.
2. Create `experiment/pareto-palette-pass`.
3. Push it to `origin` with upstream tracking.
4. Verify clean status.

### Task 2: Add categorical-to-foreground metrics and release targets

**Objective:** Make the omitted collision dimension visible and enforceable.

**Files:**
- Modify: `src/ember/definitions.py`
- Modify: `src/ember/generate.py`
- Modify: `tests/test_palettes.py`

1. Write failing tests that recompute nearest category↔foreground distances for every foreground role in commanded and transformed states.
2. Add per-family daylight and transformed minimum targets without weakening existing gates.
3. Emit exact metrics from reparsed Hex8 colors.
4. Run focused tests and confirm the baseline fails where expected.
5. Commit the metric contract separately from candidate palette changes.

### Task 3: Optimize deep categorical palettes

**Objective:** Improve the 2000K and 1200K categorical/text collision while preserving all existing nominal gates and mature commanded appearance.

**Files:**
- Modify: `src/ember/definitions.py`
- Modify: `tests/test_palettes.py`
- Regenerate: palette JSON/CSS, swatches, data specimens, gallery

1. Build an offline exact-Hex8 optimizer under `/tmp` using the repository's color functions.
2. Preserve current category count, background contrast, daylight separation/hue/chroma budgets, transformed separation, and transformed-target reproduction.
3. Optimize worst category↔foreground distance in both states, then the worst observed ±5% G/B corner, then minimal perceptual movement.
4. Audit finalists in commanded and transformed data/application specimens.
5. Lock the selected Hex8 values and transformed targets.
6. Run focused tests and deterministic generation.
7. Commit and push the coherent categorical checkpoint.

### Task 4: Add gain-sensitivity envelopes and metrics

**Objective:** Report exact system behavior at the four corners of a transparent ±5% G/B gain box rather than only at the nominal vector.

**Files:**
- Modify: `src/ember/definitions.py`
- Modify: `src/ember/generate.py`
- Modify: `tests/test_palettes.py`
- Modify: `README.md`

1. Write failing tests for the four G/B corner vectors; red stays fixed and exact zero gains stay zero.
2. Emit the sensitivity fraction, corner vectors, and categorical, terminal, foreground, surface-text, and sequential extrema observed at those corners.
3. Assert recomputation parity and non-regression against the baseline manifest where the experimental palette changed.
4. Optimize only roles with a concrete corner-sensitivity opportunity; do not redesign stable surfaces or terminal banks for symmetry.
5. Commit and push the robustness checkpoint.

### Task 5: Improve deep sequential-map bi-state uniformity

**Objective:** Reduce commanded step irregularity for 2000K and 1200K while preserving transformed monotonicity, range, and near-uniformity.

**Files:**
- Modify: `src/ember/definitions.py` and/or `src/ember/generate.py`
- Modify: `tests/test_palettes.py`
- Regenerate: JSON, swatches, data specimens, gallery

1. Write failing experimental targets for commanded CV/max:min improvement and transformed quality preservation.
2. Search blue-channel anchor geometry first, with bi-state sample allocation as a lower-churn fallback.
3. Require monotonic lightness in both states and preserve useful endpoint/range behavior.
4. Prefer the smallest algorithmic change that produces a material improvement in both deep profiles.
5. Render and inspect heatmaps and overview ramps in both states.
6. Commit and push the sequential checkpoint.

### Task 6: Publish the comparison surface

**Objective:** Make `main` versus experimental behavior easy to evaluate in GitHub.

**Files:**
- Modify: `README.md`
- Create or update: `docs/experiments/pareto-palette-pass.md`
- Regenerate: all managed artifacts

1. Add a clearly labeled experimental section with exact baseline/candidate metrics.
2. Explain the gain-sensitivity model as engineering sensitivity analysis, not calibration.
3. Include commanded/transformed specimen links and identify what to inspect.
4. Document preserved gates and any deliberate non-Pareto tradeoffs.
5. Run link and artifact-freshness checks.
6. Commit and push.

### Task 7: Exact final verification

**Objective:** Prove the branch is reproducible, reviewable, and safe to compare.

1. Run Ruff check and format check.
2. Run pytest on Python 3.10, 3.11, and 3.13.
3. Run deterministic generation checks on all three versions.
4. Build and inspect wheel/sdist.
5. Run independent numerical/spec review and visual artifact audit against exact branch HEAD.
6. Fix all blocking findings and rerun the gate.
7. Push final HEAD and verify GitHub CI succeeds.
