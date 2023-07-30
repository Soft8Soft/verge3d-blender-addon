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
import json
import math
import os.path
import shutil

join = os.path.join
norm = os.path.normpath

from pluginUtils.log import printLog
import pluginUtils.gltf as gltf
import pluginUtils.rawdata

from .gltf2_animate import *
from .gltf2_extract import *
from .gltf2_filter import *
from .gltf2_get import *
from .utils import *


# Blender default grey color
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

ROTATION_NODE_TYPES = [
    'NODE_X_90',
    'NODE_INV_X_90',
    'NODE_INV_X_90_X_90'

]

def generateAsset(operator, context, exportSettings, glTF):
    """
    Generates the top level asset entry.
    """

    asset = {}

    asset['version'] = '2.0'
    asset['generator'] = 'Verge3D for Blender'

    if exportSettings['copyright'] != "":
        asset['copyright'] = exportSettings['copyright']

    glTF['asset'] = asset

def generateAnimChannel(glTF, blObject, samplerName, path, nodeName, samplers, channels):

    idx = getIndex(samplers, samplerName)
    if idx > -1:
        channel = gltf.createAnimChannel(idx, gltf.getNodeIndex(glTF, nodeName), path)

        # HACK: avoid channel duplication (occurs when animating an armature object)
        for ch in channels:
            if ch['target'] == channel['target']:
                return None

        # to resolve default animation params
        channel['bl_obj'] = blObject

        channels.append(channel)

        return channel

    return None

