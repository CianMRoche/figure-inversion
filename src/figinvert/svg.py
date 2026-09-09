"""SVG backend -- rewrites colour attributes and CSS, keeping the file vector."""

from __future__ import annotations

import re

import numpy as np
from lxml import etree
from PIL import ImageColor

from .colour import get_transform

SVG_NS = "http://www.w3.org/2000/svg"

# Presentation attributes that hold a colour
COLOUR_ATTRS = (
    "fill", "stroke", "stop-color", "color", "flood-color",
    "lighting-color", "solid-color", "background-color",
)

_SKIP = {"none", "currentcolor", "transparent", "inherit", "initial", "unset", ""}

_CSS_DECL = re.compile(r"([-\w]+)\s*:\s*([^;]+)")


def _parse(value):
    v = value.strip()
    if v.lower() in _SKIP or v.startswith("url("):
        return None
    try:
        rgb = ImageColor.getrgb(v)
    except ValueError:
        return None
    if len(rgb) == 4:
        return np.array(rgb[:3]) / 255.0, rgb[3] / 255.0
    return np.array(rgb) / 255.0, None


def _fmt(rgb, alpha=None):
    r, g, b = (np.clip(rgb, 0, 1) * 255).round().astype(int)
    if alpha is not None and alpha < 1.0:
        return f"rgba({r},{g},{b},{alpha:.4g})"
    return f"#{r:02x}{g:02x}{b:02x}"


def _convert_value(value, fn):
    parsed = _parse(value)
    if parsed is None:
        return None
    rgb, alpha = parsed
    return _fmt(fn(rgb), alpha)


def _convert_style(style, fn):
    def sub(m):
        prop, val = m.group(1), m.group(2)
        if prop.strip().lower() in COLOUR_ATTRS:
            new = _convert_value(val, fn)
            if new is not None:
                return f"{prop}:{new}"
        return m.group(0)
    return _CSS_DECL.sub(sub, style)


def _is_full_canvas_white(el, width, height, fn=None):
    if etree.QName(el).localname != "rect":
        return False
    fill = el.get("fill", "")
    if not fill and el.get("style"):
        m = re.search(r"fill\s*:\s*([^;]+)", el.get("style"))
        fill = m.group(1) if m else ""
    p = _parse(fill or "#000")
    if p is None or float(np.min(p[0])) < 0.97:
        return False
    try:
        w = float(re.sub(r"[a-z%]", "", el.get("width", "0")))
        h = float(re.sub(r"[a-z%]", "", el.get("height", "0")))
    except ValueError:
        return False
    if width and height:
        return w >= 0.95 * width and h >= 0.95 * height
    return False


def _dims(root):
    def n(v):
        if not v:
            return None
        try:
            return float(re.sub(r"[a-z%]+$", "", v.strip()))
        except ValueError:
            return None
    w, h = n(root.get("width")), n(root.get("height"))
    if w is None or h is None:
        vb = root.get("viewBox")
        if vb:
            parts = re.split(r"[ ,]+", vb.strip())
            if len(parts) == 4:
                try:
                    w, h = float(parts[2]), float(parts[3])
                except ValueError:
                    pass
    return w, h


def convert_svg(src, dst, mode="overleaf", lo=None, hi=100.0, chroma=1.0,
                transparent=False):
    from .colour import BG_LSTAR
    if lo is None:
        lo = BG_LSTAR
    fn = get_transform(mode, lo=lo, hi=hi, chroma=chroma)

    parser = etree.XMLParser(remove_blank_text=False, huge_tree=True)
    tree = etree.parse(str(src), parser)
    root = tree.getroot()
    width, height = _dims(root)

    had_bg = False
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            continue
        local = etree.QName(el).localname

        if _is_full_canvas_white(el, width, height):
            had_bg = True
            if transparent:
                el.getparent().remove(el)
                continue

        for attr in COLOUR_ATTRS:
            if attr in el.attrib:
                new = _convert_value(el.get(attr), fn)
                if new is not None:
                    el.set(attr, new)

        if "style" in el.attrib:
            el.set("style", _convert_style(el.get("style"), fn))

        if local == "style" and el.text:
            el.text = _CSS_DECL.sub(
                lambda m: (f"{m.group(1)}:{_convert_value(m.group(2), fn)}"
                           if m.group(1).strip().lower() in COLOUR_ATTRS
                           and _convert_value(m.group(2), fn) else m.group(0)),
                el.text,
            )

    if not transparent and not had_bg and width and height:
        bg = fn(np.array([1.0, 1.0, 1.0]))
        rect = etree.Element(f"{{{SVG_NS}}}rect")
        rect.set("x", "0"); rect.set("y", "0")
        rect.set("width", str(width)); rect.set("height", str(height))
        rect.set("fill", _fmt(bg))
        root.insert(0, rect)

    tree.write(str(dst), xml_declaration=True, encoding="utf-8")
    return dst
