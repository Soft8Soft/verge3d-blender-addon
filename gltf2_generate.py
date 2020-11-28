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

import base64
import bpy
import copy
import json
import math
import pathlib
import os.path
import shutil

join = os.path.join
norm = os.path.normpath

from pluginUtils.log import printLog
import pluginUtils.gltf as gltf

from .gltf2_animate import *
from .gltf2_extract import *
from .gltf2_filter import *
from .gltf2_get import *
from .utils import *


# Blender default grey color
DEFAULT_COLOR = [0.041, 0.041, 0.041]
PRIMITIVE_MODE_LINES = 1
PRIMITIVE_MODE_TRIANGLES = 4

PROXY_NODE_PREFIX = 'v3d_Proxy_Node_{idx}_{name}'

SPOT_SHADOW_MIN_NEAR = 0.01

CAM_ANGLE_EPSILON = math.pi / 180

# some small offset to be added to the alphaCutoff option, it's needed bcz
# Blender uses the "less or equal" condition for clipping values, but the engine
# uses just "less"
ALPHA_CUTOFF_EPS = 1e-4

SUN_DEFAULT_NEAR = 0.1
SUN_DEFAULT_FAR = 100
MAX_SHADOW_CAM_FAR = 10000

PMREM_SIZE_MIN = 256
PMREM_SIZE_MAX = 1024


def generateAsset(operator, context, exportSettings, glTF):
    """
    Generates the top level asset entry.
    """

    asset = {}

    asset['version'] = '2.0'
    asset['generator'] = 'Soft8Soft Verge3D for Blender add-on'

    if exportSettings['copyright'] != "":
        asset['copyright'] = exportSettings['copyright']

    glTF['asset'] = asset

def generateAnimChannel(glTF, blObject, samplerName, path, nodeName, samplers, channels):

    channel = gltf.createAnimChannel(getIndex(samplers, samplerName), gltf.getNodeIndex(glTF, nodeName), path)
    # to resolve default animation params
    channel['bl_obj'] = blObject

    channels.append(channel)

    return channel

def generateAnimationsParameter(operator,
                  context,
                  exportSettings,
                  glTF,
                  action,
                  channels,
                  samplers,
                  bl_obj,
                  bl_bone_name,
                  bl_mat_name,
                  bl_mat_node_name,
                  rotation_mode,
                  matrix_correction,
                  matrix_basis,
                  is_morph_data):
    """
    Helper function for storing animation parameters.
    """

    bl_node_name = bl_obj.name

    prefix = ""
    postfix = ""

    location = [None, None, None]
    rotation_axis_angle = [None, None, None, None]
    rotation_euler = [None, None, None]
    rotation_quaternion = [None, None, None, None]
    scale = [None, None, None]
    value = []
    # for material node animation
    default_value = [None]
    energy = [None]

    data = {
        'location' : location,
        'rotation_axis_angle' : rotation_axis_angle,
        'rotation_euler' : rotation_euler,
        'rotation_quaternion' : rotation_quaternion,
        'scale' : scale,
        'value' : value,
        'default_value': default_value,
        'energy': energy
    }

    node_type = 'NODE'
    used_node_name = bl_node_name

    if bl_obj.type == 'CAMERA' or bl_obj.type == 'LIGHT' or bl_obj.type == 'CURVE':
        node_type = 'NODE_X_90'

    if bl_bone_name != None:
        node_type = 'JOINT'
        used_node_name = bl_bone_name
    elif bl_mat_node_name != None:
        node_type = 'MAT_NODE'
        used_node_name = bl_mat_node_name
        default_value *= getAnimParamDim(action.fcurves, used_node_name)

    # gather fcurves in data dict
    for bl_fcurve in action.fcurves:
        node_name = getNameInBrackets(bl_fcurve.data_path)

        if node_name != None and not is_morph_data:
            if (node_type == 'JOINT' or node_type == 'MAT_NODE') and used_node_name != node_name:
                continue
            elif node_type == 'NODE' or node_type == 'NODE_X_90':
                continue
            else:
                prefix = node_name + "_"
                postfix = "_"  + node_name

        data_path = getAnimParam(bl_fcurve.data_path)

        if (data_path not in ['location', 'rotation_axis_angle', 'rotation_euler',
                'rotation_quaternion', 'scale', 'value', 'default_value', 'energy']):
            continue

        if data_path != 'value':
            data[data_path][bl_fcurve.array_index] = bl_fcurve
        else:
            data[data_path].append(bl_fcurve)


    # create location sampler

    if location.count(None) < 3:

        sampler_name = prefix + action.name + "_translation"

        if getIndex(samplers, sampler_name) == -1:

            sampler = {}

            interpolation = animateGetInterpolation(exportSettings, location)
            if interpolation == 'CUBICSPLINE' and node_type == 'JOINT':
                interpolation = 'CONVERSION_NEEDED'

            sampler['interpolation'] = interpolation
            if interpolation == 'CONVERSION_NEEDED':
                sampler['interpolation'] = 'LINEAR'

            translation_data, in_tangent_data, out_tangent_data = animateLocation(
                    exportSettings, location, interpolation, node_type, used_node_name,
                    matrix_correction, matrix_basis)


            keys = sorted(translation_data.keys())
            values = []
            final_keys = []

            key_offset = 0.0
            if len(keys) > 0 and exportSettings['move_keyframes']:
                key_offset = bpy.context.scene.frame_start / bpy.context.scene.render.fps

            for key in keys:
                if key - key_offset < 0.0:
                    continue

                final_keys.append(key - key_offset)

                if interpolation == 'CUBICSPLINE':
                    for i in range(0, 3):
                        values.append(in_tangent_data[key][i])
                for i in range(0, 3):
                    values.append(translation_data[key][i])
                if interpolation == 'CUBICSPLINE':
                    for i in range(0, 3):
                        values.append(out_tangent_data[key][i])


            componentType = "FLOAT"
            count = len(final_keys)
            type = "SCALAR"

            input = gltf.generateAccessor(glTF, exportSettings['binary'],
                    final_keys, componentType, count, type, '')

            sampler['input'] = input


            componentType = "FLOAT"
            count = len(values) // 3
            type = "VEC3"

            output = gltf.generateAccessor(glTF, exportSettings['binary'],
                    values, componentType, count, type, "")

            sampler['output'] = output
            sampler['name'] = sampler_name

            samplers.append(sampler)

    # create rotation sampler

    rotation_data = None
    rotation_in_tangent_data = [0.0, 0.0, 0.0, 0.0]
    rotation_out_tangent_data = [0.0, 0.0, 0.0, 0.0]
    interpolation = None

    sampler_name = prefix + action.name + "_rotation"

    if getIndex(samplers, sampler_name) == -1:
        if rotation_axis_angle.count(None) < 4:
            interpolation = animateGetInterpolation(exportSettings, rotation_axis_angle)
            # conversion required in any case
            if interpolation == 'CUBICSPLINE':
                interpolation = 'CONVERSION_NEEDED'
            rotation_data = animateRotationAxisAngle(exportSettings, rotation_axis_angle, interpolation, node_type, used_node_name, matrix_correction, matrix_basis)

        if rotation_euler.count(None) < 3:
            interpolation = animateGetInterpolation(exportSettings, rotation_euler)
            # conversion required in any case
            # also for linear interpolation to fix issues with e.g 2*PI keyframe differences
            if interpolation == 'CUBICSPLINE' or interpolation == 'LINEAR':
                interpolation = 'CONVERSION_NEEDED'
            rotation_data = animateRotationEuler(exportSettings, rotation_euler, rotation_mode, interpolation, node_type, used_node_name, matrix_correction, matrix_basis)

        if rotation_quaternion.count(None) < 4:
            interpolation = animateGetInterpolation(exportSettings, rotation_quaternion)
            if interpolation == 'CUBICSPLINE' and node_type == 'JOINT':
                interpolation = 'CONVERSION_NEEDED'
            rotation_data, rotation_in_tangent_data, rotation_out_tangent_data = animateRotationQuaternion(exportSettings, rotation_quaternion, interpolation, node_type, used_node_name, matrix_correction, matrix_basis)

    if rotation_data is not None:
        keys = sorted(rotation_data.keys())
        values = []
        final_keys = []

        key_offset = 0.0
        if len(keys) > 0 and exportSettings['move_keyframes']:
            key_offset = bpy.context.scene.frame_start / bpy.context.scene.render.fps

        for key in keys:
            if key - key_offset < 0.0:
                continue

            final_keys.append(key - key_offset)

            if interpolation == 'CUBICSPLINE':
                for i in range(0, 4):
                    values.append(rotation_in_tangent_data[key][i])
            for i in range(0, 4):
                values.append(rotation_data[key][i])
            if interpolation == 'CUBICSPLINE':
                for i in range(0, 4):
                    values.append(rotation_out_tangent_data[key][i])


        sampler = {}

        componentType = "FLOAT"
        count = len(final_keys)
        type = "SCALAR"

        input = gltf.generateAccessor(glTF, exportSettings['binary'], final_keys, componentType, count, type, "")

        sampler['input'] = input

        componentType = "FLOAT"
        count = len(values) // 4
        type = "VEC4"

        output = gltf.generateAccessor(glTF, exportSettings['binary'], values, componentType, count, type, "")

        sampler['output'] = output

        sampler['interpolation'] = interpolation
        if interpolation == 'CONVERSION_NEEDED':
            sampler['interpolation'] = 'LINEAR'

        sampler['name'] = sampler_name

        samplers.append(sampler)

    # create scale sampler

    if scale.count(None) < 3:
        sampler_name = prefix + action.name + "_scale"

        if getIndex(samplers, sampler_name) == -1:

            sampler = {}



            interpolation = animateGetInterpolation(exportSettings, scale)
            if interpolation == 'CUBICSPLINE' and node_type == 'JOINT':
                interpolation = 'CONVERSION_NEEDED'

            sampler['interpolation'] = interpolation
            if interpolation == 'CONVERSION_NEEDED':
                sampler['interpolation'] = 'LINEAR'

            scale_data, in_tangent_data, out_tangent_data = animateScale(exportSettings, scale, interpolation, node_type, used_node_name, matrix_correction, matrix_basis)



            keys = sorted(scale_data.keys())
            values = []
            final_keys = []

            key_offset = 0.0
            if len(keys) > 0 and exportSettings['move_keyframes']:
                key_offset = bpy.context.scene.frame_start / bpy.context.scene.render.fps

            for key in keys:
                if key - key_offset < 0.0:
                    continue

                final_keys.append(key - key_offset)

                if interpolation == 'CUBICSPLINE':
                    for i in range(0, 3):
                        values.append(in_tangent_data[key][i])
                for i in range(0, 3):
                    values.append(scale_data[key][i])
                if interpolation == 'CUBICSPLINE':
                    for i in range(0, 3):
                        values.append(out_tangent_data[key][i])



            componentType = "FLOAT"
            count = len(final_keys)
            type = "SCALAR"

            input = gltf.generateAccessor(glTF, exportSettings['binary'], final_keys, componentType, count, type, "")

            sampler['input'] = input



            componentType = "FLOAT"
            count = len(values) // 3
            type = "VEC3"

            output = gltf.generateAccessor(glTF, exportSettings['binary'], values, componentType, count, type, "")

            sampler['output'] = output



            sampler['name'] = sampler_name

            samplers.append(sampler)

    # create morph target sampler

    if len(value) > 0 and is_morph_data:
        sampler_name = prefix + action.name + "_weights"

        if getIndex(samplers, sampler_name) == -1:

            sampler = {}



            interpolation = animateGetInterpolation(exportSettings, value)
            if interpolation == 'CUBICSPLINE' and node_type == 'JOINT':
                interpolation = 'CONVERSION_NEEDED'

            sampler['interpolation'] = interpolation
            if interpolation == 'CONVERSION_NEEDED':
                sampler['interpolation'] = 'LINEAR'

            value_data, in_tangent_data, out_tangent_data = animateValue(exportSettings, value, interpolation, node_type, used_node_name, matrix_correction, matrix_basis)



            keys = sorted(value_data.keys())
            values = []
            final_keys = []

            key_offset = 0.0
            if len(keys) > 0 and exportSettings['move_keyframes']:
                key_offset = bpy.context.scene.frame_start / bpy.context.scene.render.fps

            for key in keys:
                if key - key_offset < 0.0:
                    continue

                final_keys.append(key - key_offset)

                if interpolation == 'CUBICSPLINE':
                    for i in range(0, len(in_tangent_data[key])):
                        values.append(in_tangent_data[key][i])
                for i in range(0, len(value_data[key])):
                    values.append(value_data[key][i])
                if interpolation == 'CUBICSPLINE':
                    for i in range(0, len(out_tangent_data[key])):
                        values.append(out_tangent_data[key][i])



            componentType = "FLOAT"
            count = len(final_keys)
            type = "SCALAR"

            input = gltf.generateAccessor(glTF, exportSettings['binary'], final_keys, componentType, count, type, "")

            sampler['input'] = input



            componentType = "FLOAT"
            count = len(values)
            type = "SCALAR"

            output = gltf.generateAccessor(glTF, exportSettings['binary'], values, componentType, count, type, "")

            sampler['output'] = output



            sampler['name'] = sampler_name

            samplers.append(sampler)

    # create material node anim sampler
    def_val_dim = len(default_value)

    # NOTE: only value/colors supported for now
    if (def_val_dim == 1 or def_val_dim == 4) and default_value.count(None) < def_val_dim:
        sampler_name = prefix + action.name + "_mat_node_anim"

        if getIndex(samplers, sampler_name) == -1:

            sampler = {}

            interpolation = animateGetInterpolation(exportSettings, default_value)
            sampler['interpolation'] = interpolation

            if interpolation == 'CONVERSION_NEEDED':
                sampler['interpolation'] = 'LINEAR'

            def_val_data, in_tangent_data, out_tangent_data = animateDefaultValue(exportSettings,
                    default_value, interpolation)

            keys = sorted(def_val_data.keys())
            values = []
            final_keys = []

            key_offset = 0.0
            if len(keys) > 0 and exportSettings['move_keyframes']:
                key_offset = bpy.context.scene.frame_start / bpy.context.scene.render.fps

            for key in keys:
                if key - key_offset < 0.0:
                    continue

                final_keys.append(key - key_offset)

                if interpolation == 'CUBICSPLINE':
                    for i in range(0, def_val_dim):
                        values.append(in_tangent_data[key][i])
                for i in range(0, def_val_dim):
                    values.append(def_val_data[key][i])
                if interpolation == 'CUBICSPLINE':
                    for i in range(0, def_val_dim):
                        values.append(out_tangent_data[key][i])

            componentType = "FLOAT"
            count = len(final_keys)
            type = "SCALAR"

            input = gltf.generateAccessor(glTF, exportSettings['binary'],
                    final_keys, componentType, count, type, "")

            sampler['input'] = input


            componentType = "FLOAT"
            count = len(values) // def_val_dim
            if def_val_dim == 1:
                type = "SCALAR"
            else:
                type = "VEC4"

            output = gltf.generateAccessor(glTF, exportSettings['binary'],
                    values, componentType, count, type, "")

            sampler['output'] = output
            sampler['name'] = sampler_name

            samplers.append(sampler)

    if energy.count(None) < 1:
        sampler_name = prefix + action.name + '_energy'

        if getIndex(samplers, sampler_name) == -1:

            sampler = {}

            interpolation = animateGetInterpolation(exportSettings, energy)
            sampler['interpolation'] = interpolation

            if interpolation == 'CONVERSION_NEEDED':
                sampler['interpolation'] = 'LINEAR'

            energy_data, in_tangent_data, out_tangent_data = animateEnergy(exportSettings,
                    energy, interpolation)

            keys = sorted(energy_data.keys())
            values = []
            final_keys = []

            key_offset = 0.0
            if len(keys) > 0 and exportSettings['move_keyframes']:
                key_offset = bpy.context.scene.frame_start / bpy.context.scene.render.fps

            for key in keys:
                if key - key_offset < 0.0:
                    continue

                final_keys.append(key - key_offset)

                if interpolation == 'CUBICSPLINE':
                    values.append(in_tangent_data[key][0])
                values.append(energy_data[key][0])
                if interpolation == 'CUBICSPLINE':
                    values.append(out_tangent_data[key][0])

            componentType = "FLOAT"
            count = len(final_keys)
            type = "SCALAR"

            input = gltf.generateAccessor(glTF, exportSettings['binary'],
                    final_keys, componentType, count, type, "")

            sampler['input'] = input

            componentType = "FLOAT"
            count = len(values)
            type = "SCALAR"

            output = gltf.generateAccessor(glTF, exportSettings['binary'],
                    values, componentType, count, type, "")

            sampler['output'] = output
            sampler['name'] = sampler_name

            samplers.append(sampler)



    processed_paths = []

    # gather fcurves in data dict
    for bl_fcurve in action.fcurves:
        node_name = getNameInBrackets(bl_fcurve.data_path)

        if node_name != None and not is_morph_data:
            if (node_type == 'JOINT' or node_type == 'MAT_NODE') and used_node_name != node_name:
                continue
            elif node_type == 'NODE' or node_type == 'NODE_X_90':
                continue
            else:
                prefix = node_name + "_"
                postfix = "_"  + node_name

        data_path = getAnimParam(bl_fcurve.data_path)

        if data_path == 'location':
            path = 'translation'
            if path in processed_paths:
                continue
            processed_paths.append(path)

            sampler_name = prefix + action.name + '_' + path
            generateAnimChannel(glTF, bl_obj, sampler_name, path, bl_node_name + postfix, samplers, channels)
        elif (data_path == 'rotation_axis_angle' or data_path == 'rotation_euler' or
                data_path == 'rotation_quaternion'):
            path = 'rotation'
            if path in processed_paths:
                continue
            processed_paths.append(path)

            sampler_name = prefix + action.name + '_'  + path
            generateAnimChannel(glTF, bl_obj, sampler_name, path, bl_node_name + postfix, samplers, channels)
        elif data_path == 'scale':
            path = 'scale'
            if path in processed_paths:
                continue
            processed_paths.append(path)

            sampler_name = prefix + action.name + '_'  + path
            generateAnimChannel(glTF, bl_obj, sampler_name, path, bl_node_name + postfix, samplers, channels)
        elif data_path == 'value':
            path = 'weights'
            if path in processed_paths:
                continue
            processed_paths.append(path)

            sampler_name = prefix + action.name + '_'  + path
            generateAnimChannel(glTF, bl_obj, sampler_name, path, bl_node_name + postfix, samplers, channels)
        elif data_path == 'default_value':
            if def_val_dim == 1:
                path = 'material.nodeValue["' + used_node_name + '"]'
            else:
                path = 'material.nodeRGB["' + used_node_name + '"]'
            if path in processed_paths:
                continue
            processed_paths.append(path)
            sampler_name = prefix + action.name + '_mat_node_anim'

            channel = generateAnimChannel(glTF, bl_obj, sampler_name, path, bl_node_name, samplers, channels)

            if bl_mat_name != None:
                channel['target']['extras'] = {
                    'material': gltf.getMaterialIndex(glTF, bl_mat_name)
                }

        elif data_path == 'energy':
            path = 'intensity'
            if path in processed_paths:
                continue
            processed_paths.append(path)

            sampler_name = prefix + action.name + '_energy'
            generateAnimChannel(glTF, bl_obj, sampler_name, path, bl_node_name, samplers, channels)