def generateAnimationsParameter(operator,
                  context,
                  exportSettings,
                  glTF,
                  action,
                  channels,
                  samplers,
                  bl_obj,
                  bl_bone,
                  bl_mat_name,
                  bl_mat_node_name,
                  rotation_mode,
                  is_morph_data,
                  constraint_name=None):
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
    eval_time = [] # follow path constraint animation
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
        'energy': energy,
        'eval_time': eval_time
    }

    node_type = 'NODE'
    used_node_name = bl_node_name

    # correcting rotation animation
    if bl_obj.type == 'CAMERA' or bl_obj.type == 'LIGHT' or bl_obj.type == 'FONT':
        node_type = 'NODE_X_90'

    parent = bl_obj.parent
    if parent:
        if parent.type in ('CAMERA', 'LIGHT', 'FONT'):
            if node_type == 'NODE_X_90':
                node_type = 'NODE_INV_X_90_X_90'
            else:
                node_type = 'NODE_INV_X_90'

    if bl_bone != None:
        node_type = 'JOINT'
        used_node_name = bl_bone.name
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
            elif node_type == 'NODE' or node_type in ROTATION_NODE_TYPES:
                continue
            else:
                prefix = node_name + "_"
                postfix = "_"  + node_name

        data_path = getAnimParam(bl_fcurve.data_path)

        if (data_path not in ['location', 'rotation_axis_angle',
                'rotation_euler', 'rotation_quaternion', 'scale',
                'value', 'default_value', 'energy', 'eval_time']):
            continue

        if data_path not in ['value', 'eval_time']:
            data[data_path][bl_fcurve.array_index] = bl_fcurve
        else:
            data[data_path].append(bl_fcurve)

    # same for all animations we export currently
    componentType = 'FLOAT'

    # create location sampler

    if location.count(None) < 3:

        sampler_name = prefix + action.name + "_translation"

        if getIndex(samplers, sampler_name) == -1:

            interpolation = animateGetInterpolation(exportSettings, location)
            if interpolation == 'CUBICSPLINE' and node_type == 'JOINT':
                interpolation = 'CONVERSION_NEEDED'

            translation_data, in_tangent_data, out_tangent_data = animateLocation(
                    exportSettings, location, interpolation, node_type, bl_obj,
                    bl_bone)


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


            count = len(final_keys)
            if count:
                sampler = {}

                sampler['interpolation'] = interpolation
                if interpolation == 'CONVERSION_NEEDED':
                    sampler['interpolation'] = 'LINEAR'

                type = 'SCALAR'
                input = gltf.generateAccessor(glTF, exportSettings['binary'],
                        final_keys, componentType, count, type, '')
                sampler['input'] = input

                count = len(values) // 3
                type = 'VEC3'
                output = gltf.generateAccessor(glTF, exportSettings['binary'],
                        values, componentType, count, type, '')
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

        has_axis_angle = rotation_axis_angle.count(None) < 4
        has_euler = rotation_euler.count(None) < 3
        has_quaternion = rotation_quaternion.count(None) < 4

        if has_axis_angle:
            interpolation = animateGetInterpolation(exportSettings, rotation_axis_angle)
            # conversion required in any case
            if interpolation == 'CUBICSPLINE':
                interpolation = 'CONVERSION_NEEDED'

            rotation_data = rotation_data or {}
            rotation_data.update(animateRotationAxisAngle(exportSettings,
                    rotation_axis_angle, interpolation, node_type, bl_obj,
                    bl_bone))

        if has_euler:
            interpolation = animateGetInterpolation(exportSettings, rotation_euler)
            # conversion required in any case
            # also for linear interpolation to fix issues with e.g 2*PI keyframe differences
            if interpolation == 'CUBICSPLINE' or interpolation == 'LINEAR':
                interpolation = 'CONVERSION_NEEDED'

            rotation_data = rotation_data or {}
            rotation_data.update(animateRotationEuler(exportSettings,
                    rotation_euler, rotation_mode, interpolation, node_type,
                    bl_obj, bl_bone))

        if has_quaternion:
            interpolation = animateGetInterpolation(exportSettings, rotation_quaternion)
            if interpolation == 'CUBICSPLINE' and node_type == 'JOINT':
                interpolation = 'CONVERSION_NEEDED'
            rotation_data_quat, rotation_in_tangent_data, rotation_out_tangent_data = animateRotationQuaternion(
                    exportSettings, rotation_quaternion, interpolation,
                    node_type, bl_obj, bl_bone)

            rotation_data = rotation_data or {}
            rotation_data.update(rotation_data_quat)

        if has_quaternion and (has_axis_angle or has_euler):
            # NOTE: set tangent data to zeros just in case, since it's not clear
            # what to do with it when mixing different types of rotation keyframes
            rotation_in_tangent_data = [0.0, 0.0, 0.0, 0.0]
            rotation_out_tangent_data = [0.0, 0.0, 0.0, 0.0]

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

        count = len(final_keys)
        if count:
            sampler = {}

            sampler['interpolation'] = interpolation
            if interpolation == 'CONVERSION_NEEDED':
                sampler['interpolation'] = 'LINEAR'

            type = 'SCALAR'
            input = gltf.generateAccessor(glTF, exportSettings['binary'], final_keys, componentType, count, type, '')
            sampler['input'] = input

            count = len(values) // 4
            type = 'VEC4'
            output = gltf.generateAccessor(glTF, exportSettings['binary'], values, componentType, count, type, '')
            sampler['output'] = output

            sampler['name'] = sampler_name

            samplers.append(sampler)

    # create scale sampler

    if scale.count(None) < 3:
        sampler_name = prefix + action.name + "_scale"

        if getIndex(samplers, sampler_name) == -1:

            interpolation = animateGetInterpolation(exportSettings, scale)
            if interpolation == 'CUBICSPLINE' and node_type == 'JOINT':
                interpolation = 'CONVERSION_NEEDED'

            scale_data, in_tangent_data, out_tangent_data = animateScale(
                    exportSettings, scale, interpolation, node_type, bl_obj,
                    bl_bone)

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

            count = len(final_keys)
            if count:
                sampler = {}

                sampler['interpolation'] = interpolation
                if interpolation == 'CONVERSION_NEEDED':
                    sampler['interpolation'] = 'LINEAR'

                type = 'SCALAR'
                input = gltf.generateAccessor(glTF, exportSettings['binary'], final_keys, componentType, count, type, '')
                sampler['input'] = input

                count = len(values) // 3
                type = 'VEC3'
                output = gltf.generateAccessor(glTF, exportSettings['binary'], values, componentType, count, type, '')
                sampler['output'] = output

                sampler['name'] = sampler_name

                samplers.append(sampler)

    # create morph target sampler

    if len(value) > 0 and is_morph_data:
        sampler_name = prefix + action.name + "_weights"

        if getIndex(samplers, sampler_name) == -1:

            interpolation = animateGetInterpolation(exportSettings, value)
            if interpolation == 'CUBICSPLINE' and node_type == 'JOINT':
                interpolation = 'CONVERSION_NEEDED'

            value_data, in_tangent_data, out_tangent_data = animateValue(
                    exportSettings, value, interpolation, node_type)

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

            count = len(final_keys)
            if count:
                sampler = {}

                sampler['interpolation'] = interpolation
                if interpolation == 'CONVERSION_NEEDED':
                    sampler['interpolation'] = 'LINEAR'

                type = 'SCALAR'
                input = gltf.generateAccessor(glTF, exportSettings['binary'], final_keys, componentType, count, type, '')
                sampler['input'] = input

                count = len(values)
                type = 'SCALAR'
                output = gltf.generateAccessor(glTF, exportSettings['binary'], values, componentType, count, type, '')
                sampler['output'] = output

                sampler['name'] = sampler_name

                samplers.append(sampler)

    # create material node anim sampler
    def_val_dim = len(default_value)

    # NOTE: only value/colors supported for now
    if (def_val_dim == 1 or def_val_dim == 4) and default_value.count(None) < def_val_dim:
        sampler_name = prefix + action.name + "_mat_node_anim"

        if getIndex(samplers, sampler_name) == -1:

            interpolation = animateGetInterpolation(exportSettings, default_value)

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

            count = len(final_keys)
            if count:
                sampler = {}

                sampler['interpolation'] = interpolation
                if interpolation == 'CONVERSION_NEEDED':
                    sampler['interpolation'] = 'LINEAR'

                type = 'SCALAR'
                input = gltf.generateAccessor(glTF, exportSettings['binary'],
                        final_keys, componentType, count, type, "")
                sampler['input'] = input

                count = len(values) // def_val_dim
                if def_val_dim == 1:
                    type = 'SCALAR'
                else:
                    type = 'VEC4'
                output = gltf.generateAccessor(glTF, exportSettings['binary'],
                        values, componentType, count, type, "")
                sampler['output'] = output

                sampler['name'] = sampler_name

                samplers.append(sampler)

    if energy.count(None) < 1:
        sampler_name = prefix + action.name + '_energy'

        if getIndex(samplers, sampler_name) == -1:

            interpolation = animateGetInterpolation(exportSettings, energy)

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

            count = len(final_keys)
            if count:
                sampler = {}

                sampler['interpolation'] = interpolation
                if interpolation == 'CONVERSION_NEEDED':
                    sampler['interpolation'] = 'LINEAR'

                type = 'SCALAR'
                input = gltf.generateAccessor(glTF, exportSettings['binary'],
                        final_keys, componentType, count, type, "")
                sampler['input'] = input

                count = len(values)
                type = 'SCALAR'
                output = gltf.generateAccessor(glTF, exportSettings['binary'],
                        values, componentType, count, type, "")
                sampler['output'] = output

                sampler['name'] = sampler_name

                samplers.append(sampler)

    if len(eval_time) > 0:
        sampler_name = prefix + action.name + "_eval_time"

        if getIndex(samplers, sampler_name) == -1:

            interpolation = animateGetInterpolation(exportSettings, eval_time)

            value_data, in_tangent_data, out_tangent_data = animateValue(
                    exportSettings, eval_time, interpolation, node_type)

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

            count = len(final_keys)

            if count < 1:
                printLog('WARNING', 'Follow path constraint supports only keyframe animation, constraint name: ' + constraint_name)
                return None

            sampler = {}

            sampler['interpolation'] = interpolation
            if interpolation == 'CONVERSION_NEEDED':
                sampler['interpolation'] = 'LINEAR'

            bl_follow_path_constraint = None
            for bl_cons in bl_obj.constraints:
                if bl_cons.is_valid and bl_cons.name == constraint_name:
                    bl_follow_path_constraint = bl_cons
                    break

            if bl_follow_path_constraint is None:
                printLog('WARNING', 'Can not export follow path animation, constraint name: ' + constraint_name)
                return None

            bl_spline = bl_follow_path_constraint.target.data
            ratio = 1.0 / bl_spline.path_duration
            for i in range(len(values)):
                values[i] *= ratio

            type ='SCALAR'
            input = gltf.generateAccessor(glTF, exportSettings['binary'], final_keys, componentType, count, type, "")
            sampler['input'] = input

            count = len(values)
            type = 'SCALAR'
            output = gltf.generateAccessor(glTF, exportSettings['binary'], values, componentType, count, type, "")
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
            elif node_type == 'NODE' or node_type in ROTATION_NODE_TYPES:
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
            if channel and bl_mat_name != None:
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

        elif data_path == 'eval_time':
            path = 'constraint["' + constraint_name + '"].value'
            if path in processed_paths:
                continue
            processed_paths.append(path)

            sampler_name = prefix + action.name + '_eval_time'
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

                # NOTE: int to prevent crashes in Blender 3.1+
                bpy.ops.nla.bake(frame_start=int(start), frame_end=int(end),
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
                False)

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
                        jointKey = getPtr(bl_bone)
                        if not exportSettings['joint_cache'].get(jointKey):
                            exportSettings['joint_cache'][jointKey] = {}

                        joint_matrix = getBoneJointMatrix(bl_obj, bl_bone,
                                exportSettings['bake_armature_actions'])

                        tmp_location, tmp_rotation, tmp_scale = decomposeTransformSwizzle(joint_matrix)

                        exportSettings['joint_cache'][jointKey][float(frame)] = [tmp_location, tmp_rotation, tmp_scale]

                for bl_bone in bl_obj.pose.bones:
                    generateAnimationsParameter(operator, context, exportSettings, glTF,
                            bl_action, channels, samplers, bl_obj, bl_bone,
                            None, None, bl_bone.rotation_mode, False)



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
                True)

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
                True)


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

            node_names = [n.name for n in bl_mat.node_tree.nodes]

            for name in node_names:
                generateAnimationsParameter(operator, context, exportSettings, glTF,
                        bl_action, channels, samplers, bl_obj, None,
                        bl_mat.name, name, bl_obj.rotation_mode, False)


    # export follow path constraint's animation

    for bl_obj in filtered_objects_with_dg:
        bl_follow_path_constraint = None
        for bl_cons in bl_obj.constraints:
            if bl_cons.is_valid and bl_cons.type == 'FOLLOW_PATH':
                bl_follow_path_constraint = bl_cons
                break

        if (bl_obj.data is None or bl_follow_path_constraint is None or
                bl_follow_path_constraint.target is None):
            continue

        bl_folow_path_obj = bl_follow_path_constraint.target
        bl_spline = bl_folow_path_obj.data

        if bl_spline is None or bl_spline.animation_data is None:
            continue

        bl_action = bl_spline.animation_data.action

        if bl_action is None:
            continue

        generateAnimationsParameter(operator, context, exportSettings, glTF, bl_action,
                channels, samplers, bl_obj, None, None, None, bl_obj.rotation_mode,
                True, bl_follow_path_constraint.name)


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

            v3dExt = gltf.appendExtension(glTF, 'S8S_v3d_animation', animation)

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

        gltf.appendExtension(glTF, 'S8S_v3d_camera')

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
        v3dExt['enablePointerLock'] = bl_camera.v3d.enable_pointer_lock

    camera['extensions'] = { 'S8S_v3d_camera' : v3dExt }

    return camera

