# Copyright (c) 2017 The Khronos Group Inc.
# Copyright (c) 2017-2024 Soft8Soft
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
import math, io, lzma, os, re, tempfile

import pluginUtils
import pluginUtils as pu
import pluginUtils.gltf as gltf

log = pluginUtils.log.getLogger('V3D-BL')

from .gltf2_get import *
from .utils import *

import pcpp, pyosl.oslparse, pyosl.glslgen
import numpy as np
from profilehooks import profile
GLTF_MAX_COLORS = 8
CURVE_DATA_SIZE = 256


def npConvertSwizzleLocation(array):
    # x,y,z -> x,z,-y
    array[:, [1,2]] = array[:, [2,1]]  # x,z,y
    array[:, 2] *= -1  # x,z,-y

def npSRGBToLinear(colors):
    colors_noa = colors[..., 0:3] # only process RGB for speed

    x = colors_noa
    x[x <= 0.0] = 0.0
    x[x >= 1] = 1.0
    x[x < 0.04045] /= 12.92
    mask = (x >= 0.04045) & (x < 1)
    x[mask] = ((x[mask] + 0.055) / 1.055) ** 2.4
    colors_noa = x

    result = np.concatenate((colors_noa, colors[..., 3, np.newaxis]), axis=-1)
    return result

def npNormalizeVecs(vectors):
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    np.divide(vectors, norms, out=vectors, where=norms != 0)

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

    attributes = {}

    if use_tangents:
        attributes['TANGENT'] = []

    result_primitive = {
        'material' : a['material'],
        'useNodeAttrs' : a['useNodeAttrs'],
        # 'indices' : [],
        'attributes' : attributes
    }

    source_attributes = a['attributes']


    texcoord_index = 0
    process_texcoord = True
    while process_texcoord:
        texcoord_id = 'TEXCOORD_' + str(texcoord_index)
        if source_attributes.get(texcoord_id) is not None:
            texcoord_index += 1
        else:
            process_texcoord = False

    texcoord_max = texcoord_index


    color_index = 0
    process_color = True
    while process_color:
        color_id = 'COLOR_' + str(color_index)
        if source_attributes.get(color_id) is not None:
            color_index += 1
        else:
            process_color = False

    color_max = color_index


    skinAttrIndex = 0
    process_bone = True
    while process_bone:
        joint_id = 'JOINTS_' + str(skinAttrIndex)
        if source_attributes.get(joint_id) is not None:
            skinAttrIndex += 1
        else:
            process_bone = False

    skinAttrIndexMax = skinAttrIndex


    morph_index = 0
    process_morph = True
    while process_morph:
        morph_position_id = 'MORPH_POSITION_' + str(morph_index)
        if source_attributes.get(morph_position_id) is not None:
            morph_index += 1
        else:
            process_morph = False

    morph_max = morph_index

    min_index = indices.min()
    max_index = indices.max() + 1

    result_primitive['indices'] = indices - min_index
    attributes['POSITION'] = source_attributes['POSITION'][min_index * 3 : max_index * 3]
    attributes['NORMAL'] = source_attributes['NORMAL'][min_index * 3 : max_index * 3]

    if use_tangents:
        attributes['TANGENT'] = source_attributes['TANGENT'][min_index * 4 : max_index * 4]

    for texcoord_index in range(0, texcoord_max):
        texcoord_id = 'TEXCOORD_' + str(texcoord_index)
        attributes[texcoord_id] = source_attributes[texcoord_id][min_index * 2 : max_index * 2]

    for color_index in range(0, color_max):
        color_id = 'COLOR_' + str(color_index)
        attributes[color_id] = source_attributes[color_id][min_index * 4 : max_index * 4]

    for skinAttrIndex in range(0, skinAttrIndexMax):
        joint_id = 'JOINTS_' + str(skinAttrIndex)
        weight_id = 'WEIGHTS_' + str(skinAttrIndex)
        attributes[joint_id] = source_attributes[joint_id][min_index * 4 : max_index * 4]
        attributes[weight_id] = source_attributes[weight_id][min_index * 4 : max_index * 4]

    for morph_index in range(0, morph_max):
        morph_position_id = 'MORPH_POSITION_' + str(morph_index)
        morph_normal_id = 'MORPH_NORMAL_' + str(morph_index)
        morph_tangent_id = 'MORPH_TANGENT_' + str(morph_index)
        attributes[morph_position_id] = source_attributes[morph_position_id][min_index * 3 : max_index * 3]
        attributes[morph_normal_id] = source_attributes[morph_normal_id][min_index * 3 : max_index * 3]
        if use_tangents:
            attributes[morph_tangent_id] = source_attributes[morph_tangent_id][min_index * 4 : max_index * 4]

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
            texcoord_index += 1
        else:
            process_texcoord = False

    texcoord_max = texcoord_index

    color_index = 0
    process_color = True
    while process_color:
        color_id = 'COLOR_' + str(color_index)
        if source_attributes.get(color_id) is not None:
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
            morph_index += 1
        else:
            process_morph = False

    morph_max = morph_index


    unqie, init_indxs = np.unique(indices, return_index=True)
    indx_fields = [('old_index', np.uint32), ('old_index_index', np.uint32)]
    unique_indices = np.empty(len(init_indxs), dtype=np.dtype(indx_fields))
    unique_indices['old_index'] = unique
    unique_indices['old_index_index'] = init_indxs
    unique_indices.sort('old_index_index')
    del unique
    del init_indxs

    # index_in_new_indices = np.searchsorted(unique, unique_indices['old_index'])
    new_indices = np.searchsorted(unique_indices['old_index'], indices)
    result_primitive['indices'] = new_indices

    old_unique_indices = unique_indices['old_index'][new_indices]

    attributes['POSITION'] = source_attributes['POSITION'].reshape(-1, 3)[old_unique_indices].reshape(-1)
    attributes['NORMAL'] = source_attributes['NORMAL'].reshape(-1, 3)[old_unique_indices].reshape(-1)

    if use_tangents:
        attributes['TANGENT'] = source_attributes['TANGENT'].reshape(-1, 4)[old_unique_indices].reshape(-1)

    for texcoord_index in range(0, texcoord_max):
        texcoord_id = 'TEXCOORD_' + str(texcoord_index)
        attributes[texcoord_id] = source_attributes[texcoord_id].reshape(-1, 2)[old_unique_indices].reshape(-1)

    for color_index in range(0, color_max):
        color_id = 'COLOR_' + str(color_index)
        attributes[color_id] = source_attributes[color_id].reshape(-1, 4)[old_unique_indices].reshape(-1)

    for skinAttrIndex in range(0, skinAttrIndexMax):
        joint_id = 'JOINTS_' + str(skinAttrIndex)
        weight_id = 'WEIGHTS_' + str(skinAttrIndex)

        attributes[joint_id] = source_attributes[joint_id].reshape(-1, 4)[old_unique_indices].reshape(-1)
        attributes[weight_id] = source_attributes[weight_id].reshape(-1, 4)[old_unique_indices].reshape(-1)

    for morph_index in range(0, morph_max):
        morph_position_id = 'MORPH_POSITION_' + str(morph_index)
        morph_normal_id = 'MORPH_NORMAL_' + str(morph_index)
        morph_tangent_id = 'MORPH_TANGENT_' + str(morph_index)
        attributes[morph_position_id] = source_attributes[morph_position_id].reshape(-1, 3)[old_unique_indices].reshape(-1)
        attributes[morph_normal_id] = source_attributes[morph_normal_id].reshape(-1, 3)[old_unique_indices].reshape(-1)
        if use_tangents:
            attributes[morph_tangent_id] = source_attributes[morph_tangent_id].reshape(-1, 4)[old_unique_indices].reshape(-1)

    return result_primitive


