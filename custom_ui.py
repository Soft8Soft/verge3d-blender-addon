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

import bpy, bpy_extras
from bpy.app.handlers import persistent

import fnmatch, re, os, sys
import shutil
import subprocess
import webbrowser

import pluginUtils
from pluginUtils.log import printLog
from pluginUtils.path import getAppManagerHost, getRoot, findExportedAssetPath

from . import utils

join = os.path.join
norm = os.path.normpath

from pluginUtils.manager import AppManagerConn

class V3DPanel():
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'

    COMPAT_ENGINES = ['CYCLES', 'BLENDER_EEVEE']

    @classmethod
    def poll(cls, context):

        if (cls.poll_datablock == 'clipping_plane' and context.object and
                context.object.type == 'EMPTY' and context.object.v3d.clipping_plane):
            return True

        elif (cls.poll_datablock == 'lightprobe' and context.object
                and context.object.type == 'LIGHT_PROBE' and context.object.data):
            # as for now only CUBEMAP lightprobes have custom v3d settings
            return context.object.data.type == 'CUBEMAP'

        elif (hasattr(context, cls.poll_datablock) and
                getattr(context, cls.poll_datablock) and
                context.scene.render.engine in cls.COMPAT_ENGINES):
            return True

        else:
            return False


class V3D_PT_RenderSettings(bpy.types.Panel, V3DPanel):
    """Located on render panel"""
    bl_context = 'render'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'scene'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        v3d_export = bpy.data.scenes[0].v3d_export

        row = layout.row()
        row.prop(v3d_export, 'copyright')

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
        row.prop(v3d_export, 'compress_textures')

        row = layout.row()
        row.prop(v3d_export, 'optimize_attrs')

        row = layout.row()
        row.prop(v3d_export, 'aa_method')

        row = layout.row()
        row.prop(v3d_export, 'use_hdr')

        row = layout.row()
        row.prop(v3d_export, 'use_oit')

        row = layout.row()
        row.prop(v3d_export, 'ibl_environment_mode')

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



class V3D_PT_RenderSettingsAnimation(bpy.types.Panel, V3DPanel):
    bl_label = 'Animation'
    bl_parent_id = 'V3D_PT_RenderSettings'

    poll_datablock = 'scene'

    def draw_header(self, context):
        v3d_export = bpy.data.scenes[0].v3d_export
        self.layout.prop(v3d_export, 'export_animations', text='')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        v3d_export = bpy.data.scenes[0].v3d_export
        layout.active = v3d_export.export_animations

        row = layout.row()
        row.prop(v3d_export, 'export_frame_range')
        row = layout.row()
        row.prop(v3d_export, 'export_move_keyframes')
        row = layout.row()
        row.prop(v3d_export, 'bake_armature_actions')



class V3D_PT_RenderSettingsShadows(bpy.types.Panel, V3DPanel):
    bl_label = 'Shadows'
    bl_parent_id = 'V3D_PT_RenderSettings'

    poll_datablock = 'scene'

    def draw_header(self, context):
        v3d_export = bpy.data.scenes[0].v3d_export
        self.layout.prop(v3d_export, 'use_shadows', text='')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        v3d_export = bpy.data.scenes[0].v3d_export
        layout.active = v3d_export.use_shadows

        row = layout.row()
        row.prop(v3d_export, 'shadow_map_type')

        row = layout.row()
        row.prop(v3d_export, 'shadow_map_side')

        row = layout.row()
        row.prop(v3d_export, 'esm_distance_scale')
        row.active = v3d_export.shadow_map_type == 'ESM'


class V3D_PT_RenderSettingsOutline(bpy.types.Panel, V3DPanel):
    bl_label = 'Outline Effect'
    bl_parent_id = 'V3D_PT_RenderSettings'
    bl_options = {'DEFAULT_CLOSED'}

    poll_datablock = 'scene'

    def draw_header(self, context):
        outline = context.scene.v3d.outline
        self.layout.prop(outline, 'enabled', text='')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        outline = context.scene.v3d.outline
        outlineActive = outline.enabled

        layout.active = outlineActive

        row = layout.row()
        row.prop(outline, 'edge_strength')
        row = layout.row()
        row.prop(outline, 'edge_glow')
        row = layout.row()
        row.prop(outline, 'edge_thickness')
        row = layout.row()
        row.prop(outline, 'pulse_period')
        row = layout.row()
        row.prop(outline, 'visible_edge_color')
        row = layout.row()
        row.prop(outline, 'hidden_edge_color')
        row = layout.row()
        row.prop(outline, 'render_hidden_edge')