def generateCameraFromView(aspectRatio):

    printLog('INFO', 'Generating default camera')

    region3D = getView3DSpaceProp('region_3d')
    if region3D == None:
        return None

    camera = {}

    camera['name'] = '__DEFAULT__'

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
    camera['extensions'] = { 'S8S_v3d_camera' : v3dExt }

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

        light['name'] = bl_light.name
        light['profile'] = 'blender'

        if bl_light.type == 'SUN':
            light['type'] = 'directional'
        elif bl_light.type == 'POINT':
            light['type'] = 'point'
        elif bl_light.type == 'SPOT':
            light['type'] = 'spot'
        elif bl_light.type == 'AREA':
            light['type'] = 'area'
        else:
            continue

        light['color'] = getLightCyclesColor(bl_light)
        light['intensity'] = getLightCyclesStrength(bl_light)

        useShadows = exportSettings['use_shadows'] and bl_light.use_shadow

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


        if bl_light.type == 'POINT' or bl_light.type == 'SPOT' or bl_light.type == 'AREA':

            if bl_light.use_custom_distance:
                dist = bl_light.cutoff_distance
            else:
                dist = calcLightThresholdDist(bl_light, eeveeCtx.light_threshold)
            light['distance'] = dist
            light['decay'] = 2

            if bl_light.type == 'SPOT':
                light['angle'] = bl_light.spot_size / 2;
                light['penumbra'] = bl_light.spot_blend;

            elif bl_light.type == 'AREA':

                width = bl_light.size

                if bl_light.shape in ['SQUARE', 'DISK']:
                    height = bl_light.size
                else:
                    height = bl_light.size_y

                # do not allow small or zero size
                width = max(width, 0.01)
                height = max(height, 0.01)

                light['intensity'] /= (width * height)

                light['width'] = width
                light['height'] = height

                light['ltcMat1'] = pluginUtils.rawdata.ltcMat1
                light['ltcMat2'] = pluginUtils.rawdata.ltcMat2


        lights.append(light)

    if len(lights) > 0:
        gltf.appendExtension(glTF, 'S8S_v3d_lights', glTF, {'lights': lights})


