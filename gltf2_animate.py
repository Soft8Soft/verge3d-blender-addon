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

import math

import bpy
import mathutils
import numpy as np

from pluginUtils.log import printLog
from .gltf2_extract import *
from .utils import *

from .curve_approx import approximateCurveMulti, calcCurveApproximationErrors

DEBUG_ANIM_APPROX = False

QUAT_X_90 = mathutils.Quaternion((1.0, 0.0, 0.0), math.pi/2)
QUAT_X_270 = mathutils.Quaternion((1.0, 0.0, 0.0), math.pi + math.pi/2)

CONST_INTERP_OFFSET = 0.001


def animateGetInterpolation(exportSettings, bl_fcurve_list):
    """
    Retrieves the glTF interpolation, depending on a fcurve list.
    Blender allows mixing and more variations of interpolations.
    In such a case, a conversion is needed.
    """

    if exportSettings['force_sampling']:
        return 'CONVERSION_NEEDED'



    prev_times = None
    for bl_fcurve in bl_fcurve_list:
        if bl_fcurve is None:
            continue

        curr_times = [p.co[0] for p in bl_fcurve.keyframe_points]
        if prev_times is not None and curr_times != prev_times:
            return 'CONVERSION_NEEDED'
        prev_times = curr_times


    interpolation = None

    for bl_fcurve in bl_fcurve_list:
        if bl_fcurve is None:
            continue



        currentKeyframeCount = len(bl_fcurve.keyframe_points)

        if currentKeyframeCount > 0 and bl_fcurve.keyframe_points[0].co[0] < 0:
            return 'CONVERSION_NEEDED'



        for bl_keyframe in bl_fcurve.keyframe_points:
            if interpolation is None:
                if bl_keyframe.interpolation == 'BEZIER':
                    interpolation = 'CUBICSPLINE'
                elif bl_keyframe.interpolation == 'LINEAR':
                    interpolation = 'LINEAR'
                elif bl_keyframe.interpolation == 'CONSTANT':
                    interpolation = 'STEP'
                else:
                    interpolation = 'CONVERSION_NEEDED'
                    return interpolation
            else:
                if bl_keyframe.interpolation == 'BEZIER' and interpolation != 'CUBICSPLINE':
                    interpolation = 'CONVERSION_NEEDED'
                    return interpolation
                elif bl_keyframe.interpolation == 'LINEAR' and interpolation != 'LINEAR':
                    interpolation = 'CONVERSION_NEEDED'
                    return interpolation
                elif bl_keyframe.interpolation == 'CONSTANT' and interpolation != 'STEP':
                    interpolation = 'CONVERSION_NEEDED'
                    return interpolation
                elif bl_keyframe.interpolation != 'BEZIER' and bl_keyframe.interpolation != 'LINEAR' and bl_keyframe.interpolation != 'CONSTANT':
                    interpolation = 'CONVERSION_NEEDED'
                    return interpolation

    if interpolation is None:
        interpolation = 'CONVERSION_NEEDED'

    # NOTE: make curve conversion since CUBICSPLINE isn't supported in the
    # engine at the moment
    if interpolation == 'CUBICSPLINE':
        interpolation = 'CONVERSION_NEEDED'

    return interpolation


def animateConvertRotationAxisAngle(axis_angle):
    """
    Converts an axis angle to a quaternion rotation.
    """
    q = mathutils.Quaternion((axis_angle[1], axis_angle[2], axis_angle[3]), axis_angle[0])

    return [q.x, q.y, q.z, q.w]


def animateConvertRotationEuler(euler, rotation_mode):
    """
    Converts an euler angle to a quaternion rotation.
    """
    rotation = mathutils.Euler((euler[0], euler[1], euler[2]), rotation_mode).to_quaternion()

    return [rotation.x, rotation.y, rotation.z, rotation.w]


def animateConvertKeys(key_list):
    """
    Converts Blender key frames to glTF time keys depending on the applied frames per second.
    """
    times = []

    for key in key_list:
        times.append(key / bpy.context.scene.render.fps)

    return times


