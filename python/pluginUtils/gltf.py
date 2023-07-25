import math, mimetypes, struct, sys

from .log import printLog

WEBGL_FILTERS = {
    'NEAREST'                : 9728,
    'LINEAR'                 : 9729,
    'NEAREST_MIPMAP_NEAREST' : 9984,
    'LINEAR_MIPMAP_NEAREST'  : 9985,
    'NEAREST_MIPMAP_LINEAR'  : 9986,
    'LINEAR_MIPMAP_LINEAR'   : 9987
}

WEBGL_WRAPPINGS = {
    'CLAMP_TO_EDGE'   : 33071,
    'MIRRORED_REPEAT' : 33648,
    'REPEAT'          : 10497
}

WEBGL_BLEND_EQUATIONS = {
    'FUNC_ADD' : 32774,
    'FUNC_SUBTRACT' : 32778,
    'FUNC_REVERSE_SUBTRACT' : 32779
}

WEBGL_BLEND_FUNCS = {
    'ZERO' : 0,
    'ONE' : 1,
    'SRC_COLOR' : 768,
    'ONE_MINUS_SRC_COLOR' : 769,
    'SRC_ALPHA' : 770,
    'ONE_MINUS_SRC_ALPHA' : 771,
    'DST_ALPHA' : 772,
    'ONE_MINUS_DST_ALPHA' : 773,
    'DST_COLOR' : 774,
    'ONE_MINUS_DST_COLOR' : 775,
    'SRC_ALPHA_SATURATE' : 776,

    # the followings are not supported by the engine yet
    # 'CONSTANT_COLOR' : 32769,
    # 'ONE_MINUS_CONSTANT_COLOR' : 32770,
    # 'CONSTANT_ALPHA' : 32771,
    # 'ONE_MINUS_CONSTANT_ALPHA' : 32772
}

# NOTE: some Windows systems use 'image/hdr' instead of 'image/vnd.radiance'
COMPAT_IMAGE_MIME = ['image/jpeg', 'image/bmp', 'image/png', 'image/x-png', 'image/vnd.radiance', 'image/hdr']

def appendEntity(gltf, name, entity):

    if not gltf.get(name):
        gltf[name] = []

    gltf[name].append(entity)

    # return index
    return (len(gltf[name]) - 1)

def appendExtension(gltf, name, entity=None, extensionData={}, isRequired=False):

    if entity is not None:
        if entity.get('extensions') is None:
            entity['extensions'] = {}

        extensions = entity['extensions']

        if extensions.get(name) is None:
            extensions[name] = {}
        extensions[name].update(extensionData)
        extension = extensions[name]
    else:
        extension = None

    # add to used extensions

    if gltf.get('extensionsUsed') is None:
        gltf['extensionsUsed'] = []

    extensionsUsed = gltf['extensionsUsed']

    if name not in extensionsUsed:
        extensionsUsed.append(name)

    # add to required extensions

    if isRequired:
        if gltf.get('extensionsRequired') is None:
            gltf['extensionsRequired'] = []

        extensionsRequired = gltf['extensionsRequired']

        if name not in extensionsRequired:
            extensionsRequired.append(name)

    return extension

def getAssetExtension(asset, extension):
    """
    Get global/local asset extension
    """

    if asset.get('extensions') == None:
        return None

    return asset['extensions'].get(extension)


def createSampler(gltf, magFilter, wrapS, wrapT):
    """
    Creates and appends a texture sampler with the given parameters
    """

    if gltf.get('samplers') is None:
        gltf['samplers'] = []

    samplers = gltf['samplers']

    if len(samplers) == 0:
        sampler = {}
        samplers.append(sampler)

    if (magFilter == WEBGL_FILTERS['LINEAR'] and
            wrapS == WEBGL_WRAPPINGS['REPEAT'] and
            wrapT == WEBGL_WRAPPINGS['REPEAT']):
        return 0

    index = 0

    for currentSampler in samplers:
        # pass by empty one
        if currentSampler.get('magFilter') is None or currentSampler.get('wrapS') is None:
            index += 1
            continue

        if (currentSampler['magFilter'] == magFilter and
                currentSampler['wrapS'] == wrapS and
                currentSampler['wrapT'] == wrapT):
            return index

        index += 1

    minFilter = WEBGL_FILTERS['LINEAR_MIPMAP_LINEAR']

    if magFilter == WEBGL_FILTERS['NEAREST']:
        # looks better while preserving "pixel art" graphics
        minFilter = WEBGL_FILTERS['NEAREST_MIPMAP_LINEAR']

    sampler = {
        'magFilter' : magFilter,
        'minFilter' : minFilter,
        'wrapS' : wrapS,
        'wrapT' : wrapT
    }

    samplers.append(sampler)

    return len(samplers) - 1