def generateLightProbes(operator, context, exportSettings, glTF):
    """
    Generates the top level lightProbes entry.
    """

    probes = []

    filteredLightProbes = exportSettings['filtered_light_probes']
    for blProbe in filteredLightProbes:

        probe = {
            'name': blProbe.name,
            'type': blProbe.type,
            'influenceDistance': blProbe.influence_distance,
            'clipStart': blProbe.clip_start,
            'visibilityGroup': (blProbe.visibility_collection.name
                    if blProbe.visibility_collection is not None else None),
            'visibilityGroupInv': blProbe.invert_visibility_collection
        }

        if blProbe.type == 'CUBEMAP':
            probe['influenceType'] = blProbe.influence_type
            probe['parallaxType'] = blProbe.parallax_type if blProbe.use_custom_parallax else blProbe.influence_type
            probe['parallaxDistance'] = blProbe.parallax_distance if blProbe.use_custom_parallax else blProbe.influence_distance
            probe['intensity'] = blProbe.intensity
            probe['clipEnd'] = blProbe.clip_end
            probe['influenceGroup'] = (blProbe.v3d.influence_collection.name
                    if blProbe.v3d.use_custom_influence
                    and blProbe.v3d.influence_collection is not None else None)
            probe['influenceGroupInv'] = blProbe.v3d.invert_influence_collection
        else:
            probe['falloff'] = blProbe.falloff

        probes.append(probe)

    if len(probes):
        gltf.appendExtension(glTF, 'S8S_v3d_light_probes', glTF, {'lightProbes': probes})


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

        v3dExt = gltf.appendExtension(glTF, 'S8S_v3d_mesh', mesh)

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
                gltf.appendExtension(glTF, 'S8S_v3d_materials')
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

            # swap UV coords, set active render UV as first (as TEXCOORD_0)
            if len(bl_mesh.uv_layers) > 0 and not bl_mesh.uv_layers[0].active_render:
                for texcoord_index in range(len(bl_mesh.uv_layers)):
                    if bl_mesh.uv_layers[texcoord_index].active_render:
                        texcoord_id = 'TEXCOORD_' + str(texcoord_index)

                        texcoord_0 = attributes['TEXCOORD_0']
                        attributes['TEXCOORD_0'] = attributes[texcoord_id]
                        attributes[texcoord_id] = texcoord_0

                        if internal_primitive['useNodeAttrs']:
                            old_uv_layer_name = bl_mesh.uv_layers[0].name
                            v3dExt['uvLayers'][old_uv_layer_name] = texcoord_id;

                            new_uv_layer_name = bl_mesh.uv_layers[texcoord_index].name
                            v3dExt['uvLayers'][new_uv_layer_name] = 'TEXCOORD_0';
                        break

            # vertex colors

            v3dExt['colorLayers'] = {}

            color_index = 0

            # COMPAT: < Blender 3.2
            bl_vertex_colors = bl_mesh.color_attributes if bpy.app.version >= (3, 2, 0) else bl_mesh.vertex_colors

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
                        vc_layer_name = bl_vertex_colors[color_index].name
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
                        if bl_shape_key != bl_shape_key.relative_key and bl_shape_key != bl_mesh.shape_keys.reference_key:

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
                        if bl_shape_key != bl_shape_key.relative_key and bl_shape_key != bl_mesh.shape_keys.reference_key:
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

    # remove unnecessary parameters
    if findArmature(bl_obj) is None:
        for prim in primitives:
            if 'JOINTS_0' in prim['attributes']: del prim['attributes']['JOINTS_0']
            if 'WEIGHTS_0' in prim['attributes']: del prim['attributes']['WEIGHTS_0']

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

        # when two objects, and one of them is skinned, have the same mesh,
        # duplicate the mesh (to have both skinned and unskinned variants)
        if not need_dublicate and findArmature(bl_obj) is None:
            idname = getPtr(bl_obj.data)
            for meshData in glTF['meshes']:
                key = 'id' if meshData.get('id') != None else 'name'
                if meshData.get(key) == idname:
                    need_dublicate = False
                    for prim in meshData['primitives']:
                        if 'JOINTS_0' in prim['attributes'] or 'WEIGHTS_0' in prim['attributes']:
                            need_dublicate = True
                            break

                    if not need_dublicate:
                        break

        if need_dublicate:
            mesh = generateDuplicateMesh(operator, context, exportSettings, glTF,
                    bl_obj)

    return mesh

