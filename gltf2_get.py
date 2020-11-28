# Copyright (c) 2017 The Khronos Group Inc.
# Modifications Copyright (c) 2017-2019 Soft8Soft LLC
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import bpy
import os

from pluginUtils.log import printLog
import pluginUtils.gltf as gltf

from .utils import *


def getUsedMaterials():
    """
    Gathers and returns all unfiltered, valid Blender materials.
    """

    materials = []

    for bl_mat in bpy.data.materials:
        materials.append(bl_mat)

    return materials


def getMaterialRequiresTexCoords(glTF, index):
    """
    Query function, if a material "needs" texture cooridnates. This is the case, if a texture is present and used.
    """

    if glTF.get('materials') is None:
        return False

    materials = glTF['materials']

    if index < 0 or index >= len(materials):
        return False

    material = materials[index]

    # General

    if material.get('emissiveTexture') is not None:
        return True

    if material.get('normalTexture') is not None:
        return True

    if material.get('occlusionTexture') is not None:
        return True

    # Metallic roughness

    if material.get('baseColorTexture') is not None:
        return True

    if material.get('metallicRoughnessTexture') is not None:
        return True

    # Common Material

    v3dExt = gltf.getAssetExtension(material, 'S8S_v3d_material_data')
    if v3dExt:

        if v3dExt.get('diffuseTexture') is not None:
            return True

        if v3dExt.get('alphaTexture') is not None:
            return True

        if v3dExt.get('specularTexture') is not None:
            return True

    return False


def getMaterialRequiresNormals(glTF, index):
    """
    Query function, if a material "needs" normals. This is the case, if a texture is present and used.
    At point of writing, same function as for texture coordinates.
    """
    return getMaterialRequiresTexCoords(glTF, index)


def getImageIndex(exportSettings, uri):
    """
    Return the image index in the glTF array.
    """

    if exportSettings['uri_data'] is None:
        return -1

    if uri in exportSettings['uri_data']['uri']:
        return exportSettings['uri_data']['uri'].index(uri)

    return -1


def getTextureIndexByImage(exportSettings, glTF, bl_image):
    """
    Return the texture index in the glTF array by a given blender image.
    """

    if bl_image.filepath is None:
        return -1

    uri = getImageExportedURI(exportSettings, bl_image)

    if exportSettings['uri_data'] is None:
        return -1


    if glTF.get('textures') is None:
        return -1

    image_uri = exportSettings['uri_data']['uri']

    index = 0

    for texture in glTF['textures']:

        if 'source' in texture:
            current_image_uri = image_uri[texture['source']]
            if current_image_uri == uri:
                return index

        index += 1

    return -1

def getTextureIndexByTexture(exportSettings, glTF, bl_texture):
    """
    Return the texture index in the glTF array by a given texture. Safer than
    "getTextureIndexByImage" and "getTextureIndex" in case of different
    textures with the same image or linked textures with the same name but with
    different images.
    """

    if (exportSettings['uri_data'] is None or glTF.get('textures') is None
            or bl_texture is None):
        return -1

    bl_image = getTexImage(bl_texture)
    if bl_image is None or bl_image.filepath is None:
        return -1

    uri = getImageExportedURI(exportSettings, bl_image)
    image_uri = exportSettings['uri_data']['uri']
    tex_name = getTextureName(bl_texture)

    index = 0
    for texture in glTF['textures']:
        if 'source' in texture and 'name' in texture:
            current_image_uri = image_uri[texture['source']]
            if current_image_uri == uri and texture['name'] == tex_name:
                return index

        index += 1

    return -1

def getTextureIndexNode(exportSettings, glTF, name, shaderNode):
    """
    Return the texture index in the glTF array.
    """

    if shaderNode is None:
        return -1

    if not isinstance(shaderNode, (bpy.types.ShaderNodeBsdfPrincipled,
                                   bpy.types.ShaderNodeMixShader,
                                   bpy.types.ShaderNodeGroup)):
        return -1

    if shaderNode.inputs.get(name) is None:
        return -1

    if len(shaderNode.inputs[name].links) == 0:
        return -1

    fromNode = shaderNode.inputs[name].links[0].from_node

    if isinstance(fromNode, bpy.types.ShaderNodeNormalMap):
        if len(fromNode.inputs['Color'].links) > 0:
            fromNode = fromNode.inputs['Color'].links[0].from_node
        else:
            return -1

    if isinstance(fromNode, bpy.types.ShaderNodeSeparateRGB):
        if len(fromNode.inputs['Image'].links) > 0:
            fromNode = fromNode.inputs['Image'].links[0].from_node
        else:
            return -1

    # color factor
    if isinstance(fromNode, bpy.types.ShaderNodeMixRGB) and fromNode.blend_type == 'MULTIPLY':
        if len(fromNode.inputs['Color1'].links) > 0:
            fromNode = fromNode.inputs['Color1'].links[0].from_node
        elif len(fromNode.inputs['Color2'].links) > 0:
            fromNode = fromNode.inputs['Color2'].links[0].from_node
        else:
            return -1

    if not isinstance(fromNode, bpy.types.ShaderNodeTexImage):
        return -1

    if getTexImage(fromNode) is None or getTexImage(fromNode).size[0] == 0 or getTexImage(fromNode).size[1] == 0:
        return -1

    return getTextureIndexByTexture(exportSettings, glTF, fromNode)


