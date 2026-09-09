"""Vector PDF backend.

Rewrites the colour operators inside the page content streams rather than
rasterising, so the output stays vector: text stays selectable, lines stay
sharp at any zoom, and file size barely changes.
"""

from __future__ import annotations

import zlib

import numpy as np
import pikepdf
from pikepdf import Name, Operator, PdfImage
from pikepdf import ContentStreamInstruction as CSI

from .colour import get_transform

# Path construction / painting operator sets
_PATH_CONSTRUCT = {"m", "l", "c", "v", "y", "h", "re"}
_PATH_PAINT = {"f", "F", "f*", "B", "B*", "b", "b*", "S", "s", "n"}
_FILL_PAINT = {"f", "F", "f*", "B", "B*", "b", "b*"}


def _cmyk_to_rgb(c, m, y, k):
    return np.array([(1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)])


def _rgb_to_cmyk(rgb):
    r, g, b = rgb
    k = 1 - max(r, g, b)
    if k >= 1 - 1e-9:
        return [0.0, 0.0, 0.0, 1.0]
    return [(1 - r - k) / (1 - k), (1 - g - k) / (1 - k), (1 - b - k) / (1 - k), k]


def _mat_mul(a, b):
    """Multiply two PDF 2x3 affine matrices [a b c d e f]."""
    a0, a1, a2, a3, a4, a5 = a
    b0, b1, b2, b3, b4, b5 = b
    return [
        a0 * b0 + a1 * b2, a0 * b1 + a1 * b3,
        a2 * b0 + a3 * b2, a2 * b1 + a3 * b3,
        a4 * b0 + a5 * b2 + b4, a4 * b1 + a5 * b3 + b5,
    ]


