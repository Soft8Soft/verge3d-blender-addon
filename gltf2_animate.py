# Copyright (c) 2017 The Khronos Group Inc.
# Copyright (c) 2017-2025 Soft8Soft
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

from .gltf2_extract import *
from .utils import *

from .curve_approx import approximateCurveMulti, calcCurveApproximationErrors

DEBUG_ANIM_APPROX = False

QUAT_X_90 = mathutils.Quaternion((1.0, 0.0, 0.0), math.pi/2)
QUAT_X_270 = mathutils.Quaternion((1.0, 0.0, 0.0), math.pi + math.pi/2)

CONST_INTERP_OFFSET = 0.001

def getActionNameFcurves(blAnimationData):
    if blAnimationData is None or blAnimationData.action is None:
        return None, None

    action = blAnimationData.action

    if bpy.app.version >= (4, 4, 0):
        slot = blAnimationData.action_slot

        if slot and action.layers and action.layers[0].strips:
            channelBag = action.layers[0].strips[0].channelbag(slot)
            if channelBag:
                return action.name, channelBag.fcurves

        return None, None
    else:
        return action.name, action.fcurves


def dataPathNameInBrackets(fcurve):
    """
    Return mat.node/bone/etc from fcurve data path.
    """

    if fcurve.data_path is None:
        return None

    path = fcurve.data_path

    index = path.find("[\"")
    if (index == -1):
        return None

    bracketName = path[(index + 2):]

    index = bracketName.find("\"")
    if (index == -1):
        return None

    return bracketName[:(index)]


def getAnimParamDim(fcurves, pathBracketName):
    dim = 0

    for fcurve in fcurves:
        if dataPathNameInBrackets(fcurve) == pathBracketName:
            dim = max(dim, fcurve.array_index+1)

    return dim


def getAnimParam(fcurve):
    """
    Return animated param in data path:
    nodes['name'].outputs[0].default_value -> default_value
    """

    index = fcurve.data_path.rfind('.')
    if index == -1:
        return fcurve.data_path

    return fcurve.data_path[(index + 1):]


def animateGetInterpolation(exportSettings, fcurves):
    """
    Retrieves the glTF interpolation, depending on a fcurve list.
    Blender allows mixing and more variations of interpolations.
    In such a case, a conversion is needed.
    """

    if exportSettings['forceSampling']:
        return 'CONVERSION_NEEDED'

    prevTimes = None
    for fcurve in fcurves:
        if fcurve is None:
            continue

        currTimes = [p.co[0] for p in fcurve.keyframe_points]
        if prevTimes is not None and currTimes != prevTimes:
            return 'CONVERSION_NEEDED'
        prevTimes = currTimes

    interpolation = None

    for fcurve in fcurves:
        if fcurve is None:
            continue

        currentKeyframeCount = len(fcurve.keyframe_points)

        if currentKeyframeCount > 0 and fcurve.keyframe_points[0].co[0] < 0:
            return 'CONVERSION_NEEDED'

        for blKeyframe in fcurve.keyframe_points:
            if interpolation is None:
                if blKeyframe.interpolation == 'BEZIER':
                    interpolation = 'CUBICSPLINE'
                elif blKeyframe.interpolation == 'LINEAR':
                    interpolation = 'LINEAR'
                elif blKeyframe.interpolation == 'CONSTANT':
                    interpolation = 'STEP'
                else:
                    interpolation = 'CONVERSION_NEEDED'
                    return interpolation
            else:
                if blKeyframe.interpolation == 'BEZIER' and interpolation != 'CUBICSPLINE':
                    interpolation = 'CONVERSION_NEEDED'
                    return interpolation
                elif blKeyframe.interpolation == 'LINEAR' and interpolation != 'LINEAR':
                    interpolation = 'CONVERSION_NEEDED'
                    return interpolation
                elif blKeyframe.interpolation == 'CONSTANT' and interpolation != 'STEP':
                    interpolation = 'CONVERSION_NEEDED'
                    return interpolation
                elif blKeyframe.interpolation != 'BEZIER' and blKeyframe.interpolation != 'LINEAR' and blKeyframe.interpolation != 'CONSTANT':
                    interpolation = 'CONVERSION_NEEDED'
                    return interpolation

    if interpolation is None:
        interpolation = 'CONVERSION_NEEDED'

    # NOTE: make curve conversion since CUBICSPLINE isn't supported in the
    # engine at the moment
    if interpolation == 'CUBICSPLINE':
        interpolation = 'CONVERSION_NEEDED'

    return interpolation


