"""Regenerate the converted example figures and the README comparison strip.

    uv run --group dev python examples/make_examples.py

Source figure: `bcg-offsets.pdf`, Figure 3 of Roche et al. (2024), "Brightest
Cluster Galaxy Offsets in Cold Dark Matter" (arXiv:2402.00928), used here with
the author's permission. Only the conversions are regenerated; the source PDF
is committed as-is.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / "bcg-offsets.pdf"

PANELS = [
    ("Original", SOURCE),
    ("--mode overleaf (default)", HERE / "bcg-offsets_overleaf.pdf"),
    ("--mode lab", HERE / "bcg-offsets_lab.pdf"),
]


def convert():
    for mode, out in [("overleaf", PANELS[1][1]), ("lab", PANELS[2][1])]:
        subprocess.run([sys.executable, "-m", "figinvert.cli", str(SOURCE),
                        "-m", mode, "-o", str(out), "-q"], check=True)


def contact_sheet(path, dpi=150, pad=12, label_h=26):
    import pymupdf
    from PIL import Image, ImageDraw

    tiles = []
    for _, pdf in PANELS:
        pm = pymupdf.open(pdf)[0].get_pixmap(dpi=dpi)
        tiles.append(Image.frombytes("RGB", (pm.width, pm.height), pm.samples))

    w, h = tiles[0].size
    sheet = Image.new("RGB", (len(tiles) * w + (len(tiles) + 1) * pad,
                              h + 2 * pad + label_h), "#8a8a8a")
    draw = ImageDraw.Draw(sheet)
    for i, (tile, (label, _)) in enumerate(zip(tiles, PANELS)):
        x = pad + i * (w + pad)
        sheet.paste(tile, (x, pad + label_h))
        draw.text((x + (w - draw.textlength(label)) / 2, pad + 6),
                  label, fill="#101010")
    sheet.save(path)
    return sheet.size


if __name__ == "__main__":
    if not SOURCE.exists():
        sys.exit(f"missing source figure: {SOURCE}")
    convert()
    size = contact_sheet(HERE / "before-after.png")
    print(f"regenerated examples in {HERE} (strip {size[0]}x{size[1]})")
