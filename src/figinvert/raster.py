"""PNG / JPEG backend."""

from __future__ import annotations

import numpy as np
from PIL import Image

from .colour import get_transform


def _to_rgba(im: Image.Image) -> Image.Image:
    if im.mode in ("P", "PA"):
        im = im.convert("RGBA")
    if im.mode in ("L", "I;16", "I", "F"):
        im = im.convert("RGB")
    if im.mode == "LA":
        im = im.convert("RGBA")
    if im.mode == "CMYK":
        im = im.convert("RGB")
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA")
    return im


def _unmix_from_white(rgb):
    """Recover (ink colour, coverage) for artwork composited over white.

    c = a*k + (1-a)*1  =>  a = 1 - min(c),  k = (c - (1-a)) / a

    Exact for antialiased strokes and glyphs, which is the common case for
    plots. Solid light-coloured fills come out partly transparent, which is why
    `key` exists as an alternative.
    """
    m = rgb.min(axis=-1, keepdims=True)
    a = 1.0 - m
    safe = np.maximum(a, 1e-6)
    k = np.clip((rgb - m) / safe, 0.0, 1.0)
    k = np.where(a > 1e-6, k, 0.0)
    return k, a[..., 0]


def _key_background(rgb, bg, tol):
    """Alpha from distance to a background colour; keeps solid fills opaque."""
    d = np.linalg.norm(rgb - bg, axis=-1) / np.sqrt(3.0)
    return np.clip(d / max(tol, 1e-6), 0.0, 1.0)


def convert_raster(src, dst, mode="lab", lo=0.0, hi=100.0, chroma=1.0,
                   transparent=False, bg_method="unmix", bg_tol=0.12):
    fn = get_transform(mode, lo=lo, hi=hi, chroma=chroma)
    im = _to_rgba(Image.open(src))
    arr = np.asarray(im).astype(float) / 255.0

    rgb = arr[..., :3]
    alpha = arr[..., 3] if arr.shape[-1] == 4 else None
    # An all-opaque alpha channel is not real transparency -- matplotlib writes
    # RGBA even for a solid white figure -- so treat it as if absent.
    had_alpha = alpha is not None and float(alpha.min()) < 1.0

    if transparent and not had_alpha:
        if bg_method == "unmix":
            rgb, alpha = _unmix_from_white(rgb)
        else:
            corners = np.stack([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]])
            bg = np.median(corners, axis=0)
            alpha = _key_background(rgb, bg, bg_tol)
    elif transparent and had_alpha:
        pass  # already has real transparency; respect it

    out_rgb = fn(rgb)

    if alpha is not None:
        out = np.concatenate([out_rgb, alpha[..., None]], axis=-1)
        pil_mode = "RGBA"
    else:
        out = out_rgb
        pil_mode = "RGB"

    img = Image.fromarray((np.clip(out, 0, 1) * 255).round().astype(np.uint8), pil_mode)
    save_kw = {}
    if str(dst).lower().endswith((".jpg", ".jpeg")):
        img = img.convert("RGB")
        save_kw["quality"] = 95
    img.save(dst, **save_kw)
    return dst
