def clamp(val, minval, maxval):
    return max(minval, min(maxval, val))

def isPowerOfTwo(val):
    return (val != 0 and (not(val & (val - 1))))

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

def vec3IsIdentity(vec3):
    return (vec3[0] == 0 and vec3[1] == 0 and vec3[2] == 0)

def quatIsIdentity(quat):
    return (quat[0] == 0 and quat[1] == 0 and quat[2] == 0 and quat[3] == 1)

def vec3IsAllOnes(vec3):
    return (vec3[0] == 1 and vec3[1] == 1 and vec3[2] == 1)
