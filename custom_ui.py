# Copyright (c) 2017-2019 Soft8Soft LLC
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
import shutil
import subprocess
import webbrowser

from pluginUtils.log import printLog
from pluginUtils.path import getAppManagerHost, getManualURL, getRoot, findExportedAssetPath

from . import utils

join = os.path.join
norm = os.path.normpath

from pluginUtils.manager import AppManagerConn

class V3DPanel():
    COMPAT_ENGINES = ['CYCLES', 'BLENDER_EEVEE']

    @classmethod
    def poll(cls, context):

        if (hasattr(context, cls.poll_datablock) and
                getattr(context, cls.poll_datablock) and
                context.scene.render.engine in cls.COMPAT_ENGINES):
            return True
        else:
            return False


class V3D_PT_RenderSettings(bpy.types.Panel, V3DPanel):
    """Located on render panel"""
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'scene'

    def draw(self, context):
        layout = self.layout

        # global export settings

        v3d_export = bpy.data.scenes[0].v3d_export

        row = layout.row()
        row.prop(v3d_export, 'copyright')

        col = layout.column()
        col.label(text='Export Collections:')
        col.template_list("COLLECTION_UL_export", "", bpy.data,
                "collections", context.scene.v3d_export, "collections_exported_idx", rows=4)

        # animation box

        box = layout.box()
        box.label(text='Animation:')

        row = box.row()
        row.prop(v3d_export, 'export_animations')
        row = box.row()
        row.prop(v3d_export, 'export_frame_range')
        row = box.row()
        row.prop(v3d_export, 'export_move_keyframes')
        row = box.row()
        row.prop(v3d_export, 'bake_armature_actions')

        row = layout.row()
        row.prop(v3d_export, 'export_constraints')

        row = layout.row()
        row.prop(v3d_export, 'export_custom_props')

        row = layout.row()
        row.prop(v3d_export, 'bake_modifiers')

        row = layout.row()
        row.prop(v3d_export, 'bake_text')

        row = layout.row()
        row.prop(v3d_export, 'lzma_enabled')

        row = layout.row()
        row.prop(v3d_export, 'optimize_attrs')


        # shadow box
        box = layout.box()
        box.label(text='Shadows:')

        row = box.row()
        row.prop(v3d_export, 'use_shadows')

        if bpy.app.version >= (2,81,0):
            split = box.split()
            split.active = v3d_export.use_shadows
            col = split.column()
            col.label(text='Shadow Map Filtering')
            col = split.column()
            col.prop(v3d_export, 'shadow_map_type', text='')

        split = box.split()
        split.active = v3d_export.use_shadows
        col = split.column()
        col.label(text='Shadow Map Side')
        col = split.column()
        col.prop(v3d_export, 'shadow_map_side', text='')

        split = box.split()
        split.active = v3d_export.use_shadows and v3d_export.shadow_map_type == 'ESM'
        col = split.column()
        col.label(text='ESM Distance Scale')
        col = split.column()
        col.prop(v3d_export, 'esm_distance_scale', text='')

        split = layout.split()
        col = split.column()
        col.label(text='Anti-Aliasing')
        col = split.column()
        col.prop(v3d_export, 'aa_method', text='')

        row = layout.row()
        row.prop(v3d_export, 'use_hdr')

        split = layout.split()
        col = split.column()
        col.label(text='IBL Environment Mode')
        col = split.column()
        col.prop(v3d_export, 'ibl_environment_mode', text='')

        # outline box

        outline = context.scene.v3d.outline
        outlineActive = outline.enabled

        box = layout.box()
        box.label(text='Outline:')

        row = box.row()
        row.prop(outline, 'enabled')
        row = box.row()
        row.active = outlineActive
        row.prop(outline, 'edge_strength')
        row = box.row()
        row.active = outlineActive
        row.prop(outline, 'edge_glow')
        row = box.row()
        row.active = outlineActive
        row.prop(outline, 'edge_thickness')
        row = box.row()
        row.active = outlineActive
        row.prop(outline, 'pulse_period')
        row = box.row()
        row.active = outlineActive
        row.prop(outline, 'visible_edge_color')
        row = box.row()
        row.active = outlineActive
        row.prop(outline, 'hidden_edge_color')
        row = box.row()
        row.active = outlineActive
        row.prop(outline, 'render_hidden_edge')