def checkUseNodeAttrs(bl_mat):
    mat_type = getMaterialType(bl_mat)

    if mat_type == 'EEVEE':
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

    log.info('Extracting {} primitives'.format(bl_mesh.name))

    use_normals = True

    # COMPAT: < Blender 4.1
    if bpy.app.version < (4, 1, 0) and (bl_mesh.has_custom_normals or bl_mesh.use_auto_smooth or use_normals):
        bl_mesh.calc_normals_split()

    use_tangents = False
    if meshNeedTangentsForExport(bl_mesh, exportSettings['optimize_attrs']):
        try:
            bl_mesh.calc_tangents(uvmap=meshPreferredTangentsUvMap(bl_mesh))
            use_tangents = True
        except:
            log.warning('Could not calculate tangents. Please try to triangulate the mesh first.')

    texcoord_max = 0
    if bl_mesh.uv_layers.active:
        texcoord_max = len(bl_mesh.uv_layers)


    morph_max = 0
    use_morph_normals = exportSettings['morph'] and use_normals
    use_morph_tangents = exportSettings['morph'] and use_tangents
    bl_shape_keys = []

    # Shape Keys can't be retrieve when using Apply Modifiers (Blender/bpy limitation)
    if bl_mesh.shape_keys:
        bl_shape_keys = [
            key_block
            for key_block in bl_mesh.shape_keys.key_blocks
            if not (key_block == key_block.relative_key or key_block.mute or key_block == bl_mesh.shape_keys.reference_key)
        ]

    vertex_colors = {}
    # COMPAT: < Blender 3.2
    bl_vertex_colors = bl_mesh.color_attributes if bpy.app.version >= (3, 2, 0) else bl_mesh.vertex_colors

    color_max = 0
    color_index = 0
    for vertex_color in bl_vertex_colors:
        vertex_color_name = 'COLOR_' + str(color_index)
        vertex_colors[vertex_color_name] = vertex_color

        color_index += 1
        if color_index >= GLTF_MAX_COLORS:
            break
    color_max = color_index


    need_skin_attributes = exportSettings['skins'] and len(bl_joint_indices) > 0
    skinAttrIndexMax = 0
    if need_skin_attributes:
        for vertex in bl_mesh.vertices:
            # any vertex should be skinned to at least one bone - to the
            # armature itself if no groups are specified
            bones_count = max(len(vertex.groups), 1)
            if bones_count % 4 == 0:
                bones_count -= 1
            skinAttrIndexMax = max(skinAttrIndexMax, bones_count // 4 + 1)

    # Gathering position, normal and texcoords.

    # Fetch vert positions and bone data (joint,weights)

    # POSITIONS
    locs = np.empty(len(bl_mesh.vertices) * 3, dtype=np.float32)
    bl_mesh.vertices.foreach_get('co', locs)
    locs = locs.reshape(len(bl_mesh.vertices), 3)

    morph_locs = []
    for key_block in bl_shape_keys:
        vs = np.empty(len(bl_mesh.vertices) * 3, dtype=np.float32)
        key_block.data.foreach_get('co', vs)
        vs = vs.reshape(len(bl_mesh.vertices), 3)
        morph_locs.append(vs)

    # glTF stores deltas in morph targets
    for vs in morph_locs:
        vs -= locs

    npConvertSwizzleLocation(locs)
    for vs in morph_locs:
        npConvertSwizzleLocation(vs)


    # In Blender there is both per-vert data, like position, and also per-loop
    # (loop=corner-of-poly) data, like normals or UVs. glTF only has per-vert
    # data, so we need to split Blender verts up into potentially-multiple glTF
    # verts.
    #
    # First, we'll collect a "dot" for every loop: a struct that stores all the
    # attributes at that loop, namely the vertex index (which determines all
    # per-vert data), and all the per-loop data like UVs, etc.
    #
    # Each unique dot will become one unique glTF vert.

    # List all fields the dot struct needs.
    dot_fields = [('vertex_index', np.uint32)]
    if use_normals:
        dot_fields += [('nx', np.float32), ('ny', np.float32), ('nz', np.float32)]
    if use_tangents:
        dot_fields += [('tx', np.float32), ('ty', np.float32), ('tz', np.float32), ('tw', np.float32)]
    for uv_i in range(texcoord_max):
        dot_fields += [('uv%dx' % uv_i, np.float32), ('uv%dy' % uv_i, np.float32)]
    for col_i in range(color_max):
        dot_fields += [
            ('color%dr' % col_i, np.float32),
            ('color%dg' % col_i, np.float32),
            ('color%db' % col_i, np.float32),
            ('color%da' % col_i, np.float32),
        ]
    if use_morph_normals:
        for morph_i, _ in enumerate(bl_shape_keys):
            dot_fields += [
                ('morph%dnx' % morph_i, np.float32),
                ('morph%dny' % morph_i, np.float32),
                ('morph%dnz' % morph_i, np.float32),
            ]

    dots = np.empty(len(bl_mesh.loops), dtype=np.dtype(dot_fields))

    vidxs = np.empty(len(bl_mesh.loops))
    bl_mesh.loops.foreach_get('vertex_index', vidxs)
    dots['vertex_index'] = vidxs
    del vidxs

    if use_normals:
        if bl_shape_keys and False:
            normals = bl_shape_keys[0].relative_key.normals_split_get()
            normals = np.array(normals, dtype=np.float32)
        else:
            normals = np.empty(len(bl_mesh.loops) * 3, dtype=np.float32)

            bl_mesh.loops.foreach_get('normal', normals)

        normals = normals.reshape(len(bl_mesh.loops), 3)
        normals = np.round(normals, 6) # Round normals to avoid vertex split

        morph_normals = []
        for key_block in bl_shape_keys:
            ns = np.array(key_block.normals_split_get(), dtype=np.float32)
            ns = ns.reshape(len(bl_mesh.loops), 3)
            ns = np.round(ns, 6)
            npNormalizeVecs(ns)
            morph_normals.append(ns)

        # Force normalization of normals in case some normals are not (why ?)
        npNormalizeVecs(normals)

        for ns in [normals, *morph_normals]:
            # Replace zero normals with the unit UP vector.
            # Seems to happen sometimes with degenerate tris?
            is_zero = ~ns.any(axis=1)
            ns[is_zero, 2] = 1

        # glTF stores deltas in morph targets
        for ns in morph_normals:
            ns -= normals

        # npNormalizeVecs(normals)
        npConvertSwizzleLocation(normals)
        for ns in morph_normals:
            npConvertSwizzleLocation(ns)

        dots['nx'] = normals[:, 0]
        dots['ny'] = normals[:, 1]
        dots['nz'] = normals[:, 2]
        del normals

        for morph_i, ns in enumerate(morph_normals):
            dots['morph%dnx' % morph_i] = ns[:, 0]
            dots['morph%dny' % morph_i] = ns[:, 1]
            dots['morph%dnz' % morph_i] = ns[:, 2]
        del morph_normals


    if use_tangents:
        tangents = np.empty(len(bl_mesh.loops) * 3, dtype=np.float32)
        bl_mesh.loops.foreach_get('tangent', tangents)
        tangents = tangents.reshape(len(bl_mesh.loops), 3)
        npNormalizeVecs(tangents)
        npConvertSwizzleLocation(tangents)

        dots['tx'] = tangents[:, 0]
        dots['ty'] = tangents[:, 1]
        dots['tz'] = tangents[:, 2]
        del tangents

        signs = np.empty(len(bl_mesh.loops), dtype=np.float32)
        bl_mesh.loops.foreach_get('bitangent_sign', signs)
        dots['tw'] = signs
        del signs


    for uv_i in range(texcoord_max):
        layer = bl_mesh.uv_layers[uv_i]
        uvs = np.empty(len(bl_mesh.loops) * 2, dtype=np.float32)
        layer.data.foreach_get('uv', uvs)
        uvs = uvs.reshape(len(bl_mesh.loops), 2)
        # Blender UV space -> glTF UV space
        # u,v -> u,1-v
        uvs[:, 1] *= -1
        uvs[:, 1] += 1

        dots['uv%dx' % uv_i] = uvs[:, 0]
        dots['uv%dy' % uv_i] = uvs[:, 1]
        del uvs

    for col_i in range(color_max):
        color_name = 'COLOR_' + str(col_i)
        if bpy.app.version >= (3, 2, 0):
            if bl_mesh.color_attributes[col_i].domain == "POINT":
                colors = np.empty(len(bl_mesh.vertices) * 4, dtype=np.float32)
            else:
                colors = np.empty(len(bl_mesh.loops) * 4, dtype=np.float32)
        else:
            colors = np.empty(len(bl_mesh.loops) * 4, dtype=np.float32)

        vertex_colors[color_name].data.foreach_get('color', colors)
        colors = colors.reshape(-1, 4)

        if bpy.app.version < (3, 2, 0):
            colors = npSRGBToLinear(colors)
        elif vertex_colors[color_name].domain == "POINT":
            colors = colors[dots['vertex_index']]

        dots['color%dr' % col_i] = colors[:, 0]
        dots['color%dg' % col_i] = colors[:, 1]
        dots['color%db' % col_i] = colors[:, 2]
        dots['color%da' % col_i] = colors[:, 3]
        del colors

    if need_skin_attributes:
        need_neutral_bone = False
        min_influence = 0.0001
        joint_name_to_index = bl_joint_indices
        group_to_joint = [joint_name_to_index.get(g.name) for g in bl_vertex_groups]

        # List of (joint, weight) pairs for each vert
        vert_bones = []
        max_num_influences = 0

        for vertex in bl_mesh.vertices:
            bones = []
            if vertex.groups:
                for group_element in vertex.groups:
                    weight = group_element.weight
                    if weight <= min_influence:
                        continue
                    try:
                        joint = group_to_joint[group_element.group]
                    except Exception:
                        continue
                    if joint is None:
                        continue
                    bones.append((joint, weight))
            bones.sort(key=lambda x: x[1], reverse=True)
            if not bones:
                # Is not assign to any bone
                bones = ((len(bl_joint_indices), 1.0),)  # Assign to a joint that will be created later
                need_neutral_bone = True
            vert_bones.append(bones)
            if len(bones) > max_num_influences:
                max_num_influences = len(bones)

        # How many joint sets do we need? 1 set = 4 influences
        num_joint_sets = (max_num_influences + 3) // 4

    # Calculate triangles and sort them into primitives.

    bl_mesh.calc_loop_triangles()
    loop_indices = np.empty(len(bl_mesh.loop_triangles) * 3, dtype=np.uint32)
    bl_mesh.loop_triangles.foreach_get('loops', loop_indices)

    prim_indices = {}  # maps material index to TRIANGLES-style indices into dots

    tri_material_idxs = np.empty(len(bl_mesh.loop_triangles), dtype=np.uint32)
    bl_mesh.loop_triangles.foreach_get('material_index', tri_material_idxs)
    loop_material_idxs = np.repeat(tri_material_idxs, 3)  # material index for every loop
    unique_material_idxs = np.unique(tri_material_idxs)
    del tri_material_idxs

    for material_idx in unique_material_idxs:
        prim_indices[material_idx] = loop_indices[loop_material_idxs == material_idx]

    # Create all the primitives.
    primitives = []

    for material_idx, dot_indices in prim_indices.items():
        # Extract just dots used by this primitive, deduplicate them, and
        # calculate indices into this deduplicated list.
        prim_dots = dots[dot_indices]
        prim_dots, indices = np.unique(prim_dots, return_inverse=True)

        if len(prim_dots) == 0:
            continue


        attributes = {}
        primitive = {
            'attributes': attributes,
            'indices': indices,
            'max_index': indices.max(),
            'useNodeAttrs': False,
            'material': DEFAULT_MAT_NAME
        }
        if (material_idx is not None
                and len(bl_mesh.materials) > material_idx
                and bl_mesh.materials[material_idx] is not None):

            primitive['useNodeAttrs'] = checkUseNodeAttrs(bl_mesh.materials[material_idx])
            primitive['material'] = bl_mesh.materials[material_idx].name


        export_color = primitive['material'] not in exportSettings['use_no_color']

        # Now just move all the data for prim_dots into attribute arrays

        blender_idxs = prim_dots['vertex_index']
        attributes['POSITION'] = locs[blender_idxs].reshape(-1)

        for morph_i, vs in enumerate(morph_locs):
            attributes['MORPH_POSITION_%d' % morph_i] = vs[blender_idxs].reshape(-1)

        if use_normals:
            normals = np.empty((len(prim_dots), 3), dtype=np.float32)
            normals[:, 0] = prim_dots['nx']
            normals[:, 1] = prim_dots['ny']
            normals[:, 2] = prim_dots['nz']
            attributes['NORMAL'] = normals.reshape(-1)

        if use_tangents:
            tangents = np.empty((len(prim_dots), 4), dtype=np.float32)
            tangents[:, 0] = prim_dots['tx']
            tangents[:, 1] = prim_dots['ty']
            tangents[:, 2] = prim_dots['tz']
            tangents[:, 3] = prim_dots['tw']
            attributes['TANGENT'] = tangents.reshape(-1)

        if use_morph_normals:
            for morph_i, _ in enumerate(bl_shape_keys):
                ns = np.empty((len(prim_dots), 3), dtype=np.float32)
                ns[:, 0] = prim_dots['morph%dnx' % morph_i]
                ns[:, 1] = prim_dots['morph%dny' % morph_i]
                ns[:, 2] = prim_dots['morph%dnz' % morph_i]
                attributes['MORPH_NORMAL_%d' % morph_i] = ns.reshape(-1)

                if use_morph_tangents:
                    morph_normal_deltas = ns
                    morph_tangent_deltas = np.empty((len(normals), 3), dtype=np.float32)
                    for i in range(len(normals)):
                        n = mathutils.Vector(normals[i])
                        morph_n = n + mathutils.Vector(morph_normal_deltas[i])  # convert back to non-delta
                        t = mathutils.Vector(tangents[i, :3])
                        rotation = morph_n.rotation_difference(n)
                        t_morph = mathutils.Vector(t)
                        t_morph.rotate(rotation)
                        morph_tangent_deltas[i] = t_morph - t  # back to delta

                    attributes['MORPH_TANGENT_%d' % morph_i] = morph_tangent_deltas.reshape(-1)

        for tex_coord_i in range(texcoord_max):
            uvs = np.empty((len(prim_dots), 2), dtype=np.float32)
            uvs[:, 0] = prim_dots['uv%dx' % tex_coord_i]
            uvs[:, 1] = prim_dots['uv%dy' % tex_coord_i]
            attributes['TEXCOORD_%d' % tex_coord_i] = uvs.reshape(-1)

        if export_color:
            for color_i in range(color_max):
                colors = np.empty((len(prim_dots), 4), dtype=np.float32)
                colors[:, 0] = prim_dots['color%dr' % color_i]
                colors[:, 1] = prim_dots['color%dg' % color_i]
                colors[:, 2] = prim_dots['color%db' % color_i]
                colors[:, 3] = prim_dots['color%da' % color_i]
                attributes['COLOR_%d' % color_i] = colors.reshape(-1)

        if need_skin_attributes:
            joints = [[] for _ in range(num_joint_sets)]
            weights = [[] for _ in range(num_joint_sets)]

            for vi in blender_idxs:
                bones = vert_bones[vi]
                for j in range(0, 4 * num_joint_sets):
                    if j < len(bones):
                        joint, weight = bones[j]
                    else:
                        joint, weight = 0, 0.0
                    joints[j//4].append(joint)
                    weights[j//4].append(weight)

            for i, (js, ws) in enumerate(zip(joints, weights)):
                attributes['JOINTS_%d' % i] = js
                attributes['WEIGHTS_%d' % i] = ws

        primitives.append(primitive)

    result_primitives = []

    for primitive in primitives:
        indices = primitive['indices']

        if len(indices) == 0:
            continue

        count = len(indices)
        if count == 0:
            continue

        max_index = primitive['max_index']

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
            pending_primitive = {
                'material' : primitive['material'],
                'useNodeAttrs' : primitive['useNodeAttrs'],
                'indices' : primitive['indices'],
                'attributes' : primitive['attributes']
            }

            pending_indices = pending_primitive['indices']

            # Continue until all are processed.
            while len(pending_indices) > 0:

                process_indices = pending_primitive['indices']
                rnum = (np.max(process_indices) // range_indices) + 1
                all_local_indices = []

                process_indices = process_indices.reshape(-1, 3)
                face_min_indices = np.amin(process_indices, axis=1)
                face_max_indices = np.amax(process_indices, axis=1)

                written_mask = np.zeros(len(process_indices), dtype=bool)

                # For all faces ...
                for i in range(0, rnum):
                    offset = i * range_indices

                    # ... check if it can be but in a range of maximum indices.
                    # Yes, so store the primitive with its indices.
                    mask = (face_min_indices >= offset) & (face_max_indices < (offset + range_indices))
                    all_local_indices.append(process_indices[mask])

                    written_mask |= mask

                # If not written, the triangel face has indices from different ranges.
                pending_indices = process_indices[~written_mask]
                pending_indices = pending_indices.reshape(-1)


                # Only add result_primitives, which do have indices in it.
                for local_indices in all_local_indices:
                    if len(local_indices) > 0:
                        current_primitive = extractPrimitiveFloor(pending_primitive, local_indices, use_tangents)

                        result_primitives.append(current_primitive)

                        log.debug('Adding primitive with splitting. Indices: ' + str(len(current_primitive['indices'])) + ' Vertices: ' + str(len(current_primitive['attributes']['POSITION']) // 3))

                # Process primitive faces having indices in several ranges.
                if len(pending_indices) > 0:
                    pending_primitive = extractPrimitivePack(pending_primitive, pending_indices, use_tangents)

                    pending_attributes = pending_primitive['attributes']

                    log.debug('Creating temporary primitive for splitting')

        else:
            # No splitting needed.
            result_primitives.append(primitive)

            log.debug('Adding primitive without splitting. Indices: ' + str(len(primitive['indices'])) + ' Vertices: ' + str(len(primitive['attributes']['POSITION']) // 3))

    log.debug('Primitives created: ' + str(len(result_primitives)))
    return result_primitives


def extractLinePrimitives(glTF, bl_mesh, exportSettings):
    """
    Extracting line primitives from a mesh.
    Furthermore, primitives are splitted up, if the indices range is exceeded.
    """

    log.debug('Extracting line primitive')

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

        elif bl_node.type == 'BSDF_METALLIC':
            node['distribution'] = bl_node.distribution
            node['fresnelType'] = bl_node.fresnel_type

        elif bl_node.type == 'BSDF_REFRACTION':
            node['distribution'] = bl_node.distribution

        elif bl_node.type == 'BUMP':
            node['invert'] = bl_node.invert
        elif bl_node.type == 'CLAMP':
            node['clampType'] = bl_node.clamp_type
        elif bl_node.type == 'COMBINE_COLOR':
            node['mode'] = bl_node.mode
        elif bl_node.type == 'CURVE_FLOAT':
            node['curveData'] = extractCurveMapping(bl_node.mapping, (-1,1))
        elif bl_node.type == 'CURVE_RGB':
            node['curveData'] = extractCurveMapping(bl_node.mapping, (0,1))
        elif bl_node.type == 'CURVE_VEC':
            node['curveData'] = extractCurveMapping(bl_node.mapping, (-1,1))

        elif bl_node.type == 'GROUP':
            node['nodeGraph'] = getNodeGraphIndex(glTF,
                    bl_node.node_tree.name)

        elif bl_node.type == 'MAPPING':
            node['vectorType'] = bl_node.vector_type

        elif bl_node.type == 'MAP_RANGE':
            # COMPAT: appeared in Blender version > 3.0.0
            if hasattr(bl_node, "data_type"):
                node['dataType'] = bl_node.data_type

            node['clamp'] = bl_node.clamp
            node['interpolationType'] = bl_node.interpolation_type

        elif bl_node.type == 'MATH':
            node['operation'] = bl_node.operation
            node['useClamp'] = bl_node.use_clamp

        elif bl_node.type == 'MIX':
            node['dataType'] = bl_node.data_type
            node['clampFactor'] = bl_node.clamp_factor

            # Color
            node['blendType'] = bl_node.blend_type
            node['clampResult'] = bl_node.clamp_result

            # Vector
            node['factorMode'] = bl_node.factor_mode

        # COMPAT: <Blender 3.5
        elif bl_node.type == 'MIX_RGB':
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

        elif bl_node.type == 'SEPARATE_COLOR':
            node['mode'] = bl_node.mode

        elif bl_node.type == 'TEX_BRICK':
            node['offset'] = bl_node.offset
            node['offsetFrequency'] = bl_node.offset_frequency
            node['squash'] = bl_node.squash
            node['squashFrequency'] = bl_node.squash_frequency

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

        elif bl_node.type == 'TEX_GABOR':
            node['gaborType'] = bl_node.gabor_type

        elif bl_node.type == 'TEX_IMAGE':
            index = gltf.getTextureIndex(glTF, getTextureName(bl_node)) if getTexImage(bl_node) else -1

            if index == -1:
                node['type'] = 'TEX_IMAGE_NONE_BL'
            else:
                node['texture'] = index

                alphaMode = getTexImage(bl_node).alpha_mode

                # set Channel Packed for disabled alpha mode
                if extractColorSpace(bl_node) in ['non-color', 'raw']:
                    alphaMode = 'CHANNEL_PACKED'

                node['alphaMode'] = alphaMode

            node['projection'] = bl_node.projection
            node['projectionBlend'] = bl_node.projection_blend

            if bl_node.extension == 'CLIP':
                node['clampToEdgeNoExtend'] = True

        elif bl_node.type == 'TEX_GRADIENT':
            node['gradientType'] = bl_node.gradient_type

        elif bl_node.type == 'TEX_NOISE':
            node['falloffFactor'] = bl_node.v3d.falloff_factor
            node['dispersionFactor'] = bl_node.v3d.dispersion_factor

            # COMPAT: Blender 4.1+
            if hasattr(bl_node, 'noise_type'):
                node['noiseType'] = bl_node.noise_type

        elif bl_node.type == 'TEX_SKY':
            node['skyType'] = bl_node.sky_type
            node['sunDirection'] = extractVec(bl_node.sun_direction)
            node['turbidity'] = bl_node.turbidity
            node['groundAlbedo'] = bl_node.ground_albedo

        elif bl_node.type == 'TEX_VORONOI':
            # only 3D is supported right now
            # node['dimension'] = '3D'
            node['distance'] = bl_node.distance
            node['feature'] = bl_node.feature

        elif bl_node.type == 'TEX_WAVE':
            node['waveType'] = bl_node.wave_type
            node['waveProfile'] = bl_node.wave_profile
            node['bandsDirection'] = bl_node.bands_direction
            node['ringsDirection'] = bl_node.rings_direction

        elif bl_node.type == 'TEX_WHITE_NOISE':
            node['noise_dimension'] = bl_node.noise_dimensions

        elif bl_node.type == 'VALTORGB':
            node['curve'] = extractColorRamp(bl_node.color_ramp)

        elif bl_node.type == 'VECT_MATH':
            node['operation'] = bl_node.operation

        elif bl_node.type == 'VECTOR_ROTATE':
            node['rotationType'] = bl_node.rotation_type
            node['invert'] = bl_node.invert

        elif bl_node.type == 'VECT_TRANSFORM':
            node['vectorType'] = bl_node.vector_type
            node['convertFrom'] = bl_node.convert_from
            node['convertTo'] = bl_node.convert_to

        elif bl_node.type == 'VERTEX_COLOR':
            node['colorLayer'] = bl_node.layer_name

        node['inputs'] = []
        for bl_input in filterNodeInputs(bl_node):
            defval = getSocketDefvalCompat(bl_input, node['type'] == 'OSL_NODE',
                    node['type'] == 'OSL_NODE')
            node['inputs'].append(defval)

        node['outputs'] = []
        for bl_output in filterNodeOutputs(bl_node):
            defval = getSocketDefvalCompat(bl_output, node['type'] == 'OSL_NODE',
                    node['type'] == 'OSL_NODE')
            node['outputs'].append(defval)

        # "is_active_output" exists on both tree outputs and group outputs
        node["is_active_output"] = (hasattr(bl_node, "is_active_output")
                and bl_node.is_active_output)


    for bl_link in node_tree.links:
        if not bl_link.is_valid:
            log.error('Invalid edge')
            continue

        # indices
        from_node = bl_nodes.find(bl_link.from_node.name)
        to_node = bl_nodes.find(bl_link.to_node.name)

        if from_node < 0 or to_node < 0:
            log.error('Invalid edge connection')
            continue

        edge = {
            'fromNode' : from_node,
            'fromOutput' : findNodeSocketNum(filterNodeOutputs(bl_nodes[from_node]),
                    bl_link.from_socket.identifier),

            'toNode' : to_node,
            'toInput' : findNodeSocketNum(filterNodeInputs(bl_nodes[to_node]),
                    bl_link.to_socket.identifier)
        }

        edges.append(edge)

    return { 'nodes' : nodes, 'edges' : edges }


def filterNodeInputs(bl_node):
    inputs = []

    for bl_input in bl_node.inputs:
        # An input of type CUSTOM is usually the last input/output socket
        # in the "Group Input"/"Group Output" nodes, should be safe to omit
        if bl_input.type == 'CUSTOM':
            continue

        # Invisible Blender-specific input introduced in Blender 3.2
        if bl_input.name == 'Weight' and bl_input.enabled == False:
            continue

        inputs.append(bl_input)

    return inputs

def filterNodeOutputs(bl_node):
    outputs = []

    for bl_output in bl_node.outputs:
        # An input of type CUSTOM is usually the last input/output socket
        # in the "Group Input"/"Group Output" nodes, should be safe to omit
        if bl_output.type == 'CUSTOM':
            continue

        outputs.append(bl_output)

    return outputs

def extractCurveMapping(mapping, x_range):
    """Extract curve points data from CurveMapping data"""

    mapping.initialize()

    data = []

    # first pixel = x_range[0], last pixel = x_range[1]
    pix_size = (x_range[1] - x_range[0]) / (CURVE_DATA_SIZE - 1)

    for i in range(CURVE_DATA_SIZE):

        x = x_range[0] + pix_size * i

        for curve_map in mapping.curves:
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

    # from Blender 4.0
    appendNode(graph, {
        'name': 'Principled-Based',
        'type': 'BSDF_PRINCIPLED_BL',
        'inputs': [
            extractVec(bl_mat.diffuse_color),
            bl_mat.metallic,
            bl_mat.roughness,
            1.45,               # IOR
            1,                  # Alpha
            [0.0, 0.0, 0.0],    # Normal
            0.0,                # Subsurface Weight
            [0.0, 0.0, 0.0],    # Subsurface Radius
            0.0,                # Subsurface Scale
            1.4,                # Subsurface IOR
            0.0,                # Subsurface Anisotropy
            bl_mat.specular_intensity,
            [1.0, 1.0, 1.0, 1.0], # Specular Tint
            0.0,                # Anisotropic
            0.0,                # Anisotropic Rotation
            [0.0, 0.0, 0.0],    # Tangent
            0.0,                # Transmission Weight
            0.0,                # Coat Weight
            0.0,                # Coat Roughness
            1.5,                # Coat IOR
            [1.0, 1.0, 1.0, 1.0], # Coat Tint
            [0.0, 0.0, 0.0],    # Coat Normal
            0.0,                # Sheen Weight
            0.0,                # Sheen Roughness
            [1.0, 1.0, 1.0, 1.0], # Sheen Tint
            [1.0, 1.0, 1.0, 1.0], # Emission Color
            0.0,                # Emission Strength
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
                constraints.append(dict(cons, **{
                    'type': 'copyLocation',
                    'target': target,
                    'useX': bl_cons.use_x,
                    'useY': bl_cons.use_z,
                    'useZ': bl_cons.use_y,
                    'invertX': bl_cons.invert_x,
                    'invertY': bl_cons.invert_z,
                    'invertZ': bl_cons.invert_y,
                    'useOffset': bl_cons.use_offset,
                    'influence': bl_cons.influence,
                }))

        elif bl_cons.type == 'COPY_ROTATION':
            if target >= 0:
                constraints.append(dict(cons, **{
                    'type': 'copyRotation',
                    'target': target,
                    'useX': bl_cons.use_x,
                    'useY': bl_cons.use_z,
                    'useZ': bl_cons.use_y,
                    'invertX': bl_cons.invert_x,
                    'invertY': bl_cons.invert_z,
                    'invertZ': bl_cons.invert_y,
                    'mixMode': bl_cons.mix_mode,
                    'influence': bl_cons.influence,
                    'fixCameraLightRotation': True,
                }))

        elif bl_cons.type == 'COPY_SCALE':
            if target >= 0:
                constraints.append(dict(cons, **{
                    'type': 'copyScale',
                    'target': target,
                    'useX': bl_cons.use_x,
                    'useY': bl_cons.use_z,
                    'useZ': bl_cons.use_y,
                    'power': bl_cons.power,
                    'useMakeUniform': bl_cons.use_make_uniform,
                    'useOffset': bl_cons.use_offset,
                    'useAdd': bl_cons.use_add,
                    'influence': bl_cons.influence,
                }))

        elif bl_cons.type == 'COPY_TRANSFORMS':
            if target >= 0:
                constraints.append(dict(cons, **{
                    'type': 'copyTransforms',
                    'target': target,
                    'mixMode': bl_cons.mix_mode,
                    'influence': bl_cons.influence,
                    'fixCameraLightRotation': True,
                }))

        elif bl_cons.type == 'DAMPED_TRACK':
            if target >= 0:
                constraints.append(dict(cons, **{
                    'type': 'dampedTrack',
                    'target': target,
                    'trackAxis': extractAxisParam(bl_cons.track_axis, 'TRACK_', True),
                    'influence': bl_cons.influence,
                    'fixCameraLightRotation': True,
                }))

        elif bl_cons.type == 'FOLLOW_PATH':
            if target < 0:
                continue

            curveObj = bl_cons.target
            spline = curveObj.data.splines.active
            if spline and spline.point_count_u > 0:
                splineAttrs = extractNURBSSpline(spline, curveObj.matrix_world)
                frontAxisPrefix = 'FORWARD_'
                if not 'FORWARD_' in bl_cons.forward_axis:
                    frontAxisPrefix = 'TRACK_'

                constraints.append(dict(cons, **{
                    'type': 'motionPath',
                    'degree': splineAttrs['degree'],
                    'cvs': splineAttrs['cvs'],
                    'knots': splineAttrs['knots'],
                    'weights': splineAttrs['weights'],
                    'value': curveObj.data.eval_time,
                    'follow': bl_cons.use_curve_follow,
                    'frontAxis': extractAxisParam(bl_cons.forward_axis, frontAxisPrefix, True),
                    'upAxis': extractAxisParam(bl_cons.up_axis, 'UP_', True),
                    'useFixedLocation': bl_cons.use_fixed_location,
                    'usePointsTilt': splineAttrs['usePointsTilt'],
                    'pointsTilt': splineAttrs['pointsTilt'],
                    'fixedValue': bl_cons.offset_factor,
                    'useClampValue': curveObj.data.use_path_clamp,
                    'useCyclic': splineAttrs['useCyclic'],
                    'influence': bl_cons.influence,
                    # Blender's specific params
                    'useChordLength': True,
                    'useObjOffset': True,
                    'objOffsetMode': 1, # MATRIX
                    'objOffsetRotMode': 1, # CONSTRAINT_FIRST
                    'fixCameraLightRotation': False, # disable, bcs useObjOffset is enabled
                    # TODO
                    # 'offsetValue': -(bl_cons.offset / curveObj.data.path_duration),
                    # 'useCurveRadius': bl_cons.use_curve_radius,
                }))

        elif bl_cons.type == 'LIMIT_DISTANCE':
            if target >= 0:
                constraints.append(dict(cons, **{
                    'type': 'limitDistance',
                    'target': target,
                    'distance': bl_cons.distance,
                    'limitMode': bl_cons.limit_mode,
                    'useTransformLimit': bl_cons.use_transform_limit,
                    'influence': bl_cons.influence,
                }))

        elif bl_cons.type == 'LIMIT_LOCATION':
            cons = dict(cons, **{
                'type': 'limitLocation',
                'space': bl_cons.owner_space,
                'minX': bl_cons.min_x if bl_cons.use_min_x else '-Infinity',
                'maxX': bl_cons.max_x if bl_cons.use_max_x else 'Infinity',
                'minY': bl_cons.min_z if bl_cons.use_min_z else '-Infinity',
                'maxY': bl_cons.max_z if bl_cons.use_max_z else 'Infinity',
                'minZ': -bl_cons.max_y if bl_cons.use_max_y else '-Infinity',
                'maxZ': -bl_cons.min_y if bl_cons.use_min_y else 'Infinity',
            })

            if getattr(bl_cons, 'space_object', None) is not None:
                cons['target'] = gltf.getNodeIndex(glTF, bl_cons.space_object.name)

            constraints.append(cons)

        elif bl_cons.type == 'LIMIT_ROTATION':
            if bl_cons.use_limit_x:
                constraints.append(dict(cons, **{
                    'type': 'limitRotation',
                    'axis': 'X',
                    'min': bl_cons.min_x,
                    'max': bl_cons.max_x
                }))
            if bl_cons.use_limit_y:
                constraints.append(dict(cons, **{
                    'type': 'limitRotation',
                    'axis': 'Z',
                    'min': -bl_cons.max_y,
                    'max': -bl_cons.min_y
                }))
            if bl_cons.use_limit_z:
                constraints.append(dict(cons, **{
                    'type': 'limitRotation',
                    'axis': 'Y',
                    'min': bl_cons.min_z,
                    'max': bl_cons.max_z
                }))


        elif bl_cons.type == 'LIMIT_SCALE':
            constraints.append(dict(cons, **{
                'type': 'limitScale',
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
                    'fixCameraLightRotation': True,
                }))

        elif bl_cons.type == 'TRACK_TO':
            if target >= 0:
                constraints.append(dict(cons, **{
                    'type': 'trackTo',
                    'target': target,
                    'trackAxis': extractAxisParam(bl_cons.track_axis, 'TRACK_', True),
                    'upAxis': extractAxisParam(bl_cons.up_axis, 'UP_', True),
                    'fixCameraLightRotation': True,
                }))

        elif bl_cons.type == 'CHILD_OF':
            if target >= 0:
                constraints.append(dict(cons, **{
                    'type': 'childOf',
                    'target': target,
                    'offsetMatrix': extractMat(convertSwizzleMatrix(
                            bl_cons.inverse_matrix @ bl_obj.matrix_basis)),
                    'fixCameraLightRotation': True,
                }))

        elif bl_cons.type == 'FLOOR':
            if target >= 0:
                floorLocation = extractAxisParam(bl_cons.floor_location, 'FLOOR_', True)
                constraints.append(dict(cons, **{
                    'type': 'floor',
                    'target': target,
                    'offset': -bl_cons.offset if floorLocation in ['Z', '-Z'] else bl_cons.offset,
                    'floorLocation': floorLocation,
                    'useRotation': bl_cons.use_rotation,
                }))

        elif bl_cons.type == 'TRANSFORM':
            if target >= 0:
                if bl_cons.map_from == 'LOCATION':
                    fromMin = [bl_cons.from_min_x, bl_cons.from_min_z, -bl_cons.from_max_y]
                    fromMax = [bl_cons.from_max_x, bl_cons.from_max_z, -bl_cons.from_min_y]
                elif bl_cons.map_from == 'ROTATION':
                    fromMin = [bl_cons.from_min_x_rot, bl_cons.from_min_z_rot, -bl_cons.from_max_y_rot]
                    fromMax = [bl_cons.from_max_x_rot, bl_cons.from_max_z_rot, -bl_cons.from_min_y_rot]
                elif bl_cons.map_from == 'SCALE':
                    fromMin = [bl_cons.from_min_x_scale, bl_cons.from_min_z_scale, bl_cons.from_min_y_scale]
                    fromMax = [bl_cons.from_max_x_scale, bl_cons.from_max_z_scale, bl_cons.from_max_y_scale]

                if bl_cons.map_to == 'LOCATION':
                    mixMode = bl_cons.mix_mode
                    toMin = [bl_cons.to_min_x, bl_cons.to_min_z, -bl_cons.to_max_y]
                    toMax = [bl_cons.to_max_x, bl_cons.to_max_z, -bl_cons.to_min_y]
                elif bl_cons.map_to == 'ROTATION':
                    mixMode = bl_cons.mix_mode_rot
                    toMin = [bl_cons.to_min_x_rot, bl_cons.to_min_z_rot, -bl_cons.to_max_y_rot]
                    toMax = [bl_cons.to_max_x_rot, bl_cons.to_max_z_rot, -bl_cons.to_min_y_rot]
                elif bl_cons.map_to == 'SCALE':
                    mixMode = bl_cons.mix_mode_scale
                    toMin = [bl_cons.to_min_x_scale,bl_cons.to_min_z_scale, bl_cons.to_min_y_scale]
                    toMax = [bl_cons.to_max_x_scale,bl_cons.to_max_z_scale, bl_cons.to_max_y_scale]

                if bl_cons.map_to in ('LOCATION', 'ROTATION'):
                    if bl_cons.map_from in ('LOCATION', 'ROTATION'):
                        mapToAxisFromAxis = [
                            {'X': 'X', 'Y': '-Z', 'Z': 'Y'}[bl_cons.map_to_x_from],
                            {'X': 'X', 'Y': '-Z', 'Z': 'Y'}[bl_cons.map_to_z_from],
                            {'X': '-X', 'Y': 'Z', 'Z': '-Y'}[bl_cons.map_to_y_from]
                        ]
                    elif bl_cons.map_from == 'SCALE':
                        mapToAxisFromAxis = [
                            {'X': 'X', 'Y': 'Z', 'Z': 'Y'}[bl_cons.map_to_x_from],
                            {'X': 'X', 'Y': 'Z', 'Z': 'Y'}[bl_cons.map_to_z_from],
                            {'X': '-X', 'Y': '-Z', 'Z': '-Y'}[bl_cons.map_to_y_from]
                        ]
                elif bl_cons.map_to == 'SCALE':
                    if bl_cons.map_from in ('LOCATION', 'ROTATION'):
                        mapToAxisFromAxis = [
                            {'X': 'X', 'Y': '-Z', 'Z': 'Y'}[bl_cons.map_to_x_from],
                            {'X': 'X', 'Y': '-Z', 'Z': 'Y'}[bl_cons.map_to_z_from],
                            {'X': 'X', 'Y': '-Z', 'Z': 'Y'}[bl_cons.map_to_y_from]
                        ]
                    elif bl_cons.map_from == 'SCALE':
                        mapToAxisFromAxis = [
                            {'X': 'X', 'Y': 'Z', 'Z': 'Y'}[bl_cons.map_to_x_from],
                            {'X': 'X', 'Y': 'Z', 'Z': 'Y'}[bl_cons.map_to_z_from],
                            {'X': 'X', 'Y': 'Z', 'Z': 'Y'}[bl_cons.map_to_y_from]
                        ]

                if bl_cons.owner_space == 'CUSTOM':
                    cons['ownerSpaceObj'] = (gltf.getNodeIndex(glTF, bl_cons.space_object.name)
                            if getattr(bl_cons, 'space_object', None) is not None else -1)
                if bl_cons.target_space == 'CUSTOM':
                    cons['targetSpaceObj'] = (gltf.getNodeIndex(glTF, bl_cons.space_object.name)
                            if getattr(bl_cons, 'space_object', None) is not None else -1)

                blAxisToV3D = {'LOCATION':'POSITION', 'ROTATION':'ROTATION', 'SCALE':'SCALE'}

                constraints.append(dict(cons, **{
                    'type': 'transformation',
                    'target': target,
                    'fromMin': fromMin,
                    'fromMax': fromMax,
                    'toMin': toMin,
                    'toMax': toMax,
                    'mapToAxisFromAxis': mapToAxisFromAxis,
                    'mapFrom': blAxisToV3D[bl_cons.map_from],
                    'mapTo': blAxisToV3D[bl_cons.map_to],
                    'ownerSpace': bl_cons.owner_space,
                    'targetSpace': bl_cons.target_space,
                    'useMotionExtrapolate': bl_cons.use_motion_extrapolate,
                    'mixMode': mixMode,
                    'influence': bl_cons.influence,
                    'fixCameraLightRotation': True,
                }))

    if objHasFixOrthoZoom(bl_obj):
        constraints.append({
            'name': 'Fix Ortho Zoom',
            'mute': False,
            'type': 'fixOrthoZoom',
            'target': gltf.getNodeIndex(glTF, bl_obj.parent.name)
        })

    if objHasCanvasFitParams(bl_obj):
        constraints.append({
            'name': 'Canvas Fit',
            'mute': False,
            'type': 'canvasFit',
            'target': gltf.getNodeIndex(glTF, bl_obj.parent.name),
            'edgeH': bl_obj.v3d.canvas_fit_x,
            'edgeV': bl_obj.v3d.canvas_fit_y,
            'fitShape': bl_obj.v3d.canvas_fit_shape,
            'offset': bl_obj.v3d.canvas_fit_offset
        })

    if bl_obj.v3d.canvas_break_enabled:
        constraints.append({
            'name': 'Canvas Visibility Breakpoints',
            'mute': False,
            'type': 'canvasBreakpoints',
            'minWidth': gltf.processInfinity(bl_obj.v3d.canvas_break_min_width),
            'maxWidth': gltf.processInfinity(bl_obj.v3d.canvas_break_max_width),
            'minHeight': gltf.processInfinity(bl_obj.v3d.canvas_break_min_height),
            'maxHeight': gltf.processInfinity(bl_obj.v3d.canvas_break_max_height),
            'orientation': bl_obj.v3d.canvas_break_orientation
        })

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
        log.error('Incorrect axis param: ' + param)
        return ''

def extractImageBindata(bl_image, scene, exportSettings):

    fileFormat = bl_image.file_format

    if imgNeedsCompression(bl_image, exportSettings):
        if fileFormat == 'JPEG':
            data = imageSaveRender(bl_image, scene, 'JPEG', 'RGB', quality=90)
        elif fileFormat == 'HDR':
            data = imageSaveRender(bl_image, scene, 'HDR', 'RGB')
        else:
            data = imageSaveRender(bl_image, scene, 'PNG', 'RGBA', color_depth='8', compression=90)

        if fileFormat == 'HDR':
            return lzma.compress(data)
        else:
            return pu.convert.compressKTX2(srcData=data, method=bl_image.v3d.compression_method)

    elif fileFormat == 'JPEG':
        return imageSaveRender(bl_image, scene, 'JPEG', 'RGB', quality=90)
    elif fileFormat == 'WEBP':
        return imageSaveRender(bl_image, scene, 'WEBP', 'RGBA', quality=90)
    elif fileFormat == 'BMP':
        # RGBA bitmaps seams to be not supported
        return imageSaveRender(bl_image, scene, 'BMP', 'RGB')
    elif fileFormat == 'HDR':
        return imageSaveRender(bl_image, scene, 'HDR', 'RGB')
    else:
        return imageSaveRender(bl_image, scene, 'PNG', 'RGBA', color_depth='8', compression=90)

def imageSaveRender(bl_image, scene, file_format, color_mode, color_depth=None, compression=None,
                    quality=None):

    if not bl_image.is_dirty:
        # it's much faster to access packed file data if no conversion is needed
        if bl_image.packed_file is not None and bl_image.file_format == file_format:
            return bl_image.packed_file.data

    tmp_img = tempfile.NamedTemporaryFile(delete=False)

    img_set = scene.render.image_settings

    file_format_save = img_set.file_format
    color_mode_save = img_set.color_mode
    color_depth_save = img_set.color_depth
    compression_save = img_set.compression
    quality_save = img_set.quality

    img_set.file_format = file_format
    img_set.color_mode = color_mode

    if color_depth is not None:
        img_set.color_depth = color_depth
    if compression is not None:
        img_set.compression = compression
    if quality is not None:
        img_set.quality = quality

    bl_image.save_render(tmp_img.name, scene=scene)

    img_set.file_format = file_format_save
    img_set.color_mode = color_mode_save
    img_set.color_depth = color_depth_save
    img_set.compression = compression_save
    img_set.quality = quality_save

    bindata = tmp_img.read()

    tmp_img.close()
    os.unlink(tmp_img.name)

    return bindata

def extractColorSpace(bl_tex):
    return getTexImage(bl_tex).colorspace_settings.name.lower()

def getPtr(blEntity):
    return blEntity.as_pointer()

def extractFontBindata(bl_font):
    if bl_font.packed_file is not None:
        return bl_font.packed_file.data
    else:
        with open(getFontPath(bl_font), 'rb') as f:
            return f.read()

def extractNURBSSpline(spline, matrixWorld = None):
    """ Extract spline parameters as a dictionary. """

    order = spline.order_u
    degree = order - 1
    knotsCount = spline.point_count_u + spline.order_u
    cvs = []
    knots = []
    weights = []
    pointsTilt = []
    usePointsTilt = False

    if spline.type == 'BEZIER':
        degree = 3
        counter = 1 if spline.use_cyclic_u else 0
        for point in spline.bezier_points:
            if matrixWorld:
                posLeft = convertSwizzleLocation(matrixWorld @ point.handle_left)
                pos = convertSwizzleLocation(matrixWorld @ point.co)
                posRight = convertSwizzleLocation(matrixWorld @ point.handle_right)
            else:
                posLeft = convertSwizzleLocation(point.handle_left)
                pos = convertSwizzleLocation(point.co)
                posRight = convertSwizzleLocation(point.handle_right)
            cvs.extend([posLeft.x, posLeft.y, posLeft.z,
                        pos.x, pos.y, pos.z,
                        posRight.x, posRight.y, posRight.z])
            pointsTilt.append(point.tilt)
            if not usePointsTilt and point.tilt != 0.0:
                usePointsTilt = True

            knots.extend([counter] * degree)
            counter += 1

        if spline.use_cyclic_u:
            cvs = cvs[-6:] + cvs
            knots = [0, 0, 0, 0] + knots
            del cvs[-3:]
            knots.append(knots[-1])
        else:
            knots.insert(0, knots[0])
            knots.append(knots[-1])
            del cvs[-3:]
            del cvs[:3]

        weights.extend([1] * (len(cvs) // 3))

    elif spline.type == 'NURBS' or spline.type == 'POLY':
        for point in spline.points:
            pos = mathutils.Vector(point.co[0:3]) # ignore weight
            if matrixWorld:
                pos = convertSwizzleLocation(matrixWorld @ pos)
            else:
                pos = convertSwizzleLocation(pos)
            cvs.extend([pos.x, pos.y, pos.z])
            weights.append(point.weight if degree > 1 else 1) # hack, Blender's behavior
            pointsTilt.append(point.tilt)
            if not usePointsTilt and point.tilt != 0.0:
                usePointsTilt = True

        # Calculate knot values, blender does not store knots
        innerMultiplicity = degree if spline.use_bezier_u else 1 # for knots

        if spline.use_cyclic_u:
            if spline.use_endpoint_u:
                # behavior in blender version >= 3.2
                head = tail = order
                extraPointsNum = 1
            elif spline.use_bezier_u:
                # behavior in blender version >= 3.1
                head = tail = order
                cvs.extend(cvs[:3])
                del cvs[:3]
                extraPointsNum = 1
            else:
                head = tail = 1
                extraPointsNum = degree
            knotsCount += extraPointsNum
            cvs.extend(cvs[:3*extraPointsNum])
            weights.extend(weights[:extraPointsNum])
            pointsTilt.extend(pointsTilt[:extraPointsNum])
        elif spline.use_endpoint_u:
            head = tail = order
        elif spline.use_bezier_u:
            head = order if order == 3 else min(2, innerMultiplicity)
            tail = 0
        else:
            head = tail = 1

        if spline.use_bezier_u and spline.use_endpoint_u:
            head = tail = 1

        knots.extend([0] * head)
        knotVal = 1
        innerKnotsCount = knotsCount - head - tail
        for i in range(0, innerKnotsCount, innerMultiplicity):
            knots.extend([knotVal] * min(innerMultiplicity, innerKnotsCount - i))
            knotVal += 1

        knots.extend([knotVal] * tail)

    splineAttrs = {
        'degree': degree,
        'cvs': cvs,
        'knots': knots,
        'weights': weights,
        'useCyclic': spline.use_cyclic_u,
        'usePointsTilt': usePointsTilt,
        'pointsTilt': pointsTilt,
    }
    return splineAttrs
