"""figinvert -- dark-background versions of figures, without screenshotting a PDF viewer."""
from .colour import (BG_HEX, BG_LSTAR, MODES, DEFAULT_MODE, get_transform,
                     lab_flip, naive_invert, overleaf_approx, background_colour)

__version__ = "0.1.0"
__all__ = ["BG_HEX", "BG_LSTAR", "MODES", "DEFAULT_MODE", "get_transform",
           "lab_flip", "naive_invert", "overleaf_approx", "background_colour"]
