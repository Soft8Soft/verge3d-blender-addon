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

from string import Template

import bpy

from .gltf2_get import *
from .gltf2_extract import *
from .node_material_wrapper import NodeMaterialWrapper
from .utils import *


TO_MESH_SOURCE_CUSTOM_PROP = "v3d_to_mesh_source_object"
WORLD_NODE_MAT_NAME = Template('Verge3D_Environment_${name}')


def flattenCollectionUnique(collection, dest_set):

    for bl_obj in collection.all_objects:

        is_unique = bl_obj not in dest_set
        dest_set.add(bl_obj)

        if bl_obj.instance_type == 'COLLECTION' and bl_obj.instance_collection != None:
            # prevent possible infinite recursion for collections
            if is_unique:
                flattenCollectionUnique(bl_obj.instance_collection, dest_set)


def meshObjGetExportData(obj_original, bake_modifiers, optimize_tangents):
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
    need_apply_mods = bake_modifiers is True and objHasExportedModifiers(obj_original)

    obj_mods_applied = obj_original
    if need_apply_mods:
        obj_mods_applied = obj_original.copy()
        obj_del_not_exported_modifiers(obj_mods_applied)
        objApplyModifiers(obj_mods_applied)

        generated_objs.append(obj_mods_applied)
        generated_meshes.append(obj_mods_applied.data)


    # TRIANGULATE
    need_tangents = meshNeedTangentsForExport(obj_mods_applied.data, optimize_tangents)
    if not need_tangents:
        printLog('DEBUG',
                'Tangent attribute will not be exported for mesh "%s"'
                % obj_original.data.name)
    need_triangulation = need_tangents and meshHasNgons(obj_mods_applied.data)

    obj_triangulated = obj_mods_applied
    if need_triangulation:
        obj_triangulated = obj_mods_applied.copy()
        obj_del_not_exported_modifiers(obj_triangulated)
        objAddTriModifier(obj_triangulated)

        # Triangulation modifier doesn't affect vertices, therefore this operation
        # can preserve shape keys. To do this we need to remove shape keys to not
        # bake them into the new mesh.

        # NOTE: need to copy object data before changes because it's shared with
        # the object coming from the previous operation (due to .copy() not
        # creating a new mesh datablock)
        tmp_data = obj_triangulated.data.copy()
        obj_triangulated.data = tmp_data
        obj_triangulated.shape_key_clear()

        objApplyModifiers(obj_triangulated)

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

        success = objTransferShapeKeys(obj_original, obj_sk_transfered, dg)
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


