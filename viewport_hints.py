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
import bpy, gpu, mathutils
from gpu_extras.batch import batch_for_shader

CAM_PIVOT_POS_LOCAL = [
    (-1, 0, 0), (1, 0, 0),
    (0, -1, 0), (0, 1, 0),
    (0, 0, -1), (0, 0, 1)
]
CAM_PIVOT_SIZE = 0.15
LINE_COLOR = (1.0, 0.7, 0.0, 1.0)

drawHandle = None
lineShader = None

def drawCallback():
    camera = bpy.context.active_object
    if not camera or camera.type != 'CAMERA':
        return

    v3d = camera.data.v3d

    if v3d.controls != 'ORBIT' or v3d.orbit_target_show == False:
        return

    viewportSize = gpu.state.viewport_get()[2:4]

    lineShader.bind()
    lineShader.uniform_float('viewportSize', viewportSize)
    lineShader.uniform_float('lineWidth', 3)
    lineShader.uniform_float('color', LINE_COLOR)

    gpu.state.blend_set('ALPHA')

    targetObj = v3d.orbit_target_object
    target = (v3d.orbit_target if targetObj is None
            else targetObj.matrix_world.to_translation())

    pivotPosWorld = []
    for pos in CAM_PIVOT_POS_LOCAL:
        pivotPosWorld.append(mathutils.Vector(pos) * CAM_PIVOT_SIZE + target)

    batch = batch_for_shader(lineShader, 'LINES', {'pos': pivotPosWorld})
    batch.draw(lineShader)

def register():
    if not bpy.app.background:
        global drawHandle, lineShader
        drawHandle = bpy.types.SpaceView3D.draw_handler_add(drawCallback, (), 'WINDOW', 'POST_VIEW')
        lineShader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')

def unregister():
    if not bpy.app.background:
        global drawHandle, lineShader
        if drawHandle:
            bpy.types.SpaceView3D.draw_handler_remove(drawHandle, 'WINDOW')
            drawHandle = None
        lineShader = None
