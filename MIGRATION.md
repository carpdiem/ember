# Migration

## 0.2 to 0.3

Version 0.3 replaces the dark-mode surface ladders with near-black warm neutrals for
low-brightness, small-text work and moves the light canvas correspondingly closer to warm
white. It also expands each family from three background roles to six and normalizes three
foreground roles. Palette IDs are unchanged, but applications that depended on old Hex values
should refresh copied CSS variables or theme overrides.

Canonical background names are now `bg_0` through `bg_5`; foregrounds are `fg_0` through
`fg_2`. `bg_0` is the base canvas and `bg_5` is the strongest background state; luminance
rises across dark families and falls across the light family. Generated CSS provides
`--rs-background`, `--rs-background-alt`, `--rs-background-high`,
`--rs-background-higher`, and `--rs-background-highest`, plus `--rs-selection` and the three
`--rs-foreground*` names, as
migration aliases. JSON and `surfaces()` return only the
numeric names; the manifest's `legacy_surface_role_aliases` map supports migration.

The JSON schema is version 5. It adds manifest-level surface-role, luminance, separation,
and primary-text-contrast targets plus per-family commanded/transformed measurements under
`metrics.surface`. The canonical ordering is recorded in `quality_targets.bg_roles_low_to_high`.
Python consumers can retrieve an independent copy of every named UI color with
`redshift_safe.surfaces(slug)`.

## 0.1 to 0.2

Ember is the public name of the project. The Python distribution and import package
remain `redshift-safe-palettes` and `redshift_safe` so an upgrade cannot install a
second distribution over the same import path.

Version 0.2 replaces the six aspirational palette names with temperature-based IDs
and removes the two deep-shift light themes that produced large orange/red emitting
surfaces.

| 0.1 ID | 0.2 ID | Status |
|---|---|---|
| `ember-dark` | `3400k-dark` | generated alias; migrate when convenient |
| `ember-light` | `3400k-light` | generated alias; migrate when convenient |
| `lowfire-dark` | `2000k-dark` | generated alias; migrate when convenient |
| `safelight-dark` | `1200k-dark` | generated alias; migrate when convenient |
| `lowfire-light` | none | removed; use `3400k-light` or a dark deep tier |
| `safelight-light` | none | removed; use `3400k-light` or a dark deep tier |

The four retained aliases work in the Python/Matplotlib API, CSS selectors, and all
three generated terminal formats. Alias files are regenerated from the current canonical
families, so they expose current palette values under legacy IDs, never the rejected 0.1
colors.

### Manifest changes

Version 0.2 used JSON schema 4. Family category counts became variable, and the manifest
records `legacy_aliases`, `removed_families`, separate terminal day/night capacities,
night-group assignments, and bi-state measurements. Code that assumed eight categories
must instead read `len(family["categorical"])`.

The terminal metric is now named
`terminal_minimum_shifted_foreground_contrast`. It covers every foreground-capable
ANSI slot; only background-like ANSI black is excluded in dark themes.

### Python

```python
from redshift_safe import categorical, categorical_norm, encode_categories

palette = "2000k-dark"
colors = categorical(palette)
norm = categorical_norm(palette)
ids = encode_categories(labels, order, slug=palette)
```

Pass the palette slug to category helpers so their capacity checks match the selected
family.