def generateClippingPlanes(operator, context, exportSettings, glTF):
    '''
    Generates the top level clippingPlanes entry.
    '''

    planes = []

    filteredClippingPlanes = exportSettings['filtered_clipping_planes']

    for blPlane in filteredClippingPlanes:
        planes.append({
            'name': blPlane.name,
            'clippingGroup': (blPlane.v3d.clipping_plane_collection.name
                              if blPlane.v3d.clipping_plane_collection is not None else None),
            'negated': blPlane.v3d.clipping_plane_negated,
            'clipShadows': blPlane.v3d.clipping_plane_shadows,
            'clipIntersection': not blPlane.v3d.clipping_plane_union,
            'crossSection': blPlane.v3d.clipping_plane_cross_section if blPlane.v3d.clipping_plane_union else False,
            'color': extractVec(blPlane.v3d.clipping_plane_color)[0:3],
            'opacity': blPlane.v3d.clipping_plane_color[3],
            'renderSide': blPlane.v3d.clipping_plane_render_side,
            'size': blPlane.v3d.clipping_plane_size
        })

    if len(planes):
        gltf.appendExtension(glTF, 'S8S_v3d_clipping_planes', glTF, {'clippingPlanes': planes})


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

    v3dExt = gltf.appendExtension(glTF, 'S8S_v3d_node', node)

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
                gltf.appendExtension(glTF, 'S8S_v3d_curves', node, {'curve' : curve})

    elif bl_obj_type == 'CAMERA':
        # NOTE: possible issues with libraries
        camera = getCameraIndex(glTF, bl_obj.data.name)
        if camera >= 0:
            node['camera'] = camera

    elif bl_obj_type == 'LIGHT':
        light = gltf.getLightIndex(glTF, bl_obj.data.name)
        if light >= 0:
            gltf.appendExtension(glTF, 'S8S_v3d_lights', node, {'light' : light})

    elif bl_obj_type == 'LIGHT_PROBE':
        probe = gltf.getLightProbeIndex(glTF, bl_obj.data.name)
        if probe >= 0:
            gltf.appendExtension(glTF, 'S8S_v3d_light_probes', node, {'lightProbe' : probe})

    elif bl_obj_type == 'EMPTY' and bl_obj.v3d.clipping_plane:
        plane = gltf.getClippingPlaneIndex(glTF, bl_obj.name)
        if plane >= 0:
            gltf.appendExtension(glTF, 'S8S_v3d_clipping_planes', node, {'clippingPlane' : plane})

    v3dExt['hidden'] = bl_obj.hide_render
    v3dExt['renderOrder'] = bl_obj.v3d.render_order
    v3dExt['frustumCulling'] = bl_obj.v3d.frustum_culling
    v3dExt['hidpiCompositing'] = bl_obj.v3d.hidpi_compositing

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

    v3dExt['objectIndex'] = bl_obj.pass_index
    v3dExt['objectColor'] = getVec4(bl_obj.color)

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
    v3dExt = gltf.getAssetExtension(node, 'S8S_v3d_node')
    v3dExtParent = gltf.getAssetExtension(nodeParent, 'S8S_v3d_node')

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

        gltf.appendExtension(glTF, 'S8S_v3d_node')

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

            for bl_bone in bl_obj.pose.bones:
                node = {}

                joint_matrix = getBoneJointMatrix(bl_obj, bl_bone,
                        exportSettings['bake_armature_actions'])

                generateNodeParameter(joint_matrix, node)

                node['name'] = bl_obj.name + "_" + bl_bone.name

                joints.append(len(nodes))
                nodes.append(node)

            # add data for the armature itself at the end
            skeleton = gltf.getNodeIndex(glTF, bl_obj.name)
            joints.append(skeleton)


            children_list = list(bl_obj.children)
            for bl_check_object in filtered_objects_with_dg:
                bl_check_armature = findArmature(bl_check_object)

                if bl_check_armature == bl_obj and bl_check_object not in children_list:
                    children_list.append(bl_check_object)

            for bl_object_child in children_list:
                inverse_matrices = []

                for bl_bone in bl_obj.pose.bones:
                    bind_shape_matrix = bl_obj.matrix_world.inverted() @ bl_object_child.matrix_world
                    inverse_bind_matrix = convertSwizzleMatrix(bl_bone.bone.matrix_local.inverted() @ bind_shape_matrix)

                    for column in range(0, 4):
                        for row in range(0, 4):
                            inverse_matrices.append(inverse_bind_matrix[row][column])

                armature_inverse_bind_matrix = convertSwizzleMatrix(
                        bl_obj.matrix_world.inverted() @ bl_object_child.matrix_world)

                for column in range(0, 4):
                    for row in range(0, 4):
                        inverse_matrices.append(armature_inverse_bind_matrix[row][column])

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

        v3dExt = gltf.getAssetExtension(node, 'S8S_v3d_node')
        if v3dExt and ((exportSettings['export_constraints'] and len(bl_obj.constraints)) or
                       objHasFixOrthoZoom(bl_obj) or objHasCanvasFitParams(bl_obj) or
                       bl_obj.v3d.canvas_break_enabled):
            v3dExt['constraints'] = extractConstraints(glTF, bl_obj)

        # first-person camera link to collision material

        if (bl_obj.type == 'CAMERA' and
                bl_obj.data and
                bl_obj.data.v3d.controls == 'FIRST_PERSON' and
                bl_obj.data.v3d.fps_collision_material):

            v3d_cam_data = gltf.getAssetExtension(glTF['cameras'][node['camera']], 'S8S_v3d_camera')
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
    return ('extensions' in node and 'S8S_v3d_lights' in node['extensions']
            and 'light' in node['extensions']['S8S_v3d_lights'])

