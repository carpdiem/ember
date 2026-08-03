# Terminal themes

Generated imports are provided for Alacritty, iTerm2, and Windows Terminal. Each
uses the family’s primary background and foreground. Alternative surfaces live in
`palettes/redshift-safe-palettes.json`; substitute them when a different canvas is
needed.

## Install

### Alacritty

Copy one TOML file into your Alacritty configuration directory, then import it
from `alacritty.toml`:

```toml
[general]
import = ["~/.config/alacritty/themes/2000k-dark.toml"]
```

Restart Alacritty or reload its configuration.

### iTerm2

Open **Settings → Profiles → Colors → Color Presets… → Import…**, choose a
`.itermcolors` file, then select the imported preset from **Color Presets…**.

### Windows Terminal

Open **Settings → Open JSON file**. Copy one generated scheme object into the
root `schemes` array, then set a profile’s `colorScheme` to the object’s exact
`name` value, such as `2000K Dark`.

## Surface roles

The file formats still require all 16 ANSI slots, but Ember intentionally aliases
the same 6, 2, or 1 semantic accents across those slots as the target gamut
collapses. Bold should come from typography, not a second glaring rainbow.

`foreground` is the body-text role. `foreground_soft` is intended for larger
supporting text or graphics, and `foreground_muted` for nonessential metadata or
decoration. The latter two are not universal body-text colors; inspect each
pairing under `metrics.shifted_text_contrast` in the JSON manifest.
