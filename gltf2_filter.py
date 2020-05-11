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

#
# Imports
#

from string import Template

import bpy

from .gltf2_get import *
from .gltf2_extract import *
from .node_material_wrapper import NodeMaterialWrapper
from .utils import *

#
# Globals
#

TO_MESH_SOURCE_CUSTOM_PROP = "v3d_to_mesh_source_object"
WORLD_NODE_MAT_NAME = Template('Verge3D_Environment_${name}')

#
# Functions
#

def flatten_collection_unique(collection, dest_set):

    for bl_obj in collection.all_objects:

        is_unique = bl_obj not in dest_set
        dest_set.add(bl_obj)

        if bl_obj.instance_type == 'COLLECTION' and bl_obj.instance_collection != None:
            # prevent possible infinite recursion for collections
            if is_unique:
                flatten_collection_unique(bl_obj.instance_collection, dest_set)


def mesh_obj_get_export_data(obj_original, bake_modifiers, optimize_tangents):
    """
    Prepare the data of the given MESH object before export by making such
    operations as:
        - applying all suitable modifiers if any
        - triangulate mesh ngons if tangents export is needed
        - restore shape keys after the previous operations if it's possible or needed
    """

    generated_objs = []
    generated_meshes = []


    # APPLY MODIFIERS
    need_apply_mods = bake_modifiers is True and obj_has_exported_modifiers(obj_original)

    obj_mods_applied = obj_original
    if need_apply_mods:
        obj_mods_applied = obj_original.copy()
        obj_del_not_exported_modifiers(obj_mods_applied)
        obj_apply_modifiers(obj_mods_applied)

        generated_objs.append(obj_mods_applied)
        generated_meshes.append(obj_mods_applied.data)


    # TRIANGULATE
    need_tangents = mesh_need_tangents_for_export(obj_mods_applied.data, optimize_tangents)
    if not need_tangents:
        printLog('DEBUG',
                'Tangent attribute will not be exported for mesh "%s"'
                % obj_original.data.name)
    need_triangulation = need_tangents and mesh_has_ngons(obj_mods_applied.data)

    obj_triangulated = obj_mods_applied
    if need_triangulation:
        obj_triangulated = obj_mods_applied.copy()
        obj_del_not_exported_modifiers(obj_triangulated)
        obj_add_tri_modifier(obj_triangulated)

        # Triangulation modifier doesn't affect vertices, therefore this operation
        # can preserve shape keys. To do this we need to remove shape keys to not
        # bake them into the new mesh.

        # NOTE: need to copy object data before changes because it's shared with
        # the object coming from the previous operation (due to .copy() not
        # creating a new mesh datablock)
        tmp_data = obj_triangulated.data.copy()
        obj_triangulated.data = tmp_data
        obj_triangulated.shape_key_clear()

        obj_apply_modifiers(obj_triangulated)

        generated_objs.append(obj_triangulated)
        generated_meshes.append(tmp_data)
        generated_meshes.append(obj_triangulated.data)


    # TRANSFER SHAPE KEYS

    # transfer shape keys to the new object only if:
    #   - shape keys were removed during mesh processing
    #   - shape keys were not baked into the mesh geometry (always baked during
    #     the APPLY MODIFIERS operation; TRIANGULATION doesn't bake them)
    shape_keys_removed = (obj_original.data.shape_keys is not None
            and obj_triangulated.data.shape_keys is None)
    need_transfer_sk = shape_keys_removed and not need_apply_mods

    obj_sk_transfered = obj_triangulated
    if need_transfer_sk:
        obj_sk_transfered = obj_triangulated.copy()
        dg = bpy.context.evaluated_depsgraph_get()

        success = obj_transfer_shape_keys(obj_original, obj_sk_transfered, dg)
        if not success:
            printLog('WARNING', 'Could not generate shape keys because they '
                    + 'change vertex count. Object "' + obj_original.name + '".')

        generated_objs.append(obj_sk_transfered)
        # no new mesh was generated


    resulting_mesh = obj_sk_transfered.data

    for tmp_obj in generated_objs:
        bpy.data.objects.remove(tmp_obj)
    for tmp_mesh in generated_meshes:
        if tmp_mesh != resulting_mesh:
            bpy.data.meshes.remove(tmp_mesh)

    return resulting_mesh


