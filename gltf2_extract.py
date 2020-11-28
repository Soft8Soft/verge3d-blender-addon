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
import copy
import mathutils
import mathutils.geometry
import math, io, os, re, tempfile

import pluginUtils
from pluginUtils.log import *
import pluginUtils.gltf as gltf

from .gltf2_get import *
from .utils import *

import pcpp, pyosl.oslparse, pyosl.glslgen


GLTF_MAX_COLORS = 8
CURVE_DATA_SIZE = 256;


def convertSwizzleLocation(loc):
    """
    Converts a location from Blender coordinate system to glTF coordinate system.
    """
    return mathutils.Vector((loc[0], loc[2], -loc[1]))


def convertSwizzleTangent(tan, sign):
    """
    Converts a tangent from Blender coordinate system to glTF coordinate system.
    """
    return mathutils.Vector((tan[0], tan[2], -tan[1], sign))


def convertSwizzleRotation(rot):
    """
    Converts a quaternion rotation from Blender coordinate system to glTF coordinate system.
    'w' is still at first position.
    """
    return mathutils.Quaternion((rot[0], rot[1], rot[3], -rot[2]))


def convertSwizzleScale(scale):
    """
    Converts a scale from Blender coordinate system to glTF coordinate system.
    """
    return mathutils.Vector((scale[0], scale[2], scale[1]))

def decomposeTransformSwizzle(matrix):
    translation, rotation, scale = matrix.decompose()
    """
    Decompose a matrix and convert transforms from Blender coordinate system to glTF coordinate system.
    """

    translation = convertSwizzleLocation(translation)
    rotation = convertSwizzleRotation(rotation)
    scale = convertSwizzleScale(scale)

    return translation, rotation, scale

def convertSwizzleMatrix(matrix):
    """
    Converts a matrix from Blender coordinate system to glTF coordinate system.
    """
    translation, rotation, scale = decomposeTransformSwizzle(matrix)

    mat_trans = mathutils.Matrix.Translation(translation)
    mat_rot = mathutils.Quaternion(rotation).to_matrix().to_4x4()
    mat_sca = mathutils.Matrix()
    mat_sca[0][0] = scale[0]
    mat_sca[1][1] = scale[1]
    mat_sca[2][2] = scale[2]

    return mat_trans @ mat_rot @ mat_sca

def extractPrimitiveFloor(a, indices, use_tangents):
    """
    Shift indices, that the first one starts with 0. It is assumed, that the indices are packed.
    """

    attributes = {
        'POSITION' : [],
        'NORMAL' : []
    }

    if use_tangents:
        attributes['TANGENT'] = []

    result_primitive = {
        'material' : a['material'],
        'useNodeAttrs' : a['useNodeAttrs'],
        'indices' : [],
        'attributes' : attributes
    }

    source_attributes = a['attributes']



    texcoord_index = 0
    process_texcoord = True
    while process_texcoord:
        texcoord_id = 'TEXCOORD_' + str(texcoord_index)

        if source_attributes.get(texcoord_id) is not None:
            attributes[texcoord_id] = []
            texcoord_index += 1
        else:
            process_texcoord = False

    texcoord_max = texcoord_index



    color_index = 0
    process_color = True
    while process_color:
        color_id = 'COLOR_' + str(color_index)

        if source_attributes.get(color_id) is not None:
            attributes[color_id] = []
            color_index += 1
        else:
            process_color = False

    color_max = color_index



    skinAttrIndex = 0
    process_bone = True
    while process_bone:
        joint_id = 'JOINTS_' + str(skinAttrIndex)
        weight_id = 'WEIGHTS_' + str(skinAttrIndex)

        if source_attributes.get(joint_id) is not None:
            attributes[joint_id] = []
            attributes[weight_id] = []
            skinAttrIndex += 1
        else:
            process_bone = False

    skinAttrIndexMax = skinAttrIndex



    morph_index = 0
    process_morph = True
    while process_morph:
        morph_position_id = 'MORPH_POSITION_' + str(morph_index)
        morph_normal_id = 'MORPH_NORMAL_' + str(morph_index)
        morph_tangent_id = 'MORPH_TANGENT_' + str(morph_index)

        if source_attributes.get(morph_position_id) is not None:
            attributes[morph_position_id] = []
            attributes[morph_normal_id] = []
            if use_tangents:
                attributes[morph_tangent_id] = []
            morph_index += 1
        else:
            process_morph = False

    morph_max = morph_index



    min_index = min(indices)
    max_index = max(indices)

    for old_index in indices:
        result_primitive['indices'].append(old_index - min_index)

    for old_index in range(min_index, max_index + 1):
        for vi in range(0, 3):
            attributes['POSITION'].append(source_attributes['POSITION'][old_index * 3 + vi])
            attributes['NORMAL'].append(source_attributes['NORMAL'][old_index * 3 + vi])

        if use_tangents:
            for vi in range(0, 4):
                attributes['TANGENT'].append(source_attributes['TANGENT'][old_index * 4 + vi])

        for texcoord_index in range(0, texcoord_max):
            texcoord_id = 'TEXCOORD_' + str(texcoord_index)
            for vi in range(0, 2):
                attributes[texcoord_id].append(source_attributes[texcoord_id][old_index * 2 + vi])

        for color_index in range(0, color_max):
            color_id = 'COLOR_' + str(color_index)
            for vi in range(0, 4):
                attributes[color_id].append(source_attributes[color_id][old_index * 4 + vi])

        for skinAttrIndex in range(0, skinAttrIndexMax):
            joint_id = 'JOINTS_' + str(skinAttrIndex)
            weight_id = 'WEIGHTS_' + str(skinAttrIndex)
            for vi in range(0, 4):
                attributes[joint_id].append(source_attributes[joint_id][old_index * 4 + vi])
                attributes[weight_id].append(source_attributes[weight_id][old_index * 4 + vi])

        for morph_index in range(0, morph_max):
            morph_position_id = 'MORPH_POSITION_' + str(morph_index)
            morph_normal_id = 'MORPH_NORMAL_' + str(morph_index)
            morph_tangent_id = 'MORPH_TANGENT_' + str(morph_index)
            for vi in range(0, 3):
                attributes[morph_position_id].append(source_attributes[morph_position_id][old_index * 3 + vi])
                attributes[morph_normal_id].append(source_attributes[morph_normal_id][old_index * 3 + vi])
            if use_tangents:
                for vi in range(0, 4):
                    attributes[morph_tangent_id].append(source_attributes[morph_tangent_id][old_index * 4 + vi])

    return result_primitive


