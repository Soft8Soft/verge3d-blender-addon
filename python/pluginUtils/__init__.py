#__all__ = ['']

from . import convert, gltf, log, manager, path, rawdata

debug = True

def clamp(val, minval, maxval):
    return max(minval, min(maxval, val))

def srgbToLinear(x):
    if x <= 0.0:
        return 0.0
    elif x >= 1:
        return 1.0
    elif x < 0.04045:
        return x / 12.92
    else:
        return ((x + 0.055) / 1.055) ** 2.4

def colorToLuminosity(color):
    return color[0] * 0.21 + color[1] * 0.72 + color[2] * 0.07

def isPowerOfTwo(val):
    return (val != 0 and (not(val & (val - 1))))
