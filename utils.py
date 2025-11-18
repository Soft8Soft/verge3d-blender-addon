# Copyright (c) 2017-2025 Soft8Soft, LLC. All rights reserved.
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
import math

import bpy
import numpy as np
import mathutils

import pyosl.glslgen

import pluginUtils
import pluginUtils as pu

log = pluginUtils.log.getLogger('V3D-BL')

ORTHO_EPS = 1e-5
DEFAULT_MAT_NAME = 'v3d_default_material'

selectedObject = None
selectedObjectsSave = []
prevActiveObject = None

def clamp(val, minval, maxval):
    return max(minval, min(maxval, val))

def integerToBlSuffix(val):

    suf = str(val)

    for i in range(0, 3 - len(suf)):
        suf = '0' + suf

    return suf

def setSelectedObject(bl_obj):
    """
    Select object for NLA baking
    """
    global prevActiveObject

    global selectedObject, selectedObjectsSave

    selectedObject = bl_obj
    selectedObjectsSave = bpy.context.selected_objects.copy()

    for o in selectedObjectsSave:
        o.select_set(False)

    prevActiveObject = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = bl_obj

    bl_obj.select_set(True)

def restoreSelectedObjects():
    global prevActiveObject

    global selectedObject, selectedObjectsSave

    selectedObject.select_set(False)

    for o in selectedObjectsSave:
        o.select_set(True)

    bpy.context.view_layer.objects.active = prevActiveObject
    prevActiveObject = None

    selectedObject = None
    selectedObjectsSave = []

def getSceneByObject(obj):

    for scene in bpy.data.scenes:
        index = scene.objects.find(obj.name)
        if index > -1 and scene.objects[index] == obj:
            return scene

    return None

def getTexImage(bl_tex):

    """
    Get texture image from a texture, avoiding AttributeError for textures
    without an image (e.g. a texture of type 'NONE').
    """

    return getattr(bl_tex, 'image', None)

def getTextureName(bl_texture):
    if (isinstance(bl_texture, (bpy.types.ShaderNodeTexImage,
            bpy.types.ShaderNodeTexEnvironment))):
        tex_name = bl_texture.image.name
    else:
        tex_name = bl_texture.name

    return tex_name

def imgNeedsCompression(bl_image, exportSettings):
    method = bl_image.v3d.compression_method

    if bl_image.get('compression_error_status') == 1:
        return False
    elif (exportSettings['compressTextures'] and method != 'DISABLE' and
            bl_image.file_format in ['JPEG', 'PNG', 'HDR'] and
            pu.isPowerOfTwo(bl_image.size[0]) and pu.isPowerOfTwo(bl_image.size[1])):
        return True
    else:
        return False

def mat4IsIdentity(mat4):
    return np.all(np.isclose(mat4, mathutils.Matrix.Identity(4), atol=1e-6))

def mat4IsTRSDecomposable(mat4):

    mat = mat4.to_3x3().transposed()
    v0 = mat[0].normalized()
    v1 = mat[1].normalized()
    v2 = mat[2].normalized()

    return (abs(v0.dot(v1)) < ORTHO_EPS
            and abs(v0.dot(v2)) < ORTHO_EPS
            and abs(v1.dot(v2)) < ORTHO_EPS)

def mat4SvdDecomposeToMatrs(mat4):
    """
    Decompose the given matrix into a couple of TRS-decomposable matrices or
    Returns None in case of an error.
    """

    try:
        u, s, vh = np.linalg.svd(mat4.to_3x3())
        mat_u = mathutils.Matrix(u)
        mat_s = mathutils.Matrix([[s[0], 0, 0], [0, s[1], 0], [0, 0, s[2]]])
        mat_vh = mathutils.Matrix(vh)

        mat_trans = mathutils.Matrix.Translation(mat4.to_translation())
        mat_left = mat_trans @ (mat_u @ mat_s).to_4x4()

        return (mat_left, mat_vh.to_4x4())

    except np.linalg.LinAlgError:
        return None

def findArmature(obj):

    for mod in obj.modifiers:
        if mod.type == 'ARMATURE' and mod.object is not None and mod.object.users > 0:
            return mod.object

    armature = obj.find_armature()
    return armature if armature is not None and armature.users > 0 else None

