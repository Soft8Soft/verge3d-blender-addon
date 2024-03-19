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
import os
import sys

from bpy.app.handlers import persistent

join = os.path.join

# used here to get path to plugin utils, afterwards use pluginUtils.path.getRoot()
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(join(ROOT_DIR, 'python'))

ADDON_DISABLE_DELAY = 2

if 'bpy' in locals():
    import imp
    if 'gltf2_animate' in locals():
        imp.reload(gltf2_animate)
    if 'gltf2_export' in locals():
        imp.reload(gltf2_export)
    if 'gltf2_extract' in locals():
        imp.reload(gltf2_extract)
    if 'gltf2_filter' in locals():
        imp.reload(gltf2_filter)
    if 'gltf2_generate' in locals():
        imp.reload(gltf2_generate)
    if 'gltf2_get' in locals():
        imp.reload(gltf2_get)

    if 'curve_approx' in locals():
        imp.reload(curve_approx)
    if 'node_material_wrapper' in locals():
        imp.reload(node_material_wrapper)
    if 'utils' in locals():
        imp.reload(utils)

import pluginUtils
from pluginUtils.manager import AppManagerConn
from pluginUtils.path import getRoot

log = pluginUtils.log.getLogger('V3D-BL')


bl_info = {
    "name": "Verge3D",
    "description": "Artist-friendly toolkit for creating 3D web experiences",
    "author": "Soft8Soft",
    "version": (4, 6, 0),
    "blender": (2, 83, 0),
    "location": "File > Import-Export",
    "doc_url": "https://www.soft8soft.com/docs/manual/en/index.html",
    "tracker_url": "https://www.soft8soft.com/forum/bug-reports-and-feature-requests/",
    "category": "Render"
}

from bpy.props import (CollectionProperty,
                       StringProperty,
                       BoolProperty,
                       EnumProperty,
                       FloatProperty)

from bpy_extras.io_utils import (ExportHelper)


class V3D_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    disable_builtin_gltf_addon: BoolProperty(
        default = True,
        description = 'Disable built-in glTF 2.0 exporter (io_scene_gltf2)'
    )

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.prop(self, 'disable_builtin_gltf_addon', text='Disable Built-in glTF Add-on')

class V3D_OT_export():

    export_sneak_peek: BoolProperty(
        name='Sneak Peek Mode',
        description='',
        default=False
    )

    def execute(self, context):
        from . import gltf2_export

        v3d_export = bpy.data.scenes[0].v3d_export

        # All custom export settings are stored in this container.
        exportSettings = {}

        exportSettings['filepath'] = bpy.path.ensure_ext(self.filepath, self.filename_ext)
        exportSettings['filedirectory'] = os.path.dirname(exportSettings['filepath']) + '/'

        exportSettings['format'] = self.export_format
        exportSettings['copyright'] = v3d_export.copyright
        exportSettings['use_shadows'] = v3d_export.use_shadows
        exportSettings['shadow_map_type'] = v3d_export.shadow_map_type
        exportSettings['shadow_map_side'] = v3d_export.shadow_map_side
        exportSettings['esm_distance_scale'] = v3d_export.esm_distance_scale
        exportSettings['ibl_environment_mode'] = v3d_export.ibl_environment_mode
        exportSettings['bake_modifiers'] = v3d_export.bake_modifiers
        exportSettings['bake_armature_actions'] = v3d_export.bake_armature_actions
        exportSettings['bake_text'] = v3d_export.bake_text
        exportSettings['export_constraints'] = v3d_export.export_constraints
        exportSettings['custom_props'] = v3d_export.export_custom_props
        exportSettings['lzma_enabled'] = v3d_export.lzma_enabled
        exportSettings['compress_textures'] = v3d_export.compress_textures
        exportSettings['optimize_attrs'] = v3d_export.optimize_attrs
        exportSettings['aa_method'] = v3d_export.aa_method
        exportSettings['use_hdr'] = v3d_export.use_hdr
        exportSettings['use_oit'] = v3d_export.use_oit
        exportSettings['animations'] = v3d_export.export_animations
        if v3d_export.export_animations:
            exportSettings['frame_range'] = v3d_export.export_frame_range
            exportSettings['move_keyframes'] = v3d_export.export_move_keyframes
        else:
            exportSettings['frame_range'] = False
            exportSettings['move_keyframes'] = False

        exportSettings['uri_cache'] = { 'uri': [], 'bl_datablocks': [] }
        exportSettings['binary'] = bytearray()
        exportSettings['binaryfilename'] = os.path.splitext(os.path.basename(self.filepath))[0] + '.bin'

        exportSettings['sneak_peek'] = self.export_sneak_peek

        exportSettings['temporary_meshes'] = None
        exportSettings['temporary_materials'] = None

        exportSettings['strip'] = True

        # valid values are: 'UNSIGNED_INT', 'UNSIGNED_SHORT', 'UNSIGNED_BYTE'
        exportSettings['indices'] = 'UNSIGNED_INT'
        exportSettings['force_indices'] = False

        exportSettings['force_sampling'] = False
        exportSettings['skins'] = True
        exportSettings['morph'] = True
        exportSettings['morph_normal'] = True
        exportSettings['morph_tangent'] = True

        exportSettings['displacement'] = False

        return gltf2_export.save(self, context, exportSettings)

    def draw(self, context):
        pass