class COLLECTION_UL_export(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index, flt_flag):
        col = layout.column()
        col.prop(item, 'name', text='', emboss=False)
        col = layout.column()
        col.prop(item.v3d, 'enable_export', text='')

    def filter_items(self, context, data, property):

        coll_list = getattr(data, property)
        filter_name = self.filter_name.lower()

        flt_flags = [self.bitflag_filter_item
            if filter_name in item.name.lower()
            else 0 for i, item in enumerate(coll_list, 1)
        ]

        if self.use_filter_sort_alpha:
            flt_neworder = [x[1] for x in sorted(
                    zip(
                        [x[0] for x in sorted(enumerate(coll_list), key=lambda x: x[1].name)],
                        range(len(coll_list))
                    )
                )
            ]
        else:
            flt_neworder = []

        return flt_flags, flt_neworder


class V3D_PT_RenderLayerSettings(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render_layer'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'scene'

    def draw(self, context):
        layout = self.layout

        scene = context.scene

        row = layout.row()
        row.label(text='Export Layers:')

        row = layout.row()
        row.prop(scene.v3d, 'export_layers', text='')

class V3D_PT_WorldSettings(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'world'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'world'

    def draw(self, context):
        layout = self.layout

        world = context.world

        row = layout.row()
        row.prop(world.v3d, 'dithering')


class V3D_PT_ObjectSettings(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'object'

    def draw(self, context):
        layout = self.layout

        obj = context.object
        v3d = obj.v3d

        row = layout.row()
        row.label(text='Animation:')

        row = layout.row()
        row.prop(v3d, 'anim_auto')

        row = layout.row()
        row.prop(v3d, 'anim_loop')

        row = layout.row()
        row.active = (v3d.anim_loop != 'ONCE')
        row.prop(v3d, 'anim_repeat_infinite')

        row = layout.row()
        row.active = (v3d.anim_loop != 'ONCE' and not v3d.anim_repeat_infinite)
        row.prop(v3d, 'anim_repeat_count')

        row = layout.row()
        row.prop(v3d, 'anim_offset')

        if context.object.type in ['MESH', 'CURVE', 'SURFACE', 'META', 'FONT']:
            row = layout.row()
            row.label(text='Rendering:')

            row = layout.row()
            row.prop(v3d, 'render_order')

            row = layout.row()
            row.prop(v3d, 'frustum_culling')

            row = layout.row()
            row.prop(v3d, 'use_shadows')

class V3D_PT_CameraSettings(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'camera'

    def draw(self, context):
        layout = self.layout

        camera = context.camera
        v3d = camera.v3d

        row = layout.row()
        row.prop(v3d, 'controls')

        if v3d.controls == 'FIRST_PERSON':
            split = layout.split()
            col = split.column()
            col.label(text='Collision Material:')

            col = split.column()
            col.prop(v3d, 'fps_collision_material', text='')

            row = layout.row()
            row.prop(v3d, 'fps_gaze_level')

            row = layout.row()
            row.prop(v3d, 'fps_story_height')

        row = layout.row()
        row.active = (v3d.controls != 'NONE')
        row.prop(v3d, 'enable_pan')

        row = layout.row()
        row.active = (v3d.controls != 'NONE')
        row.prop(v3d, 'rotate_speed')

        row = layout.row()
        row.active = (v3d.controls != 'NONE')
        row.prop(v3d, 'move_speed')

        if v3d.controls == 'ORBIT':

            box = layout.box()
            box.label(text='Target Object/Point')

            split = box.split(factor=0.5)

            column = split.column()
            column.prop(v3d, 'orbit_target', text='Manual')
            column.enabled = v3d.orbit_target_object is None

            column = split.column()
            column.label(text='From Object:')
            column.prop(v3d, 'orbit_target_object', text='')

            column.operator('v3d.orbit_camera_target_from_cursor', text='From Cursor')

            box.operator('v3d.orbit_camera_update_view', text='Update View')

            row = layout.row()

            if camera.type == 'ORTHO':
                row.prop(v3d, 'orbit_min_zoom')
                row.prop(v3d, 'orbit_max_zoom')
            else:
                row.prop(v3d, 'orbit_min_distance')
                row.prop(v3d, 'orbit_max_distance')

            row = layout.row()
            row.label(text='Vertical Rotation Limits:')

            row = layout.row()
            row.prop(v3d, 'orbit_min_polar_angle')
            row.prop(v3d, 'orbit_max_polar_angle')


            row = layout.row()
            row.label(text='Horizontal Rotation Limits:')

            row = layout.row()
            row.prop(v3d, 'orbit_min_azimuth_angle')
            row.prop(v3d, 'orbit_max_azimuth_angle')

class V3D_PT_LightSettings(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'light'

    def draw(self, context):
        layout = self.layout

        light = context.light
        type = light.type
        shadow = light.v3d.shadow

        if bpy.app.version < (2,81,0):

            if type == 'SUN':

                row = layout.row()
                row.label(text='Shadow:')

                row = layout.row()
                row.prop(shadow, 'camera_size', text='Shadow Size (fallback)')
            else:
                row = layout.row()
                row.label(text='Not available for this light type')

        else:

            if type == 'POINT' or type == 'SPOT' or type == 'SUN':

                row = layout.row()
                row.label(text='Shadow:')

                row = layout.row()
                row.active = (context.scene.v3d_export.shadow_map_type
                        not in ['BASIC', 'BILINEAR'])
                row.prop(shadow, 'radius', text='Blur Radius')

                row = layout.row()
                row.active = context.scene.v3d_export.shadow_map_type == 'ESM'
                row.prop(shadow, 'esm_exponent', text='ESM Bias')

            else:
                row = layout.row()
                row.label(text='Not available for this light type')


class V3D_PT_CurveSettings(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'curve'

    @classmethod
    def poll(cls, context):
        return (super().poll(context) and not
                isinstance(getattr(context, cls.poll_datablock), bpy.types.TextCurve))

    def draw(self, context):
        layout = self.layout
        v3d = context.curve.v3d

        box = layout.box()
        row = box.row()
        row.prop(v3d.line_rendering_settings, 'enable')

        is_active = getattr(v3d.line_rendering_settings, 'enable') is True

        row = box.row()
        row.prop(v3d.line_rendering_settings, 'color')
        row.active = is_active

        row = box.row()
        row.prop(v3d.line_rendering_settings, 'width')
        row.active = is_active

class V3D_PT_MeshSettings(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'mesh'

    def draw(self, context):
        layout = self.layout
        v3d = context.mesh.v3d

        box = layout.box()
        row = box.row()
        row.prop(v3d.line_rendering_settings, 'enable')

        is_active = getattr(v3d.line_rendering_settings, 'enable') is True

        row = box.row()
        row.prop(v3d.line_rendering_settings, 'color')
        row.active = is_active

        row = box.row()
        row.prop(v3d.line_rendering_settings, 'width')
        row.active = is_active

class V3D_PT_MaterialSettings(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'material'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'material'

    def draw(self, context):
        layout = self.layout

        material = context.material

        layout.use_property_split = True

        blend_back = utils.matHasBlendBackside(material)

        if blend_back:
            row = layout.row()
            row.label(text='Overridden by the "Settings->Show Backface" option.', icon='INFO')

        row = layout.row()
        row.prop(material.v3d, 'render_side')
        row.active = not blend_back

        row = layout.row()
        row.prop(material.v3d, 'depth_write')
        row.active = not blend_back and not material.blend_method == 'OPAQUE'

        row = layout.row()
        row.prop(material.v3d, 'depth_test')

        row = layout.row()
        row.prop(material.v3d, 'dithering')

        row = layout.row()
        row.prop(material.v3d, 'gltf_compat')

class V3D_PT_TextureSettings(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'texture'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'texture'

    def draw(self, context):
        layout = self.layout

        texture = context.texture

        row = layout.row()
        row.label(text='Anisotropic Filtering:')

        row = layout.row()
        row.prop(texture.v3d, 'anisotropy', 'Ratio')


class V3D_PT_NodeSettings(bpy.types.Panel):
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_label = 'Verge3D Settings'
    bl_parent_id = 'NODE_PT_active_node_generic'

    @classmethod
    def poll(cls, context):
        node = context.active_node
        return node is not None and (
                isinstance(node, bpy.types.ShaderNodeTexImage)
                or isinstance(node, bpy.types.ShaderNodeTexNoise)
        )

    def draw(self, context):
        layout = self.layout

        node = context.active_node

        if isinstance(node, bpy.types.ShaderNodeTexImage):

            row = layout.row()
            row.label(text='Anisotropic Filtering:')

            row = layout.row()
            row.prop(node.v3d, 'anisotropy', text='Ratio')

        elif isinstance(node, bpy.types.ShaderNodeTexNoise):

            row = layout.row()
            row.label(text='Noise Parameters:')

            row = layout.row()
            row.prop(node.v3d, 'falloff_factor')

            row = layout.row()
            row.prop(node.v3d, 'dispersion_factor')


def execBrowser(url):
    # always try to run server before starting browers
    # fixes several issues with closed Blender
    AppManagerConn.start(getRoot(), 'BLENDER', True)

    try:
        webbrowser.open(url)
    except BaseException:
        print("Failed to open URL: " + url)

class V3D_OT_orbit_camera_target_from_cursor(bpy.types.Operator):
    bl_idname = 'v3d.orbit_camera_target_from_cursor'
    bl_label = 'From Cursor'
    bl_description = 'Update target coordinates from cursor position'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        context.object.data.v3d.orbit_target_object = None
        context.object.data.v3d.orbit_target = bpy.context.scene.cursor.location
        utils.updateOrbitCameraView(context.object, context.scene)
        return {'FINISHED'}

class V3D_OT_orbit_camera_update_view(bpy.types.Operator):
    bl_idname = "v3d.orbit_camera_update_view"
    bl_label = "Update View"
    bl_description = "Update view for the orbit camera"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        utils.updateOrbitCameraView(context.object, context.scene)
        return {"FINISHED"}

class V3D_OT_app_manager(bpy.types.Operator):
    bl_idname = "v3d.app_manager"
    bl_label = "Open App Manager"
    bl_description = "Open Verge3D App Manager"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        execBrowser(getAppManagerHost())
        return {"FINISHED"}


class V3D_OT_sneak_peek(bpy.types.Operator):
    bl_idname = "v3d.sneak_peek"
    bl_label = "Sneak Peek"
    bl_description = "Export to temporary location and preview the scene in Verge3D"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        prev_dir = join(getRoot(), "player", "preview")

        if os.path.exists(prev_dir):
            shutil.rmtree(prev_dir)
        os.mkdir(prev_dir)

        bpy.ops.v3d.export_gltf(filepath=join(prev_dir, 'sneak_peek.gltf'),
                                export_sneak_peek = True)

        execBrowser(getAppManagerHost() +
                'player/player.html?load=preview/sneak_peek.gltf')

        return {"FINISHED"}

@persistent
def loadHandler(dummy):
    printLog('INFO', 'Reexporting ' + V3D_OT_reexport_all.currBlend)
    bpy.ops.v3d.export_gltf(filepath=V3D_OT_reexport_all.currGLTF)
    V3D_OT_reexport_all.reexportNext()

class V3D_OT_reexport_all(bpy.types.Operator):
    bl_idname = "v3d.reexport_all"
    bl_label = "Reexport all Verge3D assets"
    bl_description = "Reexport all glTF files inside Verge3D SDK"

    exported = []
    currBlend = None
    currGLTF = None

    @classmethod
    def reexportNext(cls):
        if len(cls.exported):
            cls.currBlend, cls.currGLTF = cls.exported.pop(0)

            if loadHandler not in bpy.app.handlers.load_post:
                bpy.app.handlers.load_post.append(loadHandler)

            bpy.ops.wm.open_mainfile(filepath=cls.currBlend)

        else:
            if loadHandler in bpy.app.handlers.load_post:
                bpy.app.handlers.load_post.remove(loadHandler)

    def execute(self, context):
        apps = join(getRoot(), 'applications')

        for root, dirs, files in os.walk(apps):
            for name in files:
                if fnmatch.fnmatch(name, '*.blend'):
                    blendpath = norm(join(root, name))

                    # use file utility to check .blend version
                    if sys.platform.startswith('linux'):
                        fileinfo = subprocess.check_output(['file', '--uncompress', blendpath]).decode()
                        ver = re.search('\d\.\d\d', fileinfo).group(0)
                        verMaj, verMin = [int(n) for n in ver.split('.')]

                        # ignore incompatible blender files

                        if verMaj != 2:
                            continue

                        if verMin < 80:
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
                        self.__class__.exported.append((blendpath, gltfpath))
                        self.__class__.exported.sort()

        self.__class__.reexportNext()

        return {"FINISHED"}

def btnSneakPeek(self, context):
    self.layout.operator('v3d.sneak_peek', text='Sneak Peek')

def btnAppManager(self, context):
    self.layout.operator('v3d.app_manager', text='App Manager')

def menuUserManual(self, context):
    if context.scene.render.engine in V3DPanel.COMPAT_ENGINES:
        self.layout.separator()
        self.layout.operator("wm.url_open", text="Verge3D User Manual", icon='URL').url = getManualURL()

def register():

    bpy.types.TOPBAR_MT_help.append(menuUserManual)

    bpy.utils.register_class(V3D_PT_RenderSettings)
    bpy.utils.register_class(V3D_PT_RenderLayerSettings)
    bpy.utils.register_class(V3D_PT_WorldSettings)
    bpy.utils.register_class(V3D_PT_ObjectSettings)
    bpy.utils.register_class(V3D_PT_CameraSettings)
    bpy.utils.register_class(V3D_PT_LightSettings)
    bpy.utils.register_class(V3D_PT_MaterialSettings)
    bpy.utils.register_class(V3D_PT_CurveSettings)
    bpy.utils.register_class(V3D_PT_TextureSettings)
    bpy.utils.register_class(V3D_PT_MeshSettings)
    bpy.utils.register_class(V3D_PT_NodeSettings)

    bpy.utils.register_class(V3D_OT_orbit_camera_target_from_cursor)
    bpy.utils.register_class(V3D_OT_orbit_camera_update_view)
    bpy.utils.register_class(V3D_OT_reexport_all)

    bpy.utils.register_class(COLLECTION_UL_export)

    if AppManagerConn.isAvailable(getRoot()):
        bpy.utils.register_class(V3D_OT_app_manager)
        bpy.utils.register_class(V3D_OT_sneak_peek)
        bpy.types.VIEW3D_HT_header.append(btnSneakPeek)
        bpy.types.VIEW3D_HT_header.append(btnAppManager)


def unregister():

    if AppManagerConn.isAvailable(getRoot()):
        bpy.types.VIEW3D_HT_header.remove(btnAppManager)
        bpy.types.VIEW3D_HT_header.remove(btnSneakPeek)
        bpy.utils.unregister_class(V3D_OT_sneak_peek)
        bpy.utils.unregister_class(V3D_OT_app_manager)

    bpy.utils.unregister_class(V3D_PT_NodeSettings)
    bpy.utils.unregister_class(V3D_PT_TextureSettings)
    bpy.utils.unregister_class(V3D_PT_MaterialSettings)
    bpy.utils.unregister_class(V3D_PT_LightSettings)
    bpy.utils.unregister_class(V3D_PT_CurveSettings)
    bpy.utils.unregister_class(V3D_PT_CameraSettings)
    bpy.utils.unregister_class(V3D_PT_ObjectSettings)
    bpy.utils.unregister_class(V3D_PT_WorldSettings)
    bpy.utils.unregister_class(V3D_PT_RenderLayerSettings)
    bpy.utils.unregister_class(V3D_PT_RenderSettings)
    bpy.utils.unregister_class(V3D_PT_MeshSettings)

    bpy.utils.unregister_class(V3D_OT_reexport_all)
    bpy.utils.unregister_class(V3D_OT_orbit_camera_target_from_cursor)
    bpy.utils.unregister_class(V3D_OT_orbit_camera_update_view)

    bpy.utils.unregister_class(COLLECTION_UL_export)