def animateConvertRotationAxisAngle(axisAngle):
    """
    Converts an axis angle to a quaternion rotation.
    """
    q = mathutils.Quaternion((axisAngle[1], axisAngle[2], axisAngle[3]), axisAngle[0])

    return [q.x, q.y, q.z, q.w]


def animateConvertRotationEuler(euler, rotationMode):
    """
    Converts an euler angle to a quaternion rotation.
    """
    rotation = mathutils.Euler((euler[0], euler[1], euler[2]), rotationMode).to_quaternion()

    return [rotation.x, rotation.y, rotation.z, rotation.w]


def animateConvertKeys(key_list):
    """
    Converts Blender key frames to glTF time keys depending on the applied frames per second.
    """
    times = []

    for key in key_list:
        times.append(key / bpy.context.scene.render.fps)

    return times


def animateGatherKeys(exportSettings, fcurves, interpolation):
    """
    Merges and sorts several key frames to one set.
    If an interpolation conversion is needed, the sample key frames are created as well.
    """
    keys = []

    if interpolation == 'CONVERSION_NEEDED':
        fcurves = [fcurve for fcurve in fcurves if fcurve is not None]
        if fcurves:

            start = min([fcurve.range()[0] for fcurve in fcurves])
            end = max([fcurve.range()[1] for fcurve in fcurves])
            if exportSettings['exportFrameRange']:
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
        for fcurve in fcurves:
            if fcurve is None:
                continue

            for blKeyframe in fcurve.keyframe_points:
                key = blKeyframe.co[0]
                if not exportSettings['exportFrameRange'] or (exportSettings['exportFrameRange'] and key >= bpy.context.scene.frame_start and key <= bpy.context.scene.frame_end):
                    if key not in keys:
                        keys.append(key)

        keys.sort()

    return keys


def animateLocation(exportSettings, fcurves, interpolation, animType, blObj, blBone):
    """
    Calculates/gathers the key value pairs for location transformations.
    """

    jointKey = None
    if animType == 'JOINT':
        jointKey = getPtr(blBone)
        if not exportSettings['jointCache'].get(jointKey):
            exportSettings['jointCache'][jointKey] = {}

    keys = animateGatherKeys(exportSettings, fcurves, interpolation)

    times = animateConvertKeys(keys)

    result = {}
    resultInTangent = {}
    resultOutTangent = {}

    keyframeIndex = 0
    for time in times:
        translation = [0.0, 0.0, 0.0]
        inTangent = [0.0, 0.0, 0.0]
        outTangent = [0.0, 0.0, 0.0]

        if animType == 'JOINT':
            if exportSettings['jointCache'][jointKey].get(keys[keyframeIndex]):
                translation, tmpRotation, tmpScale = exportSettings['jointCache'][jointKey][keys[keyframeIndex]]
            else:
                sceneFrameSetFloat(bpy.context.scene, keys[keyframeIndex])

                jointMatrix = getBoneJointMatrix(blObj, blBone, exportSettings['bakeArmatureActions'])
                translation, tmpRotation, tmpScale = decomposeTransformSwizzle(jointMatrix)

                exportSettings['jointCache'][jointKey][keys[keyframeIndex]] = [translation, tmpRotation, tmpScale]
        else:
            channelIndex = 0

            for fcurve in fcurves:
                if fcurve is not None:

                    if interpolation == 'CUBICSPLINE':
                        blKeyframe = fcurve.keyframe_points[keyframeIndex]

                        translation[channelIndex] = blKeyframe.co[1]

                        inTangent[channelIndex] = 3.0 * (blKeyframe.co[1] - blKeyframe.handle_left[1])
                        outTangent[channelIndex] = 3.0 * (blKeyframe.handle_right[1] - blKeyframe.co[1])
                    else:
                        value = fcurve.evaluate(keys[keyframeIndex])

                        translation[channelIndex] = value

                channelIndex += 1

            translation = convertSwizzleLocation(translation)
            inTangent = convertSwizzleLocation(inTangent)
            outTangent = convertSwizzleLocation(outTangent)

        result[time] = translation
        resultInTangent[time] = inTangent
        resultOutTangent[time] = outTangent

        keyframeIndex += 1

    return result, resultInTangent, resultOutTangent