def getSceneIndex(gltf, idname):

    if gltf.get('scenes') is None:
        return -1

    index = 0
    for scene in gltf['scenes']:
        key = 'id' if scene.get('id') != None else 'name'
        if scene.get(key) == idname:
            return index

        index += 1

    return -1

def getNodeIndex(gltf, idname):
    """
    Return the node index in the gltf array.
    """

    if gltf.get('nodes') is None:
        return -1

    index = 0
    for node in gltf['nodes']:
        key = 'id' if node.get('id') != None else 'name'
        if node.get(key) == idname:
            return index

        index += 1

    return -1

def getMeshIndex(gltf, idname):
    """
    Return the mesh index in the gltf array.
    """

    if gltf.get('meshes') is None:
        return -1

    index = 0
    for mesh in gltf['meshes']:
        key = 'id' if mesh.get('id') != None else 'name'
        if mesh.get(key) == idname:
            return index

        index += 1

    return -1


def getMaterialIndex(gltf, idname):
    """
    Return the material index in the gltf array.
    """
    if idname is None:
        return -1

    if gltf.get('materials') is None:
        return -1

    index = 0
    for material in gltf['materials']:
        key = 'id' if material.get('id') != None else 'name'
        if material.get(key) == idname:
            return index

        index += 1

    return -1

def getCameraIndex(gltf, idname):
    """
    Return the camera index in the gltf array.
    """

    if gltf.get('cameras') is None:
        return -1

    index = 0
    for camera in gltf['cameras']:
        key = 'id' if camera.get('id') != None else 'name'
        if camera.get(key) == idname:
            return index

        index += 1

    return -1

def getLightIndex(gltf, idname):
    """
    Return the light index in the gltf array.
    """

    v3dExt = appendExtension(gltf, 'S8S_v3d_lights', gltf)

    if v3dExt.get('lights') == None:
        return -1

    lights = v3dExt['lights']

    index = 0
    for light in lights:
        key = 'id' if light.get('id') != None else 'name'
        if light.get(key) == idname:
            return index

        index += 1

    return -1

def getLightProbeIndex(gltf, idname):
    """
    Return the light probe index in the gltf array.
    """

    v3dExt = appendExtension(gltf, 'S8S_v3d_light_probes', gltf)

    if v3dExt.get('lightProbes') == None:
        return -1

    lightProbes = v3dExt['lightProbes']

    index = 0
    for probe in lightProbes:
        key = 'id' if probe.get('id') != None else 'name'
        if probe.get(key) == idname:
            return index

        index += 1

    return -1

def getCurveIndex(gltf, idname):
    """
    Return the curve index in the gltf array.
    """

    v3dExt = appendExtension(gltf, 'S8S_v3d_curves', gltf)

    if v3dExt.get('curves') == None:
        return -1

    curves = v3dExt['curves']

    index = 0
    for curve in curves:
        key = 'id' if curve.get('id') != None else 'name'
        if curve.get(key) == idname:
            return index

        index += 1

    return -1

def getTextureIndex(gltf, idname):

    if gltf.get('textures') is None:
        return -1

    index = 0
    for tex in gltf['textures']:
        key = 'id' if tex.get('id') != None else 'name'
        if tex.get(key) == idname:
            return index

        index += 1

    return -1

def getImageIndex(gltf, idname):

    if gltf.get('images') is None:
        return -1

    index = 0
    for image in gltf['images']:
        key = 'id' if image.get('id') != None else 'name'
        if image.get(key) == idname:
            return index

        index += 1

    return -1