#
# Property: animations
#
def generateAnimations(operator, context, exportSettings, glTF):
    """
    Generates the top level animations, channels and samplers entry.
    """

    animations = []
    channels = []
    samplers = []

    filtered_objects_with_dg = exportSettings['filtered_objects_with_dg']

    bl_backup_action = {}

    if exportSettings['bake_armature_actions']:

        start = None
        end = None

        for current_bl_action in bpy.data.actions:
            # filter out non-object actions
            if current_bl_action.id_root != 'OBJECT':
                continue
            for current_bl_fcurve in current_bl_action.fcurves:
                if current_bl_fcurve is None:
                    continue

                if start == None:
                    start = current_bl_fcurve.range()[0]
                else:
                    start = min(start, current_bl_fcurve.range()[0])

                if end == None:
                    end = current_bl_fcurve.range()[1]
                else:
                    end = max(end, current_bl_fcurve.range()[1])

        if start is None or end is None or exportSettings['frame_range']:
            start = bpy.context.scene.frame_start
            end = bpy.context.scene.frame_end



        for bl_obj in filtered_objects_with_dg:
            if bl_obj.animation_data is not None:
                bl_backup_action[bl_obj.name] = bl_obj.animation_data.action

            if bl_obj.pose is None:
                continue

            obj_scene = getSceneByObject(bl_obj)
            if obj_scene is not None:

                prev_active_scene = bpy.context.scene
                bpy.context.window.scene = obj_scene

                setSelectedObject(bl_obj)

                bpy.ops.nla.bake(frame_start=start, frame_end=end,
                        only_selected=False, visual_keying=True)

                restoreSelectedObjects()

                bpy.context.window.scene = prev_active_scene




    for bl_obj in filtered_objects_with_dg:
        if bl_obj.animation_data is None:
            continue

        bl_action = bl_obj.animation_data.action

        if bl_action is None:
            continue

        generateAnimationsParameter(operator, context, exportSettings, glTF, bl_action,
                channels, samplers, bl_obj, None, None, None, bl_obj.rotation_mode,
                mathutils.Matrix.Identity(4),  mathutils.Matrix.Identity(4), False)

        if exportSettings['skins']:
            if bl_obj.type == 'ARMATURE' and len(bl_obj.pose.bones) > 0:



                # Precalculate joint animation data.

                start = None
                end = None

                for current_bl_action in bpy.data.actions:
                    # filter out non-object actions
                    if current_bl_action.id_root != 'OBJECT':
                        continue

                    for current_bl_fcurve in current_bl_action.fcurves:
                        if current_bl_fcurve is None:
                            continue

                        if start == None:
                            start = current_bl_fcurve.range()[0]
                        else:
                            start = min(start, current_bl_fcurve.range()[0])

                        if end == None:
                            end = current_bl_fcurve.range()[1]
                        else:
                            end = max(end, current_bl_fcurve.range()[1])

                if start is None or end is None:
                    start = bpy.context.scene.frame_start
                    end = bpy.context.scene.frame_end


                for frame in range(int(start), int(end) + 1):
                    bpy.context.scene.frame_set(frame)

                    for bl_bone in bl_obj.pose.bones:

                        matrix_basis = bl_bone.matrix_basis

                        correction_matrix_local = bl_bone.bone.matrix_local.copy()

                        if bl_bone.parent is not None:
                            correction_matrix_local = bl_bone.parent.bone.matrix_local.inverted() @ correction_matrix_local

                        if not exportSettings['joint_cache'].get(bl_bone.name):
                            exportSettings['joint_cache'][bl_bone.name] = {}

                        if exportSettings['bake_armature_actions']:
                            matrix_basis = bl_obj.convert_space(pose_bone=bl_bone, matrix=bl_bone.matrix, from_space='POSE', to_space='LOCAL')

                        matrix = correction_matrix_local @ matrix_basis

                        tmp_location, tmp_rotation, tmp_scale = decomposeTransformSwizzle(matrix)

                        exportSettings['joint_cache'][bl_bone.name][float(frame)] = [tmp_location, tmp_rotation, tmp_scale]

                for bl_bone in bl_obj.pose.bones:

                    matrix_basis = bl_bone.matrix_basis

                    correction_matrix_local = bl_bone.bone.matrix_local.copy()

                    if bl_bone.parent is not None:
                        correction_matrix_local = bl_bone.parent.bone.matrix_local.inverted() @ correction_matrix_local

                    if exportSettings['bake_armature_actions']:
                        matrix_basis = bl_obj.convert_space(pose_bone=bl_bone, matrix=bl_bone.matrix, from_space='POSE', to_space='LOCAL')

                    generateAnimationsParameter(operator, context, exportSettings, glTF,
                            bl_action, channels, samplers, bl_obj, bl_bone.name,
                            None, None, bl_bone.rotation_mode, correction_matrix_local,
                            matrix_basis, False)



    # export morph targets animation data

    processed_meshes = []
    for bl_obj in filtered_objects_with_dg:


        if bl_obj.type != 'MESH' or bl_obj.data is None:
            continue

        bl_mesh = bl_obj.data

        if bl_mesh in processed_meshes:
            continue

        if bl_mesh.shape_keys is None or bl_mesh.shape_keys.animation_data is None:
            continue

        bl_action = bl_mesh.shape_keys.animation_data.action

        if bl_action is None:
            continue


        generateAnimationsParameter(operator, context, exportSettings, glTF, bl_action,
                channels, samplers, bl_obj, None, None, None, bl_obj.rotation_mode,
                mathutils.Matrix.Identity(4), mathutils.Matrix.Identity(4), True)

        processed_meshes.append(bl_mesh)

    # export light animation

    for bl_obj in filtered_objects_with_dg:

        if bl_obj.type != 'LIGHT' or bl_obj.data is None:
            continue

        bl_light = bl_obj.data

        if bl_light.animation_data is None:
            continue

        bl_action = bl_light.animation_data.action

        if bl_action is None:
            continue

        generateAnimationsParameter(operator, context, exportSettings, glTF, bl_action,
                channels, samplers, bl_obj, None, None, None, bl_obj.rotation_mode,
                mathutils.Matrix.Identity(4), mathutils.Matrix.Identity(4), True)


    # export material animation

    for bl_obj in filtered_objects_with_dg:

        # export morph targets animation data.

        if bl_obj.type != 'MESH' or bl_obj.data is None:
            continue

        bl_mesh = bl_obj.data

        for bl_mat in bl_mesh.materials:
            if bl_mat == None:
                continue

            if bl_mat.node_tree == None or bl_mat.node_tree.animation_data == None:
                continue

            bl_action = bl_mat.node_tree.animation_data.action

            if bl_action == None:
                continue

            correction_matrix_local = mathutils.Matrix.Identity(4)
            matrix_basis = mathutils.Matrix.Identity(4)

            node_names = [n.name for n in bl_mat.node_tree.nodes]

            for name in node_names:
                generateAnimationsParameter(operator, context, exportSettings, glTF,
                        bl_action, channels, samplers, bl_obj, None,
                        bl_mat.name, name, bl_obj.rotation_mode,
                        correction_matrix_local, matrix_basis, False)


    if exportSettings['bake_armature_actions']:
        for bl_obj in filtered_objects_with_dg:
            if bl_backup_action.get(bl_obj.name) is not None:
                bl_obj.animation_data.action = bl_backup_action[bl_obj.name]


    if len(channels) > 0 or len(samplers) > 0:

        # collect channel/samplers by node

        anim_data = {}

        for channel in channels:
            bl_obj = channel['bl_obj']
            name = bl_obj.name

            # shallow copy (might be repetitions, need to find out why)
            sampler = samplers[channel['sampler']].copy()

            if not name in anim_data:
                anim_data[name] = [[], [], None]

            # fix sampler index in new array
            channel['sampler'] = len(anim_data[name][1])

            # sampler 'name' is used to gather the index. However, 'name' is
            # no property of sampler and has to be removed.
            del sampler['name']

            anim_data[name][0].append(channel)
            anim_data[name][1].append(sampler)
            anim_data[name][2] = bl_obj

            del channel['bl_obj']

        for name, data in anim_data.items():

            animation = {
                'name': name,
                'channels' : data[0],
                'samplers' : data[1]
            }

            v3dExt = gltf.appendExtension(glTF, 'S8S_v3d_animation_data', animation)

            bl_obj = data[2]
            v3dExt['auto'] = bl_obj.v3d.anim_auto
            v3dExt['loop'] = bl_obj.v3d.anim_loop
            v3dExt['repeatInfinite'] = bl_obj.v3d.anim_repeat_infinite
            v3dExt['repeatCount'] = bl_obj.v3d.anim_repeat_count
            # frame to sec
            v3dExt['offset'] = animateConvertKeys([bl_obj.v3d.anim_offset])[0]

            animations.append(animation)


    if len(animations) > 0:
        glTF['animations'] = animations