def extractAlphaMode(bl_mat):
    blendMethod = bl_mat.v3d.blend_method

    if blendMethod in ['OPAQUE', 'BLEND']:
        return blendMethod
    elif blendMethod == 'CLIP':
        return 'MASK'
    elif blendMethod == 'HASHED':
        return 'BLEND'

    if bl_mat and bl_mat.use_nodes and bl_mat.node_tree != None:
        node_trees = extractMaterialNodeTrees(bl_mat.node_tree)
        for node_tree in node_trees:
            for bl_node in node_tree.nodes:
                if isinstance(bl_node, bpy.types.ShaderNodeBsdfPrincipled):
                    if len(bl_node.inputs['Alpha'].links) > 0:
                        return 'BLEND'
                    elif bl_node.inputs['Alpha'].default_value < 1:
                        return 'BLEND'
                    elif len(bl_node.inputs['Transmission Weight'].links) > 0:
                        return 'BLEND'
                    elif bl_node.inputs['Transmission Weight'].default_value > 0:
                        return 'BLEND'
                elif isinstance(bl_node, bpy.types.ShaderNodeBsdfTransparent):
                    return 'BLEND'

    return 'OPAQUE'

def updateOrbitCameraView(cam_obj, scene):

    target_obj = cam_obj.data.v3d.orbit_target_object

    eye = cam_obj.matrix_world.to_translation()
    target = (cam_obj.data.v3d.orbit_target if target_obj is None
            else target_obj.matrix_world.to_translation())

    quat = getLookAtAlignedUpMatrix(eye, target).to_quaternion()
    quat.rotate(cam_obj.matrix_world.inverted())
    quat.rotate(cam_obj.matrix_basis)

    rot_mode = cam_obj.rotation_mode
    cam_obj.rotation_mode = 'QUATERNION'
    cam_obj.rotation_quaternion = quat
    cam_obj.rotation_mode = rot_mode

    bpy.context.view_layer.update()

def getLookAtAlignedUpMatrix(eye, target):

    """
    This method uses camera axes for building the matrix.
    """

    axis_z = (eye - target).normalized()

    if axis_z.length == 0:
        axis_z = mathutils.Vector((0, -1, 0))

    axis_x = mathutils.Vector((0, 0, 1)).cross(axis_z)

    if axis_x.length == 0:
        axis_x = mathutils.Vector((1, 0, 0))

    axis_y = axis_z.cross(axis_x)

    return mathutils.Matrix([
        axis_x,
        axis_y,
        axis_z,
    ]).transposed()

def objDataUsesLineRendering(bl_obj_data):
    line_settings = getattr(getattr(bl_obj_data, 'v3d', None), 'line_rendering_settings', None)
    return bool(line_settings and line_settings.enable)

def getObjectAllCollections(blObj):
    return [coll for coll in bpy.data.collections if blObj in coll.all_objects[:]]

def objHasExportedModifiers(obj):
    """
    Check if an object has any modifiers that should be applied before export.
    """

    return any([modifierNeedsExport(mod) for mod in obj.modifiers])

def objDelNotExportedModifiers(obj):
    """
    Remove modifiers that shouldn't be applied before export from an object.
    """

    for mod in obj.modifiers:
        if not modifierNeedsExport(mod):
            obj.modifiers.remove(mod)

def objAddTriModifier(obj):
    mod = obj.modifiers.new('Temporary_Triangulation', 'TRIANGULATE')
    mod.quad_method = 'FIXED'

def objApplyModifiers(obj):
    """
    Creates a new mesh from applying modifiers to the mesh of the given object.
    Assignes the newly created mesh to the given object. The old mesh's user
    count will be decreased by 1.
    """

    dg = bpy.context.evaluated_depsgraph_get()

    need_linking = dg.scene.collection.objects.find(obj.name) == -1
    need_showing = obj.hide_viewport

    if need_linking:
        dg.scene.collection.objects.link(obj)

    obj.update_tag()

    if need_showing:
        obj.hide_viewport = False

    bpy.context.view_layer.update()

    obj_eval = obj.evaluated_get(dg)

    obj.data = bpy.data.meshes.new_from_object(obj_eval,
            preserve_all_data_layers=True, depsgraph=dg)
    obj.modifiers.clear()

    if need_linking:
        dg.scene.collection.objects.unlink(obj)
    if need_showing:
        obj.hide_viewport = True

