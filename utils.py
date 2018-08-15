# Copyright (c) 2017-2018 Soft8Soft LLC
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
import mathutils

ORTHO_EPS = 1e-5

def integer_to_bl_suffix(val):

    suf = str(val)
    
    for i in range(0, 3 - len(suf)):
        suf = '0' + suf

    return suf

def get_world_first_valid_texture_slot(world):

    for blender_texture_slot in world.texture_slots:
        if (blender_texture_slot is not None and
                blender_texture_slot.texture and
                blender_texture_slot.texture.users != 0 and
                (blender_texture_slot.texture.type == 'ENVIRONMENT_MAP' 
                or blender_texture_slot.texture.type == 'IMAGE' 
                and blender_texture_slot.texture_coords == 'EQUIRECT') and
                get_tex_image(blender_texture_slot.texture) is not None and
                get_tex_image(blender_texture_slot.texture).users != 0 and
                get_tex_image(blender_texture_slot.texture).size[0] > 0 and
                get_tex_image(blender_texture_slot.texture).size[1] > 0):
            
            return blender_texture_slot

    return None

def isCyclesRender(context):
    return context.scene.render.engine == 'CYCLES'

def getWorldCyclesEnvTexture(world):
    
    if world.node_tree is not None and world.use_nodes:
        for bl_node in world.node_tree.nodes:
            if (bl_node.type == 'TEX_ENVIRONMENT' and 
                    get_tex_image(bl_node) is not None and 
                    get_tex_image(bl_node).users != 0 and 
                    get_tex_image(bl_node).size[0] > 0 and 
                    get_tex_image(bl_node).size[1] > 0):
                
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
    if bl_light.node_tree is not None and bl_light.use_nodes:
        for bl_node in bl_light.node_tree.nodes:
            if bl_node.type == 'EMISSION':
                return bl_node.inputs['Strength'].default_value

    # point and spot light have 100 as default strength
    if bl_light.type == 'POINT' or bl_light.type == 'SPOT':
        return 100 * bl_light.energy
    else:
        return bl_light.energy


def getLightCyclesColor(bl_light):
    if bl_light.node_tree is not None and bl_light.use_nodes:
        for bl_node in bl_light.node_tree.nodes:
            if bl_node.type == 'EMISSION':
                col = bl_node.inputs['Color'].default_value
                return [col[0], col[1], col[2]]

    col = bl_light.color
    return [col[0], col[1], col[2]]


def get_scene_by_object(obj):

    for scene in bpy.data.scenes:
        index = scene.objects.find(obj.name)
        if index > -1 and scene.objects[index] == obj:
            return scene

    return None

def is_on_exported_layer(obj):

    scene = get_scene_by_object(obj)
    if scene is None:
        scene = bpy.context.scene

    for i in range(len(obj.layers)):
        if obj.layers[i] and scene.v3d.export_layers[i]:
            return True

    return False

def is_dupli_obj_visible_in_group(dgroup, dobj):

    for a, b in zip(dobj.layers, dgroup.layers):
        if a and b:
            return True

    return False

def get_tex_image(bl_tex):

    """
    Get texture image from a texture, avoiding AttributeError for textures
    without an image (e.g. a texture of type 'NONE').
    """

    return getattr(bl_tex, 'image', None)

def get_texture_name(bl_texture):
    if (isinstance(bl_texture, (bpy.types.ShaderNodeTexImage, 
            bpy.types.ShaderNodeTexEnvironment))):
        tex_name = bl_texture.image.name
    elif (isinstance(bl_texture, (bpy.types.ShaderNodeTexture, 
            bpy.types.MaterialTextureSlot, bpy.types.WorldTextureSlot))):
        tex_name = bl_texture.texture.name
    else:
        tex_name = bl_texture.name

    return tex_name


def get_obj_matrix_parent_inverse_status(obj):

    is_identity = obj.matrix_parent_inverse == mathutils.Matrix.Identity(4)
    is_decomposable = mat4_is_decomposable(obj.matrix_parent_inverse)

    return is_identity, is_decomposable

def mat4_is_decomposable(mat4):

    # don't use mathutils.Matrix.is_orthogonal_axis_vectors property, because it
    # doesn't normalize vectors before checking

    mat = mat4.to_3x3().transposed()
    v0 = mat[0].normalized()
    v1 = mat[1].normalized()
    v2 = mat[2].normalized()

    return (abs(v0.dot(v1)) < ORTHO_EPS 
            and abs(v0.dot(v2)) < ORTHO_EPS 
            and abs(v1.dot(v2)) < ORTHO_EPS)
