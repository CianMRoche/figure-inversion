"""Format backends, plus regression tests for two bugs that shipped silently."""

from __future__ import annotations

import re
import zlib

import numpy as np
import pytest
from PIL import Image

from figinvert.cli import main

from conftest import render_pdf


def content_streams(path):
    """Every (decompressed) content stream in a PDF, as text."""
    data = path.read_bytes()
    out = []
    for raw in re.findall(rb"stream\r?\n(.*?)endstream", data, re.S):
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            pass
        out.append(raw.decode("latin1"))
    return "\n".join(out)


def tokens(path):
    """Whitespace-separated tokens of a PDF's content streams.

    Operators sit on their own lines, so substring checks like `" f" in text`
    are unreliable -- compare tokens instead.
    """
    return content_streams(path).split()


# ---------------------------------------------------------------- PDF

def test_pdf_conversion_actually_changes_the_file(pdf_file, tmp_path):
    """REGRESSION: parse_content_stream takes a pikepdf object, not bytes.

    Passing bytes raised TypeError into a broad `except`, so conversion
    reported success while writing an unchanged file.
    """
    out = tmp_path / "out.pdf"
    assert main([str(pdf_file), "-o", str(out), "-q"]) == 0
    before, after = content_streams(pdf_file), content_streams(out)
    assert before != after, "content stream was not rewritten at all"
    assert "1 g" not in after, "the white background operator survived"


def test_pdf_background_renders_as_the_calibrated_colour(pdf_file, tmp_path):
    out = tmp_path / "out.pdf"
    main([str(pdf_file), "-o", str(out), "-q"])
    px = render_pdf(out)
    corner = px[3, 3][:3]
    assert np.all(np.abs(corner.astype(int) - 23) <= 2), f"corner was {corner}"


def test_pdf_stays_vector(pdf_file, tmp_path):
    """No rasterisation: no image XObjects, path operators still present."""
    out = tmp_path / "out.pdf"
    main([str(pdf_file), "-o", str(out), "-q"])
    body = out.read_bytes()
    assert b"/Image" not in body
    tok = tokens(out)
    assert "re" in tok and "S" in tok, "path operators were lost"
    assert len(body) < 4 * len(pdf_file.read_bytes())


def test_pdf_transparent_drops_the_background(pdf_file, tmp_path):
    out = tmp_path / "out.pdf"
    main([str(pdf_file), "-o", str(out), "-t", "-q"])
    px = render_pdf(out)
    assert px.shape[2] == 4
    assert px[3, 3][3] == 0, "corner should be fully transparent"
    # the foreground must survive
    assert px[..., 3].max() == 255


def test_pdf_transparent_keeps_a_non_background_white_shape(tmp_path):
    """The drop heuristic is area-gated; a small white shape must survive."""
    from conftest import _minimal_pdf
    src = tmp_path / "small.pdf"
    src.write_bytes(_minimal_pdf(
        b"0.2 0.4 0.6 rg 0 0 200 120 re f\n1 g 80 50 20 20 re f\n"))
    out = tmp_path / "out.pdf"
    main([str(src), "-o", str(out), "-t", "-q"])
    assert tokens(out).count("f") >= 2, "the small white rect was wrongly dropped"


@pytest.mark.parametrize("mode,expected", [("overleaf", 23), ("lab", 23), ("naive", 0)])
def test_pdf_modes_produce_their_documented_background(pdf_file, tmp_path, mode, expected):
    out = tmp_path / f"{mode}.pdf"
    main([str(pdf_file), "-o", str(out), "-m", mode, "-q"])
    corner = render_pdf(out)[3, 3][:3].astype(int)
    assert np.all(np.abs(corner - expected) <= 2), f"{mode}: {corner}"


def test_indexed_image_keeps_its_palette_colour_space(indexed_image_pdf, tmp_path):
    """REGRESSION: an /Indexed image was re-encoded to DeviceRGB while its
    /Decode [0 255] was copied across, giving a 2-entry decode on 3 components.
    Real-world figures rendered the affected areas as solid red.

    The fix transforms the palette in place, so the image stays Indexed.
    """
    import pikepdf
    out = tmp_path / "out.pdf"
    assert main([str(indexed_image_pdf), "-o", str(out), "-q"]) == 0

    with pikepdf.open(out) as pdf:
        xo = pdf.pages[0].Resources.XObject["/Im0"]
        cs = xo.ColorSpace
        assert isinstance(cs, pikepdf.Array) and cs[0] == pikepdf.Name.Indexed, (
            "image should still be palette-indexed")
        palette = bytes(cs[3])
        assert len(palette) == 6, "two RGB palette entries expected"
        # white entry must become the calibrated dark ground
        assert tuple(palette[:3]) == (23, 23, 23), tuple(palette[:3])
        # a /Decode present here is still the indexed default, so it stays valid
        if "/Decode" in xo:
            assert len(xo.Decode) == 2