def applyShapeKey(obj, index):
    shapekeys = obj.data.shape_keys.key_blocks

    if index < 0 or index > len(shapekeys):
        return

    for i in reversed(range(0, len(shapekeys))):
        if i != index:
            obj.shape_key_remove(shapekeys[i])

    obj.shape_key_remove(shapekeys[0])

def objTransferShapeKeys(objFrom, objTo, generatedObjs, generatedMeshes, generatedShapeKeys):
    names = [shkey.name for shkey in objFrom.data.shape_keys.key_blocks]
    weights = [shkey.value for shkey in objFrom.data.shape_keys.key_blocks]

    log.debug('Transferring {} shapekeys on {}'.format(len(names) - 1, objFrom.name))

    for index in range(1, len(objFrom.data.shape_keys.key_blocks)):
        log.debug('Transferring shapekey {} with name {}'.format(index, names[index]))

        objShapeKey = objFrom.copy()
        tmpMesh = objShapeKey.data.copy()
        generatedShapeKeys.append(tmpMesh.shape_keys)
        objShapeKey.data = tmpMesh

        bpy.context.collection.objects.link(objShapeKey)

        applyShapeKey(objShapeKey, index)
        objApplyModifiers(objShapeKey)

        generatedObjs.append(objShapeKey)
        generatedMeshes.append(tmpMesh)
        generatedMeshes.append(objShapeKey.data)

        for obj in bpy.context.scene.objects:
            obj.select_set(False)

        objShapeKey.select_set(True)
        bpy.context.view_layer.objects.active = objTo
        bpy.ops.object.join_shapes()

        if objTo.data.shape_keys is None:
            return False

        numTransferredKeys = len(objTo.data.shape_keys.key_blocks) - 1
        if numTransferredKeys != index:
            return False

        objTo.data.shape_keys.key_blocks[index].name = names[index]
        objTo.data.shape_keys.key_blocks[index].value = weights[index]

    return True

def meshNeedTangentsForExport(mesh, optimize_tangents):
    """
    Check if it's needed to export tangents for the given mesh.
    """

    return (meshHasUvLayers(mesh) and (meshMaterialsUseTangents(mesh)
            or not optimize_tangents))

def meshHasUvLayers(mesh):
    return bool(mesh.uv_layers.active and len(mesh.uv_layers) > 0)

def meshMaterialsUseTangents(mesh):

    for mat in mesh.materials:
        if mat and mat.use_nodes and mat.node_tree != None:
            node_trees = extractMaterialNodeTrees(mat.node_tree)
            for node_tree in node_trees:
                for bl_node in node_tree.nodes:
                    if matNodeUseTangents(bl_node):
                        return True

        elif mat == None:
            return True

    return False

def matNodeUseTangents(bl_node):

    if isinstance(bl_node, bpy.types.ShaderNodeNormalMap):
        return True

    if (isinstance(bl_node, bpy.types.ShaderNodeTangent)
            and bl_node.direction_type == 'UV_MAP'):
        return True

    if isinstance(bl_node, bpy.types.ShaderNodeNewGeometry):
        for out in bl_node.outputs:
            if out.identifier == 'Tangent' and out.is_linked:
                return True

    return False

def meshPreferredTangentsUvMap(mesh):
    uvMaps = []

    for mat in mesh.materials:
        if mat and mat.use_nodes and mat.node_tree != None:
            nodeTrees = extractMaterialNodeTrees(mat.node_tree)
            for nodeTree in nodeTrees:
                for node in nodeTree.nodes:
                    if ((isinstance(node, bpy.types.ShaderNodeNormalMap) or
                            (isinstance(node, bpy.types.ShaderNodeTangent) and node.direction_type == 'UV_MAP'))
                            and node.uv_map):
                        uvMaps.append(node.uv_map)

    if len(uvMaps) == 1 and uvMaps[0] in mesh.uv_layers:
        return uvMaps[0]
    else:

        if len(uvMaps) > 1:
            log.warning('More than 1 UV map is used to calculate tangents in material(s) ' +
                        'assigned on mesh {}, expect incorrect normal mapping'.format(mesh.name))

        for uvLayer in mesh.uv_layers:
            if uvLayer.active_render:
                return uvLayer.name

    log.error('Tangents UV map not found')
    return ''