class V3D_PT_RenderSettingsCollections(bpy.types.Panel, V3DPanel):
    bl_label = 'Export Collections'
    bl_parent_id = 'V3D_PT_RenderSettings'

    poll_datablock = 'scene'

    def draw(self, context):
        layout = self.layout
        layout.template_list('COLLECTION_UL_export', '', bpy.data,
                'collections', context.scene.v3d_export, 'collections_exported_idx', rows=4)


class V3D_PT_WorldSettings(bpy.types.Panel, V3DPanel):
    bl_context = 'world'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'world'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        world = context.world

        row = layout.row()
        row.prop(world.v3d, 'dithering')


class V3D_PT_ObjectSettings(bpy.types.Panel, V3DPanel):
    bl_context = 'object'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'object'

    def draw(self, context):
        pass


class V3D_PT_ObjectSettingsAnimation(bpy.types.Panel, V3DPanel):
    bl_label = 'Animation'
    bl_parent_id = 'V3D_PT_ObjectSettings'

    poll_datablock = 'object'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        v3d = context.object.v3d

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


class V3D_PT_ObjectSettingsRendering(bpy.types.Panel, V3DPanel):
    bl_label = 'Rendering'
    bl_parent_id = 'V3D_PT_ObjectSettings'

    poll_datablock = 'object'

    @classmethod
    def poll(cls, context):
        return (super().poll(context) and
                context.object.type in ['MESH', 'CURVE', 'SURFACE', 'META', 'FONT'])

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        obj = context.object
        v3d = obj.v3d

        row = layout.row()
        row.prop(v3d, 'render_order')

        row = layout.row()
        row.prop(v3d, 'frustum_culling')

        row = layout.row()
        row.prop(v3d, 'use_shadows')

        row = layout.row()
        row.prop(v3d, 'hidpi_compositing')

        if obj.parent and obj.parent.type == 'CAMERA':
            if obj.parent.data.type == 'ORTHO':
                row = layout.row()
                row.prop(v3d, 'fix_ortho_zoom')


class V3D_PT_ObjectSettingsChildRendering(bpy.types.Panel, V3DPanel):
    bl_label = 'Child Rendering'
    bl_parent_id = 'V3D_PT_ObjectSettings'

    poll_datablock = 'object'

    @classmethod
    def poll(cls, context):
        return (super().poll(context) and not
                context.object.type in ['MESH', 'CURVE', 'SURFACE', 'META', 'FONT'])

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        v3d = context.object.v3d

        row = layout.row()
        row.prop(v3d, 'hidpi_compositing')


class V3D_PT_ObjectSettingsVisibilityBreakpoints(bpy.types.Panel, V3DPanel):
    bl_label = 'Visibility Breakpoints'
    bl_parent_id = 'V3D_PT_ObjectSettings'

    poll_datablock = 'object'

    def draw_header(self, context):
        v3d = context.object.v3d
        self.layout.prop(v3d, 'canvas_break_enabled', text='')

    def draw(self, context):
        layout = self.layout

        v3d = context.object.v3d

        brkpnts = v3d.canvas_break_enabled

        row = layout.row()
        row.active = brkpnts
        row.prop(v3d, 'canvas_break_min_width')
        row.prop(v3d, 'canvas_break_max_width')

        row = layout.row()
        row.active = brkpnts
        row.prop(v3d, 'canvas_break_min_height')
        row.prop(v3d, 'canvas_break_max_height')

        split = layout.split()
        split.active = brkpnts
        col = split.column()
        col.alignment = 'RIGHT'
        col.label(text='Orientation')
        col = split.column()
        col.prop(v3d, 'canvas_break_orientation', text='')


