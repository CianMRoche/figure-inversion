"""Test fixtures.

Deliberately no matplotlib: fixtures build minimal files by hand so CI installs
only the runtime dependencies plus pytest.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

# Colours used across the tests, chosen to exercise hue preservation.
BLUE = (0.12, 0.47, 0.71)
RED = (0.84, 0.15, 0.16)


def _minimal_pdf(content: bytes, width=200, height=120) -> bytes:
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
         b"/Contents 4 0 R /Resources << >> >>" % (width, height)),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"endstream",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    start = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, start))
    return out


@pytest.fixture
def pdf_file(tmp_path):
    """A white-backgrounded PDF with a blue fill and a red stroke."""
    content = (
        b"1 g 0 0 200 120 re f\n"
        b"%.4f %.4f %.4f rg 20 20 70 50 re f\n" % BLUE
        + b"%.4f %.4f %.4f RG 4 w 20 90 m 180 90 l S\n" % RED
    )
    p = tmp_path / "fig.pdf"
    p.write_bytes(_minimal_pdf(content))
    return p


def _indexed_image_pdf() -> bytes:
    """A PDF whose only content is an /Indexed (palette) image.

    Palette is white + blue, with the `/Decode [0 255]` array matplotlib emits
    for indexed images. Rewriting such an image to DeviceRGB while copying that
    2-entry Decode onto 3 components renders as solid red.
    """
    content = b"q 100 0 0 100 20 10 cm /Im0 Do Q\n"
    img = (b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 "
           b"/BitsPerComponent 8 /Decode [0 255] "
           b"/ColorSpace [/Indexed /DeviceRGB 1 <FFFFFF0000FF>] "
           b"/Length 4 >>\nstream\n" + bytes([0, 1, 1, 0]) + b"\nendstream")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 140 120] /Contents 4 0 R "
         b"/Resources << /XObject << /Im0 5 0 R >> >> >>"),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"endstream",
        img,
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    start = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, start))
    return out


@pytest.fixture
def indexed_image_pdf(tmp_path):
    p = tmp_path / "indexed.pdf"
    p.write_bytes(_indexed_image_pdf())
    return p


@pytest.fixture
def svg_file(tmp_path):
    p = tmp_path / "fig.svg"
    p.write_text(
        '<?xml version="1.0"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="120">'
        '<rect x="0" y="0" width="200" height="120" fill="#ffffff"/>'
        '<rect x="20" y="20" width="70" height="50" fill="#1f77b4"/>'
        '<text x="10" y="110" style="fill:#000000">hello</text>'
        '<path d="M20 90 L180 90" stroke="rgb(214,39,40)" fill="none"/>'
        "</svg>\n"
    )
    return p


@pytest.fixture
def png_file(tmp_path):
    """White background, one opaque blue square, saved RGBA and fully opaque.

    The all-opaque alpha channel matters: matplotlib writes RGBA even for a
    solid figure, and mistaking that for real transparency once made
    --transparent silently do nothing.
    """
    a = np.full((60, 100, 4), 255, dtype=np.uint8)
    a[10:40, 10:50, :3] = (31, 119, 180)
    p = tmp_path / "fig.png"
    Image.fromarray(a, "RGBA").save(p)
    return p


def render_pdf(path, dpi=72):
    """Render a PDF to an RGBA array, or skip if no renderer is installed."""
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open(path)
    pm = doc[0].get_pixmap(dpi=dpi, alpha=True)
    return np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)
