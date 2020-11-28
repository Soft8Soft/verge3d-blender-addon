# Copyright (c) 2017-2019 Soft8Soft LLC
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

ORTHO_EPS = 1e-5
DEFAULT_MAT_NAME = 'v3d_default_material'
BOUND_BOX_MAX = 1e10

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

def getWorldFirstValidTextureSlot(world):

    for bl_texture_slot in world.texture_slots:
        if (bl_texture_slot is not None and
                bl_texture_slot.texture and
                bl_texture_slot.texture.users != 0 and
                (bl_texture_slot.texture.type == 'ENVIRONMENT_MAP'
                or bl_texture_slot.texture.type == 'IMAGE'
                and bl_texture_slot.texture_coords == 'EQUIRECT') and
                getTexImage(bl_texture_slot.texture) is not None and
                getTexImage(bl_texture_slot.texture).users != 0 and
                getTexImage(bl_texture_slot.texture).size[0] > 0 and
                getTexImage(bl_texture_slot.texture).size[1] > 0):

            return bl_texture_slot

    return None

def getWorldCyclesEnvTexture(world):

    if world.node_tree is not None and world.use_nodes:
        for bl_node in world.node_tree.nodes:
            if (bl_node.type == 'TEX_ENVIRONMENT' and
                    getTexImage(bl_node) is not None and
                    getTexImage(bl_node).users != 0 and
                    getTexImage(bl_node).size[0] > 0 and
                    getTexImage(bl_node).size[1] > 0):

                return bl_node

    return None

def getWorldCyclesBkgStrength(world):

    if world.node_tree is not None and world.use_nodes:
        for bl_node in world.node_tree.nodes:
            if bl_node.type == 'BACKGROUND':
                return bl_node.inputs['Strength'].default_value

        return 0
    else:
        return 1

def getWorldCyclesBkgColor(world):

    if world.node_tree is not None and world.use_nodes:
        for bl_node in world.node_tree.nodes:
            if bl_node.type == 'BACKGROUND':
                return bl_node.inputs['Color'].default_value

        return [0, 0, 0]
    else:
        # Blender default grey color
        return [0.041, 0.041, 0.041]

def getLightCyclesStrength(bl_light):
    return bl_light.energy


def getLightCyclesColor(bl_light):
    col = bl_light.color
    return [col[0], col[1], col[2]]

def setSelectedObject(bl_obj):
    """
    Select object for NLA baking
    """
    global prevActiveObject

    global selectedObject, selectedObjectsSave

    selectedObject = bl_obj
    selectedObjectsSave = bpy.context.selected_objects.copy()

    # NOTE: seems like we need both selection and setting active object
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

def mat4IsIdentity(mat4):
    return mat4 == mathutils.Matrix.Identity(4)

def mat4IsTRSDecomposable(mat4):
    # don't use mathutils.Matrix.is_orthogonal_axis_vectors property, because it
    # doesn't normalize vectors before checking

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

        # NOTE: a potential reflection part in U and VH matrices isn't considered
        mat_trans = mathutils.Matrix.Translation(mat4.to_translation())
        mat_left = mat_trans @ (mat_u @ mat_s).to_4x4()

        return (mat_left, mat_vh.to_4x4())

    except np.linalg.LinAlgError:
        # numpy failed to decompose the matrix
        return None

def findArmature(obj):

    for mod in obj.modifiers:
        if mod.type == 'ARMATURE' and mod.object is not None:
            return mod.object

    # use obj.find_armature as a last resort, because it doesn't work with many
    # armature modifiers
    return obj.find_armature()

def matHasBlendBackside(bl_mat):
    return (matIsBlend(bl_mat) and
        (hasattr(bl_mat, 'show_transparent_back') and bl_mat.show_transparent_back))

def matIsBlend(bl_mat):
    return bl_mat.blend_method in ['BLEND', 'MULTIPLY', 'ADD']

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

    # need to update the camera state (i.e. world matrix) immediately in case of
    # several consecutive UI updates

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

def getBlurPixelRadius(context, blLight):

    if blLight.type == 'SUN':
        relativeRadius = (blLight.shadow_buffer_soft / 100
                * int(context.scene.eevee.shadow_cascade_size))
        # blur strength doesn't increase after a certain point
        return min(max(relativeRadius, 0), 100)
    else:
        blurGrade = math.floor(blLight.shadow_buffer_soft
                * int(context.scene.eevee.shadow_cube_size) / 1000)
        blurGrade = min(blurGrade, 9)

        # some approximation of Blender blur radius
        if blurGrade > 2:
            return 4.22 * (blurGrade - 1.5)
        else:
            return blurGrade


def objHasExportedModifiers(obj):
    """
    Check if an object has any modifiers that should be applied before export.
    """

    return any([modifierNeedsExport(mod) for mod in obj.modifiers])

def obj_del_not_exported_modifiers(obj):
    """
    Remove modifiers that shouldn't be applied before export from an object.
    """

    for mod in obj.modifiers:
        if not modifierNeedsExport(mod):
            obj.modifiers.remove(mod)

def objAddTriModifier(obj):
    mod = obj.modifiers.new('Temporary_Triangulation', 'TRIANGULATE')
    mod.quad_method = 'FIXED'
    mod.keep_custom_normals = True