def getFontIndex(gltf, idname):

    v3dExt = appendExtension(gltf, 'S8S_v3d_curves', gltf)

    if v3dExt.get('fonts') == None:
        return -1

    fonts = v3dExt['fonts']

    index = 0
    for font in fonts:
        key = 'id' if font.get('id') != None else 'name'
        if font.get(key) == idname:
            return index

        index += 1

    return -1

def getClippingPlaneIndex(gltf, idname):

    v3dExt = appendExtension(gltf, 'S8S_v3d_clipping_planes', gltf)

    if v3dExt.get('clippingPlanes') == None:
        return -1

    clippingPlanes = v3dExt['clippingPlanes']

    index = 0
    for plane in clippingPlanes:
        key = 'id' if plane.get('id') != None else 'name'
        if plane.get(key) == idname:
            return index

        index += 1

    return -1

def generateBufferView(gltf, binary, data_buffer, target, alignment):

    if data_buffer is None:
        return -1

    gltf_target_number = [ 34962, 34963 ]
    gltf_target_enums = [ "ARRAY_BUFFER", "ELEMENT_ARRAY_BUFFER" ]

    target_number = 0
    if target in gltf_target_enums:
        target_number = gltf_target_number[gltf_target_enums.index(target)]

    if gltf.get('bufferViews') is None:
        gltf['bufferViews'] = []

    bufferViews = gltf['bufferViews']

    bufferView = {}

    if target_number != 0:
        bufferView['target'] = target_number

    bufferView['byteLength'] = len(data_buffer)

    binary_length = len(binary)

    remainder = 0

    if alignment > 0:
        remainder = binary_length % alignment

    if remainder > 0:
        padding_byte = struct.pack(bytes(str('<1b').encode()), 0)
        for i in range(0, alignment - remainder):
            binary.extend(padding_byte)


    bufferView['byteOffset'] = len(binary)
    binary.extend(data_buffer)

    # only have one buffer.
    bufferView['buffer'] = 0

    bufferViews.append(bufferView)

    return len(bufferViews) - 1


def generateAccessor(gltf, binary, data, componentType, count, type, target):

    if data is None:
        printLog('ERROR', 'No data')
        return -1

    gltf_convert_type = [ "b", "B", "h", "H", "I", "f" ]
    gltf_enumNames = [ "BYTE", "UNSIGNED_BYTE", "SHORT", "UNSIGNED_SHORT", "UNSIGNED_INT", "FLOAT" ]
    gltf_convert_type_size = [ 1, 1, 2, 2, 4, 4 ]

    if componentType not in gltf_enumNames:
        printLog('ERROR', 'Invalid componentType ' + componentType)
        return -1

    componentTypeInteger = [ 5120, 5121, 5122, 5123, 5125, 5126 ][gltf_enumNames.index(componentType)]

    convert_type = gltf_convert_type[gltf_enumNames.index(componentType)]
    convert_type_size = gltf_convert_type_size[gltf_enumNames.index(componentType)]

    if count < 1:
        printLog('ERROR', 'Invalid count ' + str(count))
        return -1

    gltf_type_count = [1, 2, 3, 4, 4, 9, 16]
    gltf_type = [ "SCALAR", "VEC2", "VEC3", "VEC4", "MAT2", "MAT3", "MAT4" ]

    if type not in gltf_type:
        printLog('ERROR', 'Invalid type ' + type)
        return -1

    type_count = gltf_type_count[gltf_type.index(type)]


    if gltf.get('accessors') is None:
        gltf['accessors'] = []

    accessors = gltf['accessors']


    accessor = {
        'componentType' : componentTypeInteger,
        'count' : count,
        'type' : type
    }


    minimum = []
    maximum = []

    for component_index in range(0, type_count):
        for component in range(0, count):
            element = data[component * type_count + component_index]

            if component == 0:
                minimum.append(element)
                maximum.append(element)
            else:
                minimum[component_index] = min(minimum[component_index], element)
                maximum[component_index] = max(maximum[component_index], element)

    accessor['min'] = minimum
    accessor['max'] = maximum

    convert_type = '<' + str(count * type_count) + convert_type

    # NOTE: There is a bug in the struct package happened on old
    # python versions, reproduced in 3ds max 2017. Need to
    # use byte strings in the pack method as a workaround.
    # see: https://bugs.python.org/issue19099

    data_buffer = struct.pack(bytes(convert_type.encode()), *data)

    bufferView = generateBufferView(gltf, binary, data_buffer, target, convert_type_size)

    if bufferView < 0:
        printLog('ERROR', 'Invalid buffer view')
        return -1

    accessor['bufferView'] = bufferView

    accessors.append(accessor)

    return len(accessors) - 1