def animateRotationAxisAngle(exportSettings, fcurves, interpolation, animType, blObj, blBone):
    """
    Calculates/gathers the key value pairs for axis angle transformations.
    """

    jointKey = None
    if animType == 'JOINT':
        jointKey = getPtr(blBone)
        if not exportSettings['jointCache'].get(jointKey):
            exportSettings['jointCache'][jointKey] = {}

    keys = animateGatherKeys(exportSettings, fcurves, interpolation)

    times = animateConvertKeys(keys)

    result = {}

    keyframeIndex = 0
    for time in times:
        axisAngleRotation = [1.0, 0.0, 0.0, 0.0]

        rotation = [1.0, 0.0, 0.0, 0.0]

        if animType == 'JOINT':
            if exportSettings['jointCache'][jointKey].get(keys[keyframeIndex]):
                tmpLocation, rotation, tmpScale = exportSettings['jointCache'][jointKey][keys[keyframeIndex]]
            else:
                sceneFrameSetFloat(bpy.context.scene, keys[keyframeIndex])

                jointMatrix = getBoneJointMatrix(blObj, blBone, exportSettings['bakeArmatureActions'])
                tmpLocation, rotation, tmpScale = decomposeTransformSwizzle(jointMatrix)

                exportSettings['jointCache'][jointKey][keys[keyframeIndex]] = [tmpLocation, rotation, tmpScale]
        else:
            channelIndex = 0

            for fcurve in fcurves:
                if fcurve is not None:
                    value = fcurve.evaluate(keys[keyframeIndex])

                    axisAngleRotation[channelIndex] = value

                channelIndex += 1

            rotation = animateConvertRotationAxisAngle(axisAngleRotation)

            # Bring back to internal Quaternion notation.
            rotation = convertSwizzleRotation([rotation[3], rotation[0], rotation[1], rotation[2]])

            # apply additional rotation for lamps, cameras, fonts and their childs
            rotation = correctRotationQuat(rotation, animType)

        # Bring back to glTF Quaternion notation.
        rotation = [rotation[1], rotation[2], rotation[3], rotation[0]]

        result[time] = rotation

        keyframeIndex += 1

    return result


