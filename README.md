# figinvert

[![CI](https://github.com/CianMRoche/figure-inversion/actions/workflows/ci.yml/badge.svg)](https://github.com/CianMRoche/figure-inversion/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Dark-background versions of figures — PDF, SVG, PNG/JPG — without screenshotting
a PDF viewer.

![before and after](examples/before-after.png)

<sub>Example figure from Roche et al. (2024), *Brightest Cluster Galaxy Offsets
in Cold Dark Matter*, The Open Journal of Astrophysics
([arXiv:2402.00928](https://arxiv.org/abs/2402.00928)). Both dark versions are
still vector PDFs — text selectable, no rasterisation.</sub>

If you write LaTeX and want dark figures, the usual hack is to compile, switch
the PDF viewer to dark mode, and screenshot the figure out of the page. That is
lossy, unrepeatable, and gives you a raster crop of what was a vector drawing.
This does the transform directly on the figure file.

**PDFs and SVGs stay vector.** Colour operators are rewritten in place, so text
stays selectable, curves stay sharp at any zoom, and the file size barely
changes. Nothing is rasterised.

## Install

You do not need to clone it to use it:

```bash
uv tool install git+https://github.com/CianMRoche/figure-inversion
```

Or run it once without installing:

```bash
uvx --from git+https://github.com/CianMRoche/figure-inversion figinvert fig.pdf
```

Or from a clone:

```bash
git clone https://github.com/CianMRoche/figure-inversion
cd figure-inversion
uv tool install --editable .     # --editable: source edits apply immediately
```

`uv` puts the executable in `~/.local/bin`. If that is not on your `PATH`, run
`uv tool update-shell` and restart your shell. Without `uv`, `pipx install .` or
`pip install .` work too. Python 3.10+.

## Usage

```bash
figinvert fig.pdf                  # -> fig_dark.pdf, still vector
figinvert fig.pdf --mode lab       # punchier alternative
figinvert *.png --transparent      # no background at all
figinvert fig.svg -o dark/fig.svg
figinvert fig.pdf --chroma 1.25    # boost saturation on dark
```

### Modes

| mode | white becomes | black becomes | notes |
|---|---|---|---|
| `overleaf` *(default)* | `#171717` | `#d1d1d1` | approximates the Overleaf PDF inversion |
| `lab` | `#171717` | `#ffffff` | flips CIELAB lightness, keeps hue and chroma |
| `naive` | `#000000` | `#ffffff` | plain `255-x`; destroys hue, for comparison |

`overleaf` reproduces what you get from screenshotting a dark PDF viewer. `lab`
puts the background on the same `#171717` but takes black all the way to white
instead of stopping at `#d1d1d1`, so lines are more saturated and text has more
contrast. Try both on a real figure.

`naive` exists to show why the other two are needed: inverting each channel
independently turns a blue line orange, because it flips *hue* along with
lightness. `overleaf` and `lab` both preserve hue.

### How accurate is `overleaf` mode?

It was fitted to a 36-swatch calibration target rendered through a real Overleaf
PDF inversion and screenshotted, so these numbers are measured, not guessed:

- **Neutral tones are exact by construction.** White lands on `#171717` and
  black on `#d1d1d1`, matching the measurement to within a rounding step.
  Backgrounds and greyscale text are most of what you look at, so output reads
  correctly.
- **Chromatic colours are approximate.** RMSE 10/255, worst case 37/255. Greens
  and cyans come out lighter here than in the real thing.
- The residuals are *structured* rather than random, which means the true filter
  is **not** in the modelled family (invert → hue-rotate about the luma axis →
  affine). It could not be identified from the calibration data alone.

Notably, a 4-parameter filter chain outperformed a 30-parameter polynomial fit,
which points to clamping behaviour in the real filter that this model does not
reproduce. If you know the exact CSS filter your viewer or extension applies,
encoding it directly beats fitting — the constants are at the top of
[`src/figinvert/colour.py`](src/figinvert/colour.py).

### Options

| flag | meaning |
|---|---|
| `-m, --mode` | `overleaf` (default), `lab`, `naive` |
| `-t, --transparent` | drop the background instead of darkening it |
| `-o, --output` | explicit output path (single input only) |
| `--suffix` | rename suffix, default `_dark` |
| `--overwrite` | edit in place instead of writing a new file |
| `--chroma` | saturation multiplier for `lab`, e.g. `1.25` |
| `--range LO HI` | `lab` output L\* range, default `7.74 100` |
| `--bg-method` | raster transparency: `unmix` (default) or `key` |
| `--no-image-recolour` | leave rasters embedded in a PDF untouched |

### `--transparent`

- **PDF / SVG** — a white shape covering ≥95% of the page is dropped.
- **Raster, `unmix` (default)** — recovers antialiased coverage from a white
  ground (`c = a·k + (1−a)·1`). Exact for lines, glyphs and axes; **solid
  light-coloured fills come out partly transparent**, so use `key` for bar
  charts and filled regions.
- **Raster, `key`** — keys out the corner colour. Keeps fills opaque, but leaves
  faint halos on antialiased edges.

### Colormap images

`--no-image-recolour` leaves rasters embedded in a PDF alone. Use it for
heatmaps: inverting a viridis image makes the colormap no longer mean what its
colourbar says.

## Using it from LaTeX

Generate both versions and switch on a flag:

```latex
\newif\ifdark\darktrue
\newcommand{\fig}[2][]{%
  \ifdark\includegraphics[#1]{#2_dark}\else\includegraphics[#1]{#2}\fi}
```

```latex
\fig[width=.8\linewidth]{plots/response}
```

If your figures come from matplotlib and you still have the plotting scripts,
re-rendering with a dark style will always beat inverting — the inverter cannot
know that a grey gridline should get *more* contrast on dark, not less. This
tool is for figures whose source you no longer have, or that came from
elsewhere.

## Development

```bash
git clone https://github.com/CianMRoche/figure-inversion
cd figure-inversion
uv sync --group dev
uv run pytest -q
```

The test fixtures build minimal PDFs, SVGs and PNGs by hand rather than pulling
in matplotlib, so the suite runs on the runtime dependencies plus pytest. To
regenerate the converted examples and the comparison strip:

```bash
uv run --group dev python examples/make_examples.py
```

### Example figure

`examples/bcg-offsets.pdf` is a published figure from:

> Cian Roche, Michael McDonald, Josh Borrow, Mark Vogelsberger, Xuejian Shen,
> Volker Springel, Lars Hernquist, Ruediger Pakmor, Sownak Bose and Rahul
> Kannan, *Brightest Cluster Galaxy Offsets in Cold Dark Matter*,
> The Open Journal of Astrophysics, 2024.
> [arXiv:2402.00928](https://arxiv.org/abs/2402.00928)

It is a useful test case as well as an illustration: it mixes vector strokes,
LaTeX-rendered text, semi-transparent fills and an **indexed-palette raster**,
which is exactly the combination that exposed a colour-space bug during
development (see `tests/test_formats.py`).

### Layout

```
src/figinvert/
  colour.py   colour transforms + the fitted constants
  pdf.py      vector PDF backend (pikepdf content-stream rewriting)
  svg.py      SVG backend (lxml attribute/CSS rewriting)
  raster.py   PNG/JPEG backend (Pillow)
  cli.py      argument parsing and dispatch
tests/        pytest suite, including regressions for three real bugs
```

## Limitations

- PDF shadings and pattern / `Separation` colour spaces are left untouched.
- The transparency heuristic keys on "white shape covering most of the page"; a
  figure whose real content is a full-bleed white rectangle would lose it.
- `overleaf` mode is approximate for saturated colours (see above).
- CMYK fills are converted through RGB, so an exact CMYK round-trip is not
  guaranteed.
- Indexed (palette) images are recoloured by transforming the palette, which is
  lossless and keeps the file small. Images in ICCBased or Lab palettes are left
  untouched.

## Licence

MIT — see [LICENSE](LICENSE).