def generateCameras(operator, context, exportSettings, glTF):
    """
    Generates the top level cameras entry.
    """

    cameras = []

    filtered_cameras = exportSettings['filtered_cameras']

    activeCam = None
    for bl_camera in filtered_cameras:
        camera = generateCamera(bl_camera, glTF)
        if camera:
            cameras.append(camera)
            if bpy.context.window.scene.camera and bpy.context.window.scene.camera.data == bl_camera:
                activeCam = camera

    if not len(cameras):
        camera = generateCameraFromView(1)
        if camera:
            cameras.append(camera)

    # ensure that the active scene camera will be used for rendering (first one)
    cameras = sorted(cameras, key=lambda cam: cam==activeCam, reverse=True)

    if len(cameras) > 0:
        glTF['cameras'] = cameras

        gltf.appendExtension(glTF, 'S8S_v3d_camera_data')

def generateCamera(bl_camera, glTF):
    camera = {}

    # NOTE: should use a scene where the camera is located for proper calculation
    vf = bl_camera.view_frame(scene=bpy.context.scene)
    aspectRatio = (vf[0].x - vf[2].x) / (vf[0].y - vf[2].y)

    if bl_camera.type == 'PERSP' or bl_camera.type == 'PANO':
        camera['type'] = 'perspective'

        perspective = {}

        perspective['aspectRatio'] = aspectRatio

        yfov = None

        if aspectRatio >= 1:
            if bl_camera.sensor_fit != 'VERTICAL':
                yfov = 2.0 * math.atan(math.tan(bl_camera.angle * 0.5) / aspectRatio)
            else:
                yfov = bl_camera.angle
        else:
            if bl_camera.sensor_fit != 'HORIZONTAL':
                yfov = bl_camera.angle
            else:
                yfov = 2.0 * math.atan(math.tan(bl_camera.angle * 0.5) / aspectRatio)

        perspective['yfov'] = yfov
        perspective['znear'] = bl_camera.clip_start
        perspective['zfar'] = bl_camera.clip_end

        camera['perspective'] = perspective
    elif bl_camera.type == 'ORTHO':
        camera['type'] = 'orthographic'

        orthographic = {}

        orthographic['xmag'] = (vf[0].x - vf[2].x) / 2
        orthographic['ymag'] = (vf[0].y - vf[2].y) / 2

        orthographic['znear'] = bl_camera.clip_start
        orthographic['zfar'] = bl_camera.clip_end

        camera['orthographic'] = orthographic
    else:
        return None


    camera['name'] = bl_camera.name

    v3dExt = {
        'controls' : bl_camera.v3d.controls
    }

    v3dExt['enablePan'] = bl_camera.v3d.enable_pan
    v3dExt['rotateSpeed'] = bl_camera.v3d.rotate_speed
    v3dExt['moveSpeed'] = bl_camera.v3d.move_speed

    v3dExt['viewportFitType'] = bl_camera.sensor_fit
    v3dExt['viewportFitInitialAspect'] = aspectRatio

    # optional orbit params
    if bl_camera.v3d.controls == 'ORBIT':
        target_point = (bl_camera.v3d.orbit_target if bl_camera.v3d.orbit_target_object is None
                else bl_camera.v3d.orbit_target_object.matrix_world.to_translation())

        v3dExt['orbitTarget'] = extractVec(convertSwizzleLocation(target_point))
        v3dExt['orbitMinDistance'] = bl_camera.v3d.orbit_min_distance
        v3dExt['orbitMaxDistance'] = bl_camera.v3d.orbit_max_distance

        v3dExt['orbitMinZoom'] = bl_camera.v3d.orbit_min_zoom
        v3dExt['orbitMaxZoom'] = bl_camera.v3d.orbit_max_zoom

        v3dExt['orbitMinPolarAngle'] = bl_camera.v3d.orbit_min_polar_angle
        v3dExt['orbitMaxPolarAngle'] = bl_camera.v3d.orbit_max_polar_angle

        min_azim_angle = bl_camera.v3d.orbit_min_azimuth_angle
        max_azim_angle = bl_camera.v3d.orbit_max_azimuth_angle

        # export only when needed
        if abs(2 * math.pi - (max_azim_angle - min_azim_angle)) > CAM_ANGLE_EPSILON:
            v3dExt['orbitMinAzimuthAngle'] = bl_camera.v3d.orbit_min_azimuth_angle
            v3dExt['orbitMaxAzimuthAngle'] = bl_camera.v3d.orbit_max_azimuth_angle

    elif bl_camera.v3d.controls == 'FIRST_PERSON':
        v3dExt['fpsGazeLevel'] = bl_camera.v3d.fps_gaze_level
        v3dExt['fpsStoryHeight'] = bl_camera.v3d.fps_story_height

    camera['extensions'] = { 'S8S_v3d_camera_data' : v3dExt }

    return camera

def generateCameraFromView(aspectRatio):

    printLog('INFO', 'Generating default camera')

    region3D = getView3DSpaceProp('region_3d')
    if region3D == None:
        return None

    camera = {}

    camera['name'] = '__DEFAULT__'

    lens = getView3DSpaceProp('lens')
    near = getView3DSpaceProp('clip_start')
    far = getView3DSpaceProp('clip_end')

    if region3D.is_perspective:
        camera['type'] = 'perspective'

        perspective = {}
        camera['perspective'] = perspective

        perspective['aspectRatio'] = aspectRatio
        # NOTE: decent default value
        perspective['yfov'] = math.pi / 4

        perspective['znear'] = near
        perspective['zfar'] = far
    else:
        camera['type'] = 'orthographic'

        orthographic = {}
        camera['orthographic'] = orthographic

        # NOTE: not quite right since far is the range around view point but OK in most cases
        orthographic['znear'] = -far
        orthographic['zfar'] = far

        xmag = 1/region3D.window_matrix[0][0]
        ymag = 1/region3D.window_matrix[1][1]

        orthographic['xmag'] = xmag
        orthographic['ymag'] = ymag

    v3dExt = {}
    camera['extensions'] = { 'S8S_v3d_camera_data' : v3dExt }

    v3dExt['viewportFitType'] = 'VERTICAL'
    v3dExt['viewportFitInitialAspect'] = aspectRatio

    v3dExt['enablePan'] = True
    v3dExt['rotateSpeed'] = 1
    v3dExt['moveSpeed'] = 1

    v3dExt['controls'] = 'ORBIT'

    v3dExt['orbitTarget'] = extractVec(convertSwizzleLocation(region3D.view_location))
    v3dExt['orbitMinDistance'] = 0
    v3dExt['orbitMaxDistance'] = 10000
    v3dExt['orbitMinPolarAngle'] = 0
    v3dExt['orbitMaxPolarAngle'] = math.pi

    return camera