def animateRotationEuler(exportSettings, fcurves, rotationMode, interpolation, animType, blObj, blBone):
    """
    Calculates/gathers the key value pairs for euler angle transformations.
    """

    jointKey = None
    if animType == 'JOINT':
        jointKey = getPtr(blBone)
        if not exportSettings['jointCache'].get(jointKey):
            exportSettings['jointCache'][jointKey] = {}

    keys = animateGatherKeys(exportSettings, fcurves, interpolation)

    times = animateConvertKeys(keys)

    result = {}

    keyframeIndex = 0
    for time in times:
        euler_rotation = [0.0, 0.0, 0.0]

        rotation = [1.0, 0.0, 0.0, 0.0]

        if animType == 'JOINT':
            if exportSettings['jointCache'][jointKey].get(keys[keyframeIndex]):
                tmpLocation, rotation, tmpScale = exportSettings['jointCache'][jointKey][keys[keyframeIndex]]
            else:
                sceneFrameSetFloat(bpy.context.scene, keys[keyframeIndex])

                jointMatrix = getBoneJointMatrix(blObj, blBone, exportSettings['bakeArmatureActions'])
                tmpLocation, rotation, tmpScale = decomposeTransformSwizzle(jointMatrix)

                exportSettings['jointCache'][jointKey][keys[keyframeIndex]] = [tmpLocation, rotation, tmpScale]
        else:
            channelIndex = 0

            for fcurve in fcurves:
                if fcurve is not None:
                    value = fcurve.evaluate(keys[keyframeIndex])

                    euler_rotation[channelIndex] = value

                channelIndex += 1

            rotation = animateConvertRotationEuler(euler_rotation, rotationMode)

            # Bring back to internal Quaternion notation.
            rotation = convertSwizzleRotation([rotation[3], rotation[0], rotation[1], rotation[2]])

            # apply additional rotation for lamps, cameras, fonts and their childs
            rotation = correctRotationQuat(rotation, animType)

        # Bring back to glTF Quaternion notation.
        rotation = [rotation[1], rotation[2], rotation[3], rotation[0]]

        result[time] = rotation

        keyframeIndex += 1

    return result


def animateRotationQuaternion(exportSettings, fcurves, interpolation, animType, blObj, blBone):
    """
    Calculates/gathers the key value pairs for quaternion transformations.
    """

    jointKey = None
    if animType == 'JOINT':
        jointKey = getPtr(blBone)
        if not exportSettings['jointCache'].get(jointKey):
            exportSettings['jointCache'][jointKey] = {}

    keys = animateGatherKeys(exportSettings, fcurves, interpolation)

    times = animateConvertKeys(keys)

    result = {}
    resultInTangent = {}
    resultOutTangent = {}

    keyframeIndex = 0
    for time in times:
        rotation = [1.0, 0.0, 0.0, 0.0]
        inTangent = [1.0, 0.0, 0.0, 0.0]
        outTangent = [1.0, 0.0, 0.0, 0.0]

        if animType == 'JOINT':
            if exportSettings['jointCache'][jointKey].get(keys[keyframeIndex]):
                tmpLocation, rotation, tmpScale = exportSettings['jointCache'][jointKey][keys[keyframeIndex]]
            else:
                sceneFrameSetFloat(bpy.context.scene, keys[keyframeIndex])

                jointMatrix = getBoneJointMatrix(blObj, blBone, exportSettings['bakeArmatureActions'])
                tmpLocation, rotation, tmpScale = decomposeTransformSwizzle(jointMatrix)

                exportSettings['jointCache'][jointKey][keys[keyframeIndex]] = [tmpLocation, rotation, tmpScale]
        else:
            channelIndex = 0

            for fcurve in fcurves:
                if fcurve is not None:
                    if interpolation == 'CUBICSPLINE':
                        blKeyframe = fcurve.keyframe_points[keyframeIndex]

                        rotation[channelIndex] = blKeyframe.co[1]

                        inTangent[channelIndex] = 3.0 * (blKeyframe.co[1] - blKeyframe.handle_left[1])
                        outTangent[channelIndex] = 3.0 * (blKeyframe.handle_right[1] - blKeyframe.co[1])
                    else:
                        value = fcurve.evaluate(keys[keyframeIndex])

                        rotation[channelIndex] = value

                channelIndex += 1

            # NOTE: fcurve.evaluate() requires normalization
            q = mathutils.Quaternion((rotation[0],rotation[1], rotation[2], rotation[3])).normalized()
            rotation = [q[0], q[1], q[2], q[3]]

            rotation = convertSwizzleRotation(rotation)

            inTangent = convertSwizzleRotation(inTangent)
            outTangent = convertSwizzleRotation(outTangent)

            # apply additional rotation for lamps, cameras, fonts and their childs
            rotation = correctRotationQuat(rotation, animType)
            inTangent = correctRotationQuat(inTangent, animType)
            outTangent = correctRotationQuat(outTangent, animType)

        # Bring to glTF Quaternion notation.
        rotation = [rotation[1], rotation[2], rotation[3], rotation[0]]
        inTangent = [inTangent[1], inTangent[2], inTangent[3], inTangent[0]]
        outTangent = [outTangent[1], outTangent[2], outTangent[3], outTangent[0]]

        result[time] = rotation
        resultInTangent[time] = inTangent
        resultOutTangent[time] = outTangent

        keyframeIndex += 1

    return result, resultInTangent, resultOutTangent