def animateGatherKeys(exportSettings, fcurve_list, interpolation):
    """
    Merges and sorts several key frames to one set.
    If an interpolation conversion is needed, the sample key frames are created as well.
    """
    keys = []

    if interpolation == 'CONVERSION_NEEDED':
        fcurves = [fcurve for fcurve in fcurve_list if fcurve is not None]
        if fcurves:

            start = min([fcurve.range()[0] for fcurve in fcurves])
            end = max([fcurve.range()[1] for fcurve in fcurves])
            if exportSettings['frame_range']:
                start = max(start, bpy.context.scene.frame_start)
                end = min(end, bpy.context.scene.frame_end)

            rangeKeys = [start, end]
            explicitKeys = []
            constInterpFixKeys = []
            for fcurve in fcurves:
                kPoints = fcurve.keyframe_points
                explicitKeys.extend([point.co[0] for point in kPoints])

                # Ensure that all points with the CONSTANT interpolation keep
                # the "step" shape regardless of point distribution in the
                # resulting piecewise linear approximation. To do that we sample
                # additional points in close proximity (just before) of certain
                # already existing keyframe point, i.e: { f(0.999) = 0; f(1) = 1 }
                # - this keeps the step shape (or to be precise - a very abrupt
                # slope).
                constIndices = [idx for idx, point in enumerate(kPoints)
                        if point.interpolation == 'CONSTANT']
                constInterpFixKeys.extend([kPoints[idx + 1].co[0] - CONST_INTERP_OFFSET
                        if idx < len(kPoints) - 1 else end - CONST_INTERP_OFFSET
                        for idx in constIndices])

            # Create a grid of points that fit into the (start, end) range.
            # The amount of points per frame (and the grid step) is chosen so
            # that all integers from the (start, end) range are among the keys.
            # This is convenient to use as an initial approximation (which is
            # the old 1 sample per frame approach). The initial approximation is
            # used to estimate the overall error level.

            # SEGM_PER_FRAME, GRID_STEP, DIGITS_TO_ROUND = 100, 0.01, 2
            # SEGM_PER_FRAME, GRID_STEP, DIGITS_TO_ROUND = 10, 0.1, 1
            SEGM_PER_FRAME, GRID_STEP, DIGITS_TO_ROUND = 4, 0.25, 2
            # SEGM_PER_FRAME, GRID_STEP, DIGITS_TO_ROUND = 2, 0.5, 1

            startCeiled = math.ceil(start * SEGM_PER_FRAME) / SEGM_PER_FRAME
            endFloored = math.floor(end * SEGM_PER_FRAME) / SEGM_PER_FRAME
            gridKeys = np.arange(startCeiled, endFloored, GRID_STEP, dtype=np.double)
            gridKeys.round(DIGITS_TO_ROUND, gridKeys)
            if gridKeys.size and gridKeys[-1] < endFloored:
                gridKeys = np.append(gridKeys, endFloored)

            allKeys = np.concatenate((rangeKeys, explicitKeys,
                    constInterpFixKeys, gridKeys))
            allKeys = np.unique(allKeys) # this also sorts the values
            allValues = [np.vectorize(fcurve.evaluate)(allKeys) for fcurve in fcurves]

            if len(allKeys) >= 2:
                rangeKeysMask = np.isin(allKeys, rangeKeys)
                explicitKeysMask = np.isin(allKeys, explicitKeys)
                constInterpFixKeysMask = np.isin(allKeys, constInterpFixKeys)
                gridIntegerKeysMask = np.equal(np.mod(allKeys, 1), 0)

                initApproxMask = (rangeKeysMask + constInterpFixKeysMask
                        + gridIntegerKeysMask)
                initApproxMask[0] = True
                initApproxMask[-1] = True
                initApproxIndices = initApproxMask.nonzero()[0]

                initApproxErrors = [calcCurveApproximationErrors(allKeys,
                        allValues[i], initApproxIndices) for i in range(len(fcurves))]

                mandatoryIndicesMask = (rangeKeysMask + constInterpFixKeysMask
                        + explicitKeysMask)

                # Detect outliers among the error data of the initial
                # approximation. These limits serve several purposes: they
                # prevent the resulting approximation from having too large
                # errors, and they keep the same level of errors while, in
                # general, reducing the number of used keyframe points.
                # See: https://en.wikipedia.org/wiki/Interquartile_range#Outliers
                maxSegmentErrors = []
                for errors in initApproxErrors:
                    q1, q3 = np.quantile(errors, [0.25, 0.75])
                    maxErrWithoutOutliers = np.amax(errors, initial=0,
                            where=errors<(q3 + 1.5 * (q3 - q1)))
                    maxSegmentErrors.append(maxErrWithoutOutliers)

                approxIndices = approximateCurveMulti(allKeys, allValues,
                        mandatoryIndicesMask, maxSegmentErrors)
                keys = list(allKeys[approxIndices])

                if DEBUG_ANIM_APPROX:
                    approxErrors = [calcCurveApproximationErrors(allKeys,
                            allValues[i], approxIndices) for i in range(len(fcurves))]
                    initMaxErr = max([max(err) for err in initApproxErrors])
                    initErrSum = sum([sum(err) for err in initApproxErrors])
                    resMaxErr = max([max(err) for err in approxErrors])
                    resErrSum = sum([sum(err) for err in approxErrors])

                    print()
                    print(f'Range: [{start}, {end}], channels: {len(fcurves)}')
                    print('                Length    MaxErr          ErrSum')
                    print('-' * 56)
                    print('Init Approx     %-8i  %.12f  %.12f' % (len(initApproxIndices), initMaxErr, initErrSum))
                    print('Result Approx   %-8i  %.12f  %.12f' % (len(approxIndices), resMaxErr, resErrSum))
                    print('-' * 56 + '\n')

    else:
        for bl_fcurve in fcurve_list:
            if bl_fcurve is None:
                continue

            for bl_keyframe in bl_fcurve.keyframe_points:
                key = bl_keyframe.co[0]
                if not exportSettings['frame_range'] or (exportSettings['frame_range'] and key >= bpy.context.scene.frame_start and key <= bpy.context.scene.frame_end):
                    if key not in keys:
                        keys.append(key)

        keys.sort()

    return keys