def objApplyModifiers(obj):
    """
    Creates a new mesh from applying modifiers to the mesh of the given object.
    Assignes the newly created mesh to the given object. The old mesh's user
    count will be decreased by 1.
    """

    dg = bpy.context.evaluated_depsgraph_get()

    need_linking = dg.scene.collection.objects.find(obj.name) == -1
    need_showing = obj.hide_viewport

    # NOTE: link the object if it's not in the 'Master Collection' and update
    # the view layer to make the depsgraph able to apply modifiers to the object
    if need_linking:
        dg.scene.collection.objects.link(obj)

    obj.update_tag()

    # a hidden object doesn't get its modifiers applied, need to make it visible
    # before updating the view layer
    if need_showing:
        obj.hide_viewport = False

    bpy.context.view_layer.update()

    # NOTE: some modifiers can remove UV layers from an object after applying
    # (e.g. Skin), which is a consistent behavior regarding uv usage in the
    # viewport (e.g. degenerate tangent space in the Normal Map node)
    obj_eval = obj.evaluated_get(dg)

    obj.data = bpy.data.meshes.new_from_object(obj_eval,
            preserve_all_data_layers=True, depsgraph=dg)
    obj.modifiers.clear()

    if need_linking:
        dg.scene.collection.objects.unlink(obj)
    if need_showing:
        obj.hide_viewport = True

def objTransferShapeKeys(obj_from, obj_to, depsgraph):
    """
    Transfer shape keys from one object to another if it's possible:
        - obj_from should be in the current view layer to be evaluated by depsgraph
        - obj_to should not have shape keys
        - obj_from (after evaluating) and obj_to should have the same amount of vertices

    Returns a boolean flag indicating successful transfer.
    """

    if obj_from.data.shape_keys is None:
        return True

    key_blocks_from = obj_from.data.shape_keys.key_blocks
    keys_from = [key for key in key_blocks_from if key != key.relative_key
            and key != obj_from.data.shape_keys.reference_key]

    key_names = [key.name for key in keys_from]
    key_values = [key.value for key in keys_from]

    key_positions = []
    for key in keys_from:
        key.value = 0

    same_vertex_count = True
    for key in keys_from:

        key.value = 1
        obj_from.update_tag()
        bpy.context.view_layer.update()

        verts = obj_from.evaluated_get(depsgraph).data.vertices
        if len(verts) != len(obj_to.data.vertices):
            same_vertex_count = False
            break

        key_pos = [0] * 3 * len(verts)
        verts.foreach_get('co', key_pos)
        key_positions.append(key_pos)
        key.value = 0

    if same_vertex_count:
        # basis shape key
        obj_to.shape_key_add(name=obj_from.data.shape_keys.reference_key.name)

        vert_co = [0] * 3 * len(obj_to.data.vertices)
        for i in range(len(key_names)):

            key_block = obj_to.shape_key_add(name=key_names[i])
            key_block.value = key_values[i]
            key_block.data.foreach_set('co', key_positions[i])
    else:
        # don't create nothing if vertex count isn't constant
        pass

    for i in range(len(keys_from)):
        keys_from[i].value = key_values[i]

    return same_vertex_count

def objCastsShadows(obj):
    # NOTE: currently unused

    if obj.type not in ['MESH', 'CURVE', 'SURFACE', 'META', 'FONT']:
        return False

    # no materials means a single default material (always casts)
    if len(obj.material_slots) == 0:
        return True

    for mat_slot in obj.material_slots:
        # default material (always casts) or a material with not NONE shadow method
        if mat_slot.material is None or mat_slot.material.shadow_method != 'NONE':
            return True

    return False

def objsGetBoundBoxWorld(objects):
    # NOTE: currently unused

    bound_box = [
        mathutils.Vector(), mathutils.Vector(), mathutils.Vector(),
        mathutils.Vector(), mathutils.Vector(), mathutils.Vector(),
        mathutils.Vector(), mathutils.Vector()
    ]

    minVec = mathutils.Vector.Fill(3, BOUND_BOX_MAX)
    maxVec = mathutils.Vector.Fill(3, -BOUND_BOX_MAX)

    for obj in objects:
        for corner in obj.bound_box:
            corner_world = obj.matrix_world @ mathutils.Vector(corner)
            minVec.x = min(minVec.x, corner_world.x)
            minVec.y = min(minVec.y, corner_world.y)
            minVec.z = min(minVec.z, corner_world.z)
            maxVec.x = max(maxVec.x, corner_world.x)
            maxVec.y = max(maxVec.y, corner_world.y)
            maxVec.z = max(maxVec.z, corner_world.z)

    for i in range(8):
        bound_box[i].x = minVec.x if i >> 0 & 1 == 0 else maxVec.x
        bound_box[i].y = minVec.y if i >> 1 & 1 == 0 else maxVec.y
        bound_box[i].z = minVec.z if i >> 2 & 1 == 0 else maxVec.z

    return bound_box

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

        # HACK: in most cases this one indicates that object linking is used
        # disable tangent optimizations for such cases
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
        # shader sockets have no default value
        return [0, 0, 0, 0]
    elif socket.type == 'STRING' and isOSL:
        # for now used for OSL only
        return pyosl.glslgen.string_to_osl_const(socket.default_value)
    elif socket.type == 'CUSTOM':
        # not supported
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

    # Custom properties, which are in most cases present and should not be exported.
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