def generateLights(operator, context, exportSettings, glTF):
    """
    Generates the top level lights entry.
    """

    lights = []

    filtered_lights = exportSettings['filtered_lights']

    for bl_light in filtered_lights:

        light = {}
        light['profile'] = 'blender'

        if bl_light.type == 'SUN':
            light['type'] = 'directional'
        elif bl_light.type == 'POINT':
            light['type'] = 'point'
        elif bl_light.type == 'SPOT':
            light['type'] = 'spot'
        else:
            continue

        useShadows = exportSettings['use_shadows'] and bl_light.use_shadow

        if bpy.app.version < (2,81,0):
            cameraNear = bl_light.shadow_buffer_clip_start
            # usability improvement
            if (bl_light.type == 'SPOT' or bl_light.type == 'POINT') and cameraNear < SPOT_SHADOW_MIN_NEAR:
                cameraNear = SPOT_SHADOW_MIN_NEAR
            cameraFar = bl_light.shadow_buffer_clip_end

            orthoSize = bl_light.v3d.shadow.camera_size

            eeveeCtx = context.scene.eevee
            light['shadow'] = {
                'enabled': useShadows,
                'mapSize': int(eeveeCtx.shadow_cascade_size
                        if bl_light.type == 'SUN' else eeveeCtx.shadow_cube_size),

                # used as a shadow size for PCF fallback
                'cameraOrthoLeft': -orthoSize / 2,
                'cameraOrthoRight': orthoSize / 2,
                'cameraOrthoBottom': -orthoSize / 2,
                'cameraOrthoTop': orthoSize / 2,

                'cameraFov': bl_light.spot_size if bl_light.type == 'SPOT' else 0,
                'cameraNear': cameraNear,
                'cameraFar': cameraFar,
                'radius': (bl_light.shadow_buffer_soft if bl_light.type == 'SUN'
                        else getBlurPixelRadius(context, bl_light)),
                # NOTE: negate bias since the negative is more appropriate in most cases
                # but keeping it positive in the UI is more user-friendly
                'bias': -bl_light.shadow_buffer_bias * 0.0018,
                'expBias': bl_light.shadow_buffer_exp
            }

            if bl_light.type == 'SUN':
                light['shadow']['csm'] = {
                    'maxDistance': bl_light.shadow_cascade_max_distance
                }

        else:

            eeveeCtx = context.scene.eevee

            if bl_light.type == 'SUN':
                # NOTE: the following values are not relevant because the engine
                # calculates near/far dynamically for directional shadows
                cameraNear = SUN_DEFAULT_NEAR
                cameraFar = SUN_DEFAULT_FAR

            else:
                cameraNear = max(bl_light.shadow_buffer_clip_start,
                        SPOT_SHADOW_MIN_NEAR) # usability improvement

                # should bl_light.cutoff_distance affect this?
                cameraFar = calcLightThresholdDist(bl_light,
                        eeveeCtx.light_threshold)
                cameraFar = min(cameraFar, MAX_SHADOW_CAM_FAR)

            light['shadow'] = {
                'enabled': useShadows,
                'mapSize': int(eeveeCtx.shadow_cascade_size
                        if bl_light.type == 'SUN' else eeveeCtx.shadow_cube_size),

                'cameraFov': bl_light.spot_size if bl_light.type == 'SPOT' else 0,
                'cameraNear': cameraNear,
                'cameraFar': cameraFar,
                'radius': bl_light.v3d.shadow.radius,
                # NOTE: negate bias since the negative is more appropriate in most cases
                # but keeping it positive in the UI is more user-friendly
                'bias': -bl_light.shadow_buffer_bias * 0.0018,
                # empirical value that gives good results
                'slopeScaledBias': 2.5,
                'expBias': bl_light.v3d.shadow.esm_exponent,
            }

            if bl_light.type == 'SUN':
                light['shadow']['csm'] = {
                    'maxDistance': bl_light.shadow_cascade_max_distance
                }


        if bl_light.type == 'POINT' or bl_light.type == 'SPOT':

            # simplified model
            if bl_light.use_custom_distance:
                dist = bl_light.cutoff_distance
            else:
                dist = calcLightThresholdDist(bl_light, eeveeCtx.light_threshold)
            light['distance'] = dist
            light['decay'] = 2

            # unused "standard" model
            light['constantAttenuation'] = 1.0
            light['linearAttenuation'] = 0.0
            light['quadraticAttenuation'] = 0.0

            if bl_light.falloff_type == 'CONSTANT':
                pass
            elif bl_light.falloff_type == 'INVERSE_LINEAR':
                light['linearAttenuation'] = 1.0 / dist
            elif bl_light.falloff_type == 'INVERSE_SQUARE':
                light['quadraticAttenuation'] = 1.0 / dist
            elif bl_light.falloff_type == 'LINEAR_QUADRATIC_WEIGHTED':
                light['linearAttenuation'] = bl_light.linear_attenuation * (1 / dist)
                light['quadraticAttenuation'] = bl_light.quadratic_attenuation * (1 /
                        (dist * dist))
            elif bl_light.falloff_type == 'INVERSE_COEFFICIENTS':
                light['constantAttenuation'] = bl_light.constant_coefficient
                light['linearAttenuation'] = bl_light.linear_coefficient * (1.0 / dist)
                light['quadraticAttenuation'] = bl_light.quadratic_coefficient * (1.0 /
                        dist)
            else:
                pass


            if bl_light.type == 'SPOT':
                # simplified model
                light['angle'] = bl_light.spot_size / 2;
                light['penumbra'] = bl_light.spot_blend;

                # unused "standard" model
                light['fallOffAngle'] = bl_light.spot_size
                light['fallOffExponent'] = 128.0 * bl_light.spot_blend

        light['color'] = getLightCyclesColor(bl_light)
        light['intensity'] = getLightCyclesStrength(bl_light)

        light['name'] = bl_light.name

        lights.append(light)

    if len(lights) > 0:
        gltf.appendExtension(glTF, 'S8S_v3d_data', glTF, {'lights': lights})


def generateMeshes(operator, context, exportSettings, glTF):
    """
    Generates the top level meshes entry.
    """

    meshes = []

    filtered_meshes = exportSettings['filtered_meshes']

    filtered_vertex_groups = exportSettings['filtered_vertex_groups']

    joint_indices = exportSettings['joint_indices']

    for bl_mesh in filtered_meshes:

        srcDatablock = (bl_mesh.get(TO_MESH_SOURCE_CUSTOM_PROP).data
                if bl_mesh.get(TO_MESH_SOURCE_CUSTOM_PROP) else bl_mesh)
        srcName = srcDatablock.name
        srcPtr = getPtr(srcDatablock)
        is_line = objDataUsesLineRendering(srcDatablock)

        if is_line:
            internal_primitives = extractLinePrimitives(glTF, bl_mesh,
                    exportSettings)
        else:
            internal_primitives = extractPrimitives(glTF, bl_mesh,
                    filtered_vertex_groups[srcPtr], joint_indices.get(srcName, {}),
                    exportSettings)

        if len(internal_primitives) == 0:
            continue


        # Property: mesh


        mesh = {}

        v3dExt = gltf.appendExtension(glTF, 'S8S_v3d_mesh_data', mesh)

        if is_line:
            line_settings = srcDatablock.v3d.line_rendering_settings
            v3dExt['lineColor'] = extractVec(line_settings.color)
            v3dExt['lineWidth'] = line_settings.width

        primitives = []

        for internal_primitive in internal_primitives:

            primitive = {}

            primitive['mode'] = PRIMITIVE_MODE_LINES if is_line else PRIMITIVE_MODE_TRIANGLES

            material = gltf.getMaterialIndex(glTF, internal_primitive['material'])

            # Meshes/primitives without material are allowed.
            if material >= 0:
                primitive['material'] = material
            elif internal_primitive['material'] == DEFAULT_MAT_NAME:
                primitive['material'] = getOrCreateDefaultMatIndex(glTF)
                # it's possible that there were no materials in the scene, so
                # the default one should 'register' the v3d material extension
                gltf.appendExtension(glTF, 'S8S_v3d_material_data')
            else:
                printLog('WARNING', 'Material ' + internal_primitive['material'] + ' not found')
            indices = internal_primitive['indices']

            componentType = "UNSIGNED_BYTE"

            max_index = max(indices)

            # NOTE: avoiding WebGL2 PRIMITIVE_RESTART_FIXED_INDEX behavior
            # see: https://www.khronos.org/registry/webgl/specs/latest/2.0/#5.18
            if max_index < 255:
                componentType = "UNSIGNED_BYTE"
            elif max_index < 65535:
                componentType = "UNSIGNED_SHORT"
            elif max_index < 4294967295:
                componentType = "UNSIGNED_INT"
            else:
                printLog('ERROR', 'Invalid max_index: ' + str(max_index))
                continue

            if exportSettings['force_indices']:
                componentType = exportSettings['indices']

            count = len(indices)

            type = "SCALAR"

            indices_index = gltf.generateAccessor(glTF, exportSettings['binary'], indices, componentType, count, type, "ELEMENT_ARRAY_BUFFER")

            if indices_index < 0:
                printLog('ERROR', 'Could not create accessor for indices')
                continue

            primitive['indices'] = indices_index

            # Attributes

            attributes = {}



            internal_attributes = internal_primitive['attributes']




            internal_position = internal_attributes['POSITION']

            componentType = "FLOAT"

            count = len(internal_position) // 3

            type = "VEC3"

            position = gltf.generateAccessor(glTF, exportSettings['binary'], internal_position, componentType, count, type, "ARRAY_BUFFER")

            if position < 0:
                printLog('ERROR', 'Could not create accessor for position')
                continue

            attributes['POSITION'] = position


            if internal_attributes.get('NORMAL') is not None:
                internal_normal = internal_attributes['NORMAL']

                componentType = "FLOAT"

                count = len(internal_normal) // 3

                type = "VEC3"

                normal = gltf.generateAccessor(glTF, exportSettings['binary'],
                        internal_normal, componentType, count, type, "ARRAY_BUFFER")

                if normal < 0:
                    printLog('ERROR', 'Could not create accessor for normal')
                    continue

                attributes['NORMAL'] = normal



            if internal_attributes.get('TANGENT') is not None:
                internal_tangent = internal_attributes['TANGENT']

                componentType = "FLOAT"

                count = len(internal_tangent) // 4

                type = "VEC4"

                tangent = gltf.generateAccessor(glTF, exportSettings['binary'], internal_tangent, componentType, count, type, "ARRAY_BUFFER")

                if tangent < 0:
                    printLog('ERROR', 'Could not create accessor for tangent')
                    continue

                attributes['TANGENT'] = tangent

            # texture coords

            v3dExt['uvLayers'] = {}

            texcoord_index = 0
            process_texcoord = True
            while process_texcoord:
                texcoord_id = 'TEXCOORD_' + str(texcoord_index)

                if internal_attributes.get(texcoord_id) is not None:
                    internal_texcoord = internal_attributes[texcoord_id]

                    componentType = "FLOAT"

                    count = len(internal_texcoord) // 2

                    type = "VEC2"

                    texcoord = gltf.generateAccessor(glTF, exportSettings['binary'], internal_texcoord, componentType, count, type, "ARRAY_BUFFER")

                    if texcoord < 0:
                        process_texcoord = False
                        printLog('ERROR', 'Could not create accessor for ' + texcoord_id)
                        continue

                    if internal_primitive['useNodeAttrs']:
                        uv_layer_name = bl_mesh.uv_layers[texcoord_index].name
                        v3dExt['uvLayers'][uv_layer_name] = texcoord_id;

                    attributes[texcoord_id] = texcoord

                    texcoord_index += 1
                else:
                    process_texcoord = False

            # vertex colors

            v3dExt['colorLayers'] = {}

            color_index = 0

            process_color = True
            while process_color:
                color_id = 'COLOR_' + str(color_index)

                if internal_attributes.get(color_id) is not None:
                    internal_color = internal_attributes[color_id]

                    componentType = "FLOAT"

                    count = len(internal_color) // 4

                    type = "VEC4"

                    color = gltf.generateAccessor(glTF, exportSettings['binary'], internal_color, componentType, count, type, "ARRAY_BUFFER")

                    if color < 0:
                        process_color = False
                        printLog('ERROR', 'Could not create accessor for ' + color_id)
                        continue

                    if internal_primitive['useNodeAttrs']:
                        vc_layer_name = bl_mesh.vertex_colors[color_index].name
                        v3dExt['colorLayers'][vc_layer_name] = color_id;

                    attributes[color_id] = color

                    color_index += 1
                else:
                    process_color = False



            if exportSettings['skins']:
                skinAttrIndex = 0

                process_bone = True
                while process_bone:
                    joint_id = 'JOINTS_' + str(skinAttrIndex)
                    weight_id = 'WEIGHTS_' + str(skinAttrIndex)

                    if (internal_attributes.get(joint_id) is not None and
                            internal_attributes.get(weight_id) is not None):
                        internal_joint = internal_attributes[joint_id]

                        componentType = "UNSIGNED_SHORT"

                        count = len(internal_joint) // 4

                        type = "VEC4"

                        joint = gltf.generateAccessor(glTF, exportSettings['binary'], internal_joint, componentType, count, type, "ARRAY_BUFFER")

                        if joint < 0:
                            process_bone = False
                            printLog('ERROR', 'Could not create accessor for ' + joint_id)
                            continue

                        attributes[joint_id] = joint




                        internal_weight = internal_attributes[weight_id]

                        componentType = "FLOAT"

                        count = len(internal_weight) // 4

                        type = "VEC4"

                        weight = gltf.generateAccessor(glTF, exportSettings['binary'], internal_weight, componentType, count, type, "ARRAY_BUFFER")

                        if weight < 0:
                            process_bone = False
                            printLog('ERROR', 'Could not create accessor for ' + weight_id)
                            continue

                        attributes[weight_id] = weight




                        skinAttrIndex += 1
                    else:
                        process_bone = False



            if exportSettings['morph']:
                if bl_mesh.shape_keys is not None:
                    targets = []

                    morph_index = 0
                    for bl_shape_key in bl_mesh.shape_keys.key_blocks:
                        if bl_shape_key != bl_shape_key.relative_key:

                            target_position_id = 'MORPH_POSITION_' + str(morph_index)
                            target_normal_id = 'MORPH_NORMAL_' + str(morph_index)
                            target_tangent_id = 'MORPH_TANGENT_' + str(morph_index)

                            if internal_attributes.get(target_position_id) is not None:
                                internal_target_position = internal_attributes[target_position_id]

                                componentType = "FLOAT"

                                count = len(internal_target_position) // 3

                                type = "VEC3"

                                target_position = gltf.generateAccessor(glTF, exportSettings['binary'], internal_target_position, componentType, count, type, "")

                                if target_position < 0:
                                    printLog('ERROR', 'Could not create accessor for ' + target_position_id)
                                    continue



                                target = {
                                    'POSITION' : target_position
                                }



                                if exportSettings['morph_normal'] and internal_attributes.get(target_normal_id) is not None:

                                    internal_target_normal = internal_attributes[target_normal_id]

                                    componentType = "FLOAT"

                                    count = len(internal_target_normal) // 3

                                    type = "VEC3"

                                    target_normal = gltf.generateAccessor(glTF, exportSettings['binary'], internal_target_normal, componentType, count, type, "")

                                    if target_normal < 0:
                                        printLog('ERROR', 'Could not create accessor for ' + target_normal_id)
                                        continue

                                    target['NORMAL'] = target_normal


                                if exportSettings['morph_tangent'] and internal_attributes.get(target_tangent_id) is not None:

                                    internal_target_tangent = internal_attributes[target_tangent_id]

                                    componentType = "FLOAT"

                                    count = len(internal_target_tangent) // 3

                                    type = "VEC3"

                                    target_tangent = gltf.generateAccessor(glTF, exportSettings['binary'], internal_target_tangent, componentType, count, type, "")

                                    if target_tangent < 0:
                                        printLog('ERROR', 'Could not create accessor for ' + target_tangent_id)
                                        continue

                                    target['TANGENT'] = target_tangent




                                targets.append(target)

                                morph_index += 1

                    if len(targets) > 0:
                        primitive['targets'] = targets




            primitive['attributes'] = attributes
            primitives.append(primitive)


        if exportSettings['morph']:
            if bl_mesh.shape_keys is not None:
                morph_max = len(bl_mesh.shape_keys.key_blocks) - 1
                if morph_max > 0:

                    weights = []
                    targetNames = []

                    for bl_shape_key in bl_mesh.shape_keys.key_blocks:
                        if bl_shape_key != bl_shape_key.relative_key:
                            weights.append(bl_shape_key.value)
                            targetNames.append(bl_shape_key.name)

                    mesh['weights'] = weights

                    if 'extras' not in mesh:
                        mesh['extras'] = {}
                    mesh['extras']['targetNames'] = targetNames



        if exportSettings['custom_props']:
            props = createCustomProperty(bl_mesh)

            if props is not None:
                if 'extras' not in mesh:
                    mesh['extras'] = {}
                mesh['extras']['customProps'] = props



        mesh['primitives'] = primitives

        mesh['name'] = srcName
        # also a pointer to object.data
        mesh['id'] = srcPtr

        meshes.append(mesh)


    if len (meshes) > 0:
        glTF['meshes'] = meshes


