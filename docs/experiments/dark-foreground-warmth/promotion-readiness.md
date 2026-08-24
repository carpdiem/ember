# Dark palette promotion readiness — roles, aliases, and remaining work

> **Approved artifact SHA:** `faab1e2cb460b618aaca56846ba487b90229b9714e0a14feedfb51de67ffe779`
> **Status:** experiment contract; canonical production definitions are unchanged

## Consumer audit verdict

Production and publication consumers require six exported `bg_0…bg_5` keys. All six carry named semantics, but usage is uneven:

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

Alias the least damaging adjacent semantic pairs while preserving the most frequently exercised boundaries:

| Real count | Export mapping `bg_0…bg_5 → surface index` | Meaning |
|---:|---|---|
| 6 | `[0,1,2,3,4,5]` | no aliases |
| 5 | `[0,1,2,3,4,4]` | rule and border/selection share the strongest surface |
| 4 | `[0,1,1,2,3,3]` | low-emphasis/sidebar and ordinary panel share; rule and border share |
| 3 | `[0,1,1,1,2,2]` | reserved fallback: low/panel/raised share; rule/border share |

Applied halfway contracts:

- 3400K N=5: `[0,1,2,3,4,4]`
- 2000K N=4: `[0,1,1,2,3,3]`
- 1200K N=4: `[0,1,1,2,3,3]`

The root landing page directly references `bg_0…bg_5` approximately `21/15/7/12/14/3` times, while `bg_4` also feeds 35 shared rule declarations. That favors keeping `bg_0 != bg_1`, `bg_2 != bg_3`, and `bg_3 != bg_4`, while allowing sparse `bg_5` to alias `bg_4`. At N=4, `bg_1 == bg_2` is less damaging than erasing hover/active `bg_2→bg_3` or panel-border `bg_3→bg_4` feedback.

The renderer now exports all six CSS variables from this explicit mapping. No candidate card relies on undefined trailing `--bg-*` variables.

## Cross-profile categorical identity contract

The same broad category families now occupy the same slot when users change profiles:

| Slot | Semantic family | 3400K | 2000K | 1200K |
|---:|---|---|---|---|
| 1 | primary warm | orange | rose (human-reviewed transformed identity) | apricot |
| 2 | cool blue/cyan | blue | blue | cyan |
| 3 | secondary warm/red | pink | rust/amber | rose |
| 4 | green/mint | green | mint | — |
| 5 | teal | teal | — | — |
| 6 | earth/brown | brown | — | — |

Current and halfway use one identical permutation within each profile. Broad commanded-hue identity produces the initial assignment; paired current/halfway transformed CAM16-UCS and commanded Oklab prefix separation break ties. Human review then swaps 2000K slots 1 and 3: its lighter rose preimage better preserves primary-warm identity under transformation, while rust becomes the secondary warm identity. The full bank colors and release metrics are unchanged by ordering.

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