def getTexcoordIndex(glTF, name, shaderNode):
    """
    Return the texture coordinate index, if assigend and used.
    """

    if shaderNode is None:
        return 0

    if not isinstance(shaderNode, (bpy.types.ShaderNodeBsdfPrincipled,
                                   bpy.types.ShaderNodeMixShader,
                                   bpy.types.ShaderNodeGroup)):
        return 0

    if shaderNode.inputs.get(name) is None:
        return 0

    if len(shaderNode.inputs[name].links) == 0:
        return 0

    fromNode = shaderNode.inputs[name].links[0].from_node

    if isinstance(fromNode, bpy.types.ShaderNodeNormalMap):
        fromNode = fromNode.inputs['Color'].links[0].from_node

    if isinstance(fromNode, bpy.types.ShaderNodeSeparateRGB):
        fromNode = fromNode.inputs['Image'].links[0].from_node

    if isinstance(fromNode, bpy.types.ShaderNodeMixRGB) and fromNode.blend_type == 'MULTIPLY':
        if len(fromNode.inputs['Color1'].links) > 0:
            fromNode = fromNode.inputs['Color1'].links[0].from_node
        elif len(fromNode.inputs['Color2'].links) > 0:
            fromNode = fromNode.inputs['Color2'].links[0].from_node

    if not isinstance(fromNode, bpy.types.ShaderNodeTexImage):
        return 0

    if len(fromNode.inputs['Vector'].links) == 0:
        return 0

    inputNode = fromNode.inputs['Vector'].links[0].from_node

    if not isinstance(inputNode, bpy.types.ShaderNodeUVMap):
        return 0

    if inputNode.uv_map == '':
        return 0

    # try to gather map index.
    for bl_mesh in bpy.data.meshes:
        texCoordIndex = bl_mesh.uv_layers.find(inputNode.uv_map)
        if texCoordIndex >= 0:
            return texCoordIndex

    return 0

def getMaterialType(bl_mat):
    """
    get blender material type: PBR, CYCLES, BASIC
    """

    if not bl_mat.use_nodes or bl_mat.node_tree == None:
        return 'BASIC'

    for bl_node in bl_mat.node_tree.nodes:
        if (isinstance(bl_node, bpy.types.ShaderNodeGroup) and
                bl_node.node_tree.name.startswith('Verge3D PBR')):
            return 'PBR'

    if bl_mat.v3d.gltf_compat:
        return 'PBR'

    return 'CYCLES'

def getSkinIndex(glTF, name, index_offset):
    """
    Return the skin index in the glTF array.
    """

    if glTF.get('skins') is None:
        return -1

    skeleton = gltf.getNodeIndex(glTF, name)

    index = 0
    for skin in glTF['skins']:
        if skin['skeleton'] == skeleton:
            return index + index_offset

        index += 1

    return -1


def getCameraIndex(glTF, name):
    """
    Return the camera index in the glTF array.
    """

    if glTF.get('cameras') is None:
        return -1

    index = 0
    for camera in glTF['cameras']:
        if camera['name'] == name:
            return index

        index += 1

    return -1

def getCurveIndex(glTF, name):
    """
    Return the curve index in the glTF array.
    """

    v3dExt = gltf.getAssetExtension(glTF, 'S8S_v3d_data')

    if v3dExt == None:
        return -1

    if v3dExt.get('curves') == None:
        return -1

    curves = v3dExt['curves']

    index = 0
    for curve in curves:
        if curve['name'] == name:
            return index

        index += 1

    return -1

def getNodeGraphIndex(glTF, name):
    """
    Return the node graph index in the glTF array.
    """

    v3dExt = gltf.getAssetExtension(glTF, 'S8S_v3d_data')

    if v3dExt == None:
        return -1

    if v3dExt.get('nodeGraphs') == None:
        return -1

    index = 0
    for graph in v3dExt['nodeGraphs']:
        if graph['name'] == name:
            return index

        index += 1

    return -1


def getImageExportedURI(exportSettings, bl_image):
    """
    Return exported URI for a blender image.
    """

    name, ext = os.path.splitext(bpy.path.basename(bl_image.filepath))

    uri_name = name if name != '' else 'v3d_exported_image_' + bl_image.name

    uri_ext = ''
    if (bl_image.file_format == 'JPEG'
            or bl_image.file_format == 'BMP'
            or bl_image.file_format == 'HDR'
            or bl_image.file_format == 'PNG'):
        if ext != '':
            uri_ext = ext
    else:
        uri_ext = '.png'

    uri_data = exportSettings['uri_data']

    unique_uri = uri_name + uri_ext
    i = 0
    while unique_uri in uri_data['uri']:

        index = uri_data['uri'].index(unique_uri)
        if uri_data['bl_datablocks'][index] == bl_image:
            break

        i += 1
        unique_uri = uri_name + '_' + integerToBlSuffix(i) + uri_ext

    return unique_uri