def extractPrimitivePack(a, indices, use_tangents):
    """
    Packs indices, that the first one starts with 0. Current indices can have gaps.
    """

    attributes = {
        'POSITION' : [],
        'NORMAL' : []
    }

    if use_tangents:
        attributes['TANGENT'] = []

    result_primitive = {
        'material' : a['material'],
        'useNodeAttrs' : a['useNodeAttrs'],
        'indices' : [],
        'attributes' : attributes
    }

    source_attributes = a['attributes']



    texcoord_index = 0
    process_texcoord = True
    while process_texcoord:
        texcoord_id = 'TEXCOORD_' + str(texcoord_index)

        if source_attributes.get(texcoord_id) is not None:
            attributes[texcoord_id] = []
            texcoord_index += 1
        else:
            process_texcoord = False

    texcoord_max = texcoord_index



    color_index = 0
    process_color = True
    while process_color:
        color_id = 'COLOR_' + str(color_index)

        if source_attributes.get(color_id) is not None:
            attributes[color_id] = []
            color_index += 1
        else:
            process_color = False

    color_max = color_index


    skinAttrIndex = 0
    process_bone = True
    while process_bone:
        joint_id = 'JOINTS_' + str(skinAttrIndex)
        weight_id = 'WEIGHTS_' + str(skinAttrIndex)

        if source_attributes.get(joint_id) is not None:
            attributes[joint_id] = []
            attributes[weight_id] = []
            skinAttrIndex += 1
        else:
            process_bone = False

    skinAttrIndexMax = skinAttrIndex


    morph_index = 0
    process_morph = True
    while process_morph:
        morph_position_id = 'MORPH_POSITION_' + str(morph_index)
        morph_normal_id = 'MORPH_NORMAL_' + str(morph_index)
        morph_tangent_id = 'MORPH_TANGENT_' + str(morph_index)

        if source_attributes.get(morph_position_id) is not None:
            attributes[morph_position_id] = []
            attributes[morph_normal_id] = []
            if use_tangents:
                attributes[morph_tangent_id] = []
            morph_index += 1
        else:
            process_morph = False

    morph_max = morph_index



    old_to_new_indices = {}
    new_to_old_indices = {}

    new_index = 0
    for old_index in indices:
        if old_to_new_indices.get(old_index) is None:
            old_to_new_indices[old_index] = new_index
            new_to_old_indices[new_index] = old_index
            new_index += 1

        result_primitive['indices'].append(old_to_new_indices[old_index])

    end_new_index = new_index

    for new_index in range(0, end_new_index):
        old_index = new_to_old_indices[new_index]

        for vi in range(0, 3):
            attributes['POSITION'].append(source_attributes['POSITION'][old_index * 3 + vi])
            attributes['NORMAL'].append(source_attributes['NORMAL'][old_index * 3 + vi])

        if use_tangents:
            for vi in range(0, 4):
                attributes['TANGENT'].append(source_attributes['TANGENT'][old_index * 4 + vi])

        for texcoord_index in range(0, texcoord_max):
            texcoord_id = 'TEXCOORD_' + str(texcoord_index)
            for vi in range(0, 2):
                attributes[texcoord_id].append(source_attributes[texcoord_id][old_index * 2 + vi])

        for color_index in range(0, color_max):
            color_id = 'COLOR_' + str(color_index)
            for vi in range(0, 4):
                attributes[color_id].append(source_attributes[color_id][old_index * 4 + vi])

        for skinAttrIndex in range(0, skinAttrIndexMax):
            joint_id = 'JOINTS_' + str(skinAttrIndex)
            weight_id = 'WEIGHTS_' + str(skinAttrIndex)
            for vi in range(0, 4):
                attributes[joint_id].append(source_attributes[joint_id][old_index * 4 + vi])
                attributes[weight_id].append(source_attributes[weight_id][old_index * 4 + vi])

        for morph_index in range(0, morph_max):
            morph_position_id = 'MORPH_POSITION_' + str(morph_index)
            morph_normal_id = 'MORPH_NORMAL_' + str(morph_index)
            morph_tangent_id = 'MORPH_TANGENT_' + str(morph_index)
            for vi in range(0, 3):
                attributes[morph_position_id].append(source_attributes[morph_position_id][old_index * 3 + vi])
                attributes[morph_normal_id].append(source_attributes[morph_normal_id][old_index * 3 + vi])
            if use_tangents:
                for vi in range(0, 4):
                    attributes[morph_tangent_id].append(source_attributes[morph_tangent_id][old_index * 4 + vi])

    return result_primitive


def checkUseNodeAttrs(bl_mat):
    mat_type = getMaterialType(bl_mat)

    if mat_type == 'CYCLES':
        return True
    else:
        return False