class V3D_OT_export_gltf(bpy.types.Operator, ExportHelper, V3D_OT_export):
    '''Export scene to glTF 2.0 format'''
    bl_idname = 'export_scene.v3d_gltf'
    bl_label = 'Export Verge3D glTF'

    filename_ext = '.gltf'
    filter_glob: StringProperty(default='*.gltf', options={'HIDDEN'})

    export_format = 'ASCII'

class V3D_OT_export_glb(bpy.types.Operator, ExportHelper, V3D_OT_export):
    '''Export scene to glTF 2.0 binary format'''
    bl_idname = 'export_scene.v3d_glb'
    bl_label = 'Export Verge3D glTF Binary'

    filename_ext = '.glb'
    filter_glob: StringProperty(default='*.glb', options={'HIDDEN'})

    export_format = 'BINARY'

def menuExportGLTF(self, context):
    self.layout.operator(V3D_OT_export_gltf.bl_idname, text='Verge3D glTF (.gltf)')

def menuExportGLB(self, context):
    self.layout.operator(V3D_OT_export_glb.bl_idname, text='Verge3D glTF Binary (.glb)')

def disableBuiltInGLTFAddon():

    import addon_utils

    is_enabled, is_loaded = addon_utils.check('io_scene_gltf2')

    if is_enabled:
        import io_scene_gltf2
        bpy.types.TOPBAR_MT_file_export.remove(io_scene_gltf2.menu_func_export)

def register():
    from . import custom_props, custom_ui, manual_map

    AppManagerConn.init(getRoot(), 'BLENDER')

    bpy.utils.register_class(V3D_AddonPreferences)
    bpy.utils.register_class(V3D_OT_export_gltf)
    bpy.utils.register_class(V3D_OT_export_glb)

    custom_props.register()
    custom_ui.register()
    manual_map.register()

    bpy.types.TOPBAR_MT_file_export.append(menuExportGLTF)
    bpy.types.TOPBAR_MT_file_export.append(menuExportGLB)

    if AppManagerConn.isAvailable():
        if not AppManagerConn.ping():
            AppManagerConn.start()
    else:
        log.warning('App Manager is not available!')

    if bpy.context.preferences.addons['verge3d'].preferences.disable_builtin_gltf_addon:
        bpy.app.timers.register(disableBuiltInGLTFAddon, first_interval=ADDON_DISABLE_DELAY, persistent=True)


def unregister():
    from . import custom_props, custom_ui, manual_map

    bpy.utils.unregister_class(V3D_AddonPreferences)
    bpy.utils.unregister_class(V3D_OT_export_gltf)
    bpy.utils.unregister_class(V3D_OT_export_glb)

    custom_props.unregister()
    custom_ui.unregister()
    manual_map.unregister()

    bpy.types.TOPBAR_MT_file_export.remove(menuExportGLTF)
    bpy.types.TOPBAR_MT_file_export.remove(menuExportGLB)