def extractMaterialNodeTrees(node_tree):
    """NOTE: located here since it's needed for meshMaterialsUseTangents()"""

    out = [node_tree]

    for bl_node in node_tree.nodes:
        if isinstance(bl_node, bpy.types.ShaderNodeGroup):
            out += extractMaterialNodeTrees(bl_node.node_tree)

    return out

def meshHasNgons(mesh):
    for poly in mesh.polygons:
        if poly.loop_total > 4:
            return True

    return False

def modifierNeedsExport(mod):
    """
    Modifiers that are applied before export shouldn't be:
        - hidden during render (a way to disable export of a modifier)
        - ARMATURE modifiers (used separately via skinning)
    """

    return mod.show_render and mod.type != 'ARMATURE'

def getSocketDefvalCompat(socket, RGBAToRGB=False, isOSL=False):
    """
    Get the default value of input/output sockets in some compatible form.
    Vector types such as bpy_prop_aray, Vector, Euler, etc... are converted to lists,
    primitive types are converted to int/float.
    """

    if socket.type == 'VALUE' or socket.type == 'INT':
        return socket.default_value
    elif socket.type == 'BOOLEAN':
        return int(socket.default_value)
    elif socket.type == 'VECTOR':
        return [i for i in socket.default_value]
    elif socket.type == 'RGBA':
        val = [i for i in socket.default_value]
        if RGBAToRGB:
            val = val[0:3]
        return val
    elif socket.type == 'SHADER':
        return [0, 0, 0, 0]
    elif socket.type == 'STRING' and isOSL:
        return pyosl.glslgen.string_to_osl_const(socket.default_value)
    elif socket.type == 'CUSTOM':
        return 0
    else:
        return 0

def createCustomProperty(bl_element):
    """
    Filters and creates a custom property, which is stored in the glTF extra field.
    """
    if not bl_element:
        return None

    props = {}

    black_list = ['cycles', 'cycles_visibility', 'cycles_curves', '_RNA_UI', 'v3d']

    count = 0
    for custom_property in bl_element.keys():
        if custom_property in black_list:
            continue

        value = bl_element[custom_property]

        add_value = False

        if isinstance(value, str):
            add_value = True

        if isinstance(value, (int, float)):
            add_value = True

        if hasattr(value, "to_list"):
            value = value.to_list()
            add_value = True

        if add_value:
            props[custom_property] = value
            count += 1

    if count == 0:
        return None

    return props

def calcLightThresholdDist(bl_light, threshold):
    """Calculate the light attenuation distance from the given threshold.

    The light power at this distance equals the threshold value.
    """
    return math.sqrt(max(1e-16,
        max(bl_light.color.r, bl_light.color.g, bl_light.color.b)
        * max(1, bl_light.specular_factor)
        * abs(bl_light.energy / 100)
        / max(threshold, 1e-16)
    ))

def objHasFixOrthoZoom(bl_obj):
    if (bl_obj.parent and bl_obj.parent.type == 'CAMERA' and
            bl_obj.parent.data.type == 'ORTHO' and bl_obj.v3d.fix_ortho_zoom):
        return True
    else:
        return False

def objHasCanvasFitParams(bl_obj):
    if (bl_obj.parent and bl_obj.parent.type == 'CAMERA' and
            (bl_obj.v3d.canvas_fit_x != 'NONE' or bl_obj.v3d.canvas_fit_y != 'NONE')):
        return True
    else:
        return False

def sceneFrameSetFloat(scene, value):
    frame = math.floor(value)
    subframe = value - frame
    scene.frame_set(frame, subframe=subframe)

def nodeIsConnectedTo(blNode, fromOutput, toType):
    for link in blNode.outputs[fromOutput].links:
        if link.is_valid and isinstance(link.to_node, toType):
            return True
    return False