def animateLocation(exportSettings, location, interpolation, node_type, bl_obj,
        bl_bone):
    """
    Calculates/gathers the key value pairs for location transformations.
    """

    jointKey = None
    if node_type == 'JOINT':
        jointKey = getPtr(bl_bone)
        if not exportSettings['joint_cache'].get(jointKey):
            exportSettings['joint_cache'][jointKey] = {}

    keys = animateGatherKeys(exportSettings, location, interpolation)

    times = animateConvertKeys(keys)

    result = {}
    result_in_tangent = {}
    result_out_tangent = {}

    keyframe_index = 0
    for time in times:
        translation = [0.0, 0.0, 0.0]
        in_tangent = [0.0, 0.0, 0.0]
        out_tangent = [0.0, 0.0, 0.0]

        if node_type == 'JOINT':
            if exportSettings['joint_cache'][jointKey].get(keys[keyframe_index]):
                translation, tmp_rotation, tmp_scale = exportSettings['joint_cache'][jointKey][keys[keyframe_index]]
            else:
                sceneFrameSetFloat(bpy.context.scene, keys[keyframe_index])

                joint_matrix = getBoneJointMatrix(bl_obj, bl_bone,
                        exportSettings['bake_armature_actions'])
                translation, tmp_rotation, tmp_scale = decomposeTransformSwizzle(joint_matrix)

                exportSettings['joint_cache'][jointKey][keys[keyframe_index]] = [translation, tmp_rotation, tmp_scale]
        else:
            channel_index = 0
            for bl_fcurve in location:

                if bl_fcurve is not None:

                    if interpolation == 'CUBICSPLINE':
                        bl_key_frame = bl_fcurve.keyframe_points[keyframe_index]

                        translation[channel_index] = bl_key_frame.co[1]

                        in_tangent[channel_index] = 3.0 * (bl_key_frame.co[1] - bl_key_frame.handle_left[1])
                        out_tangent[channel_index] = 3.0 * (bl_key_frame.handle_right[1] - bl_key_frame.co[1])
                    else:
                        value = bl_fcurve.evaluate(keys[keyframe_index])

                        translation[channel_index] = value

                channel_index += 1

            translation = convertSwizzleLocation(translation)
            in_tangent = convertSwizzleLocation(in_tangent)
            out_tangent = convertSwizzleLocation(out_tangent)

        result[time] = translation
        result_in_tangent[time] = in_tangent
        result_out_tangent[time] = out_tangent

        keyframe_index += 1

    return result, result_in_tangent, result_out_tangent