def extractPrimitives(glTF, bl_mesh, bl_vertex_groups,
        bl_joint_indices, exportSettings):
    """
    Extracting primitives from a mesh. Polygons are triangulated and sorted by material.
    Furthermore, primitives are splitted up, if the indices range is exceeded.
    Finally, triangles are also splitted up/dublicatted, if face normals are used instead of vertex normals.
    """

    need_skin_attributes = exportSettings['skins'] and len(bl_joint_indices) > 0

    printLog('INFO', 'Extracting {} primitives'.format(bl_mesh.name))

    if bl_mesh.has_custom_normals or bl_mesh.use_auto_smooth:
        bl_mesh.calc_normals_split()

    use_tangents = False
    if meshNeedTangentsForExport(bl_mesh, exportSettings['optimize_attrs']):
        try:
            bl_mesh.calc_tangents()
            use_tangents = True
        except:
            printLog('WARNING', 'Could not calculate tangents. Please try to triangulate the mesh first.')


    # Gathering position, normal and texcoords.

    primitive_attributes = {
        'POSITION' : [],
        'NORMAL' : []
    }
    if use_tangents:
        primitive_attributes['TANGENT'] = []

    def_mat_primitive = {
        'material' : DEFAULT_MAT_NAME,
        'useNodeAttrs' : False,
        'indices' : [],
        'attributes' : copy.deepcopy(primitive_attributes)
    }

    # NOTE: don't use a dictionary here, because if several slots have the same
    # material it leads to processing their corresponding geometry as a one
    # primitive thus making it a problem to assign separately different Object-linked
    # materials later
    material_primitives = []
    for bl_mat in bl_mesh.materials:
        if bl_mat is None:
            material_primitives.append(copy.deepcopy(def_mat_primitive))
        else:
            material_primitives.append({
                'material' : bl_mat.name,
                'useNodeAttrs' : checkUseNodeAttrs(bl_mat),
                'indices' : [],
                'attributes' : copy.deepcopy(primitive_attributes)
            })
    # explicitly add the default primitive for exceptional cases
    material_primitives.append(copy.deepcopy(def_mat_primitive))

    material_vertex_map = [{} for prim in material_primitives]


    texcoord_max = 0
    if bl_mesh.uv_layers.active:
        texcoord_max = len(bl_mesh.uv_layers)


    vertex_colors = {}

    color_max = 0
    color_index = 0
    for vertex_color in bl_mesh.vertex_colors:
        vertex_color_name = 'COLOR_' + str(color_index)
        vertex_colors[vertex_color_name] = vertex_color

        color_index += 1
        if color_index >= GLTF_MAX_COLORS:
            break
    color_max = color_index


    skinAttrIndexMax = 0
    if need_skin_attributes:
        for bl_polygon in bl_mesh.polygons:
            for loop_index in bl_polygon.loop_indices:
                vertex_index = bl_mesh.loops[loop_index].vertex_index

                # any vertex should be skinned to at least one bone - to the
                # armature itself if no groups are specified
                bones_count = max(len(bl_mesh.vertices[vertex_index].groups), 1)
                if bones_count % 4 == 0:
                    bones_count -= 1
                skinAttrIndexMax = max(skinAttrIndexMax, bones_count // 4 + 1)


    morph_max = 0

    bl_shape_keys = []

    if bl_mesh.shape_keys is not None:
        morph_max = len(bl_mesh.shape_keys.key_blocks) - 1

        for bl_shape_key in bl_mesh.shape_keys.key_blocks:
            if bl_shape_key != bl_shape_key.relative_key:
                bl_shape_keys.append(bl_shape_key)

    # lazy normals calculation to optimize shape keys processing
    _shape_key_normals = {}
    def getShapeKeyNormals(key, normal_type):
        if _shape_key_normals.get(key.name) is None:
            _shape_key_normals[key.name] = {
                'vertex': None,
                'polygon': None,
                'split': None,
            }

        if _shape_key_normals[key.name].get(normal_type) is None:
            if normal_type == 'polygon':
                normals = key.normals_polygon_get()
            elif normal_type == 'split':
                normals = key.normals_split_get()
            else:
                normals = key.normals_vertex_get()

            _shape_key_normals[key.name][normal_type] = normals

        return _shape_key_normals[key.name][normal_type]


    # Convert polygon to primitive indices and eliminate invalid ones. Assign to material.

    for bl_polygon in bl_mesh.polygons:

        if bl_polygon.material_index < 0 or bl_polygon.material_index >= len(bl_mesh.materials):
            # use default material
            primitive = material_primitives[-1]
            vertex_index_to_new_indices = material_vertex_map[-1]
        else:
            primitive = material_primitives[bl_polygon.material_index]
            vertex_index_to_new_indices = material_vertex_map[bl_polygon.material_index]

        export_color = primitive['material'] not in exportSettings['use_no_color']

        attributes = primitive['attributes']

        face_normal = bl_polygon.normal
        face_tangent = mathutils.Vector((0.0, 0.0, 0.0))
        face_bitangent_sign = 1.0
        if use_tangents:
            for loop_index in bl_polygon.loop_indices:
                temp_vertex = bl_mesh.loops[loop_index]
                face_tangent += temp_vertex.tangent
                face_bitangent_sign = temp_vertex.bitangent_sign

            face_tangent.normalize()

        indices = primitive['indices']

        loop_index_list = []


        if len(bl_polygon.loop_indices) == 3:
            loop_index_list.extend(bl_polygon.loop_indices)
        elif len(bl_polygon.loop_indices) > 3:
            # Triangulation of polygon. Using internal function, as non-convex polygons could exist.

            polyline = []

            for loop_index in bl_polygon.loop_indices:
                vertex_index = bl_mesh.loops[loop_index].vertex_index
                v = bl_mesh.vertices[vertex_index].co
                polyline.append(mathutils.Vector((v[0], v[1], v[2])))

            triangles = mathutils.geometry.tessellate_polygon((polyline,))

            for triangle in triangles:
                if bpy.app.version >= (2,81,0):
                    for loop_idx in triangle:
                        loop_index_list.append(bl_polygon.loop_indices[loop_idx])
                else:
                    # old Blender version had bug with flipped triangles
                    loop_index_list.append(bl_polygon.loop_indices[triangle[0]])
                    loop_index_list.append(bl_polygon.loop_indices[triangle[2]])
                    loop_index_list.append(bl_polygon.loop_indices[triangle[1]])

        else:
            continue

        for loop_index in loop_index_list:
            vertex_index = bl_mesh.loops[loop_index].vertex_index

            if vertex_index_to_new_indices.get(vertex_index) is None:
                vertex_index_to_new_indices[vertex_index] = []


            v = None
            n = None
            t = None
            uvs = []
            colors = []
            joints = []
            weights = []

            target_positions = []
            target_normals = []
            target_tangents = []

            vertex = bl_mesh.vertices[vertex_index]

            v = convertSwizzleLocation(vertex.co)
            if bl_polygon.use_smooth:

                if bl_mesh.has_custom_normals or bl_mesh.use_auto_smooth:
                    n = convertSwizzleLocation(bl_mesh.loops[loop_index].normal)
                else:
                    n = convertSwizzleLocation(vertex.normal)
                if use_tangents:
                    t = convertSwizzleTangent(bl_mesh.loops[loop_index].tangent, bl_mesh.loops[loop_index].bitangent_sign)
            else:
                n = convertSwizzleLocation(face_normal)
                if use_tangents:
                    t = convertSwizzleTangent(face_tangent, face_bitangent_sign)

            if bl_mesh.uv_layers.active:
                for texcoord_index in range(0, texcoord_max):
                    uv = bl_mesh.uv_layers[texcoord_index].data[loop_index].uv
                    # NOTE: to comply with glTF spec [0,0] upper left angle
                    uvs.append([uv.x, 1.0 - uv.y])


            if color_max > 0 and export_color:
                for color_index in range(0, color_max):
                    color_name = 'COLOR_' + str(color_index)
                    color = vertex_colors[color_name].data[loop_index].color

                    # vertex colors are defined in sRGB space but only needed to
                    # be linear when rendered
                    colors.append([pluginUtils.srgbToLinear(color[0]),
                            pluginUtils.srgbToLinear(color[1]),
                            pluginUtils.srgbToLinear(color[2]), color[3]])


            if need_skin_attributes:

                skinAttrCount = 0

                if vertex.groups is not None and len(vertex.groups) > 0:
                    joint = []
                    weight = []
                    for group_element in vertex.groups:

                        if len(joint) == 4:
                            skinAttrCount += 1
                            joints.append(joint)
                            weights.append(weight)
                            joint = []
                            weight = []


                        vertex_group_index = group_element.group

                        vertex_group_name = bl_vertex_groups[vertex_group_index].name


                        joint_index = 0
                        joint_weight = 0.0

                        if bl_joint_indices.get(vertex_group_name) is not None:
                            joint_index = bl_joint_indices[vertex_group_name]
                            joint_weight = group_element.weight


                        joint.append(joint_index)
                        weight.append(joint_weight)

                    if len(joint) > 0:
                        skinAttrCount += 1

                        for fill in range(0, 4 - len(joint)):
                            joint.append(0)
                            weight.append(0.0)

                        joints.append(joint)
                        weights.append(weight)

                for fill in range(0, skinAttrIndexMax - skinAttrCount):
                    joints.append([0, 0, 0, 0])
                    weights.append([0.0, 0.0, 0.0, 0.0])


                # use the armature (the last joint) with the unity weight
                # if no joints influence a vertex
                weight_sum = 0
                for skinAttrIndex in range(0, skinAttrIndexMax):
                    weight_sum += sum(weights[skinAttrIndex])

                if weight_sum == 0:
                    joints = [[0, 0, 0, 0] for i in range(0, skinAttrIndexMax)]
                    weights = [[0, 0, 0, 0] for i in range(0, skinAttrIndexMax)]

                    # there will be a joint representing the armature itself,
                    # which will be placed at the end of the joint list in the glTF data
                    joints[0][0] = len(bl_joint_indices)
                    weights[0][0] = 1.0


            if morph_max > 0 and exportSettings['morph']:
                for morph_index in range(0, morph_max):
                    bl_shape_key = bl_shape_keys[morph_index]

                    v_morph = convertSwizzleLocation(bl_shape_key.data[vertex_index].co)

                    # Store delta.
                    v_morph -= v

                    target_positions.append(v_morph)


                    n_morph = None

                    if bl_mesh.use_auto_smooth:
                        temp_normals = getShapeKeyNormals(bl_shape_key, 'split')
                        n_morph = (temp_normals[loop_index * 3 + 0],
                                temp_normals[loop_index * 3 + 1],
                                temp_normals[loop_index * 3 + 2])
                    elif bl_polygon.use_smooth:
                        temp_normals = getShapeKeyNormals(bl_shape_key, 'vertex')
                        n_morph = (temp_normals[vertex_index * 3 + 0],
                                temp_normals[vertex_index * 3 + 1],
                                temp_normals[vertex_index * 3 + 2])
                    else:
                        temp_normals = getShapeKeyNormals(bl_shape_key, 'polygon')
                        n_morph = (temp_normals[bl_polygon.index * 3 + 0],
                                temp_normals[bl_polygon.index * 3 + 1],
                                temp_normals[bl_polygon.index * 3 + 2])

                    n_morph = convertSwizzleLocation(n_morph)

                    # Store delta.
                    n_morph -= n

                    target_normals.append(n_morph)


                    if use_tangents:
                        rotation = n_morph.rotation_difference(n)

                        t_morph = mathutils.Vector((t[0], t[1], t[2]))

                        t_morph.rotate(rotation)

                        target_tangents.append(t_morph)


            create = True

            for current_new_index in vertex_index_to_new_indices[vertex_index]:
                found = True

                for i in range(0, 3):
                    if attributes['POSITION'][current_new_index * 3 + i] != v[i]:
                        found = False
                        break

                    if attributes['NORMAL'][current_new_index * 3 + i] != n[i]:
                        found = False
                        break

                if use_tangents:
                    for i in range(0, 4):
                        if attributes['TANGENT'][current_new_index * 4 + i] != t[i]:
                            found = False
                            break

                if not found:
                    continue

                for texcoord_index in range(0, texcoord_max):
                    uv = uvs[texcoord_index]

                    texcoord_id = 'TEXCOORD_' + str(texcoord_index)
                    for i in range(0, 2):
                        if attributes[texcoord_id][current_new_index * 2 + i] != uv[i]:
                            found = False
                            break

                if export_color:
                    for color_index in range(0, color_max):
                        color = colors[color_index]

                        color_id = 'COLOR_' + str(color_index)
                        for i in range(0, 4):
                            if attributes[color_id][current_new_index * 4 + i] != color[i]:
                                found = False
                                break

                if need_skin_attributes:
                    for skinAttrIndex in range(0, skinAttrIndexMax):
                        joint = joints[skinAttrIndex]
                        weight = weights[skinAttrIndex]

                        joint_id = 'JOINTS_' + str(skinAttrIndex)
                        weight_id = 'WEIGHTS_' + str(skinAttrIndex)
                        for i in range(0, 4):
                            if attributes[joint_id][current_new_index * 4 + i] != joint[i]:
                                found = False
                                break
                            if attributes[weight_id][current_new_index * 4 + i] != weight[i]:
                                found = False
                                break

                if exportSettings['morph']:
                    for morph_index in range(0, morph_max):
                        target_position = target_positions[morph_index]
                        target_normal = target_normals[morph_index]
                        if use_tangents:
                            target_tangent = target_tangents[morph_index]

                        target_position_id = 'MORPH_POSITION_' + str(morph_index)
                        target_normal_id = 'MORPH_NORMAL_' + str(morph_index)
                        target_tangent_id = 'MORPH_TANGENT_' + str(morph_index)
                        for i in range(0, 3):
                            if attributes[target_position_id][current_new_index * 3 + i] != target_position[i]:
                                found = False
                                break
                            if attributes[target_normal_id][current_new_index * 3 + i] != target_normal[i]:
                                found = False
                                break
                            if use_tangents:
                                if attributes[target_tangent_id][current_new_index * 3 + i] != target_tangent[i]:
                                    found = False
                                    break

                if found:
                    indices.append(current_new_index)

                    create = False
                    break

            if not create:
                continue

            new_index = 0

            if primitive.get('max_index') is not None:
                new_index = primitive['max_index'] + 1

            primitive['max_index'] = new_index

            vertex_index_to_new_indices[vertex_index].append(new_index)


            indices.append(new_index)

            attributes['POSITION'].extend(v)
            attributes['NORMAL'].extend(n)
            if use_tangents:
                attributes['TANGENT'].extend(t)

            if bl_mesh.uv_layers.active:
                for texcoord_index in range(0, texcoord_max):
                    texcoord_id = 'TEXCOORD_' + str(texcoord_index)

                    if attributes.get(texcoord_id) is None:
                        attributes[texcoord_id] = []

                    attributes[texcoord_id].extend(uvs[texcoord_index])

            if export_color:
                for color_index in range(0, color_max):
                    color_id = 'COLOR_' + str(color_index)

                    if attributes.get(color_id) is None:
                        attributes[color_id] = []

                    attributes[color_id].extend(colors[color_index])

            if need_skin_attributes:
                for skinAttrIndex in range(0, skinAttrIndexMax):
                    joint_id = 'JOINTS_' + str(skinAttrIndex)

                    if attributes.get(joint_id) is None:
                        attributes[joint_id] = []

                    attributes[joint_id].extend(joints[skinAttrIndex])

                    weight_id = 'WEIGHTS_' + str(skinAttrIndex)

                    if attributes.get(weight_id) is None:
                        attributes[weight_id] = []

                    attributes[weight_id].extend(weights[skinAttrIndex])

            if exportSettings['morph']:
                for morph_index in range(0, morph_max):
                    target_position_id = 'MORPH_POSITION_' + str(morph_index)

                    if attributes.get(target_position_id) is None:
                        attributes[target_position_id] = []

                    attributes[target_position_id].extend(target_positions[morph_index])

                    target_normal_id = 'MORPH_NORMAL_' + str(morph_index)

                    if attributes.get(target_normal_id) is None:
                        attributes[target_normal_id] = []

                    attributes[target_normal_id].extend(target_normals[morph_index])

                    if use_tangents:
                        target_tangent_id = 'MORPH_TANGENT_' + str(morph_index)

                        if attributes.get(target_tangent_id) is None:
                            attributes[target_tangent_id] = []

                        attributes[target_tangent_id].extend(target_tangents[morph_index])


    # Add primitive plus split them if needed.

    result_primitives = []

    for primitive in material_primitives:
        export_color = True
        if primitive['material'] in exportSettings['use_no_color']:
            export_color = False

        indices = primitive['indices']

        if len(indices) == 0:
            continue

        position = primitive['attributes']['POSITION']
        normal = primitive['attributes']['NORMAL']
        if use_tangents:
            tangent = primitive['attributes']['TANGENT']
        texcoords = []
        for texcoord_index in range(0, texcoord_max):
            texcoords.append(primitive['attributes']['TEXCOORD_' + str(texcoord_index)])
        colors = []
        if export_color:
            for color_index in range(0, color_max):
                texcoords.append(primitive['attributes']['COLOR_' + str(color_index)])
        joints = []
        weights = []
        if need_skin_attributes:
            for skinAttrIndex in range(0, skinAttrIndexMax):
                joints.append(primitive['attributes']['JOINTS_' + str(skinAttrIndex)])
                weights.append(primitive['attributes']['WEIGHTS_' + str(skinAttrIndex)])

        target_positions = []
        target_normals = []
        target_tangents = []
        if exportSettings['morph']:
            for morph_index in range(0, morph_max):
                target_positions.append(primitive['attributes']['MORPH_POSITION_' + str(morph_index)])
                target_normals.append(primitive['attributes']['MORPH_NORMAL_' + str(morph_index)])
                if use_tangents:
                    target_tangents.append(primitive['attributes']['MORPH_TANGENT_' + str(morph_index)])


        count = len(indices)

        if count == 0:
            continue

        max_index = max(indices)

        # NOTE: avoiding WebGL2 PRIMITIVE_RESTART_FIXED_INDEX behavior
        # see: https://www.khronos.org/registry/webgl/specs/latest/2.0/#5.18
        range_indices = 65535
        if exportSettings['indices'] == 'UNSIGNED_BYTE':
            range_indices = 255
        elif exportSettings['indices'] == 'UNSIGNED_INT':
            range_indices = 4294967295


        if max_index >= range_indices:
            # Spliting result_primitives.

            # At start, all indicees are pending.
            pending_attributes = {
                'POSITION' : [],
                'NORMAL' : []
            }

            if use_tangents:
                pending_attributes['TANGENT'] = []

            pending_primitive = {
                'material' : primitive['material'],
                'useNodeAttrs' : primitive['useNodeAttrs'],
                'indices' : [],
                'attributes' : pending_attributes
            }

            pending_primitive['indices'].extend(indices)


            pending_attributes['POSITION'].extend(position)
            pending_attributes['NORMAL'].extend(normal)
            if use_tangents:
                pending_attributes['TANGENT'].extend(tangent)
            texcoord_index = 0
            for texcoord in texcoords:
                pending_attributes['TEXCOORD_' + str(texcoord_index)] = texcoord
                texcoord_index += 1
            if export_color:
                color_index = 0
                for color in colors:
                    pending_attributes['COLOR_' + str(color_index)] = color
                    color_index += 1
            if need_skin_attributes:
                joint_index = 0
                for joint in joints:
                    pending_attributes['JOINTS_' + str(joint_index)] = joint
                    joint_index += 1
                weight_index = 0
                for weight in weights:
                    pending_attributes['WEIGHTS_' + str(weight_index)] = weight
                    weight_index += 1
            if exportSettings['morph']:
                morph_index = 0
                for target_position in target_positions:
                    pending_attributes['MORPH_POSITION_' + str(morph_index)] = target_position
                    morph_index += 1
                morph_index = 0
                for target_normal in target_normals:
                    pending_attributes['MORPH_NORMAL_' + str(morph_index)] = target_normal
                    morph_index += 1
                if use_tangents:
                    morph_index = 0
                    for target_tangent in target_tangents:
                        pending_attributes['MORPH_TANGENT_' + str(morph_index)] = target_tangent
                        morph_index += 1

            pending_indices = pending_primitive['indices']

            # Continue until all are processed.
            while len(pending_indices) > 0:

                process_indices = pending_primitive['indices']

                pending_indices = []

                all_local_indices = []

                for i in range(0, (max(process_indices) // range_indices) + 1):
                    all_local_indices.append([])

                # For all faces ...
                for face_index in range(0, len(process_indices), 3):

                    written = False

                    face_min_index = min(process_indices[face_index + 0], process_indices[face_index + 1], process_indices[face_index + 2])
                    face_max_index = max(process_indices[face_index + 0], process_indices[face_index + 1], process_indices[face_index + 2])

                    # ... check if it can be but in a range of maximum indices.
                    for i in range(0, (max(process_indices) // range_indices) + 1):
                        offset = i * range_indices

                        # Yes, so store the primitive with its indices.
                        if face_min_index >= offset and face_max_index < offset + range_indices:
                            all_local_indices[i].extend([process_indices[face_index + 0], process_indices[face_index + 1], process_indices[face_index + 2]])

                            written = True
                            break

                    # If not written, the triangel face has indices from different ranges.
                    if not written:
                        pending_indices.extend([process_indices[face_index + 0], process_indices[face_index + 1], process_indices[face_index + 2]])

                # Only add result_primitives, which do have indices in it.
                for local_indices in all_local_indices:
                    if len(local_indices) > 0:
                        current_primitive = extractPrimitiveFloor(pending_primitive, local_indices, use_tangents)

                        result_primitives.append(current_primitive)

                        printLog('DEBUG', 'Adding primitive with splitting. Indices: ' + str(len(current_primitive['indices'])) + ' Vertices: ' + str(len(current_primitive['attributes']['POSITION']) // 3))

                # Process primitive faces having indices in several ranges.
                if len(pending_indices) > 0:
                    pending_primitive = extractPrimitivePack(pending_primitive, pending_indices, use_tangents)

                    pending_attributes = pending_primitive['attributes']

                    printLog('DEBUG', 'Creating temporary primitive for splitting')

        else:
            # No splitting needed.
            result_primitives.append(primitive)

            printLog('DEBUG', 'Adding primitive without splitting. Indices: ' + str(len(primitive['indices'])) + ' Vertices: ' + str(len(primitive['attributes']['POSITION']) // 3))

    printLog('DEBUG', 'Primitives created: ' + str(len(result_primitives)))

    return result_primitives


def extractLinePrimitives(glTF, bl_mesh, exportSettings):
    """
    Extracting line primitives from a mesh.
    Furthermore, primitives are splitted up, if the indices range is exceeded.
    """

    printLog('DEBUG', 'Extracting line primitive')

    # material property currently isn't used for line meshes in the engine
    mat_name = (bl_mesh.materials[0].name if bl_mesh.materials
            and bl_mesh.materials[0] is not None else '')

    primitive = {
        'material' : mat_name,
        'useNodeAttrs' : False,
        'indices' : [],
        'attributes' : { 'POSITION': [] }
    }

    orig_indices = primitive['indices']
    orig_positions = primitive['attributes']['POSITION']

    vertex_index_to_new_index = {}

    for bl_edge in bl_mesh.edges:
        for vertex_index in bl_edge.vertices:
            vertex = bl_mesh.vertices[vertex_index]

            new_index = vertex_index_to_new_index.get(vertex_index, -1)
            if new_index == -1:
                orig_positions.extend(convertSwizzleLocation(vertex.co))
                new_index = len(orig_positions) // 3 - 1
                vertex_index_to_new_index[vertex_index] = new_index

            orig_indices.append(new_index)


    result_primitives = []

    # NOTE: avoiding WebGL2 PRIMITIVE_RESTART_FIXED_INDEX behavior
    # see: https://www.khronos.org/registry/webgl/specs/latest/2.0/#5.18
    range_indices = 65535
    if exportSettings['indices'] == 'UNSIGNED_BYTE':
        range_indices = 255
    elif exportSettings['indices'] == 'UNSIGNED_INT':
        range_indices = 4294967295

    if len(set(orig_indices)) >= range_indices:
        # Splitting the bunch of a primitive's edges into several parts.
        split_parts = []

        # Process every edge.
        for i in range(0, len(orig_indices), 2):
            edge = orig_indices[i:i+2]

            part_count = len(split_parts)
            part_suitabilities = [0]*part_count

            # Define which split_part is more suitable for a particular edge.
            # The best case is when the both edge indices are already contained
            # in a split_part, so we won't increase the number of the part's
            # unique indices by adding the edge into it.
            for i in range(0, part_count):
                if edge[0] in split_parts[i]:
                    part_suitabilities[i] += 1
                if edge[1] in split_parts[i]:
                    part_suitabilities[i] += 1

            # Sort split_parts by their suitability, e.g. 2,1,1,1,0,0.
            split_part_order = sorted(range(part_count),
                    key=lambda i: part_suitabilities[i], reverse=True)

            # Trying to find the first most suitable split_part with free space.
            need_new_part = True
            for i in split_part_order:
                if len(set(split_parts[i] + edge)) <= range_indices:
                    split_parts[i].extend(edge)
                    need_new_part = False
                    break

            # Create new split_part if no existed part can contain an edge.
            if need_new_part:
                split_parts.append(edge)

        # Create new primitives based on the calculated split_parts.
        for old_indices in split_parts:

            part_primitive = {
                'material' : mat_name,
                'useNodeAttrs' : False,
                'indices' : [],
                'attributes' : { 'POSITION': [] }
            }

            sorted_indices = sorted(set(old_indices))
            for i in sorted_indices:
                part_primitive['attributes']['POSITION'].extend(orig_positions[i*3:i*3+3])

            part_primitive['indices'] = [sorted_indices.index(i) for i in old_indices]

            result_primitives.append(part_primitive)

    else:
        # No splitting needed.
        result_primitives.append(primitive)

    return result_primitives

def extractVec(vec):
    return [i for i in vec]

def extractMat(mat):
    """
    Return matrix in glTF column-major order
    """
    return [mat[0][0], mat[1][0], mat[2][0], mat[3][0],
            mat[0][1], mat[1][1], mat[2][1], mat[3][1],
            mat[0][2], mat[1][2], mat[2][2], mat[3][2],
            mat[0][3], mat[1][3], mat[2][3], mat[3][3]]

def extractNodeGraph(node_tree, exportSettings, glTF):

    nodes = []
    edges = []

    bl_nodes = node_tree.nodes

    for bl_node in bl_nodes:
        node = {
            'name': bl_node.name,
            'type': bl_node.type + '_BL'
        }

        nodes.append(node);

        if bl_node.type == 'ATTRIBUTE':
            # rename for uniformity with GEOMETRY node
            node['colorLayer'] = bl_node.attribute_name

        elif bl_node.type == 'BSDF_REFRACTION':
            node['distribution'] = bl_node.distribution

        elif bl_node.type == 'BUMP':
            node['invert'] = bl_node.invert
        elif bl_node.type == 'CURVE_RGB':
            node['curveData'] = extractCurveMapping(bl_node.mapping, (0,1))
        elif bl_node.type == 'CURVE_VEC':
            node['curveData'] = extractCurveMapping(bl_node.mapping, (-1,1))

        elif bl_node.type == 'GROUP':
            node['nodeGraph'] = getNodeGraphIndex(glTF,
                    bl_node.node_tree.name)

        elif bl_node.type == 'MAPPING':
            # reproducing ShaderNodeMapping
            # https://docs.blender.org/api/current/bpy.types.ShaderNodeMapping.html

            if bpy.app.version < (2,81,0):
                node['rotation'] = extractVec(bl_node.rotation)
                node['scale'] = extractVec(bl_node.scale)
                node['translation'] = extractVec(bl_node.translation)

                node['max'] = extractVec(bl_node.max)
                node['min'] = extractVec(bl_node.min)

                node['useMax'] = bl_node.use_max
                node['useMin'] = bl_node.use_min

            node['vectorType'] = bl_node.vector_type

        elif bl_node.type == 'MAP_RANGE':
            node['clamp'] = bl_node.clamp

        elif bl_node.type == 'MATH':
            # reproducing ShaderNodeMath
            # https://docs.blender.org/api/current/bpy.types.ShaderNodeMath.html

            node['operation'] = bl_node.operation
            node['useClamp'] = bl_node.use_clamp

        elif bl_node.type == 'MIX_RGB':
            # reproducing ShaderNodeMixRGB
            # https://docs.blender.org/api/current/bpy.types.ShaderNodeMixRGB.html

            node['blendType'] = bl_node.blend_type
            node['useClamp'] = bl_node.use_clamp

        elif bl_node.type == 'NORMAL_MAP' or bl_node.type == 'UVMAP':
            # rename for uniformity with GEOMETRY node
            node['uvLayer'] = bl_node.uv_map

        elif bl_node.type == 'TANGENT':
            node['directionType'] = bl_node.direction_type
            node['axis'] = bl_node.axis
            node['uvLayer'] = bl_node.uv_map

        elif bl_node.type == 'SCRIPT':
            node['type'] = 'OSL_NODE'

            if bl_node.mode == 'INTERNAL':
                if bl_node.script:
                    script = bl_node.script.as_string()
                else:
                    script = 'shader Black(output color Col = 0) { Col = 0; }'
            else:
                path = bpy.path.abspath(bl_node.filepath)
                with open(path, 'r', encoding='utf-8') as f:
                    script = f.read()

            oslCode = preprocessOSL(script)
            oslAST = pyosl.oslparse.get_ast(oslCode)

            shaderName = 'node_osl_' + oslAST.get_shader_name().lower()
            node['shaderName'] = shaderName

            inputs, outputs = parseOSLInOuts(oslAST, shaderName)

            node['globalVariables'] = [varName for _, varName in pyosl.glslgen.find_global_variables(oslAST)]

            inputTypes = []
            initializers = []

            for i in range(len(inputs)):
                inputTypes.append(inputs[i][0])

                if inputs[i][3]:
                    initializers.append([inputs[i][3], inputs[i][4]])
                else:
                    initializers.append(None)

            node['initializers'] = initializers

            node['inputTypes'] = inputTypes
            node['outputTypes'] = []

            for o in outputs:
                node['outputTypes'].append(o[0])

            node['fragCode'] = genOSLCode(oslAST, shaderName)

        elif bl_node.type == 'TEX_COORD':
            # NOTE: will be replaced by the corresponding index from glTF['nodes'] later
            node['object'] = bl_node.object

        elif bl_node.type == 'TEX_ENVIRONMENT':
            index = gltf.getTextureIndex(glTF, getTextureName(bl_node)) if getTexImage(bl_node) else -1

            if index == -1:
                node['type'] = 'TEX_ENVIRONMENT_NONE_BL'
            else:
                node['texture'] = index

            node['projection'] = bl_node.projection;

        elif bl_node.type == 'TEX_IMAGE':
            index = gltf.getTextureIndex(glTF, getTextureName(bl_node)) if getTexImage(bl_node) else -1

            if index == -1:
                node['type'] = 'TEX_IMAGE_NONE_BL'
            else:
                node['texture'] = index

            node['projection'] = bl_node.projection
            node['projectionBlend'] = bl_node.projection_blend

            if bl_node.extension == 'CLIP':
                node['clampToEdgeNoExtend'] = True

        elif bl_node.type == 'TEX_GRADIENT':
            node['gradientType'] = bl_node.gradient_type

        elif bl_node.type == 'TEX_NOISE':
            node['falloffFactor'] = bl_node.v3d.falloff_factor
            node['dispersionFactor'] = bl_node.v3d.dispersion_factor

        elif bl_node.type == 'TEX_SKY':
            node['skyType'] = bl_node.sky_type
            node['sunDirection'] = extractVec(bl_node.sun_direction)
            node['turbidity'] = bl_node.turbidity
            node['groundAlbedo'] = bl_node.ground_albedo

        elif bl_node.type == 'TEX_VORONOI':

            if bpy.app.version < (2, 81, 11):

                node['coloring'] = bl_node.coloring
                node['distance'] = bl_node.distance
                node['feature'] = bl_node.feature

            else:
                # only 3D is supported right now
                # node['dimension'] = '3D'
                node['distance'] = bl_node.distance
                node['feature'] = bl_node.feature

        elif bl_node.type == 'TEX_WAVE':
            node['waveType'] = bl_node.wave_type
            node['waveProfile'] = bl_node.wave_profile
            node['bandsDirection'] = ('DIAGONAL' if bpy.app.version < (2, 83, 0)
                    else bl_node.bands_direction)
            node['ringsDirection'] = ('SPHERICAL' if bpy.app.version < (2, 83, 0)
                    else bl_node.rings_direction)

        elif bl_node.type == 'VALTORGB':
            node['curve'] = extractColorRamp(bl_node.color_ramp)

        elif bl_node.type == 'VECT_MATH':
            node['operation'] = bl_node.operation

        elif bl_node.type == 'VECTOR_ROTATE':
            node['rotationType'] = bl_node.rotation_type
            node['invert'] = bl_node.invert

        elif bl_node.type == 'VECT_TRANSFORM':
            # reproducing ShaderNodeVectorTransform
            # https://docs.blender.org/api/current/bpy.types.ShaderNodeVectorTransform.html

            node['vectorType'] = bl_node.vector_type
            node['convertFrom'] = bl_node.convert_from
            node['convertTo'] = bl_node.convert_to

        elif bl_node.type == 'VERTEX_COLOR':
            node['colorLayer'] = bl_node.layer_name

        node['inputs'] = []
        for bl_input in bl_node.inputs:

            # An input of type CUSTOM is usually the last input/output socket
            # in the "Group Input"/"Group Output" nodes, should be safe to omit
            if bl_input.type == 'CUSTOM':
                continue

            defval = getSocketDefvalCompat(bl_input, node['type'] == 'OSL_NODE',
                    node['type'] == 'OSL_NODE')

            node['inputs'].append(defval)

        node['outputs'] = []
        for bl_output in bl_node.outputs:

            # An input of type CUSTOM is usually the last input/output socket
            # in the "Group Input"/"Group Output" nodes, should be safe to omit
            if bl_output.type == 'CUSTOM':
                continue

            defval = getSocketDefvalCompat(bl_output, node['type'] == 'OSL_NODE',
                    node['type'] == 'OSL_NODE')
            node['outputs'].append(defval)

        # "is_active_output" exists on both tree outputs and group outputs
        node["is_active_output"] = (hasattr(bl_node, "is_active_output")
                and bl_node.is_active_output)


    for bl_link in node_tree.links:
        if not bl_link.is_valid:
            printLog('ERROR', 'Invalid edge')
            continue

        # indices
        from_node = bl_nodes.find(bl_link.from_node.name)
        to_node = bl_nodes.find(bl_link.to_node.name)

        if from_node < 0 or to_node < 0:
            printLog('ERROR', 'Invalid edge connection')
            continue

        edge = {
            'fromNode' : from_node,
            'fromOutput' : findNodeSocketNum(bl_nodes[from_node].outputs,
                    bl_link.from_socket.identifier),

            'toNode' : to_node,
            'toInput' : findNodeSocketNum(bl_nodes[to_node].inputs,
                    bl_link.to_socket.identifier)
        }

        edges.append(edge)

    return { 'nodes' : nodes, 'edges' : edges }


def extractCurveMapping(mapping, x_range):
    """Extract curve points data from CurveMapping data"""

    mapping.initialize()

    data = []

    # first pixel = x_range[0], last pixel = x_range[1]
    pix_size = (x_range[1] - x_range[0]) / (CURVE_DATA_SIZE - 1)

    for i in range(CURVE_DATA_SIZE):

        x = x_range[0] + pix_size * i

        for curve_map in mapping.curves:

            if bpy.app.version < (2, 82, 1):
                data.append(curve_map.evaluate(x))
            else:
                data.append(mapping.evaluate(curve_map, x))

    return data

def extractColorRamp(color_ramp):
    """Make a curve from color ramp data"""

    # for uniformity looks like a glTF animation sampler
    curve = {
        'input' : [],
        'output' : [],
        'interpolation' : ('STEP' if color_ramp.interpolation == 'CONSTANT' else 'LINEAR')
    }

    for e in color_ramp.elements:
        curve['input'].append(e.position)

        for i in range(4):
            curve['output'].append(e.color[i])

    return curve

def findNodeSocketNum(socket_list, identifier):
    for i in range(len(socket_list)):
        sock = socket_list[i]
        if sock.identifier == identifier:
            return i
    return -1


def preprocessOSL(code):
    out = io.StringIO()

    p = pcpp.Preprocessor()
    p.line_directive = None
    p.parse(code)
    p.write(out)

    return out.getvalue()

def parseOSLInOuts(ast, shaderName):

    inputs, outputs = ast.get_shader_params()

    def typeToVal(type):
        if type in ['point', 'vector', 'normal', 'color']:
            return [0, 0, 0]
        else:
            return 0

    def typeToGLSLType(type):
        if type in ['point', 'vector', 'normal', 'color']:
            return 'vec3'
        elif type in ['int', 'string']:
            return 'int'
        else:
            return 'float'

    def getInitCode(ast, n):
        if ast is None:
            return None
        return genOSLCode(ast, shaderName + '_init_' + str(n))

    def getInitGlobVars(ast):
        if ast is None:
            return None
        return [varName for _, varName in pyosl.glslgen.find_global_variables(ast)]

    inputs = [(typeToGLSLType(i[0]), i[1], typeToVal(i[0]), getInitCode(i[2], inputs.index(i)), getInitGlobVars(i[2])) for i in inputs]
    outputs = [(typeToGLSLType(o[0]), o[1], typeToVal(o[0])) for o in outputs]

    return inputs, outputs

def genOSLCode(ast, shaderName):
    ast = pyosl.glslgen.osl_to_glsl(ast)
    pyosl.glslgen.rename_shader(ast, shaderName)
    code = pyosl.glslgen.generate(ast)
    return code


def composeNodeGraph(bl_mat, exportSettings, glTF):

    graph = { 'nodes' : [], 'edges' : [] }

    appendNode(graph, {
        'name': 'Output',
        'type': 'OUTPUT_MATERIAL_BL',
        'inputs': [
            [0, 0, 0, 0],
            [0, 0, 0, 0],
            [0, 0, 0]
        ],
        'outputs': [],
        'is_active_output': True
    })

    appendNode(graph, {
        'name': 'Principled',
        'type': 'BSDF_PRINCIPLED_BL',
        'inputs': [
            extractVec(bl_mat.diffuse_color),
            0.0,
            [1.0, 1.0, 1.0],
            [0.0, 0.0, 0.0, 1.0],
            bl_mat.metallic,
            bl_mat.specular_intensity,
            0.0,
            bl_mat.roughness,
            0.0,
            0.0,
            0.0,
            0.5,
            0.0,
            0.03,
            1.45,
            0.0,
            0.0,
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0]
        ],
        'outputs': [[0, 0, 0, 0]]
    }, 0)

    return graph

def appendNode(nodeGraph, node, toNode=-1, connections=[(0, 0)]):

    if node not in nodeGraph['nodes']:
        nodeGraph['nodes'].append(node)

    nodeIndex = nodeGraph['nodes'].index(node)

    if toNode > -1:
        for conn in connections:
            nodeGraph['edges'].append({
                'fromNode' : nodeIndex,
                'fromOutput' : conn[0],
                'toNode' : toNode,
                'toInput' : conn[1]
            })

    return nodeIndex


def getView3DSpaceProp(prop):
    # screen -> area -> space
    #for area in bpy.data.screens[bpy.context.screen.name].areas:
    for area in bpy.context.screen.areas:
        if area.type != 'VIEW_3D':
            continue

        for space in area.spaces:
            if space.type == 'VIEW_3D':
                return getattr(space, prop)

    return None


def extractConstraints(glTF, bl_obj):
    bl_constraints = bl_obj.constraints

    constraints = []

    for bl_cons in bl_constraints:

        if not bl_cons.is_valid:
            continue

        cons = { 'name': bl_cons.name, 'mute': bl_cons.mute }
        target = (gltf.getNodeIndex(glTF, bl_cons.target.name)
                if getattr(bl_cons, 'target', None) is not None else -1)

        if bl_cons.type == 'COPY_LOCATION':
            if target >= 0:
                constraints.append(dict(cons, **{ 'type': 'copyLocation', 'target': target }))

        elif bl_cons.type == 'COPY_ROTATION':
            if target >= 0:
                constraints.append(dict(cons, **{ 'type': 'copyRotation', 'target': target }))

        elif bl_cons.type == 'COPY_SCALE':
            if target >= 0:
                constraints.append(dict(cons, **{ 'type': 'copyScale', 'target': target }))

        elif bl_cons.type == 'COPY_TRANSFORMS':
            if target >= 0:
                constraints.append(dict(cons, **{ 'type': 'copyLocation', 'target': target }))
                constraints.append(dict(cons, **{ 'type': 'copyRotation', 'target': target }))
                constraints.append(dict(cons, **{ 'type': 'copyScale', 'target': target }))

        elif bl_cons.type == 'LIMIT_LOCATION':
            constraints.append(dict(cons, **{ 'type': 'limitLocation',
                'minX': bl_cons.min_x if bl_cons.use_min_x else '-Infinity',
                'maxX': bl_cons.max_x if bl_cons.use_max_x else 'Infinity',
                'minY': bl_cons.min_z if bl_cons.use_min_z else '-Infinity',
                'maxY': bl_cons.max_z if bl_cons.use_max_z else 'Infinity',
                'minZ': -bl_cons.max_y if bl_cons.use_max_y else '-Infinity',
                'maxZ': -bl_cons.min_y if bl_cons.use_min_y else 'Infinity',
            }))

        elif bl_cons.type == 'LIMIT_ROTATION':
            if bl_cons.use_limit_x:
                constraints.append(dict(cons, **{ 'type': 'limitRotation',
                        'axis': 'X', 'min': bl_cons.min_x, 'max': bl_cons.max_x }))
            if bl_cons.use_limit_y:
                constraints.append(dict(cons, **{ 'type': 'limitRotation',
                        'axis': 'Z', 'min': -bl_cons.max_y, 'max': -bl_cons.min_y }))
            if bl_cons.use_limit_z:
                constraints.append(dict(cons, **{ 'type': 'limitRotation',
                        'axis': 'Y', 'min': bl_cons.min_z, 'max': bl_cons.max_z }))


        elif bl_cons.type == 'LIMIT_SCALE':
            constraints.append(dict(cons, **{ 'type': 'limitScale',
                'minX': max(bl_cons.min_x, 0) if bl_cons.use_min_x else 0,
                'maxX': max(bl_cons.max_x, 0) if bl_cons.use_max_x else 'Infinity',
                'minY': max(bl_cons.min_z, 0) if bl_cons.use_min_z else 0,
                'maxY': max(bl_cons.max_z, 0) if bl_cons.use_max_z else 'Infinity',
                'minZ': max(bl_cons.min_y, 0) if bl_cons.use_min_y else 0,
                'maxZ': max(bl_cons.max_y, 0) if bl_cons.use_max_y else 'Infinity',
            }))

        elif bl_cons.type == 'LOCKED_TRACK':
            if target >= 0:
                constraints.append(dict(cons, **{
                    'type': 'lockedTrack',
                    'target': target,
                    'trackAxis': extractAxisParam(bl_cons.track_axis, 'TRACK_', True),
                    'lockAxis': extractAxisParam(bl_cons.lock_axis, 'LOCK_', False),
                }))

        elif bl_cons.type == 'TRACK_TO':
            if target >= 0:
                constraints.append(dict(cons, **{
                    'type': 'trackTo',
                    'target': target,
                    'trackAxis': extractAxisParam(bl_cons.track_axis, 'TRACK_', True),
                    'upAxis': extractAxisParam(bl_cons.up_axis, 'UP_', True),
                }))

        elif bl_cons.type == 'CHILD_OF':
            if target >= 0:
                constraints.append(dict(cons, **{
                    'type': 'childOf',
                    'target': target,
                    'offsetMatrix': extractMat(convertSwizzleMatrix(
                            bl_cons.inverse_matrix @ bl_obj.matrix_basis))
                }))

        elif bl_cons.type == 'FLOOR':
            if target >= 0:
                floorLocation = extractAxisParam(bl_cons.floor_location, 'FLOOR_', True)
                constraints.append(dict(cons, **{
                    'type': 'floor',
                    'target': target,
                    'offset': -bl_cons.offset if floorLocation in ['Z', '-Z'] else bl_cons.offset,
                    'floorLocation': floorLocation
                }))

    return constraints

def extractAxisParam(param, prefix, use_negative):
    param = param.replace(prefix, '')

    if 'NEGATIVE_' in param:
        param = param.replace('NEGATIVE_', '')
        param = '-' + param

    # param = param.lower()

    if param == 'X':
        return 'X'
    elif param == 'Y':
        return '-Z' if use_negative else 'Z'
    elif param == 'Z':
        return 'Y'
    elif param == '-X':
        return '-X'
    elif param == '-Y':
        return 'Z'
    elif param == '-Z':
        return '-Y'
    else:
        printLog('ERROR', 'Incorrect axis param: ' + param)
        return ''

def extractImageBindata(bl_image, scene):

    if bl_image.file_format == 'JPEG':
        return extractImageBindataJPEG(bl_image, scene)
    elif bl_image.file_format == 'BMP':
        return extractImageBindataBMP(bl_image, scene)
    elif bl_image.file_format == 'HDR':
        return extractImageBindataHDR(bl_image, scene)
    else:
        return extractImageBindataPNG(bl_image, scene)

def extractImageBindataPNG(bl_image, scene):

    if not bl_image.is_dirty:
        # it's much faster to access packed file data if no conversion is needed
        if bl_image.packed_file is not None and bl_image.file_format == 'PNG':
            return bl_image.packed_file.data

    tmp_img = tempfile.NamedTemporaryFile(delete=False)

    img_set = scene.render.image_settings

    file_format = img_set.file_format
    color_mode = img_set.color_mode
    color_depth = img_set.color_depth
    compression = img_set.compression

    img_set.file_format = 'PNG'
    img_set.color_mode = 'RGBA'
    img_set.color_depth = '16'
    img_set.compression = 90

    bl_image.save_render(tmp_img.name, scene=scene)

    img_set.file_format = file_format
    img_set.color_mode = color_mode
    img_set.color_depth = color_depth
    img_set.compression = compression

    bindata = tmp_img.read()

    tmp_img.close()
    os.unlink(tmp_img.name)

    return bindata

def extractImageBindataJPEG(bl_image, scene):

    if not bl_image.is_dirty:
        # it's much faster to access packed file data if no conversion is needed
        if bl_image.packed_file is not None and bl_image.file_format == 'JPEG':
            return bl_image.packed_file.data

    tmp_img = tempfile.NamedTemporaryFile(delete=False)

    img_set = scene.render.image_settings

    file_format = img_set.file_format
    color_mode = img_set.color_mode
    quality = img_set.quality

    img_set.file_format = 'JPEG'
    img_set.color_mode = 'RGB'
    img_set.quality = 90

    bl_image.save_render(tmp_img.name, scene=scene)

    img_set.file_format = file_format
    img_set.color_mode = color_mode
    img_set.quality = quality

    bindata = tmp_img.read()
    tmp_img.close()
    os.unlink(tmp_img.name)

    return bindata

def extractImageBindataBMP(bl_image, scene):

    if not bl_image.is_dirty:
        # it's much faster to access packed file data if no conversion is needed
        if bl_image.packed_file is not None and bl_image.file_format == 'BMP':
            return bl_image.packed_file.data

    tmp_img = tempfile.NamedTemporaryFile(delete=False)

    img_set = scene.render.image_settings

    file_format = img_set.file_format
    color_mode = img_set.color_mode

    img_set.file_format = 'BMP'
    img_set.color_mode = 'RGB'

    bl_image.save_render(tmp_img.name, scene=scene)

    img_set.file_format = file_format
    img_set.color_mode = color_mode

    bindata = tmp_img.read()
    tmp_img.close()
    os.unlink(tmp_img.name)

    return bindata

def extractImageBindataHDR(bl_image, scene):

    if not bl_image.is_dirty:
        # it's much faster to access packed file data if no conversion is needed
        if bl_image.packed_file is not None and bl_image.file_format == 'HDR':
            return bl_image.packed_file.data

    tmp_img = tempfile.NamedTemporaryFile(delete=False)

    img_set = scene.render.image_settings

    file_format = img_set.file_format
    color_mode = img_set.color_mode

    img_set.file_format = 'HDR'
    img_set.color_mode = 'RGB'

    bl_image.save_render(tmp_img.name, scene=scene)

    img_set.file_format = file_format
    img_set.color_mode = color_mode

    bindata = tmp_img.read()
    tmp_img.close()
    os.unlink(tmp_img.name)

    return bindata

def extractColorSpace(bl_tex):
    if (isinstance(bl_tex, (bpy.types.ShaderNodeTexImage,
            bpy.types.ShaderNodeTexEnvironment))):

        colorSpace = getTexImage(bl_tex).colorspace_settings.name.lower()
    else:
        # possible c/s values:
        # 'Filmic Log', 'Linear', 'Linear ACES', 'Non-Color', 'Raw', 'sRGB', 'VD16', 'XYZ'
        colorSpace = getTexImage(bl_tex.texture).colorspace_settings.name.lower()

    return colorSpace

def getPtr(blEntity):
    return blEntity.as_pointer()
