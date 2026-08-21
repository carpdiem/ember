# Ember validation reference

[Back to the README](../README.md#the-science-behind-ember)

This reference records the exact measured properties and release gates behind Ember's
four generated palettes. The README explains the design mechanisms and intended use.

## Measured properties

`ΔEOK` below is Euclidean Oklab distance multiplied by 100. It is an engineering
measure used consistently by the generator and tests, not a standardized CIE ΔE
formula.

| Family | Categories | Day min ΔEOK | Transformed min ΔEOK | Mean / max raw chroma | Transformed L range | Min ANSI contrast |
|---|---:|---:|---:|---:|---:|---:|
| 3400K Dark | 6 | 15.00 | 11.45 | 0.0971 / 0.1045 | 0.2206 | 5.29:1 |
| 3400K Light | 6 | 16.64 | 12.15 | 0.1006 / 0.1069 | 0.3137 | 4.71:1 |
| 2000K Dark | 4 | 17.00 | 12.91 | 0.0956 / 0.1082 | 0.1538 | 4.52:1 |
| 1200K Dark | 3 | 20.72 | 10.25 | 0.1047 / 0.1107 | 0.1268 | 4.55:1 |

Daytime hue breadth and transformed category/background contrast are separate release gates.
Contrast here is for graphical category marks, not small text.

| Family | Day minimum hue gap | Target | Transformed category / `bg_0` | Target |
|---|---:|---:|---:|---:|
| 3400K Dark | 20.23° | ≥ 20° | 3.01:1 | ≥ 3:1 |
| 3400K Light | 30.07° | ≥ 30° | 3.33:1 | ≥ 3:1 |
| 2000K Dark | 27.76° | ≥ 20° | 3.05:1 | ≥ 3:1 |
| 1200K Dark | 65.03° | ≥ 45° | 3.12:1 | ≥ 3:1 |

Terminal-bank separation includes the complete foreground ladder as well as accent-to-accent
comparisons:

| Family | Day accent min | Day → `fg_0` | Day → `fg_1` | Day → `fg_2` | Transformed accent min | Transformed → `fg_0` | Transformed → `fg_1` | Transformed → `fg_2` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3400K Dark | 10.76 | 8.67 | 8.13 | 11.72 | 7.31 | 6.58 | 5.16 | 10.18 |
| 3400K Light | 17.17 | 9.98 | 11.52 | 9.51 | 12.74 | 7.73 | 7.09 | 7.42 |
| 2000K Dark | 12.62 | 13.73 | 10.86 | 8.25 | 7.75 | 7.64 | 5.03 | 4.75 |
| 1200K Dark | 12.35 | 9.69 | 8.96 | 14.68 | 4.13 | 4.49 | 4.13 | 11.29 |

Foreground coherence is independently gated rather than assumed:

| Family | `fg_0 / fg_1 / fg_2` | Day adjacent steps | Transformed adjacent steps | Day / transformed gap ratio | Day / transformed hue span | Max day chroma |
|---|---|---:|---:|---:|---:|---:|
| 3400K Dark | `#DDD0B2 / #BDAE93 / #908472` | 10.41 / 13.79 | 8.70 / 11.88 | 0.7568 / 0.7372 | 9.32° / 2.63° | 0.0426 |
| 3400K Light | `#342F2C / #4D4540 / #665C54` | 8.75 / 8.52 | 7.55 / 7.32 | 0.9734 / 0.9707 | 0.00° / 1.12° | 0.0181 |
| 2000K Dark | `#EED5AE / #D3BB99 / #AA9D8B` | 8.04 / 10.44 | 6.20 / 9.04 | 0.7886 / 0.7008 | 2.74° / 2.51° | 0.0584 |
| 1200K Dark | `#FFE5BD / #CBAF89 / #A18C73` | 16.43 / 11.79 | 11.07 / 9.16 | 0.7099 / 0.8177 | 6.73° / 0.71° | 0.0607 |

Dark-surface measurements use WCAG's sRGB relative-luminance calculation on the exact
serialized Hex values. The contrast range covers transformed `fg_0` on all six background
roles.

| Dark family | `bg_0` | Commanded luminance, `bg_0` → `bg_5` | Transformed `fg_0` contrast range |
|---|---:|---:|---:|
| 3400K Dark | `#090807` | 0.00247 → 0.02019 | 6.83–8.52:1 |
| 2000K Dark | `#070504` | 0.00162 → 0.01852 | 5.86–6.98:1 |
| 1200K Dark | `#060302` | 0.00108 → 0.01571 | 5.32–6.08:1 |

These are digital signal measurements, not physical display luminance. Actual black
level still depends on panel technology, brightness, calibration, ambient light, and the
display's behavior near black.

The build also checks `fg_0` against every declared background, verifies endpoint visibility,
parses every terminal format, and reproduces all generated artifacts from source.

## Reproduce the build

```bash
uv sync --extra dev
uv run python tools/build_all.py --check
uv run pytest -q
uv run ruff check src tests tools examples
uv build
```

The release gates enforce:

- exactly four palette families with categorical capacities `6, 6, 4, 3`;
- categorical commanded mean Oklab chroma between `0.09` and `0.105`, with no color
  above `0.111`;
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
  graphics, and `fg_2` to nonessential metadata or decoration—not body text;
- profile-specific accent-distance floors against each foreground role in commanded and
  transformed states, so an accent cannot hide a collision in the supporting or muted tier;
- connected foreground ladders with bounded adjacent distances, balanced adjacent lightness
  gaps, lightness-dominant steps, aligned chroma vectors, mode-aware chroma direction within a
  quantization tolerance, and narrow commanded/transformed hue spans;
- dark-mode commanded relative-luminance caps of `0.003`, `0.005`, `0.009`, `0.013`,
  `0.020`, and `0.021` across the six-step ladder;
- at least `1.8 ΔEOK` between adjacent transformed dark-surface ladder steps and `2.8 ΔEOK`
  between adjacent transformed light-surface steps;
- transformed primary-text floors of `6.8:1`, `5.65:1`, and `5.3:1` across every
  surface in the 3400 K, 2000 K, and 1200 K dark families, plus `5.0:1` for 3400 K
  Light;
- at least `6.0 ΔEOK` across each transformed background ladder from `bg_0` to `bg_5`,
  tightened to `15.0 ΔEOK` for 3400 K Light;
- 256 unique float samples per sequential map, with monotonic lightness in both display
  states, transformed step CV no greater than `0.0001`, transformed max:min step ratio no
  greater than `1.001`, and the deep commanded CV tightened
  to `0.11` at 2000 K and `0.15` at 1200 K;
- exact recomputation of the four ±5% green/blue sensitivity corners; and
- exact regeneration of JSON, CSS, themes, diagrams, specimens, and diagnostics.