def nodeIsCurve(node):
    return ('extensions' in node and 'S8S_v3d_curves' in node['extensions']
            and 'curve' in node['extensions']['S8S_v3d_curves'])

def nodeIsPlaneReflProbe(node):
    return ('extensions' in node and 'S8S_v3d_light_probes' in node['extensions']
            and 'lightProbe' in node['extensions']['S8S_v3d_light_probes'])


def generateImages(operator, context, exportSettings, glTF):
    """
    Generates the top level images entry.
    """

    filtered_images = exportSettings['filtered_images']

    images = []

    for bl_image in filtered_images:
        try:
            image = createImage(bl_image, context, exportSettings, glTF)
        except pu.convert.CompressionFailed:
            bl_image['compression_error_status'] = 1
            # try again without compression
            image = createImage(bl_image, context, exportSettings, glTF)

        images.append(image)

    if len (images) > 0:
        glTF['images'] = images

def createImage(bl_image, context, exportSettings, glTF):

    image = {}

    uri = getImageExportedURI(exportSettings, bl_image)

    if exportSettings['format'] == 'ASCII':

        old_path = bl_image.filepath_from_user()
        # try to reuse external file if new_path == old_path
        new_path = norm(exportSettings['filedirectory'] + uri)

        if (bl_image.is_dirty or bl_image.packed_file is not None
                or not os.path.isfile(old_path)):
            # always extract data for dirty/packed/missing images,
            # because they can differ from an external source's data

            img_data = extractImageBindata(bl_image, context.scene, exportSettings)

            with open(new_path, 'wb') as f:
                f.write(img_data)

        elif os.path.normcase(old_path) != os.path.normcase(new_path):
            # copy an image to a new location

            if (bl_image.file_format != 'JPEG' and bl_image.file_format != 'PNG' and
                    bl_image.file_format != 'WEBP' and bl_image.file_format != 'BMP' and
                    bl_image.file_format != 'HDR'):
                # need conversion to PNG

                img_data = extractImageBindata(bl_image, context.scene, exportSettings)

                with open(new_path, 'wb') as f:
                    f.write(img_data)

            elif imgNeedsCompression(bl_image, exportSettings):
                if bl_image.file_format == 'HDR':
                    pu.convert.compressLZMA(old_path, dstPath=new_path)
                else:
                    pu.convert.compressKTX2(old_path, dstPath=new_path, method=bl_image.v3d.compression_method)
            else:
                shutil.copyfile(old_path, new_path)

        image['uri'] = uri

    else:
        # store image in glb

        img_data = extractImageBindata(bl_image, context.scene, exportSettings)

        bufferView = gltf.generateBufferView(glTF, exportSettings['binary'], img_data, '', 0)

        image['mimeType'] = getImageExportedMimeType(bl_image, exportSettings)
        image['bufferView'] = bufferView

    exportSettings['uri_cache']['uri'].append(uri)
    exportSettings['uri_cache']['bl_datablocks'].append(bl_image)

    return image


def generateTextures(operator, context, exportSettings, glTF):
    """
    Generates the top level textures entry.
    """

    filtered_textures = exportSettings['filtered_textures']

    textures = []

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
            printLog('ERROR', 'Unknown Blender texture type')
            return

        texture['sampler'] = gltf.createSampler(glTF, magFilter, wrap, wrap)

        # 'source' isn't required but must be >=0 according to GLTF 2.0 spec.
        img_index = getImageIndex(exportSettings, uri)
        if img_index >= 0:
            if os.path.splitext(uri)[1].lower() == '.ktx2':
                gltf.appendExtension(glTF, 'KHR_texture_basisu', texture, { 'source' : img_index })
            elif os.path.splitext(uri)[1].lower() == '.webp':
                gltf.appendExtension(glTF, 'EXT_texture_webp', texture, { 'source' : img_index })
            elif os.path.splitext(uri)[1].lower() in ['.hdr', '.xz']: # HDR or compressed HDR
                v3dExt['source'] = img_index
            else:
                texture['source'] = img_index

        gltf.appendExtension(glTF, 'S8S_v3d_texture', texture, v3dExt)

        textures.append(texture)

    if len (textures) > 0:
        glTF['textures'] = textures