def animateRotationAxisAngle(exportSettings, rotation_axis_angle, interpolation,
        node_type, bl_obj, bl_bone):
    """
    Calculates/gathers the key value pairs for axis angle transformations.
    """

    jointKey = None
    if node_type == 'JOINT':
        jointKey = getPtr(bl_bone)
        if not exportSettings['joint_cache'].get(jointKey):
            exportSettings['joint_cache'][jointKey] = {}

    keys = animateGatherKeys(exportSettings, rotation_axis_angle, interpolation)

    times = animateConvertKeys(keys)

    result = {}

    keyframe_index = 0
    for time in times:
        axis_angle_rotation = [1.0, 0.0, 0.0, 0.0]

        rotation = [1.0, 0.0, 0.0, 0.0]

        if node_type == 'JOINT':
            if exportSettings['joint_cache'][jointKey].get(keys[keyframe_index]):
                tmp_location, rotation, tmp_scale = exportSettings['joint_cache'][jointKey][keys[keyframe_index]]
            else:
                sceneFrameSetFloat(bpy.context.scene, keys[keyframe_index])

                joint_matrix = getBoneJointMatrix(bl_obj, bl_bone,
                        exportSettings['bake_armature_actions'])
                tmp_location, rotation, tmp_scale = decomposeTransformSwizzle(joint_matrix)

                exportSettings['joint_cache'][jointKey][keys[keyframe_index]] = [tmp_location, rotation, tmp_scale]
        else:
            channel_index = 0
            for bl_fcurve in rotation_axis_angle:
                if bl_fcurve is not None:
                    value = bl_fcurve.evaluate(keys[keyframe_index])

                    axis_angle_rotation[channel_index] = value

                channel_index += 1

            rotation = animateConvertRotationAxisAngle(axis_angle_rotation)

            # Bring back to internal Quaternion notation.
            rotation = convertSwizzleRotation([rotation[3], rotation[0], rotation[1], rotation[2]])

            # apply additional rotation for lamps, cameras, fonts and their childs
            rotation = correctRotationQuat(rotation, node_type)

        # Bring back to glTF Quaternion notation.
        rotation = [rotation[1], rotation[2], rotation[3], rotation[0]]

        result[time] = rotation

        keyframe_index += 1

    return result


def animateRotationEuler(exportSettings, rotation_euler, rotation_mode,
        interpolation, node_type, bl_obj, bl_bone):
    """
    Calculates/gathers the key value pairs for euler angle transformations.
    """

    jointKey = None
    if node_type == 'JOINT':
        jointKey = getPtr(bl_bone)
        if not exportSettings['joint_cache'].get(jointKey):
            exportSettings['joint_cache'][jointKey] = {}

    keys = animateGatherKeys(exportSettings, rotation_euler, interpolation)

    times = animateConvertKeys(keys)

    result = {}

    keyframe_index = 0
    for time in times:
        euler_rotation = [0.0, 0.0, 0.0]

        rotation = [1.0, 0.0, 0.0, 0.0]

        if node_type == 'JOINT':
            if exportSettings['joint_cache'][jointKey].get(keys[keyframe_index]):
                tmp_location, rotation, tmp_scale = exportSettings['joint_cache'][jointKey][keys[keyframe_index]]
            else:
                sceneFrameSetFloat(bpy.context.scene, keys[keyframe_index])

                joint_matrix = getBoneJointMatrix(bl_obj, bl_bone,
                        exportSettings['bake_armature_actions'])
                tmp_location, rotation, tmp_scale = decomposeTransformSwizzle(joint_matrix)

                exportSettings['joint_cache'][jointKey][keys[keyframe_index]] = [tmp_location, rotation, tmp_scale]
        else:
            channel_index = 0
            for bl_fcurve in rotation_euler:
                if bl_fcurve is not None:
                    value = bl_fcurve.evaluate(keys[keyframe_index])

                    euler_rotation[channel_index] = value

                channel_index += 1

            rotation = animateConvertRotationEuler(euler_rotation, rotation_mode)

            # Bring back to internal Quaternion notation.
            rotation = convertSwizzleRotation([rotation[3], rotation[0], rotation[1], rotation[2]])

            # apply additional rotation for lamps, cameras, fonts and their childs
            rotation = correctRotationQuat(rotation, node_type)

        # Bring back to glTF Quaternion notation.
        rotation = [rotation[1], rotation[2], rotation[3], rotation[0]]

        result[time] = rotation

        keyframe_index += 1

    return result


