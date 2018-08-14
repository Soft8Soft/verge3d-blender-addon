# Copyright (c) 2017 The Khronos Group Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#
# Imports
#

import bpy

from .gltf2_get import *
from .gltf2_extract import *
from .utils import *

#
# Globals
#

TO_MESH_SOURCE_CUSTOM_PROP = "v3d_to_mesh_source_object"

#
# Functions
#

def filter_apply(export_settings):
    """
    Gathers and filters the objects and assets to export.
    Also filters out invalid, deleted and not exportable elements.
    """
    filtered_objects_shallow = []
    filtered_objects_with_dg = []

    for blender_object in bpy.data.objects:
        
        if blender_object.users == 0:
            continue

        if not is_on_exported_layer(blender_object):
            continue
        
        filtered_objects_shallow.append(blender_object)

        # handle dupli groups
        if blender_object not in filtered_objects_with_dg:
            filtered_objects_with_dg.append(blender_object)
                    
        if blender_object.dupli_type == 'GROUP' and blender_object.dupli_group != None:
            for blender_dupli_object in blender_object.dupli_group.objects:

                if not is_dupli_obj_visible_in_group(blender_object.dupli_group, 
                        blender_dupli_object):
                    continue

                if blender_dupli_object not in filtered_objects_with_dg:
                    filtered_objects_with_dg.append(blender_dupli_object)
        
    export_settings['filtered_objects_shallow'] = filtered_objects_shallow
    export_settings['filtered_objects_with_dg'] = filtered_objects_with_dg
    
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

                use_auto_smooth = current_blender_mesh.use_auto_smooth
                if use_auto_smooth and current_blender_mesh.shape_keys is not None:
                    use_auto_smooth = False
                    
                    printLog('WARNING', 'Auto smooth and shape keys cannot' 
                            + ' be exported in parallel. Falling back to non auto smooth.')

                need_triangulation = False
                if current_blender_mesh.uv_layers.active and len(current_blender_mesh.uv_layers) > 0:
                    for poly in current_blender_mesh.polygons:
                        if poly.loop_total > 4:
                            need_triangulation = True

                got_modifiers = False
                for mod in current_blender_object.modifiers:
                    if mod.show_render:
                        got_modifiers = True
                
                if (got_modifiers and export_settings['gltf_bake_modifiers']) or use_auto_smooth or need_triangulation:

                    copy_obj = current_blender_object.copy()

                    # don't apply the ARMATURE modifier, which is always 
                    # used for a skinned mesh
                    for mod in copy_obj.modifiers:
                        if mod.type == 'ARMATURE':
                            copy_obj.modifiers.remove(mod)

                    if use_auto_smooth:
                        copy_obj.modifiers.clear()
                    
                    if use_auto_smooth:
                        blender_modifier = copy_obj.modifiers.new('Temporary_Auto_Smooth', 'EDGE_SPLIT')
                    
                        blender_modifier.split_angle = current_blender_mesh.auto_smooth_angle
                        blender_modifier.use_edge_angle = current_blender_mesh.has_custom_normals == False

                    if need_triangulation:
                        blender_modifier = copy_obj.modifiers.new('Temporary_Triangulation', 'TRIANGULATE')
                        # seems to produce smoother results
                        blender_modifier.ngon_method = 'CLIP'

                    current_blender_mesh = copy_obj.to_mesh(bpy.context.scene, True, 'PREVIEW', calc_tessface=True)
                    if current_blender_mesh is not None:
                        current_blender_mesh[TO_MESH_SOURCE_CUSTOM_PROP] = current_blender_object
                        temporary_meshes.append(current_blender_mesh)
                    else:
                        skip = True

                    bpy.data.objects.remove(copy_obj)
                
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
        if isinstance(bl_curve, bpy.types.TextCurve) and not export_settings['gltf_bake_text']:
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
                    
                    if not export_settings['gltf_bake_modifiers']:
                        copy_obj.modifiers.clear()
                    
                    current_blender_mesh = copy_obj.to_mesh(bpy.context.scene, True, 'PREVIEW')
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
    
            
    export_settings['filtered_curves'] = filtered_curves
    export_settings['filtered_meshes'] = filtered_meshes
    export_settings['filtered_vertex_groups'] = filtered_vertex_groups
    export_settings['temporary_meshes'] = temporary_meshes
    
    # MATERIALS

    filtered_materials = []

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
                    
    export_settings['filtered_materials'] = filtered_materials                

    filtered_node_groups = []
    for group in bpy.data.node_groups:
        if group.users == 0:
            continue

        # only groups used by 'NODE' and 'CYCLES' materials
        for bl_material in filtered_materials:
            mat_type = get_material_type(bl_material)
            if mat_type == 'NODE' or mat_type == 'CYCLES':
                if (group not in filtered_node_groups and
                        group in extract_material_node_trees(bl_material.node_tree)):
                    filtered_node_groups.append(group)

    export_settings['filtered_node_groups'] = filtered_node_groups
    

    filtered_textures = []
    
    for blender_material in filtered_materials:
        # PBR, NODE, CYCLES materials
        if blender_material.node_tree and blender_material.use_nodes:
            for bl_node in blender_material.node_tree.nodes:
                if (isinstance(bl_node, (bpy.types.ShaderNodeTexImage, bpy.types.ShaderNodeTexEnvironment)) and 
                        get_tex_image(bl_node) is not None and 
                        get_tex_image(bl_node).users != 0 and
                        get_tex_image(bl_node).size[0] > 0 and
                        get_tex_image(bl_node).size[1] > 0 and
                        bl_node not in filtered_textures):
                    filtered_textures.append(bl_node)

                elif (isinstance(bl_node, bpy.types.ShaderNodeTexture) and 
                        bl_node.texture is not None and 
                        get_tex_image(bl_node.texture) is not None and
                        get_tex_image(bl_node.texture).users != 0 and
                        get_tex_image(bl_node.texture).size[0] > 0 and
                        get_tex_image(bl_node.texture).size[1] > 0 and
                        bl_node not in filtered_textures):
                    filtered_textures.append(bl_node)
        # BASIC materials
        else:
            for blender_texture_slot in blender_material.texture_slots:

                if (blender_texture_slot is not None and
                        blender_texture_slot.texture and
                        blender_texture_slot.texture.users != 0 and
                        blender_texture_slot.texture.type == 'IMAGE' and
                        get_tex_image(blender_texture_slot.texture) is not None and
                        get_tex_image(blender_texture_slot.texture).users != 0 and
                        get_tex_image(blender_texture_slot.texture).size[0] > 0 and
                        get_tex_image(blender_texture_slot.texture).size[1] > 0):

                    # NOTE: removed blender_texture_slot.name not in temp_filtered_texture_names

                    if blender_texture_slot not in filtered_textures:
                        accept = False
                        
                        if blender_texture_slot.use_map_color_diffuse:
                            accept = True
                        if blender_texture_slot.use_map_alpha:
                            accept = True
                        if blender_texture_slot.use_map_color_spec:
                            accept = True

                        if blender_texture_slot.use_map_emit:
                            accept = True
                        if blender_texture_slot.use_map_normal:
                            accept = True

                        if export_settings['gltf_displacement']:
                            if blender_texture_slot.use_map_displacement:
                                accept = True
                            
                        if accept:
                            filtered_textures.append(blender_texture_slot)

    for node_group in filtered_node_groups:
        for bl_node in node_group.nodes:
            if (isinstance(bl_node, bpy.types.ShaderNodeTexture) and 
                    bl_node.texture is not None and 
                    get_tex_image(bl_node.texture) is not None and 
                    bl_node not in filtered_textures):
                filtered_textures.append(bl_node)

    curr_world = bpy.context.scene.world

    if curr_world is not None and export_settings['gltf_format'] != 'FB':
        # append environment map from world
        
        slot = get_world_first_valid_texture_slot(curr_world)

        if slot is not None and slot not in filtered_textures:
            filtered_textures.append(slot)

        # append cycles environment texture
        envTexNode = getWorldCyclesEnvTexture(curr_world)
        if envTexNode is not None and envTexNode not in filtered_textures:
            filtered_textures.append(envTexNode)

    export_settings['filtered_textures'] = filtered_textures

    filtered_images = []

    for blender_texture in filtered_textures:

        img = (get_tex_image(blender_texture) if isinstance(blender_texture, 
                (bpy.types.ShaderNodeTexImage, bpy.types.ShaderNodeTexEnvironment)) 
                else get_tex_image(blender_texture.texture))

        if (img is not None and img not in filtered_images and img.users != 0 
                and img.size[0] > 0 and img.size[1] > 0):
            filtered_images.append(img)

    export_settings['filtered_images'] = filtered_images
    

    filtered_cameras = []
    
    for blender_camera in bpy.data.cameras:
        
        if blender_camera.users == 0:
            continue
        
        filtered_cameras.append(blender_camera)

    export_settings['filtered_cameras'] = filtered_cameras

    #
    #
    
    filtered_lights = []
    
    for blender_light in bpy.data.lamps:
        
        if blender_light.users == 0:
            continue

        if blender_light.type == 'AREA':
            continue

        filtered_lights.append(blender_light)
                
    export_settings['filtered_lights'] = filtered_lights

    #
    #
    
    filtered_lights_pbr = []
    
    for blender_light in bpy.data.lamps:
        
        if blender_light.users == 0:
            continue

        if blender_light.type == 'AREA':
            continue

        if not blender_light.use_nodes or blender_light.node_tree is None:
            continue
        
        add_light = False
        
        for blender_node in blender_light.node_tree.nodes:
            if isinstance(blender_node, bpy.types.ShaderNodeGroup):
                if blender_node.node_tree.name.startswith('glTF Directional Light') or blender_node.node_tree.name.startswith('glTF Point Light') or blender_node.node_tree.name.startswith('glTF Spot Light'):
                    add_light = True
                    break 

        if add_light:
            filtered_lights_pbr.append(blender_light)
                
    export_settings['filtered_lights_pbr'] = filtered_lights_pbr
    
    

    joint_indices = {}

    if export_settings['gltf_skins']:
        for blender_object in filtered_objects_with_dg:

            if blender_object.type != 'MESH':
                continue

            armature_object = blender_object.find_armature()
            if armature_object is None or len(armature_object.pose.bones) == 0:
                continue
            
            grp = joint_indices[blender_object.data.name] = {}

            for blender_bone in armature_object.pose.bones:
                grp[blender_bone.name] = len(grp)

    export_settings['joint_indices'] = joint_indices
