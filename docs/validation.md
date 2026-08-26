# Ember validation reference

[Back to the README](../README.md#the-science-behind-ember)

This reference records the exact measured properties and release gates behind Ember's
four generated palettes. The README explains the design mechanisms and intended use.

## Measured properties

`ΔEOK` below is Euclidean Oklab distance multiplied by 100. It is an engineering
measure used consistently by the generator and tests, not a standardized CIE ΔE
formula.

The transformed-first table also reports flare-aware CAM16-UCS distances. Its viewing
conditions are fixed at adapting luminance 8, background luminance 3, and flare fraction
0.0075. WCAG contrast remains a separate gate.

| Family | Categories | Day min ΔEOK | Transformed min ΔEOK | Mean / max raw chroma | Transformed L range | Min ANSI contrast |
|---|---:|---:|---:|---:|---:|---:|
| 3400K Dark | 6 | 16.18 | 10.53 | 0.1009 / 0.1107 | 0.2153 | 4.79:1 |
| 3400K Light | 6 | 16.37 | 11.58 | 0.1266 / 0.1408 | 0.1818 | 4.71:1 |
| 2000K Dark | 4 | 20.47 | 14.52 | 0.1034 / 0.1109 | 0.1657 | 4.55:1 |
| 1200K Dark | 3 | 22.00 | 10.05 | 0.1049 / 0.1103 | 0.1458 | 4.52:1 |

Daytime hue breadth and transformed category/background contrast are separate release gates.
Contrast here is for graphical category marks, not small text.

| Family | Day minimum hue gap | Target | Transformed category / `bg_0` | Target |
|---|---:|---:|---:|---:|
| 3400K Dark | 20.03° | ≥ 20° | 3.03:1 | ≥ 3:1 |
| 3400K Light | 44.96° | ≥ 30° | 3.35:1 | ≥ 3:1 |
| 2000K Dark | 21.04° | ≥ 20° | 3.01:1 | ≥ 3:1 |
| 1200K Dark | 48.12° | ≥ 45° | 3.07:1 | ≥ 3:1 |

Terminal-bank separation includes the complete foreground ladder as well as accent-to-accent
comparisons:

| Family | Day accent min | Day → `fg_0` | Day → `fg_1` | Day → `fg_2` | Transformed accent min | Transformed → `fg_0` | Transformed → `fg_1` | Transformed → `fg_2` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3400K Dark | 15.23 | 8.61 | 8.35 | 12.75 | 8.94 | 6.80 | 6.83 | 12.67 |
| 3400K Light | 17.17 | 9.98 | 11.52 | 9.51 | 12.74 | 7.73 | 7.09 | 7.42 |
| 2000K Dark | 17.10 | 12.62 | 8.72 | 13.30 | 6.22 | 7.70 | 2.77 | 10.78 |
| 1200K Dark | 11.12 | 9.51 | 11.86 | 13.80 | 4.34 | 4.89 | 3.14 | 10.75 |

Foreground coherence is independently gated rather than assumed:

| Family | `fg_0 / fg_1 / fg_2` | Day adjacent steps | Transformed adjacent steps | Day / transformed gap ratio | Day / transformed hue span | Max day chroma |
|---|---|---:|---:|---:|---:|---:|
| 3400K Dark | `#DCD9BF` / `#9B9784` / `#7D7564` | 20.65 / 10.99 | 17.46 / 9.06 | 0.5318 / 0.5207 | 15.90° / 3.88° | 0.0349 |
| 3400K Light | `#342F2C / #4D4540 / #665C54` | 8.75 / 8.52 | 7.55 / 7.32 | 0.9734 / 0.9707 | 0.00° / 1.12° | 0.0181 |
| 2000K Dark | `#ECDCBF` / `#B4AA8E` / `#8D8570` | 16.11 / 12.14 | 12.73 / 9.45 | 0.7525 / 0.7451 | 8.23° / 1.99° | 0.0423 |
| 1200K Dark | `#FFFBEE` / `#CDC4BA` / `#A1978F` | 16.30 / 14.22 | 10.68 / 9.73 | 0.8732 / 0.9072 | 0.00° / 0.37° | 0.0176 |

Dark-surface measurements use WCAG's sRGB relative-luminance calculation on the exact
serialized Hex values. The contrast range covers transformed `fg_0` on all six background
roles.

| Dark family | Unique surfaces | `bg_0` | Commanded luminance, `bg_0` → `bg_5` | Transformed `fg_0` contrast range |
|---|---:|---:|---:|---:|
| 3400K Dark | 5 | `#050404` | 0.00128 → 0.02404 | 6.97–9.12:1 |
| 2000K Dark | 4 | `#050404` | 0.00128 → 0.02404 | 5.77–7.13:1 |
| 1200K Dark | 4 | `#050404` | 0.00128 → 0.02404 | 5.31–6.26:1 |

These are digital signal measurements, not physical display luminance. Actual black
level still depends on panel technology, brightness, calibration, ambient light, and the
display's behavior near black.

Transformed-first CAM16-UCS metrics use the unique background ladder, not repeated role
aliases. The final two columns report nominal sequential-step CV and the maximum CV found
on the nominal/±5% gain grid.

| Family | Category min | Terminal min | Unique surface steps | Sequential CV | Gain-grid CV max |
|---|---:|---:|---:|---:|---:|
| 3400K Dark | 16.69 | 15.94 | 3.36 / 3.33 / 3.69 / 3.02 | 0.0494 | 0.0846 |
| 3400K Light | 15.91 | 15.78 | 3.12 / 2.97 / 3.08 / 3.01 / 2.98 | 0.0563 | 0.0699 |
| 2000K Dark | 17.31 | 13.52 | 5.13 / 4.91 / 4.75 | 0.0493 | 0.0798 |
| 1200K Dark | 14.14 | 7.58 | 5.63 / 5.95 / 4.82 | 0.0923 | 0.1613 |

The build also checks `fg_0` against every declared background, verifies endpoint visibility,
parses every terminal format, and reproduces all generated artifacts from source.

## Reproduce the build

```bash
uv sync --extra dev --extra experiment
uv run python tools/build_all.py --check
uv run pytest -q
uv run ruff check src tests tools examples
uv build
```

The release gates enforce:

- schema 14 with exactly four palette families and categorical capacities `6, 6, 4, 3`;
- categorical commanded mean Oklab chroma between `0.09` and `0.105`, with no color
  above `0.111`, for the dark families; the accepted 3400K Light bank uses mean `0.1266`
  and maximum `0.1408` while preserving its separation and contrast floors;
- categorical minimum-distance floors in both unshifted and transformed states;
- categorical separation from every foreground role in both states, plus sampled-corner
  floors for deep-profile category spacing, foreground clearance, and background contrast;
- terminal day / night capacities `6 / 6`, `6 / 6`, `4 / 4`, `3 / 3`;
- no more than `0.15 ΔEOK` between each authored transformed accent target and the
  transformed serialized color that reproduces it;
- at least 4.5:1 transformed contrast for foreground-capable ANSI slots against the terminal
  base background (`bg_0`);
- transformed contrast floors of `4.5:1`, `3.5:1`, and `2.4:1` for `fg_0`, `fg_1`, and
  `fg_2` respectively on every background; `fg_1` is limited to larger supporting text or
  graphics, and `fg_2` to nonessential metadata or decoration, not body text;
- no opacity-derived text and no alpha-composited foreground roles;
- profile-specific accent-distance floors against each foreground role in commanded and
  transformed states, so an accent cannot hide a collision in the supporting or muted tier;
- connected foreground ladders with bounded adjacent distances, balanced adjacent lightness
  gaps, lightness-dominant steps, aligned chroma vectors, mode-aware chroma direction within a
  quantization tolerance, and narrow commanded/transformed hue spans;
- dark-mode commanded relative-luminance caps of `0.003`, `0.007`, `0.011`, `0.017`,
  `0.025`, and `0.025` across the six role names;
- explicit dark role aliases `[0,1,2,3,4,4]` at 3400K and `[0,1,1,2,3,3]` at
  2000K/1200K, with strict ordering and distance checks on the unique surfaces;
- at least `1.8 ΔEOK` between adjacent transformed unique dark surfaces and `2.8 ΔEOK`
  between adjacent transformed light surfaces;
- transformed primary-text floors of `6.8:1`, `5.65:1`, and `5.3:1` across every
  surface in the 3400 K, 2000 K, and 1200 K dark families, plus `5.0:1` for 3400 K
  Light;
- at least `6.0 ΔEOK` across each transformed background ladder from `bg_0` to `bg_5`,
  tightened to `15.0 ΔEOK` for 3400 K Light;
- 256 unique float samples per sequential map, with monotonic lightness in both display
  states; nominal transformed CAM16-UCS CV no greater than `0.05` at 3400K/2000K and
  `0.10` at 1200K; gain-grid CV no greater than `0.10`, `0.10`, and `0.17` respectively;
- commanded Oklab CV no greater than `0.06`, `0.13`, and `0.18` for the three dark maps;
- exact recomputation of the four legacy green/blue sensitivity corners and the nominal/±5%
  CAM16-UCS gain grid; and
- exact regeneration of JSON, CSS, themes, diagrams, specimens, and diagnostics.
