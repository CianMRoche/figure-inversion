# figinvert

[![CI](https://github.com/CianMRoche/figure-inversion/actions/workflows/ci.yml/badge.svg)](https://github.com/CianMRoche/figure-inversion/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Dark-background versions of figures — PDF, SVG, PNG/JPG — without screenshotting
a PDF viewer. **PDFs and SVGs stay vector**: colour operators are rewritten in
place, so text stays selectable and nothing is rasterised.

![before and after](examples/before-after.png)

<sub>Example figure from Roche et al. (2024), *Brightest Cluster Galaxy Offsets
in Cold Dark Matter*, The Open Journal of Astrophysics
([arXiv:2402.00928](https://arxiv.org/abs/2402.00928)).</sub>

## Install

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv tool install git+https://github.com/CianMRoche/figure-inversion
```

## Use

```bash
figinvert fig.pdf              # -> fig_dark.pdf
figinvert fig.pdf -m lab       # punchier
figinvert *.png -t             # transparent background
figinvert fig.svg -o out.svg
```

## Modes

| mode | white → | black → | |
|---|---|---|---|
| `overleaf` *(default)* | `#171717` | `#d1d1d1` | approximates the Overleaf PDF inversion |
| `lab` | `#171717` | `#ffffff` | flips CIELAB lightness, keeps hue and chroma |
| `naive` | `#000000` | `#ffffff` | plain `255-x`; destroys hue, for comparison |

`overleaf` matches what screenshotting a dark PDF viewer gives you. `lab` uses
the same background but takes black all the way to white, so more contrast and
more saturated lines. Both preserve hue; `naive` turns a blue line orange, which
is why the other two exist.

## Options

| flag | |
|---|---|
| `-m, --mode` | `overleaf` (default), `lab`, `naive` |
| `-t, --transparent` | drop the background instead of darkening it |
| `-o, --output` | output path (single input only) |
| `--suffix` | rename suffix, default `_dark` |
| `--overwrite` | edit in place |
| `--chroma` | saturation multiplier for `lab`, e.g. `1.25` |
| `--range LO HI` | `lab` output L\* range, default `7.74 100` |
| `--bg-method` | raster transparency: `unmix` (default) or `key` |
| `--no-image-recolour` | leave rasters embedded in a PDF untouched |

**`--transparent`** — PDF/SVG: a white shape covering ≥95% of the page is
dropped. Raster `unmix` (default) recovers antialiased coverage from a white
ground, exact for lines and text but solid light fills go partly transparent;
use `key` for bar charts and filled regions.

**Heatmaps** — use `--no-image-recolour`, or an inverted viridis image stops
meaning what its colourbar says.

## Accuracy of `overleaf` mode

Fitted to a 36-swatch calibration target rendered through a real Overleaf
inversion and screenshotted, so these are measured, not guessed:

- **Neutral tones are exact by construction** — white → `#171717`, black →
  `#d1d1d1`, matching to within a rounding step. Backgrounds and greyscale text
  are most of what you see, so output reads correctly.
- **Chromatic colours are approximate** — RMSE 10/255, worst case 37/255. Greens
  and cyans come out lighter than the real thing.
- Residuals are *structured*, not random, so the true filter is **not** in the
  modelled family (invert → hue-rotate about the luma axis → affine). It could
  not be identified from the calibration data alone. A 4-parameter chain beat a
  30-parameter polynomial, pointing at clamping this model does not reproduce.

Know the exact CSS filter your viewer applies? Encoding it beats fitting — the
constants are at the top of [`src/figinvert/colour.py`](src/figinvert/colour.py).

## In LaTeX

```latex
\newif\ifdark\darktrue
\newcommand{\fig}[2][]{%
  \ifdark\includegraphics[#1]{#2_dark}\else\includegraphics[#1]{#2}\fi}
```

If the figure came from matplotlib and you still have the script, re-rendering
with a dark style beats inverting — the inverter cannot know a grey gridline
needs *more* contrast on dark, not less. This is for figures whose source you no
longer have.

## Development

```bash
git clone https://github.com/CianMRoche/figure-inversion
cd figure-inversion
uv sync --group dev
uv run pytest -q
```

Fixtures build minimal PDFs, SVGs and PNGs by hand, so the suite needs only the
runtime dependencies plus pytest. Regenerate the examples and comparison strip
with `uv run --group dev python examples/make_examples.py`.

```
src/figinvert/
  colour.py   colour transforms + fitted constants
  pdf.py      vector PDF backend (pikepdf content-stream rewriting)
  svg.py      SVG backend (lxml attribute/CSS rewriting)
  raster.py   PNG/JPEG backend (Pillow)
  cli.py      argument parsing and dispatch
```

`examples/bcg-offsets.pdf` is a figure from Roche et al. (2024) above. It
doubles as a test case: vector strokes, LaTeX text, semi-transparent fills and
an indexed-palette raster — the combination that exposed a colour-space bug
during development (see `tests/test_formats.py`).

## Limitations

- PDF shadings and pattern / `Separation` colour spaces are left untouched.
- The transparency heuristic keys on "white shape covering most of the page"; a
  figure whose real content is a full-bleed white rectangle would lose it.
- `overleaf` mode is approximate for saturated colours (above).
- CMYK fills round-trip through RGB, so exact CMYK is not preserved.
- Indexed images are recoloured via their palette (lossless, keeps files small);
  ICCBased and Lab palettes are left alone.

## Licence

MIT — see [LICENSE](LICENSE).
