# Dark palette promotion readiness — roles, aliases, and remaining work

> **Approved artifact SHA:** `3f319ce37d25f740f1762cfdd2f812c8d57dc74a75178e8bf86a77ccef94f5fe`
> **Status:** experiment contract; canonical production definitions are unchanged

## Consumer audit verdict

Production and publication consumers require six exported `bg_0…bg_5` keys, but only five roles carry distinct named semantics in the codebase:

| Exported role | Observed semantic usage | Evidence |
|---|---|---|
| `bg_0` | canvas / terminal background | `tools/render_style.py:7`; `tools/build_all.py:177,214` |
| `bg_1` | subtle header / first elevation in specimens | `tools/render_samples.py:94`; `tools/render_story.py:160` |
| `bg_2` | panel / outline / terminal normal-black source | `tools/render_style.py:8`; `src/ember/generate.py:98-103`; `tools/render_samples.py:91` |
| `bg_3` | raised panel | `tools/render_style.py:9` |
| `bg_4` | rule / divider | `tools/render_style.py:10` |
| `bg_5` | border / selection background | `tools/render_style.py:11`; `tools/build_all.py:181,216`; `tools/render_samples.py:147` |

All six roles are part of the public manifest/CSS contract (`src/ember/definitions.py:133-140`; `tests/test_exports.py:157-164`; `tests/test_palettes.py:111-117`). Promotion therefore must keep six exported names even when only four or five visual surfaces are real.

## Approved six-role alias contract

Alias the least structurally important intermediate roles while preserving distinct canvas, panel, raised-panel, and border/selection planes:

| Real count | Export mapping `bg_0…bg_5 → surface index` | Meaning |
|---:|---|---|
| 6 | `[0,1,2,3,4,5]` | no aliases |
| 5 | `[0,0,1,2,3,4]` | `bg_1` aliases canvas; panel/raised/rule/border stay distinct |
| 4 | `[0,0,1,2,3,3]` | `bg_1` aliases canvas; rule aliases border; panel and raised stay distinct |
| 3 | `[0,0,1,1,2,2]` | reserved fallback: panel/raised share; rule/border share |

Applied halfway contracts:

- 3400K N=5: `[0,0,1,2,3,4]`
- 2000K N=4: `[0,0,1,2,3,3]`
- 1200K N=4: `[0,0,1,2,3,3]`

This replaces the experiment’s former trailing-repeat padding, which collapsed the most semantically important raised/rule/border end of the ladder.

## Cross-profile categorical identity contract

The same broad category families now occupy the same slot when users change profiles:

| Slot | Semantic family | 3400K | 2000K | 1200K |
|---:|---|---|---|---|
| 1 | warm amber | orange | rust/amber | apricot |
| 2 | cool blue/cyan | blue | blue | cyan |
| 3 | rose/magenta | pink | rose | rose |
| 4 | green/mint | green | mint | — |
| 5 | teal | teal | — | — |
| 6 | earth/brown | brown | — | — |

Current and halfway use one identical permutation within each profile. Broad commanded-hue identity is the primary ordering objective; paired current/halfway transformed CAM16-UCS and commanded Oklab prefix separation break ties. The full bank colors and release metrics are unchanged by ordering.

## Promotion requirements

Before changing canonical `src/ember/definitions.py` and generated exports:

1. Export the six aliases explicitly in manifest metadata; do not rely on repeated hex values to imply the contract.
2. Update publication/terminal tests to assert the mapping above.
3. Verify selected-row (`bg_5`), terminal normal black (`bg_2`), panel (`bg_2`), and raised panel (`bg_3`) behavior in real consumers.
4. Keep `fg_2` metadata-only and prohibit alpha-composited halfway text.
5. Dogfood the frozen artifact under actual OS Night Shift before canonical promotion.

## Preserved backlog

These approved follow-ups remain after steps 1–3:

- 1200K-specific redundant terminal and chart encoding
- explicit foreground usage contract (`fg_1` supporting; `fg_2` metadata; no opacity-derived text)
- real application dogfood and final promote-or-archive decision

None of these require reopening numeric palette optimization unless dogfood produces a concrete failure.