def _path_bbox_area(pending, ctm):
    """Device-space bounding-box area of the pending path, or None.

    Covers both `re` and the closed m/l/l/l/h polygon matplotlib actually emits
    for a figure background.
    """
    pts = []
    for op, ops in pending:
        try:
            v = [float(o) for o in ops]
        except (TypeError, ValueError):
            return None
        if op in ("m", "l") and len(v) == 2:
            pts.append((v[0], v[1]))
        elif op == "c" and len(v) == 6:
            pts += [(v[0], v[1]), (v[2], v[3]), (v[4], v[5])]
        elif op in ("v", "y") and len(v) == 4:
            pts += [(v[0], v[1]), (v[2], v[3])]
        elif op == "re" and len(v) == 4:
            x, y, w, h = v
            pts += [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        elif op == "h":
            continue
    if not pts:
        return None
    a, b, c, d, e, f = ctm
    dev = [(x * a + y * c + e, x * b + y * d + f) for x, y in pts]
    xs = [p[0] for p in dev]
    ys = [p[1] for p in dev]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def _rgb_ins(rgb, operator):
    """Build an `r g b rg|RG` instruction. Operands come first, operator second."""
    return CSI([float(np.clip(v, 0.0, 1.0)) for v in rgb], Operator(operator))


def _numeric_operands(ops):
    """All operands as floats, or None if any is not a number (e.g. a Name)."""
    vals = []
    for o in ops:
        if isinstance(o, Name):
            return None
        try:
            vals.append(float(o))
        except (TypeError, ValueError):
            return None
    return vals


class _State:
    __slots__ = ("fill", "stroke", "ctm")

    def __init__(self, fill=None, stroke=None, ctm=None):
        self.fill = fill if fill is not None else np.zeros(3)
        self.stroke = stroke if stroke is not None else np.zeros(3)
        self.ctm = list(ctm) if ctm is not None else [1, 0, 0, 1, 0, 0]

    def copy(self):
        return _State(self.fill.copy(), self.stroke.copy(), list(self.ctm))


def _rewrite_instructions(instructions, fn, page_area, drop_white_bg):
    out = []
    st = _State()
    stack = []
    pending = []          # path construction ops since the last paint
    changed = False

    def num(o):
        return float(o)

    for ins in instructions:
        op = str(ins.operator)
        ops = list(ins.operands)

        # ---- graphics state ----
        if op == "q":
            stack.append(st.copy())
            out.append(ins); continue
        if op == "Q":
            if stack:
                st = stack.pop()
            out.append(ins); continue
        if op == "cm":
            try:
                st.ctm = _mat_mul([num(o) for o in ops], st.ctm)
            except Exception:
                pass
            out.append(ins); continue

        # ---- colour operators ----
        # NOTE: ContentStreamInstruction is (operands, operator), in that order.
        new = None
        if op == "g" and len(ops) == 1:
            v = num(ops[0]); st.fill = np.array([v, v, v])
            new = _rgb_ins(fn(st.fill), "rg")
        elif op == "G" and len(ops) == 1:
            v = num(ops[0]); st.stroke = np.array([v, v, v])
            new = _rgb_ins(fn(st.stroke), "RG")
        elif op == "rg" and len(ops) == 3:
            st.fill = np.array([num(o) for o in ops])
            new = _rgb_ins(fn(st.fill), "rg")
        elif op == "RG" and len(ops) == 3:
            st.stroke = np.array([num(o) for o in ops])
            new = _rgb_ins(fn(st.stroke), "RG")
        elif op == "k" and len(ops) == 4:
            st.fill = _cmyk_to_rgb(*[num(o) for o in ops])
            new = CSI([float(x) for x in _rgb_to_cmyk(fn(st.fill))], Operator("k"))
        elif op == "K" and len(ops) == 4:
            st.stroke = _cmyk_to_rgb(*[num(o) for o in ops])
            new = CSI([float(x) for x in _rgb_to_cmyk(fn(st.stroke))], Operator("K"))
        elif op in ("sc", "scn", "SC", "SCN") and ops:
            # Only numeric operands map cleanly; Separation/Pattern colours
            # (a Name operand) are left alone on purpose.
            vals = _numeric_operands(ops)
            if vals is not None and len(vals) in (1, 3, 4):
                stroking = op in ("SC", "SCN")
                if len(vals) == 1:
                    rgb = np.array([vals[0]] * 3)
                elif len(vals) == 3:
                    rgb = np.array(vals)
                else:
                    rgb = _cmyk_to_rgb(*vals)
                if stroking:
                    st.stroke = rgb
                else:
                    st.fill = rgb
                new = _rgb_ins(fn(rgb), "RG" if stroking else "rg")

        if new is not None:
            out.append(new)
            changed = True
            continue

        # ---- path tracking, for background removal ----
        if op in _PATH_CONSTRUCT:
            pending.append((op, ops))
            out.append(ins)
            continue

        if op in _PATH_PAINT:
            # `st.fill` still holds the ORIGINAL colour, so a white page
            # background is recognisable here even though the colour operator
            # emitted upstream has already been darkened.
            if drop_white_bg and op in _FILL_PAINT and float(st.fill.min()) > 0.97:
                area = _path_bbox_area(pending, st.ctm)
                if area is not None and area >= 0.95 * page_area:
                    out.append(CSI([], Operator("n")))
                    pending = []
                    changed = True
                    continue
            pending = []
            out.append(ins)
            continue

        out.append(ins)

    if not changed:
        return None
    return pikepdf.unparse_content_stream(out)


def _rewrite_object(obj, fn, page_area, drop_white_bg):
    """Parse and rewrite the content stream of a Page or Form XObject.

    `parse_content_stream` takes a pikepdf Page/Stream object, never raw bytes.
    Errors are deliberately not swallowed here: a silently skipped stream looks
    exactly like a figure that had no colours in it.
    """
    instructions = pikepdf.parse_content_stream(obj)
    return _rewrite_instructions(instructions, fn, page_area, drop_white_bg)


def _recolour_indexed_palette(xo, fn):
    """Transform an /Indexed image by rewriting its palette only.

    Far better than re-encoding to DeviceRGB: the pixel data (indices) is
    untouched, the file stays small, and nothing about the image dictionary
    changes, so entries tied to the original colour space -- /Decode, /Mask
    colour-key ranges -- stay valid.

    Returns True if handled.
    """
    cs = xo.get("/ColorSpace")
    if cs is None or not isinstance(cs, pikepdf.Array) or len(cs) != 4:
        return False
    if cs[0] != Name.Indexed:
        return False
    base = cs[1]
    if base == Name.DeviceRGB:
        ncomp = 3
    elif base == Name.DeviceGray:
        ncomp = 1
    else:
        return False        # ICCBased/Lab palettes: leave alone

    lookup = cs[3]
    try:
        raw = (lookup.read_bytes() if isinstance(lookup, pikepdf.Stream)
               else bytes(lookup))
    except Exception:
        return False
    if not raw or len(raw) % ncomp:
        return False

    table = np.frombuffer(raw, np.uint8).reshape(-1, ncomp).astype(float) / 255.0
    if ncomp == 1:
        table = np.repeat(table, 3, axis=1)
    out = (np.clip(fn(table), 0, 1) * 255).round().astype(np.uint8)

    # The transform is chromatic, so a grey palette must widen to RGB.
    cs[1] = Name.DeviceRGB
    cs[3] = pikepdf.String(out.tobytes())
    xo.ColorSpace = cs
    return True


def _process_images(pdf, resources, fn):
    """Recolour raster images embedded in the PDF."""
    xobjs = resources.get("/XObject")
    if xobjs is None:
        return
    for name in list(xobjs.keys()):
        xo = xobjs[name]
        if xo.get("/Subtype") != Name.Image:
            continue

        if _recolour_indexed_palette(xo, fn):
            continue

        try:
            pim = PdfImage(xo)
            pil = pim.as_pil_image().convert("RGB")
        except Exception:
            continue
        arr = np.asarray(pil).astype(float) / 255.0
        out = (np.clip(fn(arr), 0, 1) * 255).round().astype(np.uint8)

        st = pdf.make_stream(zlib.compress(out.tobytes(), 6))
        st.Type = Name.XObject
        st.Subtype = Name.Image
        st.Width, st.Height = int(out.shape[1]), int(out.shape[0])
        st.ColorSpace = Name.DeviceRGB
        st.BitsPerComponent = 8
        st.Filter = Name.FlateDecode
        # Keep the soft mask so image transparency survives, and /Interpolate
        # because it is colour-space independent. Deliberately NOT copied:
        #   /Decode -- its length and meaning are tied to the ORIGINAL colour
        #              space. Copying an Indexed image's [0 255] onto DeviceRGB
        #              produces a malformed 2-entry decode for 3 components,
        #              which renders as solid red.
        #   /Mask   -- only when it is a colour-key ARRAY, for the same reason.
        #              A stencil-mask stream is colour-space independent, so it
        #              is safe to carry over.
        for key in ("/SMask", "/Interpolate"):
            if key in xo:
                st[key] = xo[key]
        mask = xo.get("/Mask")
        if isinstance(mask, pikepdf.Stream):
            st.Mask = mask
        xobjs[name] = st


def _walk(pdf, obj, fn, page_area, drop_white_bg, seen, do_images):
    """Recurse into Form XObjects, rewriting their streams too."""
    res = obj.get("/Resources")
    if res is None:
        return
    if do_images:
        _process_images(pdf, res, fn)
    xobjs = res.get("/XObject")
    if xobjs is None:
        return
    for name in list(xobjs.keys()):
        xo = xobjs[name]
        key = xo.objgen if hasattr(xo, "objgen") else None
        if key in seen:
            continue
        if key is not None:
            seen.add(key)
        if xo.get("/Subtype") != Name.Form:
            continue
        new = _rewrite_object(xo, fn, page_area, drop_white_bg)
        if new is not None:
            xo.write(new)
        _walk(pdf, xo, fn, page_area, drop_white_bg, seen, do_images)


def convert_pdf(src, dst, mode="overleaf", lo=None, hi=100.0, chroma=1.0,
                transparent=False, recolour_images=True):
    from .colour import BG_LSTAR
    if lo is None:
        lo = BG_LSTAR
    fn = get_transform(mode, lo=lo, hi=hi, chroma=chroma)

    with pikepdf.open(src) as pdf:
        for page in pdf.pages:
            box = page.get("/MediaBox", [0, 0, 612, 792])
            try:
                x0, y0, x1, y1 = [float(v) for v in box]
                page_area = abs((x1 - x0) * (y1 - y0))
            except Exception:
                page_area = 612 * 792

            new = _rewrite_object(page, fn, page_area, transparent)
            if new is not None:
                page.Contents = pdf.make_stream(new)

            _walk(pdf, page, fn, page_area, transparent, set(), recolour_images)

            if not transparent:
                _paint_background(pdf, page, fn)

        pdf.save(dst)
    return dst


def _paint_background(pdf, page, fn):
    """Insert the inverted page colour behind everything.

    A figure PDF usually has no explicit background rectangle -- the page is
    "white" only because a viewer paints it white. Inverting the drawing
    operators alone would leave dark text on a still-white page, so we lay the
    inverted white underneath.
    """
    bg = fn(np.array([1.0, 1.0, 1.0]))
    box = page.get("/MediaBox", [0, 0, 612, 792])
    x0, y0, x1, y1 = [float(v) for v in box]
    rect = (f"q {bg[0]:.5f} {bg[1]:.5f} {bg[2]:.5f} rg "
            f"{x0:.4f} {y0:.4f} {x1 - x0:.4f} {y1 - y0:.4f} re f Q\n")
    page.contents_add(pikepdf.Stream(pdf, rect.encode()), prepend=True)