def animateScale(exportSettings, fcurves, interpolation, animType, blObj, blBone):
    """
    Calculates/gathers the key value pairs for scale transformations.
    """

    jointKey = None
    if animType == 'JOINT':
        jointKey = getPtr(blBone)
        if not exportSettings['jointCache'].get(jointKey):
            exportSettings['jointCache'][jointKey] = {}

    keys = animateGatherKeys(exportSettings, fcurves, interpolation)

    times = animateConvertKeys(keys)

    result = {}
    resultInTangent = {}
    resultOutTangent = {}

    keyframeIndex = 0
    for time in times:
        scaleData = [1.0, 1.0, 1.0]
        inTangent = [0.0, 0.0, 0.0]
        outTangent = [0.0, 0.0, 0.0]

        if animType == 'JOINT':
            if exportSettings['jointCache'][jointKey].get(keys[keyframeIndex]):
                tmpLocation, tmpRotation, scaleData = exportSettings['jointCache'][jointKey][keys[keyframeIndex]]
            else:
                sceneFrameSetFloat(bpy.context.scene, keys[keyframeIndex])

                jointMatrix = getBoneJointMatrix(blObj, blBone, exportSettings['bakeArmatureActions'])
                tmpLocation, tmpRotation, scaleData = decomposeTransformSwizzle(jointMatrix)

                exportSettings['jointCache'][jointKey][keys[keyframeIndex]] = [tmpLocation, tmpRotation, scaleData]
        else:
            channelIndex = 0
            for fcurve in fcurves:

                if fcurve is not None:
                    if interpolation == 'CUBICSPLINE':
                        blKeyframe = fcurve.keyframe_points[keyframeIndex]

                        scaleData[channelIndex] = blKeyframe.co[1]

                        inTangent[channelIndex] = 3.0 * (blKeyframe.co[1] - blKeyframe.handle_left[1])
                        outTangent[channelIndex] = 3.0 * (blKeyframe.handle_right[1] - blKeyframe.co[1])
                    else:
                        value = fcurve.evaluate(keys[keyframeIndex])

                        scaleData[channelIndex] = value

                channelIndex += 1

            scaleData = convertSwizzleScale(scaleData)
            inTangent = convertSwizzleScale(inTangent)
            outTangent = convertSwizzleScale(outTangent)

        result[time] = scaleData
        resultInTangent[time] = inTangent
        resultOutTangent[time] = outTangent

        keyframeIndex += 1

    return result, resultInTangent, resultOutTangent


def animateValue(exportSettings, fcurves, interpolation, animType):
    """
    Calculates/gathers the key value pairs for scalar animations.
    """
    keys = animateGatherKeys(exportSettings, fcurves, interpolation)

    times = animateConvertKeys(keys)

    result = {}
    resultInTangent = {}
    resultOutTangent = {}

    keyframeIndex = 0
    for time in times:
        valueData = []
        inTangent = []
        outTangent = []

        for fcurve in fcurves:

            if fcurve is not None:
                if interpolation == 'CUBICSPLINE':
                    blKeyframe = fcurve.keyframe_points[keyframeIndex]

                    valueData.append(blKeyframe.co[1])

                    inTangent.append(3.0 * (blKeyframe.co[1] - blKeyframe.handle_left[1]))
                    outTangent.append(3.0 * (blKeyframe.handle_right[1] - blKeyframe.co[1]))
                else:
                    value = fcurve.evaluate(keys[keyframeIndex])

                    valueData.append(value)

        result[time] = valueData
        resultInTangent[time] = inTangent
        resultOutTangent[time] = outTangent

        keyframeIndex += 1

    return result, resultInTangent, resultOutTangent