def animateRotationQuaternion(exportSettings, rotation_quaternion,
        interpolation, node_type, bl_obj, bl_bone):
    """
    Calculates/gathers the key value pairs for quaternion transformations.
    """

    jointKey = None
    if node_type == 'JOINT':
        jointKey = getPtr(bl_bone)
        if not exportSettings['joint_cache'].get(jointKey):
            exportSettings['joint_cache'][jointKey] = {}

    keys = animateGatherKeys(exportSettings, rotation_quaternion, interpolation)

    times = animateConvertKeys(keys)

    result = {}
    result_in_tangent = {}
    result_out_tangent = {}

    keyframe_index = 0
    for time in times:
        rotation = [1.0, 0.0, 0.0, 0.0]
        in_tangent = [1.0, 0.0, 0.0, 0.0]
        out_tangent = [1.0, 0.0, 0.0, 0.0]

        if node_type == 'JOINT':
            if exportSettings['joint_cache'][jointKey].get(keys[keyframe_index]):
                tmp_location, rotation, tmp_scale = exportSettings['joint_cache'][jointKey][keys[keyframe_index]]
            else:
                sceneFrameSetFloat(bpy.context.scene, keys[keyframe_index])

                joint_matrix = getBoneJointMatrix(bl_obj, bl_bone,
                        exportSettings['bake_armature_actions'])
                tmp_location, rotation, tmp_scale = decomposeTransformSwizzle(joint_matrix)

                exportSettings['joint_cache'][jointKey][keys[keyframe_index]] = [tmp_location, rotation, tmp_scale]
        else:
            channel_index = 0
            for bl_fcurve in rotation_quaternion:

                if bl_fcurve is not None:
                    if interpolation == 'CUBICSPLINE':
                        bl_key_frame = bl_fcurve.keyframe_points[keyframe_index]

                        rotation[channel_index] = bl_key_frame.co[1]

                        in_tangent[channel_index] = 3.0 * (bl_key_frame.co[1] - bl_key_frame.handle_left[1])
                        out_tangent[channel_index] = 3.0 * (bl_key_frame.handle_right[1] - bl_key_frame.co[1])
                    else:
                        value = bl_fcurve.evaluate(keys[keyframe_index])

                        rotation[channel_index] = value

                channel_index += 1

            # NOTE: fcurve.evaluate() requires normalization
            q = mathutils.Quaternion((rotation[0],rotation[1], rotation[2], rotation[3])).normalized()
            rotation = [q[0], q[1], q[2], q[3]]

            rotation = convertSwizzleRotation(rotation)

            in_tangent = convertSwizzleRotation(in_tangent)
            out_tangent = convertSwizzleRotation(out_tangent)

            # apply additional rotation for lamps, cameras, fonts and their childs
            rotation = correctRotationQuat(rotation, node_type)
            in_tangent = correctRotationQuat(in_tangent, node_type)
            out_tangent = correctRotationQuat(out_tangent, node_type)

        # Bring to glTF Quaternion notation.
        rotation = [rotation[1], rotation[2], rotation[3], rotation[0]]
        in_tangent = [in_tangent[1], in_tangent[2], in_tangent[3], in_tangent[0]]
        out_tangent = [out_tangent[1], out_tangent[2], out_tangent[3], out_tangent[0]]

        result[time] = rotation
        result_in_tangent[time] = in_tangent
        result_out_tangent[time] = out_tangent

        keyframe_index += 1

    return result, result_in_tangent, result_out_tangent


