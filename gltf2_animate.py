# Copyright (c) 2017-2026 Soft8Soft, LLC. All rights reserved.
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

from .gltf2_extract import *
from .utils import *

QUAT_X_90 = mathutils.Quaternion((1.0, 0.0, 0.0), math.pi/2)
QUAT_X_270 = mathutils.Quaternion((1.0, 0.0, 0.0), math.pi + math.pi/2)

def getActionNameFcurves(blAnimationData):
    if blAnimationData is None or blAnimationData.action is None:
        return None, None

    action = blAnimationData.action

    fcurves = getActionFcurves(action)
    if fcurves:
        return action.name, fcurves
    else:
        return None, None

def getActionFcurves(action):
    if bpy.app.version >= (4, 4, 0):
        slot = action.slots[0] if action.slots else None

        if slot and action.layers and action.layers[0].strips:
            channelBag = action.layers[0].strips[0].channelbag(slot)
            if channelBag:
                return channelBag.fcurves

        return None
    else:
        return action.fcurves

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
        start = None
        end = None

        for fcurve in fcurves:
            if fcurve is None:
                continue

            if start == None:
                start = fcurve.range()[0]
            else:
                start = min(start, fcurve.range()[0])

            if end == None:
                end = fcurve.range()[1]
            else:
                end = max(end, fcurve.range()[1])

            add_epsilon_keyframe = False
            for blKeyframe in fcurve.keyframe_points:
                if add_epsilon_keyframe:
                    key = blKeyframe.co[0] - 0.001

                    if key not in keys:
                        keys.append(key)

                    add_epsilon_keyframe = False

                if blKeyframe.interpolation == 'CONSTANT':
                    add_epsilon_keyframe = True

            if add_epsilon_keyframe:
                key = end - 0.001

                if key not in keys:
                    keys.append(key)

        key = start
        while key <= end:
            if not exportSettings['exportFrameRange'] or (exportSettings['exportFrameRange'] and key >= bpy.context.scene.frame_start and key <= bpy.context.scene.frame_end):
                keys.append(key)
            key += 1.0

        keys.sort()

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

            rotation = convertSwizzleRotation([rotation[3], rotation[0], rotation[1], rotation[2]])

            rotation = correctRotationQuat(rotation, animType)

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

            rotation = convertSwizzleRotation([rotation[3], rotation[0], rotation[1], rotation[2]])

            rotation = correctRotationQuat(rotation, animType)

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

            q = mathutils.Quaternion((rotation[0],rotation[1], rotation[2], rotation[3])).normalized()
            rotation = [q[0], q[1], q[2], q[3]]

            rotation = convertSwizzleRotation(rotation)

            inTangent = convertSwizzleRotation(inTangent)
            outTangent = convertSwizzleRotation(outTangent)

            rotation = correctRotationQuat(rotation, animType)
            inTangent = correctRotationQuat(inTangent, animType)
            outTangent = correctRotationQuat(outTangent, animType)

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