class V3D_PT_ObjectSettingsFitCameraEdge(bpy.types.Panel, V3DPanel):
    bl_label = 'Fit to Camera Edge'
    bl_parent_id = 'V3D_PT_ObjectSettings'

    poll_datablock = 'object'

    @classmethod
    def poll(cls, context):
        return (super().poll(context) and
                context.object.parent and context.object.parent.type == 'CAMERA')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        v3d = context.object.v3d

        layout.prop(v3d, 'canvas_fit_x')
        layout.prop(v3d, 'canvas_fit_y')
        layout.prop(v3d, 'canvas_fit_shape')
        layout.prop(v3d, 'canvas_fit_offset')


class V3D_PT_CameraSettings(bpy.types.Panel, V3DPanel):
    bl_context = 'data'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'camera'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        camera = context.camera
        v3d = camera.v3d

        row = layout.row()
        row.prop(v3d, 'controls')

        if v3d.controls == 'FIRST_PERSON':
            row = layout.row()
            row.prop(v3d, 'fps_collision_material')

            row = layout.row()
            row.prop(v3d, 'fps_gaze_level')

            row = layout.row()
            row.prop(v3d, 'fps_story_height')

            row = layout.row()
            row.prop(v3d, 'enable_pointer_lock')

        row = layout.row()
        row.active = (v3d.controls != 'NONE')
        row.prop(v3d, 'enable_pan')

        row = layout.row()
        row.active = (v3d.controls != 'NONE')
        row.prop(v3d, 'rotate_speed')

        row = layout.row()
        row.active = (v3d.controls != 'NONE')
        row.prop(v3d, 'move_speed')


class V3D_PT_CameraSettingsTarget(bpy.types.Panel, V3DPanel):
    bl_context = 'data'
    bl_label = 'Target Object / Point'
    bl_parent_id = 'V3D_PT_CameraSettings'

    poll_datablock = 'camera'

    @classmethod
    def poll(cls, context):
        return (super().poll(context) and
                context.camera.v3d.controls == 'ORBIT')

    def draw(self, context):
        layout = self.layout

        camera = context.camera
        v3d = camera.v3d

        split = layout.split(factor=0.5)

        column = split.column()
        column.prop(v3d, 'orbit_target', text='Manual')
        column.enabled = v3d.orbit_target_object is None

        column = split.column()
        column.label(text='From Object:')
        column.prop(v3d, 'orbit_target_object', text='')

        column.operator(V3D_OT_orbit_camera_target_from_cursor.bl_idname, text='From Cursor')

        layout.operator(V3D_OT_orbit_camera_update_view.bl_idname, text='Update View')

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
    bl_context = 'data'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'light'

    def draw(self, context):
        pass


class V3D_PT_LightSettingsShadow(bpy.types.Panel, V3DPanel):
    bl_context = 'data'
    bl_label = 'Shadows'
    bl_parent_id = 'V3D_PT_LightSettings'

    poll_datablock = 'light'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        light = context.light
        type = light.type
        shadow = light.v3d.shadow

        row = layout.row()
        row.active = (context.scene.v3d_export.shadow_map_type
                not in ['BASIC', 'BILINEAR'])
        row.prop(shadow, 'radius', text='Blur Radius')

        row = layout.row()
        row.active = context.scene.v3d_export.shadow_map_type == 'ESM'
        row.prop(shadow, 'esm_exponent', text='ESM Bias')


class V3D_PT_CurveSettings(bpy.types.Panel, V3DPanel):
    bl_context = 'data'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'curve'

    @classmethod
    def poll(cls, context):
        return (super().poll(context) and not
                isinstance(getattr(context, cls.poll_datablock), bpy.types.TextCurve))

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

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
    bl_context = 'data'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'mesh'

    def draw(self, context):
        pass


class V3D_PT_MeshSettingsLineRendering(bpy.types.Panel, V3DPanel):
    bl_context = 'data'
    bl_label = 'Line Rendering'
    bl_parent_id = 'V3D_PT_MeshSettings'

    poll_datablock = 'mesh'

    def draw_header(self, context):
        v3d = context.mesh.v3d
        self.layout.prop(v3d.line_rendering_settings, 'enable', text='')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        v3d = context.mesh.v3d

        layout.active = getattr(v3d.line_rendering_settings, 'enable') is True

        row = layout.row()
        row.prop(v3d.line_rendering_settings, 'color')

        row = layout.row()
        row.prop(v3d.line_rendering_settings, 'width')


