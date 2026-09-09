"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .colour import BG_HEX, BG_LSTAR, DEFAULT_MODE, MODES, background_colour

RASTER = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
VECTOR_PDF = {".pdf"}
VECTOR_SVG = {".svg"}


def _default_out(path: Path, suffix: str) -> Path:
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="figinvert",
        description="Make dark-background versions of figures (PDF, SVG, PNG/JPG) "
                    "without screenshotting a PDF viewer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
modes:
  overleaf  (default) approximates the Overleaf PDF inversion. Neutral tones
            are exact -- white lands on {BG_HEX}, black on #d1d1d1 -- but
            chromatic colours are fitted, RMSE 10/255, worst case 37/255.
  lab       flips perceptual lightness in CIELAB keeping hue and chroma. Same
            {BG_HEX} background, but takes black all the way to pure white,
            so more contrast and more saturated lines. Usually looks better.
  naive     plain 255-x. Destroys hue (blue becomes orange). For comparison.

examples:
  figinvert fig.pdf                      # -> fig_dark.pdf, stays vector
  figinvert fig.pdf --mode lab           # punchier
  figinvert *.png --transparent          # drop the white ground entirely
  figinvert fig.svg -o dark/fig.svg
  figinvert fig.pdf --chroma 1.25        # boost saturation on dark
""")
    p.add_argument("inputs", nargs="+", type=Path, help="figure file(s)")
    p.add_argument("-o", "--output", type=Path,
                   help="output path (only valid with a single input)")
    p.add_argument("-m", "--mode", choices=sorted(MODES), default=DEFAULT_MODE,
                   help=f"colour transform (default: {DEFAULT_MODE})")
    p.add_argument("-t", "--transparent", action="store_true",
                   help="make the page/figure background transparent instead of dark")
    p.add_argument("--suffix", default="_dark",
                   help="suffix for generated names (default: _dark)")
    p.add_argument("--chroma", type=float, default=1.0,
                   help="saturation multiplier, lab mode (e.g. 1.25)")
    p.add_argument("--range", nargs=2, type=float, metavar=("LO", "HI"),
                   default=[BG_LSTAR, 100.0],
                   help=f"lab mode L* output range (default: {BG_LSTAR:g} 100)")
    p.add_argument("--bg-method", choices=("unmix", "key"), default="unmix",
                   help="raster transparency: 'unmix' recovers antialiased coverage "
                        "from a white ground (best for line plots); 'key' matches the "
                        "corner colour (best for solid fills)")
    p.add_argument("--no-image-recolour", action="store_true",
                   help="leave raster images embedded inside a PDF untouched")
    p.add_argument("--overwrite", action="store_true",
                   help="edit files in place instead of writing <name>_dark")
    p.add_argument("-q", "--quiet", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.output and len(args.inputs) > 1:
        print("error: -o/--output needs exactly one input", file=sys.stderr)
        return 2

    lo, hi = args.range
    bg = background_colour(args.mode, lo=lo, hi=hi, chroma=args.chroma)
    bg_hex = "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in bg)

    rc = 0
    for src in args.inputs:
        if not src.exists():
            print(f"error: {src}: no such file", file=sys.stderr)
            rc = 1
            continue

        ext = src.suffix.lower()
        if args.output:
            dst = args.output
        elif args.overwrite:
            dst = src
        else:
            dst = _default_out(src, args.suffix)
        dst.parent.mkdir(parents=True, exist_ok=True)

        try:
            if ext in VECTOR_PDF:
                from .pdf import convert_pdf
                convert_pdf(src, dst, mode=args.mode, lo=lo, hi=hi,
                            chroma=args.chroma, transparent=args.transparent,
                            recolour_images=not args.no_image_recolour)
                kind = "vector pdf"
            elif ext in VECTOR_SVG:
                from .svg import convert_svg
                convert_svg(src, dst, mode=args.mode, lo=lo, hi=hi,
                            chroma=args.chroma, transparent=args.transparent)
                kind = "vector svg"
            elif ext in RASTER:
                from .raster import convert_raster
                convert_raster(src, dst, mode=args.mode, lo=lo, hi=hi,
                               chroma=args.chroma, transparent=args.transparent,
                               bg_method=args.bg_method)
                kind = "raster"
            else:
                print(f"error: {src}: unsupported extension {ext}", file=sys.stderr)
                rc = 1
                continue
        except Exception as exc:  # noqa: BLE001
            print(f"error: {src}: {type(exc).__name__}: {exc}", file=sys.stderr)
            rc = 1
            continue

        if not args.quiet:
            ground = "transparent" if args.transparent else bg_hex
            print(f"{src.name} -> {dst}  [{kind}, {args.mode}, bg {ground}]")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