def getImageExportedMimeType(bl_image):

    if bl_image.file_format == 'JPEG':
        return 'image/jpeg'
    elif bl_image.file_format == 'BMP':
        return 'image/bmp'
    elif bl_image.file_format == 'HDR':
        return 'image/vnd.radiance'
    else:
        return 'image/png'

def getNameInBrackets(data_path):
    """
    Return Blender node on a given Blender data path.
    """

    if data_path is None:
        return None

    index = data_path.find("[\"")
    if (index == -1):
        return None

    node_name = data_path[(index + 2):]

    index = node_name.find("\"")
    if (index == -1):
        return None

    return node_name[:(index)]

def getAnimParamDim(fcurves, node_name):
    dim = 0

    for fcurve in fcurves:
        if getNameInBrackets(fcurve.data_path) == node_name:
            dim = max(dim, fcurve.array_index+1)

    return dim

def getAnimParam(data_path):
    """
    return animated param in data path:
    nodes['name'].outputs[0].default_value -> default_value
    """

    index = data_path.rfind('.')

    if index == -1:
        return data_path

    return data_path[(index + 1):]


def getScalar(default_value, init_value = 0.0):
    """
    Return scalar with a given default/fallback value.
    """

    return_value = init_value

    if default_value is None:
        return return_value

    return_value = default_value

    return return_value


def getVec2(default_value, init_value = [0.0, 0.0]):
    """
    Return vec2 with a given default/fallback value.
    """

    return_value = init_value

    if default_value is None or len(default_value) < 2:
        return return_value

    index = 0
    for number in default_value:
        return_value[index] = number

        index += 1
        if index == 2:
            return return_value

    return return_value


def getVec3(default_value, init_value = [0.0, 0.0, 0.0]):
    """
    Return vec3 with a given default/fallback value.
    """

    return_value = init_value

    if default_value is None or len(default_value) < 3:
        return return_value

    index = 0
    for number in default_value:
        return_value[index] = number

        index += 1
        if index == 3:
            return return_value

    return return_value


def getVec4(default_value, init_value = [0.0, 0.0, 0.0, 1.0]):
    """
    Return vec4 with a given default/fallback value.
    """

    return_value = init_value

    if default_value is None or len(default_value) < 4:
        return return_value

    index = 0
    for number in default_value:
        return_value[index] = number

        index += 1
        if index == 4:
            return return_value

    return return_value


def getIndex(list, name):
    """
    Return index of a glTF element by a given name.
    """

    if list is None or name is None:
        return -1

    index = 0
    for element in list:
        if element.get('name') is None:
            continue

        if element['name'] == name:
            return index

        index += 1

    return -1

def getByName(list, name):
    """
    Return element by a given name.
    """

    if list is None or name is None:
        return None

    for element in list:
        if element.get('name') is None:
            continue

        if element['name'] == name:
            return element

    return None


def getOrCreateDefaultMatIndex(glTF):
    def_idx = gltf.getMaterialIndex(glTF, DEFAULT_MAT_NAME)

    if def_idx == -1:
        if 'materials' not in glTF:
            glTF['materials'] = []

        glTF['materials'].append(createDefaultMaterialCycles())

        def_idx = len(glTF['materials']) - 1

    return def_idx

def createDefaultMaterialCycles():
    return {
        "emissiveFactor" : [
            0.0,
            0.0,
            0.0
        ],
        "extensions" : {
            "S8S_v3d_material_data" : {
                "nodeGraph" : {
                    "edges" : [
                        {
                            "fromNode" : 1,
                            "fromOutput" : 0,
                            "toInput" : 0,
                            "toNode" : 0
                        }
                    ],
                    "nodes" : [
                        {
                            "inputs" : [
                                [ 0, 0, 0, 0 ],
                                [ 0, 0, 0, 0 ],
                                0.0
                            ],
                            "is_active_output" : True,
                            "name" : "Material Output",
                            "outputs" : [],
                            "type" : "OUTPUT_MATERIAL_BL"
                        },
                        {
                            "inputs" : [
                                [ 0.800000011920929, 0.800000011920929, 0.800000011920929, 1.0 ],
                                0.0,
                                [ 0.0, 0.0, 0.0 ]
                            ],
                            "is_active_output" : False,
                            "name" : "Diffuse BSDF",
                            "outputs" : [
                                [ 0, 0, 0, 0 ]
                            ],
                            "type" : "BSDF_DIFFUSE_BL"
                        }
                    ]
                },
                "useCastShadows" : True,
                "useShadows" : True
            }
        },
        "name" : DEFAULT_MAT_NAME
    }