def createAnimChannel(sampler, nodeIndex, path):
    channel = {
        'sampler' : sampler,
        'target': {
            'node': nodeIndex,
            'path': path
        }
    }

    return channel

def createAnimSampler(gltf, binary, keys, values, dim, interpolation='LINEAR'):
    sampler = {}

    sampler['interpolation'] = interpolation

    input = generateAccessor(gltf, binary,
            keys, 'FLOAT', len(keys), 'SCALAR', '')
    sampler['input'] = input

    if dim == 1:
        accessorType = 'SCALAR'
    elif dim == 2:
        accessorType = 'VEC2'
    elif dim == 3:
        accessorType = 'VEC3'
    elif dim == 4:
        accessorType = 'VEC4'

    output = generateAccessor(gltf, binary,
            values, 'FLOAT', len(values) // dim, accessorType, '')
    sampler['output'] = output

    return sampler

def mergeAnimations(gltf, animations):
    '''
    Find animations with the same name and merge them into one
    '''

    newAnimations = []
    animMergeInfo = {}

    for anim in animations:

        name = anim['name']
        channels = anim['channels']
        samplers = anim['samplers']

        if not name in animMergeInfo:
            animMergeInfo[name] = [[], [], None]

        for channel in channels:
            sampler = samplers[channel['sampler']]

            # fix sampler index in new array
            channel['sampler'] = len(animMergeInfo[name][1])

            animMergeInfo[name][0].append(channel)
            animMergeInfo[name][1].append(sampler)
            animMergeInfo[name][2] = getAssetExtension(anim, 'S8S_v3d_animation')

    for name, mergeInfoElem in animMergeInfo.items():
        anim = {
            'name': name,
            'channels' : mergeInfoElem[0],
            'samplers' : mergeInfoElem[1]
        }

        if mergeInfoElem[2]:
            appendExtension(gltf, 'S8S_v3d_animation', anim, mergeInfoElem[2])

        newAnimations.append(anim)

    return newAnimations

def isCompatibleImagePath(path):

    # NOTE: add missing HDR mime type to python database
    if mimetypes.guess_type('somefile.hdr')[0] == None:
        mimetypes.add_type('image/vnd.radiance', '.hdr')

    mime = mimetypes.guess_type(path)[0]

    if mime in COMPAT_IMAGE_MIME:
        return True
    else:
        return False


def imageMimeType(path):

    # NOTE: add missing HDR mime type to python database
    if mimetypes.guess_type('somefile.hdr')[0] == None:
        mimetypes.add_type('image/vnd.radiance', '.hdr')

    mime = mimetypes.guess_type(path)[0]

    # NOTE: no image/x-png
    if mime in ['image/jpeg', 'image/bmp', 'image/vnd.radiance', 'image/png']:
        return mime
    else:
        return 'image/png'

def flatten(arr):
    if len(arr) and isinstance(arr[0], tuple):
        return list(sum(arr, ()))
    elif len(arr) and isinstance(arr[0], list):
        return list(sum(arr, []))
    else:
        return arr

def getNodeGraph(mat):
    if ('extensions' in mat and 'S8S_v3d_materials' in mat['extensions']
            and 'nodeGraph' in mat['extensions']['S8S_v3d_materials']):
        return mat['extensions']['S8S_v3d_materials']['nodeGraph']
    else:
        return None

def createBlendMode(equation, srcRGB, dstRGB):

    blendMode = {
        'blendEquation': WEBGL_BLEND_EQUATIONS[equation],
        'srcRGB': WEBGL_BLEND_FUNCS[srcRGB],
        'dstRGB': WEBGL_BLEND_FUNCS[dstRGB]
    }

    return blendMode

def processInfinity(value):
    if math.isinf(value):
        if value > 0:
            return 'Infinity'
        else:
            return '-Infinity'
    else:
        return value