def animateScale(exportSettings, scale, interpolation, node_type, bl_obj,
        bl_bone):
    """
    Calculates/gathers the key value pairs for scale transformations.
    """

    jointKey = None
    if node_type == 'JOINT':
        jointKey = getPtr(bl_bone)
        if not exportSettings['joint_cache'].get(jointKey):
            exportSettings['joint_cache'][jointKey] = {}

    keys = animateGatherKeys(exportSettings, scale, interpolation)

    times = animateConvertKeys(keys)

    result = {}
    result_in_tangent = {}
    result_out_tangent = {}

    keyframe_index = 0
    for time in times:
        scale_data = [1.0, 1.0, 1.0]
        in_tangent = [0.0, 0.0, 0.0]
        out_tangent = [0.0, 0.0, 0.0]

        if node_type == 'JOINT':
            if exportSettings['joint_cache'][jointKey].get(keys[keyframe_index]):
                tmp_location, tmp_rotation, scale_data = exportSettings['joint_cache'][jointKey][keys[keyframe_index]]
            else:
                sceneFrameSetFloat(bpy.context.scene, keys[keyframe_index])

                joint_matrix = getBoneJointMatrix(bl_obj, bl_bone,
                        exportSettings['bake_armature_actions'])
                tmp_location, tmp_rotation, scale_data = decomposeTransformSwizzle(joint_matrix)

                exportSettings['joint_cache'][jointKey][keys[keyframe_index]] = [tmp_location, tmp_rotation, scale_data]
        else:
            channel_index = 0
            for bl_fcurve in scale:

                if bl_fcurve is not None:
                    if interpolation == 'CUBICSPLINE':
                        bl_key_frame = bl_fcurve.keyframe_points[keyframe_index]

                        scale_data[channel_index] = bl_key_frame.co[1]

                        in_tangent[channel_index] = 3.0 * (bl_key_frame.co[1] - bl_key_frame.handle_left[1])
                        out_tangent[channel_index] = 3.0 * (bl_key_frame.handle_right[1] - bl_key_frame.co[1])
                    else:
                        value = bl_fcurve.evaluate(keys[keyframe_index])

                        scale_data[channel_index] = value

                channel_index += 1

            scale_data = convertSwizzleScale(scale_data)
            in_tangent = convertSwizzleScale(in_tangent)
            out_tangent = convertSwizzleScale(out_tangent)

        result[time] = scale_data
        result_in_tangent[time] = in_tangent
        result_out_tangent[time] = out_tangent

        keyframe_index += 1

    return result, result_in_tangent, result_out_tangent


def animateValue(exportSettings, value_parameter, interpolation, node_type):
    """
    Calculates/gathers the key value pairs for scalar animations.
    """
    keys = animateGatherKeys(exportSettings, value_parameter, interpolation)

    times = animateConvertKeys(keys)

    result = {}
    result_in_tangent = {}
    result_out_tangent = {}

    keyframe_index = 0
    for time in times:
        value_data = []
        in_tangent = []
        out_tangent = []

        for bl_fcurve in value_parameter:

            if bl_fcurve is not None:
                if interpolation == 'CUBICSPLINE':
                    bl_key_frame = bl_fcurve.keyframe_points[keyframe_index]

                    value_data.append(bl_key_frame.co[1])

                    in_tangent.append(3.0 * (bl_key_frame.co[1] - bl_key_frame.handle_left[1]))
                    out_tangent.append(3.0 * (bl_key_frame.handle_right[1] - bl_key_frame.co[1]))
                else:
                    value = bl_fcurve.evaluate(keys[keyframe_index])

                    value_data.append(value)

        result[time] = value_data
        result_in_tangent[time] = in_tangent
        result_out_tangent[time] = out_tangent

        keyframe_index += 1

    return result, result_in_tangent, result_out_tangent