class V3D_PT_LightProbeSettings(bpy.types.Panel, V3DPanel):
    bl_context = 'data'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'lightprobe'

    def draw(self, context):
        pass


class V3D_PT_LightProbeSettingsCustomInfluence(bpy.types.Panel, V3DPanel):
    bl_context = 'data'
    bl_label = 'Custom Influence'
    bl_parent_id = 'V3D_PT_LightProbeSettings'

    poll_datablock = 'lightprobe'

    def draw_header(self, context):
        v3d = context.lightprobe.v3d
        self.layout.prop(v3d, 'use_custom_influence', text='')

    def draw(self, context):
        layout = self.layout

        v3d = context.lightprobe.v3d
        layout.active = getattr(v3d, 'use_custom_influence') is True

        row = layout.row(align=True)
        row.use_property_split = True
        row.prop(v3d, 'influence_collection')
        row.prop(v3d, 'invert_influence_collection', text='', icon='ARROW_LEFTRIGHT')


class V3D_PT_ClippingPlaneSettings(bpy.types.Panel, V3DPanel):
    bl_context = 'data'
    bl_label = 'Verge3D Clipping Plane'

    poll_datablock = 'clipping_plane'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        plane = context.object

        row = layout.row()
        row.prop(plane.v3d, 'clipping_plane_collection')

        row = layout.row()
        row.prop(plane.v3d, 'clipping_plane_negated')

        row = layout.row()
        row.prop(plane.v3d, 'clipping_plane_shadows')

        row = layout.row()
        row.prop(plane.v3d, 'clipping_plane_union')


class V3D_PT_ClippingPlaneSettingsCrossSection(bpy.types.Panel, V3DPanel):
    bl_context = 'data'
    bl_label = 'Filled Cross-Section'
    bl_parent_id = 'V3D_PT_ClippingPlaneSettings'

    poll_datablock = 'clipping_plane'

    def draw_header(self, context):
        layout = self.layout

        plane = context.object
        layout.active = plane.v3d.clipping_plane_cross_section and plane.v3d.clipping_plane_union

        layout.prop(plane.v3d, 'clipping_plane_cross_section', text='')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        plane = context.object
        layout.active = plane.v3d.clipping_plane_cross_section and plane.v3d.clipping_plane_union

        row = layout.row()
        row.prop(plane.v3d, 'clipping_plane_color', text='Color')

        row = layout.row()
        row.prop(plane.v3d, 'clipping_plane_render_side', text='Render Side')

        row = layout.split()
        row.prop(plane.v3d, 'clipping_plane_size', text='Plane Size')


class V3D_PT_MaterialSettings(bpy.types.Panel, V3DPanel):
    bl_context = 'material'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'material'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        material = context.material

        blend_back = utils.matHasBlendBackside(material)

        if blend_back:
            row = layout.row()
            row.label(text='Overridden by Settings → Show Backface', icon='INFO')

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
                or isinstance(node, bpy.types.ShaderNodeTexEnvironment)
                or isinstance(node, bpy.types.ShaderNodeTexNoise)
        )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True

        node = context.active_node

        if isinstance(node, bpy.types.ShaderNodeTexImage):

            row = layout.row()
            row.label(text='Anisotropic Filtering:')

            row = layout.row()
            row.prop(node.v3d, 'anisotropy', text='Ratio')

            image = node.image
            if image:
                row = layout.row()
                row.label(text='Texture Compression:')

                row = layout.row()
                row.prop(image.v3d, 'compression_method', text='Method')

        elif isinstance(node, bpy.types.ShaderNodeTexEnvironment):
            image = node.image
            if image:
                row = layout.row()
                row.label(text='Texture Compression:')

                row = layout.row()
                row.prop(image.v3d, 'compression_method', text='Hint')

        elif isinstance(node, bpy.types.ShaderNodeTexNoise):

            row = layout.row()
            row.label(text='Noise Parameters:')

            row = layout.row()
            row.prop(node.v3d, 'falloff_factor')

            row = layout.row()
            row.prop(node.v3d, 'dispersion_factor')


