# Sample-screen analysis

Generated from the exact README screenshots. These image-level diagnostics are
guardrails, not a model of eye strain: they detect saturation and abrupt luminance
edges but cannot substitute for long-duration viewing on real hardware.

## Palette-level bi-state gates

| Family | Categories | Day min ΔEOK | Shifted min ΔEOK | Mean / max raw chroma | Min shifted terminal contrast |
|---|---:|---:|---:|---:|---:|
| 3400K Dark | 6 | 15.00 | 11.45 | 0.0969 / 0.1045 | 6.06:1 |
| 3400K Light | 6 | 15.91 | 13.76 | 0.1016 / 0.1053 | 5.17:1 |
| 2000K Dark | 4 | 14.84 | 9.01 | 0.0982 / 0.1104 | 5.53:1 |
| 1200K Dark | 3 | 21.00 | 8.65 | 0.1050 / 0.1082 | 5.17:1 |

Release gates: categorical commanded mean chroma 0.09–0.105 and maximum
chroma ≤ 0.111; family-specific daytime and transformed separation floors;
authored transformed accent targets reproduced within 0.15 ΔEOK; transformed
terminal foreground-capable ANSI slots ≥ 4.5:1; category and accent counts
must never increase as the target temperature falls.

## Screenshot-level diagnostics

| Screenshot | High-contrast edge fraction | High-chroma pixel fraction | Oklab chroma p99 |
|---|---:|---:|---:|
| `terminal-commanded.png` | 2.1553% | 0.2486% | 0.0894 |
| `terminal-simulated.png` | 1.0237% | 16.1608% | 0.1728 |
| `data-commanded.png` | 1.5503% | 0.0000% | 0.1043 |
| `data-simulated.png` | 0.7688% | 22.4936% | 0.1753 |

Interpretation: small high-contrast edge fractions are expected around glyphs,
axes, and markers. Commanded high-chroma area should remain scarce. A deep warm
transform itself makes most surviving pixels red, so transformed chroma is
descriptive rather than a release gate. Lines use dash, marker, and text-label
redundancy because no color metric can rescue information after the display
transform removes a channel.
