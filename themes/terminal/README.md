# Terminal themes

Generated imports are provided for Alacritty, iTerm2, and Windows Terminal. Each
uses the family’s primary background and foreground. Alternative surfaces live in
the JSON manifest, generated CSS, and Python `surfaces()` API; substitute them when a
different canvas is needed. Terminal formats themselves expose only their native primary
background and selection roles; generated themes map those to `bg_0` and `bg_5`.

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

Terminal formats require all 16 ANSI slots. Ember repeats 6, 6, 4, or 3
commanded daytime accents across those slots. Under the target transforms they form
6, 6, 4, or 3 distinct nighttime identities. Bold should come from typography,
not a second high-chroma bank.

Reduced banks preserve recognizable ANSI roles by day. At 1200 K, magenta aliases red,
cyan aliases green, and blue aliases yellow instead of using a modulo cycle that would
assign those names to misleading hues.

`fg_0` is the body-text role. `fg_1` is intended for larger supporting text or graphics,
and `fg_2` for nonessential metadata or decoration. The latter two are not universal
body-text colors; inspect each
pairing under `metrics.shifted_text_contrast` in the JSON manifest.