def generateNodeGraphs(operator, context, exportSettings, glTF):
    """
    Generates the top level node graphs entry.
    """

    filtered_node_groups = exportSettings['filtered_node_groups']

    if len(filtered_node_groups) > 0:
        ext = gltf.appendExtension(glTF, 'S8S_v3d_materials', glTF)
        graphs = ext['nodeGraphs'] = []

        # store group names prior to processing them in case of group multiple
        # nesting
        for bl_node_group in filtered_node_groups:
            graphs.append({ 'name': bl_node_group.name })

        for bl_node_group in filtered_node_groups:
            graph = extractNodeGraph(bl_node_group, exportSettings, glTF)

            index = filtered_node_groups.index(bl_node_group)
            graphs[index].update(graph)


def generateFonts(operator, context, exportSettings, glTF):

    filtered_fonts = exportSettings['filtered_fonts']

    fonts = []

    for bl_font in filtered_fonts:

        font = {
            'name': bl_font.name
        }

        uri = getFontExportedURI(bl_font)
        font['id'] = uri

        if exportSettings['format'] == 'ASCII':
            # use external file

            old_path = getFontPath(bl_font)
            new_path = norm(exportSettings['filedirectory'] + uri)

            if bl_font.packed_file is not None:
                font_data = extractFontBindata(bl_font)

                with open(new_path, 'wb') as f:
                    f.write(font_data)

            elif old_path != new_path:
                # copy an font to a new location

                shutil.copyfile(old_path, new_path)

            font['uri'] = uri

        else:
            # store font in glb

            font_data = extractFontBindata(bl_font)
            bufferView = gltf.generateBufferView(glTF, exportSettings['binary'], font_data, '', 0)

            font['mimeType'] = getFontExportedMimeType(bl_font)
            font['bufferView'] = bufferView

        fonts.append(font)

    if len(fonts) > 0:
        gltf.appendExtension(glTF, 'S8S_v3d_curves', glTF, {'fonts': fonts})

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
            curve['text'] = bl_curve.body

            uri = getFontExportedURI(bl_curve.font)
            font_index = gltf.getFontIndex(glTF, uri)
            if font_index >= 0:
                curve['font'] = font_index


            # NOTE: default bfont.pfb font has slightly different metrics
            curve['size'] = bl_curve.size * 1.13 if uri == 'bfont.woff' else bl_curve.size
            curve['height'] = bl_curve.extrude
            curve['curveSegments'] = max(bl_curve.resolution_u - 1, 1)

            # NOTE: 0.88 = 1/1.13
            curve['lineHeight'] = bl_curve.space_line * 0.88 if uri == 'bfont.woff' else bl_curve.space_line

            curve['scaledEmSize'] = True

            curve['bevelThickness'] = bl_curve.bevel_depth
            curve['bevelSize'] = bl_curve.bevel_depth
            curve['bevelSegments'] = bl_curve.bevel_resolution + 1

            alignX = bl_curve.align_x

            if alignX == 'LEFT':
                curve['alignX'] = 'left'
            elif alignX == 'CENTER':
                curve['alignX'] = 'center'
            elif alignX == 'RIGHT':
                curve['alignX'] = 'right'
            else:
                # JUSTIFY,FLUSH
                printLog('WARNING', 'Unsupported font alignment: ' + alignX)
                curve['alignX'] = 'left'

            alignY = bl_curve.align_y

            if alignY == 'TOP_BASELINE':
                curve['alignY'] = 'topBaseline'
            elif alignY == 'TOP':
                curve['alignY'] = 'top'
            elif alignY == 'CENTER':
                curve['alignY'] = 'center'
            elif alignY == 'BOTTOM':
                curve['alignY'] = 'bottom'
            elif alignY == 'BOTTOM_BASELINE':
                curve['alignY'] = 'bottomBaseline'
            else:
                printLog('WARNING', 'Unsupported font alignment: ' + alignY)
                curve['alignY'] = 'topBaseline'

            # optional
            if len(bl_curve.materials) and bl_curve.materials[0] is not None:
                material = gltf.getMaterialIndex(glTF, bl_curve.materials[0].name)

                if material >= 0:
                    curve['material'] = material
                else:
                    printLog('WARNING', 'Material ' + bl_curve.materials[0].name + ' not found')

        curves.append(curve)

    if len(curves) > 0:
        ext = gltf.appendExtension(glTF, 'S8S_v3d_curves', glTF)
        ext['curves'] = curves