def generateDuplicateMesh(operator, context, exportSettings, glTF, bl_obj):
    """
    Helper function for dublicating meshes with linked object materials.
    """

    if bl_obj is None:
        return -1

    mesh_index = gltf.getMeshIndex(glTF, getPtr(bl_obj.data))

    if mesh_index == -1:
        return False

    new_mesh = copy.deepcopy(glTF['meshes'][mesh_index])

    primitives = new_mesh['primitives']

    primitive_index = 0
    for bl_material_slot in bl_obj.material_slots:
        if bl_material_slot.link == 'OBJECT' and primitive_index < len(primitives):
            primitives[primitive_index]['material'] = (getOrCreateDefaultMatIndex(glTF)
                    if bl_material_slot.material is None
                    else gltf.getMaterialIndex(glTF, bl_material_slot.material.name))
        primitive_index += 1

    new_name = bl_obj.data.name + '_' + bl_obj.name

    new_mesh['name'] = new_name

    glTF['meshes'].append(new_mesh)

    return len(glTF['meshes']) - 1


def generateNodeParameter(matrix, node):
    """
    Helper function for storing node parameters.
    """

    translation, rotation, scale = decomposeTransformSwizzle(matrix)
    # Put w at the end.
    rotation = mathutils.Quaternion((rotation[1], rotation[2], rotation[3], rotation[0]))

    if translation[0] != 0.0 or translation[1] != 0.0 or translation[2] != 0.0:
        node['translation'] = [translation[0], translation[1], translation[2]]

    if rotation[0] != 0.0 or rotation[1] != 0.0 or rotation[2] != 0.0 or rotation[3] != 1.0:
        node['rotation'] = [rotation[0], rotation[1], rotation[2], rotation[3]]

    if scale[0] != 1.0 or scale[1] != 1.0 or scale[2] != 1.0:
        node['scale'] = [scale[0], scale[1], scale[2]]


def getMeshIndexDupliCheck(operator, context, exportSettings, glTF, bl_obj):

    mesh = gltf.getMeshIndex(glTF, getPtr(bl_obj.data))
    is_line = objDataUsesLineRendering(bl_obj.data)

    if mesh >= 0 and not is_line:
        need_dublicate = False

        if bl_obj.material_slots:
            for bl_material_slot in bl_obj.material_slots:
                if bl_material_slot.link == 'OBJECT':
                    need_dublicate = True
                    break

        if need_dublicate:
            mesh = generateDuplicateMesh(operator, context, exportSettings, glTF,
                    bl_obj)

    return mesh


def generateNodeInstance(operator, context, exportSettings, glTF, bl_obj):
    """
    Helper function for storing node instances.
    """

    node = {}

    bl_obj_type = bl_obj.type

    # the parent inverse matrix is considered later when generating scene
    # hierarchy
    node_matrix = bl_obj.matrix_basis
    generateNodeParameter(node_matrix, node)

    v3dExt = {}
    node['extensions'] = { 'S8S_v3d_node_data' : v3dExt }

    if bl_obj_type in ['MESH', 'CURVE', 'SURFACE', 'META']:

        mesh = getMeshIndexDupliCheck(operator, context, exportSettings, glTF, bl_obj)
        if mesh >= 0:
            node['mesh'] = mesh

    elif bl_obj_type == 'FONT':

        if exportSettings['bake_text']:
            mesh = getMeshIndexDupliCheck(operator, context, exportSettings, glTF, bl_obj)
            if mesh >= 0:
                node['mesh'] = mesh
        else:
            curve = getCurveIndex(glTF, bl_obj.data.name)
            if curve >= 0:
                v3dExt['curve'] = curve

    elif bl_obj_type == 'CAMERA':
        # NOTE: possible issues with libraries
        camera = getCameraIndex(glTF, bl_obj.data.name)
        if camera >= 0:
            node['camera'] = camera

    elif bl_obj_type == 'LIGHT':
        light = gltf.getLightIndex(glTF, bl_obj.data.name)
        if light >= 0:
            v3dExt['light'] = light

    v3dExt['hidden'] = bl_obj.hide_render
    v3dExt['renderOrder'] = bl_obj.v3d.render_order
    v3dExt['frustumCulling'] = bl_obj.v3d.frustum_culling

    if (bl_obj_type in ['MESH', 'CURVE', 'SURFACE', 'FONT', 'META'] and
            exportSettings['use_shadows']):
        v3dExt['useShadows'] = bl_obj.v3d.use_shadows

    if len(bl_obj.users_collection):

        collections = getObjectAllCollections(bl_obj)
        v3dExt['groupNames'] = [coll.name for coll in collections]
        for coll in collections:
            if coll is not None and coll.hide_render:
                v3dExt['hidden'] = True
                break

    if exportSettings['custom_props']:
        props = createCustomProperty(bl_obj)

        if props is not None:
            if 'extras' not in node:
                node['extras'] = {}
            node['extras']['customProps'] = props

    node['name'] = bl_obj.name

    return node

def inheritParentProps(node, nodeParent):
    """
    Inherit parent props such as groups and visibility
    """
    v3dExt = gltf.getAssetExtension(node, 'S8S_v3d_node_data')
    v3dExtParent = gltf.getAssetExtension(nodeParent, 'S8S_v3d_node_data')

    if v3dExt and v3dExtParent:
        if v3dExtParent['hidden'] == True:
            v3dExt['hidden'] = True

        if 'groupNames' in v3dExtParent:
            if 'groupNames' in v3dExt:
                v3dExt['groupNames'] += v3dExtParent['groupNames']
            else:
                v3dExt['groupNames'] = v3dExtParent['groupNames'].copy()


def generateCameraNodeFromView(glTF):
    printLog('INFO', 'Generating default camera node')

    node = {}

    node['name'] = '__DEFAULT_CAMERA__'

    # checked in generateCameraFromView()
    region3D = getView3DSpaceProp('region_3d')

    if region3D.is_perspective:
        matrix = region3D.view_matrix.inverted()
        generateNodeParameter(matrix, node)
    else:
        # ortho: calculate based on view location and rotation
        q = region3D.view_rotation
        t = q @ mathutils.Vector((0, 0, region3D.view_distance)) + region3D.view_location

        node['translation'] = [t[0], t[2], -t[1]]
        node['rotation'] = [q[1], q[3], -q[2], q[0]]
        node['scale'] = [1, 1, 1]

    camera = getCameraIndex(glTF, '__DEFAULT__')
    if camera >= 0:
        node['camera'] = camera

    return node


def generateProxyNodes(operator, context, glTF, node, bl_obj):
    """
    Generate additional nodes for objects with the non-identity (for applying
    animations properly) and even non-decomposable parent inverse matrix (to
    ensure that the exported node matrix is a TRS matrix).
    """

    if bl_obj.parent is None:
        return []

    proxy_nodes = []


    parInvMats = list(filter(lambda mat: not mat4IsIdentity(mat),
            mat4ToTRSMatrices(bl_obj.matrix_parent_inverse)))
    if parInvMats:
        printLog('WARNING', 'Object "' + bl_obj.name
                + '" has a non-identity parent inverse matrix. Creating proxy nodes.')

    relBoneMats = []
    if bl_obj.parent is not None and bl_obj.parent_type == 'BONE':
        pose_bone = bl_obj.parent.pose.bones.get(bl_obj.parent_bone)
        if pose_bone is not None:
            if pose_bone.bone.use_relative_parent:
                relBoneMats = list(filter(lambda mat: not mat4IsIdentity(mat),
                        mat4ToTRSMatrices(pose_bone.bone.matrix_local.inverted())))
                if relBoneMats:
                    printLog('WARNING', 'Object "' + bl_obj.name
                            + '" has a non-identity parent bone relative matrix. '
                            + 'Creating proxy nodes.')
            else:
                # objects parented to a bone without the "Relative Parent"
                # option will have their node['translation'] modified later
                bone_len = (pose_bone.bone.tail_local - pose_bone.bone.head_local).length
                relBoneMats = [mathutils.Matrix.Translation((0, bone_len, 0))]

    proxyMats = relBoneMats + parInvMats
    proxyMats.reverse()

    for i in range(len(proxyMats)):
        proxy_node = {}
        proxy_node['name'] = PROXY_NODE_PREFIX.format(idx=str(i), name=node['name'])
        generateNodeParameter(proxyMats[i], proxy_node)
        proxy_nodes.append(proxy_node)

    return proxy_nodes


def mat4ToTRSMatrices(mat4):
    """
    Represent the given matrix in a form of a product of TRS-decomposable matrices.
    """

    if mat4IsTRSDecomposable(mat4):
        return [mat4]

    result = mat4SvdDecomposeToMatrs(mat4)
    if result is None:
        # fallback to the original matrix
        return [mat4]

    return [result[0], result[1]]

