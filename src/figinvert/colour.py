"""Colour transforms shared by every backend.

All functions take and return float arrays in [0, 1] with a trailing axis of
size 3 (sRGB, non-linear). They are vectorised and shape-agnostic, so the same
code serves a single swatch, an SVG attribute, or a full image.
"""

from __future__ import annotations

import numpy as np

# --------------------------------------------------------------------------
# sRGB <-> CIELAB (D65)
# --------------------------------------------------------------------------

_M_RGB2XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
])
_M_XYZ2RGB = np.linalg.inv(_M_RGB2XYZ)
_WHITE = np.array([0.95047, 1.0, 1.08883])
_DELTA = 6.0 / 29.0


def _srgb_to_linear(c):
    c = np.asarray(c, dtype=float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=float), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def _f(t):
    return np.where(t > _DELTA ** 3, np.cbrt(t), t / (3 * _DELTA ** 2) + 4 / 29)


def _f_inv(t):
    return np.where(t > _DELTA, t ** 3, 3 * _DELTA ** 2 * (t - 4 / 29))


def rgb_to_lab(rgb):
    xyz = _srgb_to_linear(rgb) @ _M_RGB2XYZ.T
    g = _f(xyz / _WHITE)
    return np.stack([
        116 * g[..., 1] - 16,
        500 * (g[..., 0] - g[..., 1]),
        200 * (g[..., 1] - g[..., 2]),
    ], axis=-1)


def lab_to_rgb(lab):
    fy = (lab[..., 0] + 16) / 116
    fx = fy + lab[..., 1] / 500
    fz = fy - lab[..., 2] / 200
    xyz = np.stack([_f_inv(fx), _f_inv(fy), _f_inv(fz)], axis=-1) * _WHITE
    return np.clip(_linear_to_srgb(xyz @ _M_XYZ2RGB.T), 0.0, 1.0)


# --------------------------------------------------------------------------
# The transforms
# --------------------------------------------------------------------------

# L* of the measured dark background #171717. Used as the default
# floor so `lab` puts white on the same ground as `overleaf`, while still
# taking black all the way up to white (unlike `overleaf`, which compresses
# both ends). Override with --range.
BG_LSTAR = 7.74
BG_HEX = "#171717"


def lab_flip(rgb, lo=BG_LSTAR, hi=100.0, chroma=1.0):
    """Flip perceptual lightness, keep hue and chroma.

    L* is mapped linearly onto [hi, lo] (so input black -> output L*=hi), while
    a* and b* are preserved. This keeps a blue line blue instead of turning it
    orange, and unlike a naive invert it flips *perceived* brightness, so
    yellow (very light) correctly becomes dark and blue (very dark) becomes
    light.

    lo/hi let you pull the endpoints in from pure black/white; chroma scales
    saturation (>1 compensates for colours looking flatter on a dark ground).
    """
    lab = rgb_to_lab(rgb)
    out = np.empty_like(lab)
    out[..., 0] = hi - (hi - lo) * (np.clip(lab[..., 0], 0, 100) / 100.0)
    out[..., 1:] = lab[..., 1:] * chroma
    return lab_to_rgb(out)


def naive_invert(rgb):
    """Per-channel 255 - x. Included for comparison; it destroys hue."""
    return np.clip(1.0 - np.asarray(rgb, dtype=float), 0.0, 1.0)


# Fitted against a calibration target (36 known swatches) rendered through the
# real Overleaf PDF inversion and screenshotted. The model is
#   invert(96.0%) -> hue-rotate(180deg) about the luma axis -> affine
# with the affine chosen so the neutral endpoints land EXACTLY on the measured
# values: white -> #171717 (23), black -> 209.
#
# HONEST ACCURACY NOTE: the neutral axis is exact by construction, so
# backgrounds and greyscale text match the real thing precisely. Chromatic
# colours are only approximated: RMSE 10/255, worst case 37/255, with greens
# and cyans coming out lighter here than in the real thing. The residuals are
# structured rather than random, which means the true filter is not exactly in
# this family -- I could not identify it from the calibration data alone. Treat
# this as "very close", not "identical".
_OVERLEAF = dict(
    invert=0.9602,
    luma=np.array([0.2043, 0.7305, 0.0652]),
    scale=0.7926,
    offset=0.0586,
)


def _hue_rotate_180(luma):
    """Hue rotation by 180 degrees about the luma axis: 2W - I."""
    return 2.0 * np.outer(np.ones(3), luma) - np.eye(3)


def overleaf_approx(rgb):
    """Approximate the Overleaf/browser-extension PDF inversion. See note above."""
    p = _OVERLEAF
    x = np.asarray(rgb, dtype=float)
    y = np.clip(p["invert"] * (1 - x) + (1 - p["invert"]) * x, 0, 1)
    y = np.clip(y @ _hue_rotate_180(p["luma"]).T, 0, 1)
    return np.clip(p["scale"] * y + p["offset"], 0, 1)


MODES = {
    "lab": lab_flip,
    "overleaf": overleaf_approx,
    "naive": naive_invert,
}


DEFAULT_MODE = "overleaf"


def background_colour(mode="overleaf", lo=BG_LSTAR, hi=100.0, chroma=1.0):
    """What a white page becomes under this mode -- i.e. the dark ground."""
    fn = get_transform(mode, lo=lo, hi=hi, chroma=chroma)
    return fn(np.array([1.0, 1.0, 1.0]))


def get_transform(mode=DEFAULT_MODE, lo=BG_LSTAR, hi=100.0, chroma=1.0):
    """Return a callable rgb->rgb for the chosen mode."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from {sorted(MODES)}")
    if mode == "lab":
        return lambda rgb: lab_flip(rgb, lo=lo, hi=hi, chroma=chroma)
    return MODES[mode]
