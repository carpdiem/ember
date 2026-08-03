# Sample-screen analysis

Generated from the exact README screenshots. These image-level diagnostics are
guardrails, not a model of eye strain: they detect saturation and abrupt luminance
edges but cannot substitute for long-duration viewing on real hardware.

## Palette-level comfort gates

| Family | Categories | Terminal accents | Max raw Oklab chroma | Min shifted category ΔEOK | Min shifted terminal contrast |
|---|---:|---:|---:|---:|---:|
| 3400K Dark | 6 | 6 | 0.0786 | 7.31 | 4.56:1 |
| 3400K Light | 6 | 6 | 0.0846 | 10.04 | 4.55:1 |
| 2000K Dark | 4 | 2 | 0.0677 | 6.25 | 4.57:1 |
| 1200K Dark | 3 | 1 | 0.0640 | 6.95 | 4.55:1 |

Release gates: categorical commanded chroma ≤ 0.09; transformed terminal
small-text roles ≥ 4.5:1; category count and terminal accent count must never
increase as the target temperature falls.

## Screenshot-level diagnostics

| Screenshot | High-contrast edge fraction | High-chroma pixel fraction | Oklab chroma p99 |
|---|---:|---:|---:|
| `terminal-commanded.png` | 1.0567% | 0.0000% | 0.0553 |
| `terminal-simulated.png` | 0.4826% | 18.3333% | 0.1214 |
| `data-commanded.png` | 1.1128% | 0.0000% | 0.0795 |
| `data-simulated.png` | 0.6238% | 25.9149% | 0.2068 |

Interpretation: small high-contrast edge fractions are expected around glyphs,
axes, and markers. Commanded high-chroma area should remain scarce. A deep warm
transform itself makes most surviving pixels red, so transformed chroma is
descriptive rather than a release gate. Lines use dash, marker, and text-label
redundancy because no color metric can rescue information after the display
transform removes a channel.