def generateNodes(operator, context, exportSettings, glTF):
    """
    Generates the top level nodes entry.
    """

    nodes = []
    skins = []


    filtered_objects_shallow = exportSettings['filtered_objects_shallow']
    filtered_objects_with_dg = exportSettings['filtered_objects_with_dg']

    for bl_obj in filtered_objects_shallow:
        node = generateNodeInstance(operator, context, exportSettings, glTF, bl_obj)
        nodes.append(node)

        proxy_nodes = generateProxyNodes(operator, context, glTF, node, bl_obj)
        nodes.extend(proxy_nodes)

    if getCameraIndex(glTF, '__DEFAULT__') >= 0:
        nodes.append(generateCameraNodeFromView(glTF))

    for bl_obj in filtered_objects_shallow:
        if (bl_obj.instance_type == 'COLLECTION'
                and bl_obj.instance_collection != None
                and bl_obj.instance_collection.v3d.enable_export):

            for bl_instance_obj in bl_obj.instance_collection.objects:

                node = generateNodeInstance(operator, context, exportSettings, glTF, bl_instance_obj)
                node['name'] = 'Instance_' + bl_obj.name + '_' + bl_instance_obj.name

                nodeParent = getByName(nodes, bl_obj.name)
                inheritParentProps(node, nodeParent)

                nodes.append(node)

                proxy_nodes = generateProxyNodes(operator, context, glTF, node, bl_instance_obj)
                nodes.extend(proxy_nodes)

            node = {}
            node['name'] = 'Instance_Offset_' + bl_obj.name

            translation = convertSwizzleLocation(bl_obj.instance_collection.instance_offset)
            node['translation'] = [-translation[0], -translation[1], -translation[2]]
            nodes.append(node)


    if len(nodes) > 0:
        glTF['nodes'] = nodes

        gltf.appendExtension(glTF, 'S8S_v3d_node_data')

    if exportSettings['skins']:
        for bl_obj in filtered_objects_with_dg:
            if bl_obj.type != 'ARMATURE' or len(bl_obj.pose.bones) == 0:
                continue

            temp_action = None

            if exportSettings['bake_armature_actions'] and not exportSettings['animations']:
                if bl_obj.animation_data is not None:
                    temp_action = bl_obj.animation_data.action

                obj_scene = getSceneByObject(bl_obj)
                if obj_scene is not None:

                    prev_active_scene = bpy.context.scene
                    bpy.context.window.scene = obj_scene

                    setSelectedObject(bl_obj)

                    bpy.ops.object.mode_set(mode='POSE')
                    bpy.ops.nla.bake(frame_start=bpy.context.scene.frame_current,
                            frame_end=bpy.context.scene.frame_current,
                            only_selected=False, visual_keying=True)

                    restoreSelectedObjects()

                    bpy.context.window.scene = obj_scene

            joints = []

            joints_written = False



            children_list = list(bl_obj.children)

            for bl_check_object in filtered_objects_with_dg:
                bl_check_armature = findArmature(bl_check_object)

                if bl_check_armature == bl_obj and bl_check_object not in children_list:
                    children_list.append(bl_check_object)



            for bl_object_child in children_list:

                # Property: skin and node


                inverse_matrices = []

                for bl_bone in bl_obj.pose.bones:

                    if not joints_written:
                        node = {}

                        correction_matrix_local = bl_bone.bone.matrix_local.copy()

                        if bl_bone.parent is not None:
                            correction_matrix_local = bl_bone.parent.bone.matrix_local.inverted() @ correction_matrix_local

                        matrix_basis = bl_bone.matrix_basis

                        if exportSettings['bake_armature_actions']:
                            matrix_basis = bl_obj.convert_space(pose_bone=bl_bone, matrix=bl_bone.matrix, from_space='POSE', to_space='LOCAL')

                        generateNodeParameter(correction_matrix_local @ matrix_basis, node)

                        node['name'] = bl_obj.name + "_" + bl_bone.name

                        joints.append(len(nodes))

                        nodes.append(node)

                    bind_shape_matrix = bl_obj.matrix_world.inverted() @ bl_object_child.matrix_world
                    inverse_bind_matrix = convertSwizzleMatrix(bl_bone.bone.matrix_local.inverted() @ bind_shape_matrix)

                    for column in range(0, 4):
                        for row in range(0, 4):
                            inverse_matrices.append(inverse_bind_matrix[row][column])

                # add data for the armature itself at the end
                skeleton = gltf.getNodeIndex(glTF, bl_obj.name)

                if not joints_written:
                    joints.append(skeleton)

                armature_inverse_bind_matrix = convertSwizzleMatrix(
                        bl_obj.matrix_world.inverted() @ bl_object_child.matrix_world)

                for column in range(0, 4):
                    for row in range(0, 4):
                        inverse_matrices.append(armature_inverse_bind_matrix[row][column])

                joints_written = True

                skin = {}

                skin['skeleton'] = skeleton

                skin['joints'] = joints

                componentType = "FLOAT"
                count = len(inverse_matrices) // 16
                type = "MAT4"

                inverseBindMatrices = gltf.generateAccessor(glTF, exportSettings['binary'], inverse_matrices, componentType, count, type, "")

                skin['inverseBindMatrices'] = inverseBindMatrices

                skins.append(skin)

            if temp_action is not None:
                bl_obj.animation_data.action = temp_action


    if len (skins) > 0:
        glTF['skins'] = skins


    # Resolve children etc.


    for bl_obj in filtered_objects_shallow:
        node_index = gltf.getNodeIndex(glTF, bl_obj.name)

        node = nodes[node_index]

        if exportSettings['skins']:
            bl_armature = findArmature(bl_obj)
            if bl_armature is not None:
                index_offset = 0

                if bl_obj in bl_armature.children:
                    index_offset = bl_armature.children.index(bl_obj)
                else:
                    index_local_offset = 0

                    for bl_check_object in filtered_objects_shallow:
                        bl_check_armature = findArmature(bl_check_object)
                        if bl_check_armature == bl_armature:
                            index_local_offset += 1

                        if bl_obj == bl_check_object:
                            index_local_offset -= 1
                            break

                    index_offset = len(bl_armature.children) + index_local_offset

                node['skin'] = getSkinIndex(glTF, bl_armature.name, index_offset)

        # constraints

        v3dExt = gltf.getAssetExtension(node, 'S8S_v3d_node_data')
        if v3dExt and exportSettings['export_constraints'] and len(bl_obj.constraints):
            v3dExt['constraints'] = extractConstraints(glTF, bl_obj)

        # first-person camera link to collision material

        if (bl_obj.type == 'CAMERA' and
                bl_obj.data and
                bl_obj.data.v3d.controls == 'FIRST_PERSON' and
                bl_obj.data.v3d.fps_collision_material):

            v3d_cam_data = gltf.getAssetExtension(glTF['cameras'][node['camera']], 'S8S_v3d_camera_data')
            if v3d_cam_data:
                mat = gltf.getMaterialIndex(glTF, bl_obj.data.v3d.fps_collision_material.name)
                if mat >= 0:
                    v3d_cam_data['fpsCollisionMaterial'] = mat


        # Nodes
        for child_obj in bl_obj.children:

            if child_obj.parent_type == 'BONE' and exportSettings['skins']:
                continue

            nodeAppendChildFromObj(glTF, node, child_obj)

        # Instancing / Duplications
        if bl_obj.instance_type == 'COLLECTION' and bl_obj.instance_collection != None:
            child_index = gltf.getNodeIndex(glTF, 'Instance_Offset_' + bl_obj.name)
            if child_index >= 0:
                if not 'children' in node:
                    node['children'] = []
                node['children'].append(child_index)

                instance_node = nodes[child_index]
                for bl_instance_obj in bl_obj.instance_collection.objects:
                    nodeAppendChildFromObj(glTF, instance_node,
                            bl_instance_obj, 'Instance_' + bl_obj.name
                            + '_' + bl_instance_obj.name)


        if exportSettings['skins']:
            # Joint
            if bl_obj.type == 'ARMATURE' and len(bl_obj.pose.bones) > 0:

                # parent root bones to the node of the armature object
                for bl_bone in bl_obj.pose.bones:

                    if bl_bone.parent:
                        continue

                    child_index = gltf.getNodeIndex(glTF, bl_obj.name + "_" + bl_bone.name)
                    if child_index < 0:
                        continue

                    if not 'children' in node:
                        node['children'] = []
                    node['children'].append(child_index)

                # process the bone's children: objects parented to the bone and child bones
                for bl_bone in bl_obj.pose.bones:

                    bone_index = gltf.getNodeIndex(glTF, bl_obj.name + "_" + bl_bone.name)
                    if bone_index == -1:
                        continue

                    bone_node = nodes[bone_index]

                    for child_obj in bl_obj.children:
                        if (child_obj.parent_type == 'BONE'
                                and child_obj.parent_bone == bl_bone.name):
                            nodeAppendChildFromObj(glTF, bone_node, child_obj)

                    for child_bone in bl_bone.children:
                        child_bone_index = gltf.getNodeIndex(glTF, bl_obj.name + "_" + child_bone.name)

                        if child_bone_index > -1:
                            if not 'children' in bone_node:
                                bone_node['children'] = []
                            bone_node['children'].append(child_bone_index)

    # NOTE: possible breakage of the children's animation
    preprocessCamLampNodes(nodes)


def nodeAppendChildFromObj(glTF, parent_node, child_obj, child_node_name=None):

    if child_node_name is None:
        child_node_name = child_obj.name

    child_index = gltf.getNodeIndex(glTF, child_node_name)
    if child_index < 0:
        return -1

    if not 'children' in parent_node:
        parent_node['children'] = []

    i = 0
    index_to_append = child_index
    while True:
        proxy_name = PROXY_NODE_PREFIX.format(idx=str(i), name=child_node_name)
        proxy_idx = gltf.getNodeIndex(glTF, proxy_name)
        i += 1

        if proxy_idx >= 0:
            proxy_node = glTF['nodes'][proxy_idx]
            if not 'children' in proxy_node:
                proxy_node['children'] = []
            proxy_node['children'].append(index_to_append)
            index_to_append = proxy_idx
        else:
            break

    parent_node['children'].append(index_to_append)

def preprocessCamLampNodes(nodes):
    """
    Rotate cameras and lamps by 90 degrees around the X local axis, apply the
    inverted rotation to their children.
    """

    rot_x_90 = mathutils.Quaternion((1.0, 0.0, 0.0), -math.pi/2).to_matrix().to_4x4()
    rot_x_90_inv = mathutils.Quaternion((1.0, 0.0, 0.0), math.pi/2).to_matrix().to_4x4()

    # rotate cameras and lamps by 90 around X axis prior(!) to applying their TRS,
    # the matrix is still decomposable after such operation
    for node in nodes:
        if nodeIsCamera(node) or nodeIsLamp(node) or nodeIsCurve(node):
            mat = nodeComposeMatrix(node)

            trans, rot, sca = (mat @ rot_x_90).decompose()
            node['translation'] = list(trans)
            node['rotation'] = [rot[1], rot[2], rot[3], rot[0]]
            node['scale'] = list(sca)

            if 'children' in node:
                for child_index in node['children']:
                    child_node = nodes[child_index]
                    child_mat = nodeComposeMatrix(child_node)

                    trans, rot, sca = (rot_x_90_inv @ child_mat).decompose()
                    child_node['translation'] = list(trans)
                    child_node['rotation'] = [rot[1], rot[2], rot[3], rot[0]]
                    child_node['scale'] = list(sca)

def nodeComposeMatrix(node):
    if 'translation' in node:
        mat_trans = mathutils.Matrix.Translation(node['translation'])
    else:
        mat_trans = mathutils.Matrix.Identity(4)

    if 'rotation' in node:
        rot = node['rotation']
        # Put w to the start
        mat_rot = mathutils.Quaternion((rot[3], rot[0], rot[1], rot[2])).to_matrix().to_4x4()
    else:
        mat_rot = mathutils.Matrix.Identity(4)

    mat_sca = mathutils.Matrix()
    if 'scale' in node:
        mat_sca[0][0] = node['scale'][0]
        mat_sca[1][1] = node['scale'][1]
        mat_sca[2][2] = node['scale'][2]

    return mat_trans @ mat_rot @ mat_sca


def nodeIsCamera(node):
    return 'camera' in node

def nodeIsLamp(node):
    return ('extensions' in node and 'S8S_v3d_node_data' in node['extensions']
            and 'light' in node['extensions']['S8S_v3d_node_data'])

def nodeIsCurve(node):
    return ('extensions' in node and 'S8S_v3d_node_data' in node['extensions']
            and 'curve' in node['extensions']['S8S_v3d_node_data'])


def generateImages(operator, context, exportSettings, glTF):
    """
    Generates the top level images entry.
    """

    filtered_images = exportSettings['filtered_images']

    images = []


    for bl_image in filtered_images:

        # Property: image


        image = {}

        uri = getImageExportedURI(exportSettings, bl_image)

        if exportSettings['format'] == 'ASCII':

            if exportSettings['embed_images']:
                # embed image as Base64

                img_data = extractImageBindata(bl_image, context.scene)

                image['uri'] = ('data:' + getImageExportedMimeType(bl_image)
                        + ';base64,'
                        + base64.b64encode(img_data).decode('ascii'))

            else:
                # use external file

                old_path = bl_image.filepath_from_user()
                new_path = norm(exportSettings['filedirectory'] + uri)

                if (bl_image.is_dirty or bl_image.packed_file is not None
                        or not os.path.isfile(old_path)):
                    # always extract data for dirty/packed/missing images,
                    # because they can differ from an external source's data

                    img_data = extractImageBindata(bl_image, context.scene)

                    with open(new_path, 'wb') as f:
                        f.write(img_data)

                elif old_path != new_path:
                    # copy an image to a new location

                    if (bl_image.file_format != "JPEG" and bl_image.file_format != "PNG"
                            and bl_image.file_format != "BMP" and bl_image.file_format != 'HDR'):
                        # need conversion to PNG

                        img_data = extractImageBindataPNG(bl_image, context.scene)

                        with open(new_path, 'wb') as f:
                            f.write(img_data)
                    else:
                        shutil.copyfile(old_path, new_path)

                image['uri'] = uri

        else:
            # store image in glb

            img_data = extractImageBindata(bl_image, context.scene)

            bufferView = gltf.generateBufferView(glTF, exportSettings['binary'], img_data, '', 0)

            image['mimeType'] = getImageExportedMimeType(bl_image)
            image['bufferView'] = bufferView

        exportSettings['uri_data']['uri'].append(uri)
        exportSettings['uri_data']['bl_datablocks'].append(bl_image)

        images.append(image)

    if len (images) > 0:
        glTF['images'] = images