def test_indexed_image_renders_without_colour_corruption(indexed_image_pdf, tmp_path):
    """End-to-end guard: no channel of the rendered image should blow out."""
    out = tmp_path / "out.pdf"
    main([str(indexed_image_pdf), "-o", str(out), "-q"])
    px = render_pdf(out)[..., :3].astype(int)
    # the blue palette entry stays blue-dominant; nothing becomes red-dominant
    reddest = px[(px[..., 0] > px[..., 2] + 40)]
    assert reddest.size == 0, "unexpected red-dominant pixels (palette corrupted)"


def test_no_image_recolour_leaves_the_palette_alone(indexed_image_pdf, tmp_path):
    import pikepdf
    out = tmp_path / "out.pdf"
    main([str(indexed_image_pdf), "-o", str(out), "--no-image-recolour", "-q"])
    with pikepdf.open(out) as pdf:
        palette = bytes(pdf.pages[0].Resources.XObject["/Im0"].ColorSpace[3])
    assert tuple(palette[:3]) == (255, 255, 255), "palette should be untouched"


# ---------------------------------------------------------------- raster

def test_raster_transparent_on_an_all_opaque_rgba_input(png_file, tmp_path):
    """REGRESSION: matplotlib writes RGBA even for a solid white figure.

    Treating that all-opaque channel as real transparency made --transparent
    silently return the opaque image.
    """
    out = tmp_path / "out.png"
    assert main([str(png_file), "-o", str(out), "-t", "-q"]) == 0
    a = np.asarray(Image.open(out))
    assert a.shape[2] == 4
    assert a[..., 3].min() == 0, "nothing was made transparent"
    assert a[0, 0, 3] == 0, "the white ground should be gone"


def test_raster_opaque_mode_uses_the_calibrated_background(png_file, tmp_path):
    out = tmp_path / "out.png"
    main([str(png_file), "-o", str(out), "-q"])
    a = np.asarray(Image.open(out).convert("RGB"))
    assert tuple(a[0, 0]) == (23, 23, 23)


def test_raster_key_method_keeps_fills_opaque(png_file, tmp_path):
    out = tmp_path / "out.png"
    main([str(png_file), "-o", str(out), "-t", "--bg-method", "key", "-q"])
    a = np.asarray(Image.open(out))
    assert a[25, 30, 3] == 255, "the solid square should stay opaque"
    assert a[0, 0, 3] == 0


def test_jpeg_output_is_written_without_alpha(png_file, tmp_path):
    out = tmp_path / "out.jpg"
    assert main([str(png_file), "-o", str(out), "-q"]) == 0
    assert Image.open(out).mode == "RGB"


# ---------------------------------------------------------------- SVG

def test_svg_rewrites_colours_and_stays_text(svg_file, tmp_path):
    out = tmp_path / "out.svg"
    assert main([str(svg_file), "-o", str(out), "-q"]) == 0
    body = out.read_text()
    assert "#ffffff" not in body.lower()
    assert "#171717" in body.lower(), "white should become the dark ground"
    assert "#d1d1d1" in body.lower(), "black text should become light grey"
    assert "<text" in body, "still a real SVG, not a raster"


def test_svg_handles_style_attributes_and_rgb_notation(svg_file, tmp_path):
    out = tmp_path / "out.svg"
    main([str(svg_file), "-o", str(out), "-q"])
    body = out.read_text()
    assert "fill:#000000" not in body
    assert "rgb(214,39,40)" not in body


def test_svg_transparent_removes_the_background_rect(svg_file, tmp_path):
    out = tmp_path / "out.svg"
    main([str(svg_file), "-o", str(out), "-t", "-q"])
    body = out.read_text()
    assert 'width="200"' not in body or "#171717" not in body


def test_svg_leaves_none_and_urls_alone(tmp_path):
    src = tmp_path / "a.svg"
    src.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
                   '<rect width="10" height="10" fill="none" stroke="url(#g)"/></svg>')
    out = tmp_path / "b.svg"
    main([str(src), "-o", str(out), "-q"])
    body = out.read_text()
    assert 'fill="none"' in body and "url(#g)" in body


# ---------------------------------------------------------------- CLI

def test_missing_file_is_reported(tmp_path):
    assert main([str(tmp_path / "nope.pdf"), "-q"]) == 1


def test_unsupported_extension_is_reported(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hi")
    assert main([str(p), "-q"]) == 1


def test_output_flag_rejects_multiple_inputs(pdf_file, svg_file, tmp_path):
    assert main([str(pdf_file), str(svg_file), "-o", str(tmp_path / "x.pdf")]) == 2


def test_default_suffix_and_batch(pdf_file, svg_file):
    assert main([str(pdf_file), str(svg_file), "-q"]) == 0
    assert pdf_file.with_name("fig_dark.pdf").exists()
    assert svg_file.with_name("fig_dark.svg").exists()


def test_custom_suffix(pdf_file):
    main([str(pdf_file), "--suffix", "_night", "-q"])
    assert pdf_file.with_name("fig_night.pdf").exists()