def execBrowser(url):
    try:
        webbrowser.open(url)
    except BaseException:
        print("Failed to open URL: " + url)

class V3D_OT_orbit_camera_target_from_cursor(bpy.types.Operator):
    bl_idname = 'camera.v3d_orbit_camera_target_from_cursor'
    bl_label = 'From Cursor'
    bl_description = 'Update target coordinates from cursor position'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        context.object.data.v3d.orbit_target_object = None
        context.object.data.v3d.orbit_target = bpy.context.scene.cursor.location
        utils.updateOrbitCameraView(context.object, context.scene)
        return {'FINISHED'}

class V3D_OT_orbit_camera_update_view(bpy.types.Operator):
    bl_idname = 'camera.v3d_orbit_camera_update_view'
    bl_label = 'Update View'
    bl_description = 'Update view for the orbit camera'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        utils.updateOrbitCameraView(context.object, context.scene)
        return {'FINISHED'}

class V3D_OT_sneak_peek(bpy.types.Operator):
    bl_idname = 'view3d.v3d_sneak_peek'
    bl_label = 'Sneak Peek'
    bl_description = 'Export to temporary location and preview the scene in Verge3D'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        # always try to run server before sneak peek
        # fixes several issues with closed Blender
        AppManagerConn.start(getRoot(), 'BLENDER', True)

        prevDir = AppManagerConn.getPreviewDir(True)

        bpy.ops.export_scene.v3d_gltf(filepath=join(prevDir, 'sneak_peek.gltf'),
                                export_sneak_peek = True)

        execBrowser(getAppManagerHost() +
                'player/player.html?load=/sneak_peek/sneak_peek.gltf')

        return {'FINISHED'}

class V3D_OT_app_manager(bpy.types.Operator):
    bl_idname = 'view3d.v3d_app_manager'
    bl_label = 'Open App Manager'
    bl_description = 'Open Verge3D App Manager'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        AppManagerConn.start(getRoot(), 'BLENDER', True)
        execBrowser(getAppManagerHost())
        return {"FINISHED"}


@persistent
def loadHandler(dummy):
    printLog('INFO', 'Reexporting ' + V3D_OT_reexport_all.currBlend)

    exported = filepath=V3D_OT_reexport_all.currGLTF

    if os.path.splitext(exported)[1] == '.gltf':
        bpy.ops.export_scene.v3d_gltf(filepath=exported)
    elif os.path.splitext(exported)[1] == '.glb':
        bpy.ops.export_scene.v3d_glb(filepath=exported)
    else:
        printLog('ERROR', 'Invalid exported extension')

    V3D_OT_reexport_all.reexportNext()

class V3D_OT_reexport_all(bpy.types.Operator):
    bl_idname = 'wm.v3d_reexport_all'
    bl_label = 'Reexport all Verge3D assets'
    bl_description = 'Reexport all glTF files inside Verge3D SDK'

    exported = []
    currBlend = None
    currGLTF = None

    debugForceGLB = False

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

        # NOTE: fixes crashes with copy.deepcopy()
        sys.setrecursionlimit(10000)

        for root, dirs, files in os.walk(apps):
            for name in files:
                if fnmatch.fnmatch(name, '*.blend'):
                    blendpath = norm(join(root, name))

                    # use file utility to check .blend version
                    if sys.platform.startswith('linux'):
                        fileinfo = subprocess.check_output(['file', '--uncompress', blendpath]).decode()
                        verStr = re.search('\d\.\d\d', fileinfo).group(0)
                        ver = tuple([int(n) for n in verStr.split('.')]) + (0,)

                        # ignore incompatible blender files
                        if ver < (2, 80, 0) or ver > bpy.app.version:
                            blendRel = os.path.relpath(blendpath, apps)
                            printLog('WARNING', f'Ignoring {blendRel}, saved in Blender {ver[0]}.{ver[1]}')
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
                        if self.__class__.debugForceGLB:
                            gltfpath = os.path.splitext(gltfpath)[0] + '.glb'
                        self.__class__.exported.append((blendpath, gltfpath))
                        self.__class__.exported.sort()

        self.__class__.reexportNext()

        return {'FINISHED'}