def animateDefaultValue(exportSettings, fcurves, interpolation):
    """
    Calculate/gather the key value pairs for node material animation.
    """

    keys = animateGatherKeys(exportSettings, fcurves, interpolation)

    times = animateConvertKeys(keys)

    result = {}
    resultInTangent = {}
    resultOutTangent = {}

    keyframeIndex = 0
    for time in times:
        def_value_data = [1.0, 1.0, 1.0, 1.0]
        inTangent = [0.0, 0.0, 0.0, 0.0]
        outTangent = [0.0, 0.0, 0.0, 0.0]

        channelIndex = 0
        for fcurve in fcurves:
            if fcurve is not None:
                if interpolation == 'CUBICSPLINE':
                    blKeyframe = fcurve.keyframe_points[keyframeIndex]

                    def_value_data[channelIndex] = blKeyframe.co[1]
                    inTangent[channelIndex] = 3.0 * (blKeyframe.co[1] - blKeyframe.handle_left[1])
                    outTangent[channelIndex] = 3.0 * (blKeyframe.handle_right[1] - blKeyframe.co[1])
                else:
                    value = fcurve.evaluate(keys[keyframeIndex])

                    def_value_data[channelIndex] = value

            channelIndex += 1

        result[time] = def_value_data
        resultInTangent[time] = inTangent
        resultOutTangent[time] = outTangent

        keyframeIndex += 1

    return result, resultInTangent, resultOutTangent


def animateEnergy(exportSettings, fcurves, interpolation):
    """
    Calculate/gather the key value pairs for node material animation.
    """

    keys = animateGatherKeys(exportSettings, fcurves, interpolation)

    times = animateConvertKeys(keys)

    result = {}
    resultInTangent = {}
    resultOutTangent = {}

    keyframeIndex = 0
    for time in times:
        energyData = [1.0]
        inTangent = [0.0]
        outTangent = [0.0]

        channelIndex = 0
        for fcurve in fcurves:

            if fcurve is not None:
                if interpolation == 'CUBICSPLINE':
                    blKeyframe = fcurve.keyframe_points[keyframeIndex]

                    energyData[channelIndex] = blKeyframe.co[1]
                    inTangent[channelIndex] = 3.0 * (blKeyframe.co[1] - blKeyframe.handle_left[1])
                    outTangent[channelIndex] = 3.0 * (blKeyframe.handle_right[1] - blKeyframe.co[1])
                else:
                    value = fcurve.evaluate(keys[keyframeIndex])

                    energyData[channelIndex] = value

            channelIndex += 1

        result[time] = energyData
        resultInTangent[time] = inTangent
        resultOutTangent[time] = outTangent

        keyframeIndex += 1

    return result, resultInTangent, resultOutTangent


def correctRotationQuat(rotation, animType):
    # apply additional rotation for lamps, cameras, fonts and their childs

    if animType == 'NODE_X_90':
        rotation = rotation @ QUAT_X_270 # right-to-left means rotation around local X
    elif animType == 'NODE_INV_X_90':
        rotation = QUAT_X_90 @ rotation
    elif animType == 'NODE_INV_X_90_X_90':
        rotation = QUAT_X_90 @ rotation @ QUAT_X_270

    return rotation


def getBoneJointMatrix(blObj, blBone, isBaked):
    correctionMatrixLocal = blBone.bone.matrix_local.copy()
    if blBone.parent is not None:
        correctionMatrixLocal = blBone.parent.bone.matrix_local.inverted() @ correctionMatrixLocal

    matrixBasis = blBone.matrix_basis
    if isBaked:
        matrixBasis = blObj.convert_space(pose_bone=blBone, matrix=blBone.matrix,
                                            from_space='POSE', to_space='LOCAL')

    return correctionMatrixLocal @ matrixBasis