def animateDefaultValue(exportSettings, default_value, interpolation):
    """
    Calculate/gather the key value pairs for node material animation.
    """

    keys = animateGatherKeys(exportSettings, default_value, interpolation)

    times = animateConvertKeys(keys)

    result = {}
    result_in_tangent = {}
    result_out_tangent = {}

    keyframe_index = 0
    for time in times:
        def_value_data = [1.0, 1.0, 1.0, 1.0]
        in_tangent = [0.0, 0.0, 0.0, 0.0]
        out_tangent = [0.0, 0.0, 0.0, 0.0]

        channel_index = 0
        for bl_fcurve in default_value:

            if bl_fcurve is not None:
                if interpolation == 'CUBICSPLINE':
                    bl_key_frame = bl_fcurve.keyframe_points[keyframe_index]

                    def_value_data[channel_index] = bl_key_frame.co[1]
                    in_tangent[channel_index] = 3.0 * (bl_key_frame.co[1] - bl_key_frame.handle_left[1])
                    out_tangent[channel_index] = 3.0 * (bl_key_frame.handle_right[1] - bl_key_frame.co[1])
                else:
                    value = bl_fcurve.evaluate(keys[keyframe_index])

                    def_value_data[channel_index] = value

            channel_index += 1

        result[time] = def_value_data
        result_in_tangent[time] = in_tangent
        result_out_tangent[time] = out_tangent

        keyframe_index += 1

    return result, result_in_tangent, result_out_tangent

def animateEnergy(exportSettings, energy, interpolation):
    """
    Calculate/gather the key value pairs for node material animation.
    """

    keys = animateGatherKeys(exportSettings, energy, interpolation)

    times = animateConvertKeys(keys)

    result = {}
    result_in_tangent = {}
    result_out_tangent = {}

    keyframe_index = 0
    for time in times:
        energy_data = [1.0]
        in_tangent = [0.0]
        out_tangent = [0.0]

        channel_index = 0
        for bl_fcurve in energy:

            if bl_fcurve is not None:
                if interpolation == 'CUBICSPLINE':
                    bl_key_frame = bl_fcurve.keyframe_points[keyframe_index]

                    energy_data[channel_index] = bl_key_frame.co[1]
                    in_tangent[channel_index] = 3.0 * (bl_key_frame.co[1] - bl_key_frame.handle_left[1])
                    out_tangent[channel_index] = 3.0 * (bl_key_frame.handle_right[1] - bl_key_frame.co[1])
                else:
                    value = bl_fcurve.evaluate(keys[keyframe_index])

                    energy_data[channel_index] = value

            channel_index += 1

        result[time] = energy_data
        result_in_tangent[time] = in_tangent
        result_out_tangent[time] = out_tangent

        keyframe_index += 1

    return result, result_in_tangent, result_out_tangent

def correctRotationQuat(rotation, node_type):
    # apply additional rotation for lamps, cameras, fonts and their childs

    if node_type == 'NODE_X_90':
        rotation = rotation @ QUAT_X_270
    elif node_type == 'NODE_INV_X_90':
        rotation = QUAT_X_90 @ rotation
    elif node_type == 'NODE_INV_X_90_X_90':
        rotation = QUAT_X_90 @ rotation @ QUAT_X_270

    return rotation

def getBoneJointMatrix(bl_obj, bl_bone, is_baked):
    correction_matrix_local = bl_bone.bone.matrix_local.copy()
    if bl_bone.parent is not None:
        correction_matrix_local = bl_bone.parent.bone.matrix_local.inverted() @ correction_matrix_local

    matrix_basis = bl_bone.matrix_basis
    if is_baked:
        matrix_basis = bl_obj.convert_space(pose_bone=bl_bone,
                matrix=bl_bone.matrix, from_space='POSE',
                to_space='LOCAL')

    return correction_matrix_local @ matrix_basis