def filter_apply(exportSettings):
    """
    Gathers and filters the objects and assets to export.
    Also filters out invalid, deleted and not exportable elements.
    """

    filtered_objects_shallow = set()
    filtered_objects_with_dg = set()
    for bl_scene in bpy.data.scenes:
        filtered_objects_shallow.update(bl_scene.objects)
        flatten_collection_unique(bl_scene.collection, filtered_objects_with_dg)

    def collExpFilter(obj):
        return all(coll.v3d.enable_export for coll in getObjectAllCollections(obj))

    filtered_objects_shallow = list(filter(collExpFilter, filtered_objects_shallow))
    filtered_objects_with_dg = list(filter(collExpFilter, filtered_objects_with_dg))

    exportSettings['filtered_objects_shallow'] = filtered_objects_shallow
    exportSettings['filtered_objects_with_dg'] = filtered_objects_with_dg

    # Meshes

    filtered_meshes = []
    filtered_vertex_groups = {}
    temporary_meshes = []

    for blender_mesh in bpy.data.meshes:

        if blender_mesh.users == 0:
            continue

        current_blender_mesh = blender_mesh

        current_blender_object = None

        skip = True

        for blender_object in filtered_objects_with_dg:

            current_blender_object = blender_object

            if current_blender_object.type != 'MESH':
                continue

            if current_blender_object.data == current_blender_mesh:

                skip = False

                mesh_for_export = mesh_obj_get_export_data(
                        current_blender_object,
                        exportSettings['bake_modifiers'],
                        exportSettings['optimize_attrs'])

                if mesh_for_export != current_blender_mesh:
                    # a new mesh was generated
                    mesh_for_export[TO_MESH_SOURCE_CUSTOM_PROP] = current_blender_object
                    temporary_meshes.append(mesh_for_export)
                    current_blender_mesh = mesh_for_export

                break

        if skip:
            continue

        filtered_meshes.append(current_blender_mesh)
        filtered_vertex_groups[getPtr(blender_mesh)] = current_blender_object.vertex_groups

    # CURVES (as well as surfaces and texts)
    filtered_curves = []

    for bl_curve in bpy.data.curves:

        if bl_curve.users == 0:
            continue

        # supported curve
        if isinstance(bl_curve, bpy.types.TextCurve) and not exportSettings['bake_text']:
            filtered_curves.append(bl_curve)

        # convert to mesh
        else:
            current_blender_curve = bl_curve
            current_blender_mesh = None
            current_blender_object = None

            skip = True

            for blender_object in filtered_objects_with_dg:

                current_blender_object = blender_object

                if current_blender_object.type not in ['CURVE', 'SURFACE', 'FONT']:
                    continue

                if current_blender_object.data == current_blender_curve:

                    skip = False

                    copy_obj = current_blender_object.copy()

                    if not exportSettings['bake_modifiers']:
                        copy_obj.modifiers.clear()

                    dg = bpy.context.evaluated_depsgraph_get()

                    dg.scene.collection.objects.link(copy_obj)
                    copy_obj.update_tag()
                    bpy.context.view_layer.update()

                    copy_obj_eval = copy_obj.evaluated_get(dg)
                    current_blender_mesh = bpy.data.meshes.new_from_object(copy_obj_eval)

                    dg.scene.collection.objects.unlink(copy_obj)

                    if current_blender_mesh is not None:
                        current_blender_mesh.name = bl_curve.name
                        current_blender_mesh[TO_MESH_SOURCE_CUSTOM_PROP] = current_blender_object
                        temporary_meshes.append(current_blender_mesh)
                    else:
                        skip = True

                    bpy.data.objects.remove(copy_obj)

                    break

            if skip:
                continue

            filtered_meshes.append(current_blender_mesh)
            filtered_vertex_groups[getPtr(bl_curve)] = current_blender_object.vertex_groups


    exportSettings['filtered_curves'] = filtered_curves
    exportSettings['filtered_meshes'] = filtered_meshes
    exportSettings['filtered_vertex_groups'] = filtered_vertex_groups
    exportSettings['temporary_meshes'] = temporary_meshes

    # MATERIALS

    filtered_materials = []
    temporary_materials = []

    for blender_material in get_used_materials():

        if blender_material.users == 0:
            continue

        for blender_mesh in filtered_meshes:
            for mat in blender_mesh.materials:
                if mat == blender_material and mat not in filtered_materials:
                    filtered_materials.append(mat)

        for blender_object in filtered_objects_with_dg:
            if blender_object.material_slots:
                for blender_material_slot in blender_object.material_slots:
                    if blender_material_slot.link == 'DATA':
                        continue

                    mat = blender_material_slot.material
                    if mat == blender_material and mat not in filtered_materials:
                        filtered_materials.append(mat)

        for bl_curve in filtered_curves:
            for mat in bl_curve.materials:
                if mat == blender_material and mat not in filtered_materials:
                    filtered_materials.append(mat)

    curr_world = bpy.context.scene.world
    if curr_world is not None:

        world_mat = bpy.data.materials.new(WORLD_NODE_MAT_NAME.substitute(
                name=curr_world.name))
        world_mat.use_nodes = True

        world_mat.v3d.dithering = curr_world.v3d.dithering

        world_mat_wrapper = NodeMaterialWrapper(world_mat)

        if curr_world.use_nodes:
            mat_node_tree = curr_world.node_tree.copy()
        else:
            mat_node_tree = world_mat.node_tree.copy()
            mat_node_tree.nodes.clear()

            bkg_node = mat_node_tree.nodes.new('ShaderNodeBackground')
            bkg_node.inputs['Color'].default_value[0] = curr_world.color[0]
            bkg_node.inputs['Color'].default_value[1] = curr_world.color[1]
            bkg_node.inputs['Color'].default_value[2] = curr_world.color[2]
            bkg_node.inputs['Color'].default_value[3] = 1
            bkg_node.inputs['Strength'].default_value = 1

            out_node = mat_node_tree.nodes.new('ShaderNodeOutputWorld')

            mat_node_tree.links.new(bkg_node.outputs['Background'], out_node.inputs['Surface'])

        world_mat_wrapper.node_tree = mat_node_tree

        temporary_materials.append(world_mat)
        filtered_materials.append(world_mat_wrapper)

    exportSettings['filtered_materials'] = filtered_materials
    exportSettings['temporary_materials'] = temporary_materials

    filtered_node_groups = []
    for group in bpy.data.node_groups:
        if group.users == 0:
            continue

        # only groups used by 'CYCLES' materials
        for bl_material in filtered_materials:
            mat_type = get_material_type(bl_material)
            if mat_type == 'CYCLES':
                if (group not in filtered_node_groups and
                        group in extract_material_node_trees(bl_material.node_tree)):
                    filtered_node_groups.append(group)

    exportSettings['filtered_node_groups'] = filtered_node_groups

    filtered_textures = []

    for blender_material in filtered_materials:
        # PBR, CYCLES materials
        if blender_material.node_tree and blender_material.use_nodes:
            for bl_node in blender_material.node_tree.nodes:
                if (isinstance(bl_node, (bpy.types.ShaderNodeTexImage, bpy.types.ShaderNodeTexEnvironment)) and
                        get_tex_image(bl_node) is not None and
                        get_tex_image(bl_node).users != 0 and
                        get_tex_image(bl_node).size[0] > 0 and
                        get_tex_image(bl_node).size[1] > 0 and
                        bl_node not in filtered_textures):
                    filtered_textures.append(bl_node)

    for node_group in filtered_node_groups:
        for bl_node in node_group.nodes:
            if (isinstance(bl_node, (bpy.types.ShaderNodeTexImage, bpy.types.ShaderNodeTexEnvironment)) and
                    get_tex_image(bl_node) is not None and
                    get_tex_image(bl_node).users != 0 and
                    get_tex_image(bl_node).size[0] > 0 and
                    get_tex_image(bl_node).size[1] > 0 and
                    bl_node not in filtered_textures):
                filtered_textures.append(bl_node)

    exportSettings['filtered_textures'] = filtered_textures

    filtered_images = []

    for blender_texture in filtered_textures:

        img = (get_tex_image(blender_texture) if isinstance(blender_texture,
                (bpy.types.ShaderNodeTexImage, bpy.types.ShaderNodeTexEnvironment))
                else get_tex_image(blender_texture.texture))

        if (img is not None and img not in filtered_images and img.users != 0
                and img.size[0] > 0 and img.size[1] > 0):
            filtered_images.append(img)

    exportSettings['filtered_images'] = filtered_images


    filtered_cameras = []

    for blender_camera in bpy.data.cameras:

        if blender_camera.users == 0:
            continue

        filtered_cameras.append(blender_camera)

    exportSettings['filtered_cameras'] = filtered_cameras


    filtered_lights = []

    for blender_light in bpy.data.lights:

        if blender_light.users == 0:
            continue

        if blender_light.type == 'AREA':
            continue

        filtered_lights.append(blender_light)

    exportSettings['filtered_lights'] = filtered_lights

    joint_indices = {}

    if exportSettings['skins']:
        for blender_object in filtered_objects_with_dg:

            if blender_object.type != 'MESH':
                continue

            armature_object = find_armature(blender_object)
            if armature_object is None or len(armature_object.pose.bones) == 0:
                continue

            grp = joint_indices[blender_object.data.name] = {}

            for blender_bone in armature_object.pose.bones:
                grp[blender_bone.name] = len(grp)

    exportSettings['joint_indices'] = joint_indices
