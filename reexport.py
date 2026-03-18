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
import bpy
from bpy.app.handlers import persistent

import fnmatch, re, os, sys
import subprocess

import pluginUtils
from pluginUtils.path import getRoot, findExportedAssetPath

from .utils import extractMaterialNodeTrees

log = pluginUtils.log.getLogger('V3D-BL')

join = os.path.join
norm = os.path.normpath

loadHandlerInfo = {
    'currBlend' : None,
    'currGLTF' : None,
    'resaveBlend': False,
    'updateCopyright': False,
    'applySceneFixes': False
}

def applySceneFixes():
    for mat in bpy.data.materials:
        if mat.use_nodes and mat.node_tree:
            for nodeTree in extractMaterialNodeTrees(mat.node_tree):
                for node in nodeTree.nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        node.distribution = 'GGX'

    for world in bpy.data.worlds:
        world.sun_threshold = 0

@persistent
def loadHandler(dummy):
    def delayReexport():
        if loadHandlerInfo['updateCopyright']:
            for scene in bpy.data.scenes:
                scene.v3d_export.copyright = pluginUtils.copyrightLine

        if loadHandlerInfo['applySceneFixes']:
            applySceneFixes()

        exported = loadHandlerInfo['currGLTF']
        if exported:
            log.info('Reexporting ' + loadHandlerInfo['currBlend'])

            if os.path.splitext(exported)[1] == '.gltf':
                bpy.ops.export_scene.v3d_gltf(filepath=exported)
            elif os.path.splitext(exported)[1] == '.glb':
                bpy.ops.export_scene.v3d_glb(filepath=exported)
            else:
                log.error('Invalid exported extension')

        if loadHandlerInfo['resaveBlend']:
            log.info('Resaving ' + loadHandlerInfo['currBlend'])
            bpy.ops.wm.save_mainfile()

        V3D_OT_reexport_all.reexportNext()

    bpy.app.timers.register(delayReexport, first_interval=0.001)

class V3D_OT_reexport_all(bpy.types.Operator):
    bl_idname = 'wm.v3d_reexport_all'
    bl_label = 'Reexport all Verge3D assets'
    bl_description = 'Reexport all glTF files inside Verge3D SDK'

    exported = []

    folder: bpy.props.StringProperty(
        name = 'Folder',
        description = 'Folder to reexport (relative to Verge3D root folder)',
        default = 'applications'
    )
    resaveBlend: bpy.props.BoolProperty(name='Resave .blend files')
    updateCopyright: bpy.props.BoolProperty(name='Update copyright')
    applySceneFixes: bpy.props.BoolProperty(name='Apply scene fixes')
    forceGLB: bpy.props.BoolProperty(name='Force GLB export')

    @classmethod
    def reexportNext(cls):
        if len(cls.exported):
            currBlend, currGLTF = cls.exported.pop(0)

            if loadHandler not in bpy.app.handlers.load_post:
                bpy.app.handlers.load_post.append(loadHandler)

            loadHandlerInfo['currBlend'] = currBlend
            loadHandlerInfo['currGLTF'] = currGLTF

            bpy.ops.wm.open_mainfile(filepath=currBlend)

        else:
            if loadHandler in bpy.app.handlers.load_post:
                bpy.app.handlers.load_post.remove(loadHandler)

    def execute(self, context):
        apps = join(getRoot(), self.folder)

        loadHandlerInfo['resaveBlend'] = self.resaveBlend
        loadHandlerInfo['updateCopyright'] = self.updateCopyright
        loadHandlerInfo['applySceneFixes'] = self.applySceneFixes

        sys.setrecursionlimit(10000)

        for root, dirs, files in os.walk(apps):
            for name in files:
                if fnmatch.fnmatch(name, '*.blend'):
                    blendpath = norm(join(root, name))

                    if sys.platform.startswith('linux'):
                        fileinfo = subprocess.check_output(['file', '--uncompress', blendpath]).decode()
                        verStrMatch = re.search(r'\d\.\d\d', fileinfo)
                        if verStrMatch:
                            verStr = verStrMatch.group(0)
                            ver = tuple([int(n) for n in verStr.split('.')]) + (0,)
                        else:
                            ver = (5, 0, 0)

                        if ver < (2, 80, 0) or ver > bpy.app.version:
                            blendRel = os.path.relpath(blendpath, apps)
                            log.warning(f'Ignoring {blendRel}, saved in Blender {ver[0]}.{ver[1]}')
                            continue

                        IGNORE = []

                        ignore = False
                        for pattern in IGNORE:
                            if fnmatch.fnmatch(name, pattern):
                                ignore = True
                        if ignore:
                            continue

                    gltfpath = findExportedAssetPath(blendpath)
                    if gltfpath:
                        if self.forceGLB:
                            gltfpath = os.path.splitext(gltfpath)[0] + '.glb'
                        self.__class__.exported.append((blendpath, gltfpath))
                    elif self.resaveBlend:
                        self.__class__.exported.append((blendpath, None))

        self.__class__.exported.sort()
        self.__class__.reexportNext()

        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

def menuReexportAll(self, context):
    self.layout.separator()
    self.layout.operator(V3D_OT_reexport_all.bl_idname, icon='TOOL_SETTINGS')

def register():
    bpy.utils.register_class(V3D_OT_reexport_all)
    if pluginUtils.debug:
        bpy.types.TOPBAR_MT_render.append(menuReexportAll)

def unregister():
    if pluginUtils.debug:
        bpy.types.TOPBAR_MT_render.remove(menuReexportAll)
    bpy.utils.unregister_class(V3D_OT_reexport_all)