def filterApply(exportSettings):
    """
    Gathers and filters the objects and assets to export.
    Also filters out invalid, deleted and not exportable elements.
    """

    filtered_objects_shallow = set()
    filtered_objects_with_dg = set()
    for bl_scene in bpy.data.scenes:
        filtered_objects_shallow.update(bl_scene.objects)
        flattenCollectionUnique(bl_scene.collection, filtered_objects_with_dg)

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

    for bl_mesh in bpy.data.meshes:

        if bl_mesh.users == 0:
            continue

        current_bl_mesh = bl_mesh

        current_bl_object = None

        skip = True

        for bl_obj in filtered_objects_with_dg:

            current_bl_object = bl_obj

            if current_bl_object.type != 'MESH':
                continue

            if current_bl_object.data == current_bl_mesh:

                skip = False

                mesh_for_export = meshObjGetExportData(
                        current_bl_object,
                        exportSettings['bake_modifiers'],
                        exportSettings['optimize_attrs'])

                if mesh_for_export != current_bl_mesh:
                    # a new mesh was generated
                    mesh_for_export[TO_MESH_SOURCE_CUSTOM_PROP] = current_bl_object
                    temporary_meshes.append(mesh_for_export)
                    current_bl_mesh = mesh_for_export

                break

        if skip:
            continue

        filtered_meshes.append(current_bl_mesh)
        filtered_vertex_groups[getPtr(bl_mesh)] = current_bl_object.vertex_groups

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
            current_bl_curve = bl_curve
            current_bl_mesh = None
            current_bl_object = None

            skip = True

            for bl_obj in filtered_objects_with_dg:

                current_bl_object = bl_obj

                if current_bl_object.type not in ['CURVE', 'SURFACE', 'FONT']:
                    continue

                if current_bl_object.data == current_bl_curve:

                    skip = False

                    copy_obj = current_bl_object.copy()

                    if not exportSettings['bake_modifiers']:
                        copy_obj.modifiers.clear()

                    dg = bpy.context.evaluated_depsgraph_get()

                    dg.scene.collection.objects.link(copy_obj)
                    copy_obj.update_tag()
                    bpy.context.view_layer.update()

                    copy_obj_eval = copy_obj.evaluated_get(dg)
                    current_bl_mesh = bpy.data.meshes.new_from_object(copy_obj_eval)

                    dg.scene.collection.objects.unlink(copy_obj)

                    if current_bl_mesh is not None:
                        current_bl_mesh.name = bl_curve.name
                        current_bl_mesh[TO_MESH_SOURCE_CUSTOM_PROP] = current_bl_object
                        temporary_meshes.append(current_bl_mesh)
                    else:
                        skip = True

                    bpy.data.objects.remove(copy_obj)

                    break

            if skip:
                continue

            filtered_meshes.append(current_bl_mesh)
            filtered_vertex_groups[getPtr(bl_curve)] = current_bl_object.vertex_groups


    # metaballs

    for bl_meta in bpy.data.metaballs:

        if bl_meta.users == 0:
            continue

        current_bl_meta = bl_meta
        current_bl_mesh = None
        current_bl_obj = None

        skip = True

        for bl_obj in filtered_objects_with_dg:

            current_bl_obj = bl_obj

            if current_bl_obj.type == 'META' and current_bl_obj.data == current_bl_meta:

                skip = False

                dg = bpy.context.evaluated_depsgraph_get()
                obj_eval = current_bl_obj.evaluated_get(dg)
                current_bl_mesh = bpy.data.meshes.new_from_object(obj_eval)

                if current_bl_mesh is not None:
                    current_bl_mesh.name = bl_meta.name
                    current_bl_mesh[TO_MESH_SOURCE_CUSTOM_PROP] = current_bl_obj
                    temporary_meshes.append(current_bl_mesh)
                else:
                    skip = True

                break

        if skip:
            continue

        filtered_meshes.append(current_bl_mesh)
        filtered_vertex_groups[getPtr(bl_meta)] = current_bl_obj.vertex_groups


    exportSettings['filtered_curves'] = filtered_curves
    exportSettings['filtered_meshes'] = filtered_meshes
    exportSettings['filtered_vertex_groups'] = filtered_vertex_groups
    exportSettings['temporary_meshes'] = temporary_meshes

    # MATERIALS

    filtered_materials = []
    temporary_materials = []

    for bl_mat in getUsedMaterials():

        if bl_mat.users == 0:
            continue

        for bl_mesh in filtered_meshes:
            for mat in bl_mesh.materials:
                if mat == bl_mat and mat not in filtered_materials:
                    filtered_materials.append(mat)

        for bl_obj in filtered_objects_with_dg:
            if bl_obj.material_slots:
                for bl_material_slot in bl_obj.material_slots:
                    if bl_material_slot.link == 'DATA':
                        continue

                    mat = bl_material_slot.material
                    if mat == bl_mat and mat not in filtered_materials:
                        filtered_materials.append(mat)

        for bl_curve in filtered_curves:
            for mat in bl_curve.materials:
                if mat == bl_mat and mat not in filtered_materials:
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
        for bl_mat in filtered_materials:
            mat_type = getMaterialType(bl_mat)
            if mat_type == 'CYCLES':
                if (group not in filtered_node_groups and
                        group in extractMaterialNodeTrees(bl_mat.node_tree)):
                    filtered_node_groups.append(group)

    exportSettings['filtered_node_groups'] = filtered_node_groups

    filtered_textures = []

    for bl_mat in filtered_materials:
        # PBR, CYCLES materials
        if bl_mat.node_tree and bl_mat.use_nodes:
            for bl_node in bl_mat.node_tree.nodes:
                if (isinstance(bl_node, (bpy.types.ShaderNodeTexImage, bpy.types.ShaderNodeTexEnvironment)) and
                        getTexImage(bl_node) is not None and
                        getTexImage(bl_node).users != 0 and
                        getTexImage(bl_node).size[0] > 0 and
                        getTexImage(bl_node).size[1] > 0 and
                        bl_node not in filtered_textures):
                    filtered_textures.append(bl_node)

    for node_group in filtered_node_groups:
        for bl_node in node_group.nodes:
            if (isinstance(bl_node, (bpy.types.ShaderNodeTexImage, bpy.types.ShaderNodeTexEnvironment)) and
                    getTexImage(bl_node) is not None and
                    getTexImage(bl_node).users != 0 and
                    getTexImage(bl_node).size[0] > 0 and
                    getTexImage(bl_node).size[1] > 0 and
                    bl_node not in filtered_textures):
                filtered_textures.append(bl_node)

    exportSettings['filtered_textures'] = filtered_textures

    filtered_images = []

    for bl_texture in filtered_textures:

        img = (getTexImage(bl_texture) if isinstance(bl_texture,
                (bpy.types.ShaderNodeTexImage, bpy.types.ShaderNodeTexEnvironment))
                else getTexImage(bl_texture.texture))

        if (img is not None and img not in filtered_images and img.users != 0
                and img.size[0] > 0 and img.size[1] > 0):
            filtered_images.append(img)

    exportSettings['filtered_images'] = filtered_images


    filtered_cameras = []

    for bl_camera in bpy.data.cameras:

        if bl_camera.users == 0:
            continue

        filtered_cameras.append(bl_camera)

    exportSettings['filtered_cameras'] = filtered_cameras


    filtered_lights = []

    for bl_light in bpy.data.lights:

        if bl_light.users == 0:
            continue

        if bl_light.type == 'AREA':
            continue

        filtered_lights.append(bl_light)

    exportSettings['filtered_lights'] = filtered_lights

    joint_indices = {}

    if exportSettings['skins']:
        for bl_obj in filtered_objects_with_dg:

            if bl_obj.type != 'MESH':
                continue

            armature_object = findArmature(bl_obj)
            if armature_object is None or len(armature_object.pose.bones) == 0:
                continue

            grp = joint_indices[bl_obj.data.name] = {}

            for bl_bone in armature_object.pose.bones:
                grp[bl_bone.name] = len(grp)

    exportSettings['joint_indices'] = joint_indices
