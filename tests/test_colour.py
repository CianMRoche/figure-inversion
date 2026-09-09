"""Colour-transform maths."""

from __future__ import annotations

import colorsys

import numpy as np
import pytest

from figinvert.colour import (BG_HEX, DEFAULT_MODE, background_colour,
                              get_transform, lab_flip, naive_invert,
                              overleaf_approx, rgb_to_lab, lab_to_rgb)

WHITE = np.array([1.0, 1.0, 1.0])
BLACK = np.array([0.0, 0.0, 0.0])


def as255(rgb):
    return tuple(int(round(v * 255)) for v in np.asarray(rgb))


def test_default_mode_is_overleaf():
    assert DEFAULT_MODE == "overleaf"


@pytest.mark.parametrize("mode", ["overleaf", "lab"])
def test_white_maps_to_the_calibrated_background(mode):
    """Both dark modes must land on the measured #171717 ground."""
    assert as255(background_colour(mode)) == (0x17, 0x17, 0x17)
    assert BG_HEX == "#171717"


def test_overleaf_endpoints_match_the_calibration():
    """Neutral endpoints are pinned by construction, so they must be exact."""
    assert as255(overleaf_approx(WHITE)) == (23, 23, 23)
    assert as255(overleaf_approx(BLACK)) == (209, 209, 209)


def test_lab_takes_black_to_pure_white():
    assert as255(lab_flip(BLACK)) == (255, 255, 255)


def test_overleaf_neutral_ramp_is_monotonic_and_linear():
    xs = np.linspace(0, 1, 21)
    ys = np.array([overleaf_approx(np.array([x] * 3))[0] for x in xs])
    assert np.all(np.diff(ys) < 0), "inverted ramp must decrease"
    fit = np.polyval(np.polyfit(xs, ys, 1), xs)
    assert np.max(np.abs(fit - ys)) * 255 < 1.0, "ramp should be linear to <1/255"


@pytest.mark.parametrize("mode", ["overleaf", "lab"])
@pytest.mark.parametrize("rgb", [(0.12, 0.47, 0.71), (0.84, 0.15, 0.16),
                                 (0.17, 0.63, 0.17), (0.58, 0.40, 0.74)])
def test_hue_is_preserved(mode, rgb):
    """The whole point: a blue line must stay blue, not turn orange."""
    fn = get_transform(mode)
    h_in = colorsys.rgb_to_hls(*rgb)[0]
    h_out = colorsys.rgb_to_hls(*fn(np.array(rgb)))[0]
    delta = abs(h_in - h_out)
    delta = min(delta, 1 - delta)          # hue is circular
    assert delta < 0.06, f"hue moved by {delta:.3f} turns"


def test_naive_destroys_hue_as_documented():
    """Guards the contrast that justifies the other two modes existing."""
    blue = np.array([0.12, 0.47, 0.71])
    h_in = colorsys.rgb_to_hls(*blue)[0]
    h_out = colorsys.rgb_to_hls(*naive_invert(blue))[0]
    delta = min(abs(h_in - h_out), 1 - abs(h_in - h_out))
    assert delta > 0.3, "naive invert is expected to flip hue"


@pytest.mark.parametrize("mode", ["overleaf", "lab", "naive"])
def test_lightness_is_actually_flipped(mode):
    """Perceptually light inputs must become dark and vice versa."""
    fn = get_transform(mode)
    for rgb in [(1, 1, 0), (0, 0, 1), (0.9, 0.9, 0.9), (0.1, 0.1, 0.1)]:
        l_in = rgb_to_lab(np.array(rgb, dtype=float))[0]
        l_out = rgb_to_lab(fn(np.array(rgb, dtype=float)))[0]
        assert (l_in - 50) * (l_out - 50) <= 0 or abs(l_in - 50) < 12, (
            f"{mode}: L* {l_in:.0f} -> {l_out:.0f} did not cross mid-grey")


def test_chroma_multiplier_increases_saturation():
    rgb = np.array([0.12, 0.47, 0.71])
    base = lab_flip(rgb, chroma=1.0)
    more = lab_flip(rgb, chroma=1.4)
    c_base = np.linalg.norm(rgb_to_lab(base)[1:])
    c_more = np.linalg.norm(rgb_to_lab(more)[1:])
    assert c_more > c_base


def test_range_controls_the_background():
    """--range LO HI must move the floor the background sits on."""
    assert as255(lab_flip(WHITE, lo=0.0))[0] == 0
    assert as255(lab_flip(WHITE, lo=20.0))[0] > as255(lab_flip(WHITE, lo=5.0))[0]


def test_lab_round_trip_is_stable():
    rng = np.random.default_rng(0)
    rgb = rng.random((500, 3))
    back = lab_to_rgb(rgb_to_lab(rgb))
    assert np.max(np.abs(back - rgb)) < 1e-6


def test_transforms_are_shape_agnostic():
    """Same code path serves a swatch, an SVG attribute and a whole image."""
    fn = get_transform("overleaf")
    one = fn(np.array([0.5, 0.2, 0.9]))
    many = fn(np.tile(np.array([0.5, 0.2, 0.9]), (4, 7, 1)))
    assert one.shape == (3,) and many.shape == (4, 7, 3)
    assert np.allclose(many[2, 3], one)


def test_outputs_stay_in_gamut():
    rng = np.random.default_rng(1)
    rgb = rng.random((2000, 3))
    for mode in ("overleaf", "lab", "naive"):
        out = get_transform(mode)(rgb)
        assert out.min() >= 0.0 and out.max() <= 1.0


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        get_transform("nope")