def generateTextures(operator, context, exportSettings, glTF):
    """
    Generates the top level textures entry.
    """

    filtered_textures = exportSettings['filtered_textures']

    textures = []

    v3dExt_used = False

    # shader node textures or texture slots
    for bl_tex in filtered_textures:

        texture = {
            'name' : getTextureName(bl_tex)
        }

        v3dExt = {}

        v3dExt['colorSpace'] = extractColorSpace(bl_tex)

        if isinstance(bl_tex, bpy.types.ShaderNodeTexEnvironment):
            magFilter = gltf.WEBGL_FILTERS['LINEAR']
            if bl_tex.interpolation == 'Closest':
                magFilter = gltf.WEBGL_FILTERS['NEAREST']
            wrap = gltf.WEBGL_WRAPPINGS['REPEAT']

            uri = getImageExportedURI(exportSettings, getTexImage(bl_tex))

        elif isinstance(bl_tex, bpy.types.ShaderNodeTexImage):
            magFilter = gltf.WEBGL_FILTERS['LINEAR']
            if bl_tex.interpolation == 'Closest':
                magFilter = gltf.WEBGL_FILTERS['NEAREST']
            wrap = gltf.WEBGL_WRAPPINGS['REPEAT']

            if bl_tex.extension == 'CLIP' or bl_tex.extension == 'EXTEND':
                wrap = gltf.WEBGL_WRAPPINGS['CLAMP_TO_EDGE']

            uri = getImageExportedURI(exportSettings, getTexImage(bl_tex))

            anisotropy = int(bl_tex.v3d.anisotropy)
            if anisotropy > 1:
                v3dExt['anisotropy'] = anisotropy

        else:

            if isinstance(bl_tex.texture, bpy.types.EnvironmentMapTexture):
                magFilter = gltf.WEBGL_FILTERS['LINEAR']
                wrap = gltf.WEBGL_WRAPPINGS['CLAMP_TO_EDGE']
                v3dExt['isCubeTexture'] = True
            else:
                magFilter = gltf.WEBGL_FILTERS['LINEAR']
                wrap = gltf.WEBGL_WRAPPINGS['REPEAT']

                if bl_tex.texture.extension == 'CLIP':
                    wrap = gltf.WEBGL_WRAPPINGS['CLAMP_TO_EDGE']

            anisotropy = int(bl_tex.texture.v3d.anisotropy)
            if anisotropy > 1:
                v3dExt['anisotropy'] = anisotropy

            uri = getImageExportedURI(exportSettings, getTexImage(bl_tex.texture))

        texture['sampler'] = gltf.createSampler(glTF, magFilter, wrap, wrap)

        # 'source' isn't required but must be >=0 according to GLTF 2.0 spec.
        img_index = getImageIndex(exportSettings, uri)
        if img_index >= 0:
            texture['source'] = img_index

        texture['extensions'] = { 'S8S_v3d_texture_data' : v3dExt }
        v3dExt_used = True

        textures.append(texture)

    if v3dExt_used:
        gltf.appendExtension(glTF, 'S8S_v3d_texture_data')

    if len (textures) > 0:
        glTF['textures'] = textures


def generateNodeGraphs(operator, context, exportSettings, glTF):
    """
    Generates the top level node graphs entry.
    """

    filtered_node_groups = exportSettings['filtered_node_groups']

    if len(filtered_node_groups) > 0:
        ext = gltf.appendExtension(glTF, 'S8S_v3d_data', glTF)
        graphs = ext['nodeGraphs'] = []

        # store group names prior to processing them in case of group multiple
        # nesting
        for bl_node_group in filtered_node_groups:
            graphs.append({ 'name': bl_node_group.name })

        for bl_node_group in filtered_node_groups:
            graph = extractNodeGraph(bl_node_group, exportSettings, glTF)

            index = filtered_node_groups.index(bl_node_group)
            graphs[index].update(graph)


def generateCurves(operator, context, exportSettings, glTF):
    """
    Generates the top level curves entry.
    """

    curves = []

    filtered_curves = exportSettings['filtered_curves']

    for bl_curve in filtered_curves:

        curve = {}

        curve['name'] = bl_curve.name

        # curve, surface, font
        # NOTE: currently only font curves supported
        curve['type'] = 'font'

        if curve['type'] == 'font':
            base_dir = os.path.dirname(os.path.abspath(__file__))

            curve['text'] = bl_curve.body

            if bl_curve.font.filepath == '<builtin>':
                font_path_json = join(base_dir, 'fonts', 'bfont.json')
            else:
                font_path = os.path.normpath(bpy.path.abspath(bl_curve.font.filepath))
                font_path_json = os.path.splitext(font_path)[0] + '.json'

                if not os.path.isfile(font_path_json):
                    printLog('ERROR', 'Unable to load .json font file ' + font_path_json)
                    font_path_json = join(base_dir, 'fonts', 'bfont.json')

            with open(font_path_json, 'r', encoding='utf-8') as f:
                # inline
                curve['font'] = json.load(f)

            # NOTE: 0.72 for bfont only
            curve['size'] = bl_curve.size * 0.72
            curve['height'] = bl_curve.extrude
            curve['curveSegments'] = max(bl_curve.resolution_u - 1, 1)

            curve['bevelThickness'] = bl_curve.bevel_depth
            curve['bevelSize'] = bl_curve.bevel_depth
            curve['bevelSegments'] = bl_curve.bevel_resolution + 1

            align_x = bl_curve.align_x

            if align_x == 'LEFT' or align_x == 'JUSTIFY' or align_x == 'FLUSH':
                curve['alignX'] = 'left'
            elif align_x == 'CENTER':
                curve['alignX'] = 'center'
            elif align_x == 'RIGHT':
                curve['alignX'] = 'right'

            align_y = bl_curve.align_y

            if align_y == 'TOP_BASELINE' or align_x == 'BOTTOM':
                curve['alignY'] = 'bottom'
            elif align_y == 'TOP':
                curve['alignY'] = 'top'
            elif align_y == 'CENTER':
                curve['alignY'] = 'center'

            # optional
            if len(bl_curve.materials) and bl_curve.materials[0] is not None:
                material = gltf.getMaterialIndex(glTF, bl_curve.materials[0].name)

                if material >= 0:
                    curve['material'] = material
                else:
                    printLog('WARNING', 'Material ' + bl_curve.materials[0].name + ' not found')

        curves.append(curve)

    if len(curves) > 0:
        ext = gltf.appendExtension(glTF, 'S8S_v3d_data', glTF)
        ext['curves'] = curves