def btnSneakPeek(self, context):
    self.layout.operator(V3D_OT_sneak_peek.bl_idname, text='Sneak Peek', icon='HIDE_OFF')

def btnAppManager(self, context):
    self.layout.operator(V3D_OT_app_manager.bl_idname, text='App Manager', icon='WORDWRAP_ON')

def menuUserManual(self, context):
    if context.scene.render.engine in V3DPanel.COMPAT_ENGINES:
        self.layout.separator()
        self.layout.operator('wm.url_open', text='Verge3D User Manual', icon='URL').url = AppManagerConn.getManualURL()

def menuReexportAll(self, context):
    self.layout.separator()
    self.layout.operator(V3D_OT_reexport_all.bl_idname, icon='TOOL_SETTINGS')


class VIEW3D_MT_verge3d_add(bpy.types.Menu):
    bl_idname = 'VIEW3D_MT_verge3d_add'
    bl_label = 'Verge3D'
    bl_options = {'INTERNAL'}

    def draw(self, context):
        self.layout.operator('object.add_clipping_plane', icon='AXIS_TOP')


class V3D_OT_add_clipping_plane(bpy.types.Operator, bpy_extras.object_utils.AddObjectHelper):
    bl_idname = 'object.add_clipping_plane'
    bl_label = 'Clipping Plane'
    bl_options = {'REGISTER', 'UNDO', 'PRESET', 'INTERNAL'}
    bl_description = 'Construct clipping plane'

    def execute(self, context):

        obj = bpy.data.objects.new('ClippingPlane', None)
        context.view_layer.active_layer_collection.collection.objects.link(obj)
        context.view_layer.objects.active = obj
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)

        obj.empty_display_type = 'ARROWS'
        obj.v3d.clipping_plane = True

        return {'FINISHED'}

def menuVerge3dAdd(self, context):
    self.layout.menu(VIEW3D_MT_verge3d_add.bl_idname, icon='SOLO_ON')

def register():

    bpy.utils.register_class(VIEW3D_MT_verge3d_add)
    bpy.utils.register_class(V3D_OT_add_clipping_plane)

    bpy.types.VIEW3D_MT_add.append(menuVerge3dAdd)
    bpy.types.TOPBAR_MT_help.append(menuUserManual)

    if pluginUtils.debug:
        bpy.types.TOPBAR_MT_render.append(menuReexportAll)

    bpy.utils.register_class(V3D_PT_RenderSettings)
    bpy.utils.register_class(V3D_PT_RenderSettingsAnimation)
    bpy.utils.register_class(V3D_PT_RenderSettingsShadows)
    bpy.utils.register_class(V3D_PT_RenderSettingsOutline)
    bpy.utils.register_class(V3D_PT_RenderSettingsCollections)
    bpy.utils.register_class(V3D_PT_WorldSettings)
    bpy.utils.register_class(V3D_PT_ObjectSettings)
    bpy.utils.register_class(V3D_PT_ObjectSettingsAnimation)
    bpy.utils.register_class(V3D_PT_ObjectSettingsRendering)
    bpy.utils.register_class(V3D_PT_ObjectSettingsChildRendering)
    bpy.utils.register_class(V3D_PT_ObjectSettingsVisibilityBreakpoints)
    bpy.utils.register_class(V3D_PT_ObjectSettingsFitCameraEdge)
    bpy.utils.register_class(V3D_PT_CameraSettings)
    bpy.utils.register_class(V3D_PT_CameraSettingsTarget)
    bpy.utils.register_class(V3D_PT_LightSettings)
    bpy.utils.register_class(V3D_PT_LightSettingsShadow)
    bpy.utils.register_class(V3D_PT_ClippingPlaneSettings)
    bpy.utils.register_class(V3D_PT_ClippingPlaneSettingsCrossSection)
    bpy.utils.register_class(V3D_PT_MaterialSettings)
    bpy.utils.register_class(V3D_PT_CurveSettings)
    bpy.utils.register_class(V3D_PT_MeshSettings)
    bpy.utils.register_class(V3D_PT_MeshSettingsLineRendering)
    bpy.utils.register_class(V3D_PT_NodeSettings)
    bpy.utils.register_class(V3D_PT_LightProbeSettings)
    bpy.utils.register_class(V3D_PT_LightProbeSettingsCustomInfluence)

    bpy.utils.register_class(V3D_OT_orbit_camera_target_from_cursor)
    bpy.utils.register_class(V3D_OT_orbit_camera_update_view)
    bpy.utils.register_class(V3D_OT_reexport_all)

    bpy.utils.register_class(COLLECTION_UL_export)

    if AppManagerConn.isAvailable(getRoot()):
        bpy.utils.register_class(V3D_OT_sneak_peek)
        bpy.utils.register_class(V3D_OT_app_manager)
        bpy.types.VIEW3D_HT_header.append(btnSneakPeek)
        bpy.types.VIEW3D_HT_header.append(btnAppManager)


