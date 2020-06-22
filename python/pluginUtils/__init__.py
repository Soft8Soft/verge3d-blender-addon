#__all__ = ['']

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