def generateMaterials(operator, context, exportSettings, glTF):
    """
    Generates the top level materials entry.
    """

    filtered_materials = exportSettings['filtered_materials']

    materials = []

    for bl_mat in filtered_materials:
        material = {}

        mat_type = getMaterialType(bl_mat)

        # PBR Materials

        if mat_type == 'PBR':
            for bl_node in bl_mat.node_tree.nodes:
                if isinstance(bl_node, bpy.types.ShaderNodeBsdfPrincipled):
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

            v3dExt = gltf.appendExtension(glTF, 'S8S_v3d_materials', material)

            if matHasBlendBackside(bl_mat):
                v3dExt['depthWrite'] = False
                backface = bl_mat.use_backface_culling
                material['doubleSided'] = not backface
                v3dExt['renderSide'] = 'FRONT' if backface else 'DOUBLE'
            else:
                if bl_mat.v3d.render_side == 'DOUBLE':
                    material['doubleSided'] = True
                if bl_mat.v3d.render_side != 'FRONT':
                    v3dExt['renderSide'] = bl_mat.v3d.render_side
                if bl_mat.blend_method != 'OPAQUE' and bl_mat.v3d.depth_write == False:
                    v3dExt['depthWrite'] = bl_mat.v3d.depth_write

                if bl_mat.blend_method == 'BLEND':
                    v3dExt['depthPrepass'] = True

            if bl_mat.v3d.depth_test == False:
                v3dExt['depthTest'] = bl_mat.v3d.depth_test

            if bl_mat.v3d.dithering == True:
                v3dExt['dithering'] = bl_mat.v3d.dithering

            if mat_type == 'EEVEE':
                v3dExt['nodeGraph'] = extractNodeGraph(bl_mat.node_tree,
                        exportSettings, glTF)
            else:
                v3dExt['nodeGraph'] = composeNodeGraph(bl_mat, exportSettings, glTF)

            v3dExt['materialIndex'] = bl_mat.pass_index

            if bl_mat.blend_method == 'HASHED':
                v3dExt['alphaToCoverage'] = True

            # disable GTAO for BLEND materials due to implementation issues
            v3dExt['gtaoVisible'] = bl_mat.blend_method != 'BLEND'

            # receive
            if exportSettings['use_shadows']:
                # useShadows is assigned on objects not materials
                v3dExt['useCastShadows'] = False if bl_mat.shadow_method == 'NONE' else True


        alphaMode = 'OPAQUE'

        if bl_mat.blend_method == 'CLIP':
            alphaMode = 'MASK'
            material['alphaCutoff'] = bl_mat.alpha_threshold + ALPHA_CUTOFF_EPS
        elif bl_mat.blend_method != 'OPAQUE':
            alphaMode = 'BLEND'

        if alphaMode != 'OPAQUE':
            material['alphaMode'] = alphaMode

        material['name'] = bl_mat.name

        if exportSettings['custom_props']:
            props = createCustomProperty(bl_mat)

            if props is not None:
                if 'extras' not in material:
                    material['extras'] = {}
                material['extras']['customProps'] = props

        materials.append(material)

    if len (materials) > 0:
        glTF['materials'] = materials


def getPostprocessingEffects(bl_scene):
    ppEffects = []

    if bl_scene.eevee.use_gtao:
        ppEffects.append({
            'type': 'gtao',
            'distance': bl_scene.eevee.gtao_distance,
            'factor': bl_scene.eevee.gtao_factor,
            'precision': bl_scene.eevee.gtao_quality,
            'bentNormals': bl_scene.eevee.use_gtao_bent_normals,
            'bounceApprox': bl_scene.eevee.use_gtao_bounce,
        })

    outline = bl_scene.v3d.outline
    if outline.enabled:
        ppEffects.append({
            'type': 'outline',
            'edgeStrength': outline.edge_strength,
            'edgeGlow': outline.edge_glow,
            'edgeThickness': outline.edge_thickness,
            'pulsePeriod': outline.pulse_period,
            'visibleEdgeColor': extractVec(outline.visible_edge_color),
            'hiddenEdgeColor': extractVec(outline.hidden_edge_color),
            'renderHiddenEdge': outline.render_hidden_edge
        })

    return ppEffects

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
        scene['extensions'] = { 'S8S_v3d_scene' : v3dExt }

        if bl_scene.world:
            world_mat = gltf.getMaterialIndex(glTF, WORLD_NODE_MAT_NAME.substitute(
                    name=bl_scene.world.name))
            if world_mat >= 0:
                v3dExt['worldMaterial'] = world_mat

        v3dExt['physicallyCorrectLights'] = True

        if exportSettings['use_shadows']:
            v3dExt['shadowMap'] = {
                'type': exportSettings['shadow_map_type'],
                'renderReverseSided' : True if exportSettings['shadow_map_side'] == 'BACK' else False,
                'renderSingleSided' : False if exportSettings['shadow_map_side'] == 'BOTH' else True,
                'esmDistanceScale': exportSettings['esm_distance_scale']
            }

        v3dExt['iblEnvironmentMode'] = exportSettings['ibl_environment_mode']

        v3dExt['aaMethod'] = exportSettings['aa_method']

        if exportSettings['use_hdr']:
            v3dExt['useHDR'] = True

        if exportSettings['use_oit']:
            v3dExt['useOIT'] = True

        ppEffects = getPostprocessingEffects(bl_scene)
        if len(ppEffects):
            v3dExt['postprocessing'] = ppEffects

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

        gltf.appendExtension(glTF, 'S8S_v3d_scene')

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

    v3dExt = gltf.getAssetExtension(glTF, 'S8S_v3d_materials')
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

    generateFonts(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(32)

    generateCurves(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(35)

    generateCameras(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(40)

    generateLights(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(50)

    generateLightProbes(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(55)

    generateMeshes(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(60)

    generateClippingPlanes(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(70)

    generateNodes(operator, context, exportSettings, glTF)
    bpy.context.window_manager.progress_update(72)

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
            buffer['uri'] = uri

        glTF['buffers'].append(buffer)