def unregister():

    if AppManagerConn.isAvailable(getRoot()):
        bpy.types.VIEW3D_HT_header.remove(btnSneakPeek)
        bpy.types.VIEW3D_HT_header.remove(btnAppManager)
        bpy.utils.unregister_class(V3D_OT_sneak_peek)
        bpy.utils.unregister_class(V3D_OT_app_manager)

    bpy.utils.unregister_class(V3D_PT_NodeSettings)
    bpy.utils.unregister_class(V3D_PT_ClippingPlaneSettings)
    bpy.utils.unregister_class(V3D_PT_ClippingPlaneSettingsCrossSection)
    bpy.utils.unregister_class(V3D_PT_MaterialSettings)
    bpy.utils.unregister_class(V3D_PT_LightSettings)
    bpy.utils.unregister_class(V3D_PT_LightSettingsShadow)
    bpy.utils.unregister_class(V3D_PT_CurveSettings)
    bpy.utils.unregister_class(V3D_PT_CameraSettings)
    bpy.utils.unregister_class(V3D_PT_CameraSettingsTarget)
    bpy.utils.unregister_class(V3D_PT_ObjectSettings)
    bpy.utils.unregister_class(V3D_PT_ObjectSettingsAnimation)
    bpy.utils.unregister_class(V3D_PT_ObjectSettingsRendering)
    bpy.utils.unregister_class(V3D_PT_ObjectSettingsChildRendering)
    bpy.utils.unregister_class(V3D_PT_ObjectSettingsVisibilityBreakpoints)
    bpy.utils.unregister_class(V3D_PT_ObjectSettingsFitCameraEdge)
    bpy.utils.unregister_class(V3D_PT_WorldSettings)
    bpy.utils.unregister_class(V3D_PT_RenderSettings)
    bpy.utils.unregister_class(V3D_PT_RenderSettingsAnimation)
    bpy.utils.unregister_class(V3D_PT_RenderSettingsShadows)
    bpy.utils.unregister_class(V3D_PT_RenderSettingsOutline)
    bpy.utils.unregister_class(V3D_PT_RenderSettingsCollections)
    bpy.utils.unregister_class(V3D_PT_MeshSettings)
    bpy.utils.unregister_class(V3D_PT_MeshSettingsLineRendering)
    bpy.utils.unregister_class(V3D_PT_LightProbeSettings)
    bpy.utils.unregister_class(V3D_PT_LightProbeSettingsCustomInfluence)

    bpy.utils.unregister_class(V3D_OT_reexport_all)
    bpy.utils.unregister_class(V3D_OT_orbit_camera_target_from_cursor)
    bpy.utils.unregister_class(V3D_OT_orbit_camera_update_view)

    bpy.utils.unregister_class(COLLECTION_UL_export)

    if pluginUtils.debug:
        bpy.types.TOPBAR_MT_render.remove(menuReexportAll)

    bpy.types.TOPBAR_MT_help.remove(menuUserManual)
    bpy.types.VIEW3D_MT_add.remove(menuVerge3dAdd)

    bpy.utils.unregister_class(V3D_OT_add_clipping_plane)
    bpy.utils.unregister_class(VIEW3D_MT_verge3d_add)