def generateMaterials(operator, context, exportSettings, glTF):
    """
    Generates the top level materials entry.
    """

    filtered_materials = exportSettings['filtered_materials']

    materials = []

    v3dExtUsed = False

    for bl_mat in filtered_materials:
        material = {}

        v3dExt = {}
        material['extensions'] = { 'S8S_v3d_material_data' : v3dExt }
        v3dExtUsed = True

        mat_type = getMaterialType(bl_mat)

        # PBR Materials

        if mat_type == 'PBR':
            for bl_node in bl_mat.node_tree.nodes:
                if (isinstance(bl_node, bpy.types.ShaderNodeGroup) and
                    bl_node.node_tree.name.startswith('Verge3D PBR')):

                    alpha = 1.0

                    material['pbrMetallicRoughness'] = {}

                    pbrMetallicRoughness = material['pbrMetallicRoughness']

                    index = getTextureIndexNode(exportSettings, glTF, 'BaseColor', bl_node)
                    if index >= 0:
                        baseColorTexture = {
                            'index' : index
                        }

                        texCoord = getTexcoordIndex(glTF, 'BaseColor', bl_node)
                        if texCoord > 0:
                            baseColorTexture['texCoord'] = texCoord

                        pbrMetallicRoughness['baseColorTexture'] = baseColorTexture

                    baseColorFactor = getVec4(bl_node.inputs['BaseColorFactor'].default_value, [1.0, 1.0, 1.0, 1.0])
                    if baseColorFactor[0] != 1.0 or baseColorFactor[1] != 1.0 or baseColorFactor[2] != 1.0 or baseColorFactor[3] != 1.0:
                        pbrMetallicRoughness['baseColorFactor'] = baseColorFactor
                        alpha = baseColorFactor[3]


                    metallicFactor = getScalar(bl_node.inputs['MetallicFactor'].default_value, 1.0)
                    if metallicFactor != 1.0:
                        pbrMetallicRoughness['metallicFactor'] = metallicFactor

                    roughnessFactor = getScalar(bl_node.inputs['RoughnessFactor'].default_value, 1.0)
                    if roughnessFactor != 1.0:
                        pbrMetallicRoughness['roughnessFactor'] = roughnessFactor


                    index = getTextureIndexNode(exportSettings, glTF, 'MetallicRoughness', bl_node)
                    if index >= 0:
                        metallicRoughnessTexture = {
                            'index' : index
                        }

                        texCoord = getTexcoordIndex(glTF, 'MetallicRoughness', bl_node)
                        if texCoord > 0:
                            metallicRoughnessTexture['texCoord'] = texCoord

                        pbrMetallicRoughness['metallicRoughnessTexture'] = metallicRoughnessTexture


                    index = getTextureIndexNode(exportSettings, glTF, 'Emissive', bl_node)
                    if index >= 0:
                        emissiveTexture = {
                            'index' : index
                        }

                        texCoord = getTexcoordIndex(glTF, 'Emissive', bl_node)
                        if texCoord > 0:
                            emissiveTexture['texCoord'] = texCoord

                        material['emissiveTexture'] = emissiveTexture


                    emissiveFactor = getVec3(bl_node.inputs['EmissiveFactor'].default_value, [0.0, 0.0, 0.0])
                    if emissiveFactor[0] != 0.0 or emissiveFactor[1] != 0.0 or emissiveFactor[2] != 0.0:
                        material['emissiveFactor'] = emissiveFactor


                    index = getTextureIndexNode(exportSettings, glTF, 'Normal', bl_node)
                    if index >= 0:
                        normalTexture = {
                            'index' : index
                        }

                        texCoord = getTexcoordIndex(glTF, 'Normal', bl_node)
                        if texCoord > 0:
                            normalTexture['texCoord'] = texCoord

                        scale = getScalar(bl_node.inputs['NormalScale'].default_value, 1.0)

                        if scale != 1.0:
                            normalTexture['scale'] = scale

                        material['normalTexture'] = normalTexture


                    if len(bl_node.inputs['Occlusion'].links) > 0:
                        index = getTextureIndexNode(exportSettings, glTF, 'Occlusion', bl_node)
                        if index >= 0:
                            occlusionTexture = {
                                'index' : index
                            }

                            texCoord = getTexcoordIndex(glTF, 'Occlusion', bl_node)
                            if texCoord > 0:
                                occlusionTexture['texCoord'] = texCoord

                            strength = getScalar(bl_node.inputs['OcclusionStrength'].default_value, 1.0)

                            if strength != 1.0:
                                occlusionTexture['strength'] = strength

                            material['occlusionTexture'] = occlusionTexture

                    if bl_mat.v3d.render_side == 'DOUBLE':
                        material['doubleSided'] = True

                    # Use Color_0

                    if getScalar(bl_node.inputs['Use COLOR_0'].default_value, 0.0) < 0.5:
                        exportSettings['use_no_color'].append(bl_mat.name)


                elif isinstance(bl_node, bpy.types.ShaderNodeBsdfPrincipled):

                    material['pbrMetallicRoughness'] = {}
                    pbrMetallicRoughness = material['pbrMetallicRoughness']

                    alpha = getScalar(bl_node.inputs['Alpha'].default_value, 1.0)

                    baseColorFactor = getVec4(bl_node.inputs['Base Color'].default_value, [1.0, 1.0, 1.0, 1.0])
                    baseColorFactor[3] = alpha

                    index = getTextureIndexNode(exportSettings, glTF, 'Base Color', bl_node)
                    if index >= 0:
                        baseColorTexture = {
                            'index' : index
                        }

                        texCoord = getTexcoordIndex(glTF, 'Base Color', bl_node)
                        if texCoord > 0:
                            baseColorTexture['texCoord'] = texCoord

                        pbrMetallicRoughness['baseColorTexture'] = baseColorTexture

                        colorNode = bl_node.inputs['Base Color'].links[0].from_node
                        if isinstance(colorNode, bpy.types.ShaderNodeMixRGB) and colorNode.blend_type == 'MULTIPLY':
                            if len(colorNode.inputs['Color1'].links) == 0:
                                vec = getVec3(colorNode.inputs['Color1'].default_value)
                                baseColorFactor[0] = vec[0]
                                baseColorFactor[1] = vec[1]
                                baseColorFactor[2] = vec[2]
                            elif len(colorNode.inputs['Color2'].links) == 0:
                                vec = getVec3(colorNode.inputs['Color2'].default_value)
                                baseColorFactor[0] = vec[0]
                                baseColorFactor[1] = vec[1]
                                baseColorFactor[2] = vec[2]
                            else:
                                baseColorFactor[0] = 1.0
                                baseColorFactor[1] = 1.0
                                baseColorFactor[2] = 1.0

                    if (baseColorFactor[0] != 1.0 or baseColorFactor[1] != 1.0 or
                        baseColorFactor[2] != 1.0 or baseColorFactor[3] != 1.0):
                        pbrMetallicRoughness['baseColorFactor'] = baseColorFactor


                    index = getTextureIndexNode(exportSettings, glTF, 'Metallic', bl_node)
                    if index < 0:
                        index = getTextureIndexNode(exportSettings, glTF, 'Roughness', bl_node)

                    if index >= 0:
                        metallicRoughnessTexture = {
                            'index' : index
                        }

                        texCoord = getTexcoordIndex(glTF, 'Metallic', bl_node)
                        if texCoord == 0:
                            texCoord = getTexcoordIndex(glTF, 'Roughness', bl_node)

                        if texCoord > 0:
                            metallicRoughnessTexture['texCoord'] = texCoord

                        pbrMetallicRoughness['metallicRoughnessTexture'] = metallicRoughnessTexture

                    else:
                        metallicFactor = getScalar(bl_node.inputs['Metallic'].default_value, 1.0)
                        if metallicFactor != 1.0:
                            pbrMetallicRoughness['metallicFactor'] = metallicFactor

                        roughnessFactor = getScalar(bl_node.inputs['Roughness'].default_value, 1.0)
                        if roughnessFactor != 1.0:
                            pbrMetallicRoughness['roughnessFactor'] = roughnessFactor


                    toNode = bl_node.outputs['BSDF'].links[0].to_node
                    if isinstance(toNode, bpy.types.ShaderNodeMixShader):
                        index = getTextureIndexNode(exportSettings, glTF, 'Fac', toNode)
                        if index >= 0:
                            occlusionTexture = {
                                'index' : index
                            }

                            texCoord = getTexcoordIndex(glTF, 'Face', toNode)
                            if texCoord > 0:
                                occlusionTexture['texCoord'] = texCoord

                            material['occlusionTexture'] = occlusionTexture


                    index = getTextureIndexNode(exportSettings, glTF, 'Emission', bl_node)
                    if index >= 0:
                        emissiveTexture = {
                            'index' : index
                        }

                        texCoord = getTexcoordIndex(glTF, 'Emission', bl_node)
                        if texCoord > 0:
                            emissiveTexture['texCoord'] = texCoord

                        material['emissiveTexture'] = emissiveTexture
                        material['emissiveFactor'] = [1.0, 1.0, 1.0]
                    else:
                        emissiveFactor = getVec3(bl_node.inputs['Emission'].default_value, [0.0, 0.0, 0.0])
                        if emissiveFactor[0] != 0.0 or emissiveFactor[1] != 0.0 or emissiveFactor[2] != 0.0:
                            material['emissiveFactor'] = emissiveFactor


                    index = getTextureIndexNode(exportSettings, glTF, 'Normal', bl_node)
                    if index >= 0:
                        normalTexture = {
                            'index' : index
                        }

                        texCoord = getTexcoordIndex(glTF, 'Normal', bl_node)
                        if texCoord > 0:
                            normalTexture['texCoord'] = texCoord

                        scale = getScalar(bl_node.inputs['Normal'].links[0].from_node.inputs['Strength'].default_value, 1.0)

                        if scale != 1.0:
                            normalTexture['scale'] = scale

                        material['normalTexture'] = normalTexture

                    if bl_mat.v3d.render_side == 'DOUBLE':
                        material['doubleSided'] = True


        else:
            # Basic and Node-based materials

            if matHasBlendBackside(bl_mat):
                v3dExt['depthWrite'] = False
                material['doubleSided'] = True
                v3dExt['renderSide'] = 'DOUBLE'
            else:
                if bl_mat.v3d.render_side == 'DOUBLE':
                    material['doubleSided'] = True
                if bl_mat.v3d.render_side != 'FRONT':
                    v3dExt['renderSide'] = bl_mat.v3d.render_side
                if bl_mat.blend_method != 'OPAQUE' and bl_mat.v3d.depth_write == False:
                    v3dExt['depthWrite'] = bl_mat.v3d.depth_write

            if bl_mat.v3d.depth_test == False:
                v3dExt['depthTest'] = bl_mat.v3d.depth_test

            if bl_mat.v3d.dithering == True:
                v3dExt['dithering'] = bl_mat.v3d.dithering

            if mat_type == 'CYCLES':
                v3dExt['nodeGraph'] = extractNodeGraph(bl_mat.node_tree,
                        exportSettings, glTF)
            else:
                v3dExt['nodeGraph'] = composeNodeGraph(bl_mat, exportSettings, glTF)


        alphaMode = 'OPAQUE'

        if bl_mat.blend_method == 'CLIP':
            alphaMode = 'MASK'
            material['alphaCutoff'] = bl_mat.alpha_threshold + ALPHA_CUTOFF_EPS
        elif bl_mat.blend_method != 'OPAQUE':
            alphaMode = 'BLEND'

        if alphaMode != 'OPAQUE':
            material['alphaMode'] = alphaMode

        material['name'] = bl_mat.name

        if matIsBlend(bl_mat):

            if bl_mat.blend_method == 'ADD':
                blendMode = gltf.createBlendMode('FUNC_ADD', 'ONE', 'ONE')
            elif bl_mat.blend_method == 'BLEND':
                blendMode = gltf.createBlendMode('FUNC_ADD', 'ONE', 'ONE_MINUS_SRC_ALPHA')
            elif bl_mat.blend_method == 'MULTIPLY':
                blendMode = gltf.createBlendMode('FUNC_ADD', 'DST_COLOR', 'ONE_MINUS_SRC_ALPHA')

            v3dExt['blendMode'] = blendMode

        # receive
        if exportSettings['use_shadows']:
            # useShadows is assigned on objects not materials
            v3dExt['useCastShadows'] = False if bl_mat.shadow_method == 'NONE' else True

        if exportSettings['custom_props']:
            props = createCustomProperty(bl_mat)

            if props is not None:
                if 'extras' not in material:
                    material['extras'] = {}
                material['extras']['customProps'] = props

        materials.append(material)


    if len (materials) > 0:
        if v3dExtUsed:
            gltf.appendExtension(glTF, 'S8S_v3d_material_data')


        glTF['materials'] = materials


def generateScenes(operator, context, exportSettings, glTF):
    """
    Generates the top level scenes entry.
    """

    scenes = []

    for bl_scene in bpy.data.scenes:

        # Property: scene


        scene = {}
        scene['extras'] = {}


        nodes = []

        scene_objects = bl_scene.collection.all_objects

        for bl_obj in scene_objects:
            if bl_obj.parent is None:
                node_index = gltf.getNodeIndex(glTF, bl_obj.name)

                if node_index < 0:
                    continue

                nodes.append(node_index)

        # TODO: need it only on the main scene
        if getCameraIndex(glTF, '__DEFAULT__') >= 0:
            nodes.append(gltf.getNodeIndex(glTF, '__DEFAULT_CAMERA__'))

        if len(nodes) > 0:
            scene['nodes'] = nodes

        v3dExt = {}
        scene['extensions'] = { 'S8S_v3d_scene_data' : v3dExt }

        if bl_scene.world:
            world_mat = gltf.getMaterialIndex(glTF, WORLD_NODE_MAT_NAME.substitute(
                    name=bl_scene.world.name))
            if world_mat >= 0:
                v3dExt['worldMaterial'] = world_mat

        v3dExt['physicallyCorrectLights'] = True

        if exportSettings['use_shadows']:
            v3dExt['shadowMap'] = {
                'type': 'ESM' if bpy.app.version < (2,81,0) else exportSettings['shadow_map_type'],
                'renderReverseSided' : True if exportSettings['shadow_map_side'] == 'BACK' else False,
                'renderSingleSided' : False if exportSettings['shadow_map_side'] == 'BOTH' else True,
                'esmDistanceScale': exportSettings['esm_distance_scale']
            }

        v3dExt['iblEnvironmentMode'] = exportSettings['ibl_environment_mode']

        v3dExt['aaMethod'] = exportSettings['aa_method']

        if exportSettings['use_hdr']:
            v3dExt['useHDR'] = True

        outline = bl_scene.v3d.outline

        if outline.enabled:
            v3dExt['postprocessing'] = []

            effect = {
                'type': 'outline',
                'edgeStrength': outline.edge_strength,
                'edgeGlow': outline.edge_glow,
                'edgeThickness': outline.edge_thickness,
                'pulsePeriod': outline.pulse_period,
                'visibleEdgeColor': extractVec(outline.visible_edge_color),
                'hiddenEdgeColor': extractVec(outline.hidden_edge_color),
                'renderHiddenEdge': outline.render_hidden_edge
            }

            v3dExt['postprocessing'].append(effect)

        if bl_scene.view_settings.view_transform == 'Filmic':
            v3dExt['toneMapping'] = {
                'type': 'filmicBlender'
            }

        v3dExt['pmremMaxTileSize'] = clamp(int(bl_scene.eevee.gi_cubemap_resolution),
                PMREM_SIZE_MIN, PMREM_SIZE_MAX)

        scene['extras']['animFrameRate'] = bl_scene.render.fps
        scene['extras']['coordSystem'] = 'Z_UP_RIGHT'

        if exportSettings['custom_props']:
            props = createCustomProperty(bl_scene)

            if props is not None:
                scene['extras']['customProps'] = props


        scene['name'] = bl_scene.name

        scenes.append(scene)

    if len(scenes) > 0:
        glTF['scenes'] = scenes

        gltf.appendExtension(glTF, 'S8S_v3d_scene_data')

def generateScene(operator, context, exportSettings, glTF):
    """
    Generates the top level scene entry.
    """

    index = gltf.getSceneIndex(glTF, bpy.context.window.scene.name)
    if index >= 0:
        glTF['scene'] = index

def generateFinish(operator, context, exportSettings, glTF):

    # Texture Coordinate nodes refer to scene objects (needed for the Object output).
    # Objects are not processed yet when generating materials and node graphs,
    # thus have to set this relation only in the end.
    if glTF.get('materials') is not None:
        for mat in glTF['materials']:
            nGraph = gltf.getNodeGraph(mat)
            if nGraph is not None:
                nodeGraphReplaceTexCoordObject(nGraph, glTF)

    v3dExt = gltf.getAssetExtension(glTF, 'S8S_v3d_data')
    if v3dExt is not None and 'nodeGraphs' in v3dExt:
        for nGraph in v3dExt['nodeGraphs']:
            nodeGraphReplaceTexCoordObject(nGraph, glTF)

def nodeGraphReplaceTexCoordObject(nGraph, glTF):
    for matNode in nGraph['nodes']:
        if matNode['type'] == 'TEX_COORD_BL':
            matNode['object'] = (gltf.getNodeIndex(glTF, matNode['object'].name)
                    if matNode['object'] is not None else -1)

def generateGLTF(operator,
                  context,
                  exportSettings,
                  glTF):
    """
    Generates the main glTF structure.
    """

    generateAsset(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(5)

    generateImages(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(10)

    generateTextures(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(20)

    generateNodeGraphs(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(25)

    generateMaterials(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(30)

    generateCurves(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(35)

    generateCameras(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(40)

    generateLights(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(50)

    generateMeshes(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(60)

    generateNodes(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(70)

    if exportSettings['animations']:
        generateAnimations(operator, context, exportSettings, glTF)
        bpy.context.window_manager.progress_update(80)

    bpy.context.window_manager.progress_update(80)

    generateScenes(operator, context, exportSettings, glTF)

    bpy.context.window_manager.progress_update(90)

    generateScene(operator, context, exportSettings, glTF)

    bpy.context.window_manager.progress_update(95)

    generateFinish(operator, context, exportSettings, glTF)

    bpy.context.window_manager.progress_update(100)



    byteLength = len(exportSettings['binary'])

    if byteLength > 0:
        glTF['buffers'] = []

        buffer = {
            'byteLength' : byteLength
        }

        if exportSettings['format'] == 'ASCII':
            uri = exportSettings['binaryfilename']

            if exportSettings['embed_buffers']:
                uri = 'data:application/octet-stream;base64,' + base64.b64encode(exportSettings['binary']).decode('ascii')

            buffer['uri'] = uri

        glTF['buffers'].append(buffer)
