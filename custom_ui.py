# Copyright (c) 2017-2018 Soft8Soft LLC
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

import verge3d

from .gltf2_debug import *
from . import utils

join = os.path.join
norm = os.path.normpath

APP_MANAGER_HOST="http://localhost:8668/"
MANUAL_URL="https://www.soft8soft.com/docs/"

class V3DPanel():
    COMPAT_ENGINES = ['BLENDER_RENDER', 'CYCLES', 'BLENDER_EEVEE']

    @classmethod
    def poll(cls, context):

        if (hasattr(context, cls.poll_datablock) and
                getattr(context, cls.poll_datablock) and 
                context.scene.render.engine in cls.COMPAT_ENGINES):
            return True
        else:
            return False

    @classmethod
    def checkRenderInternal(cls, context):
        return context.scene.render.engine == 'BLENDER_RENDER'


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

        v3d_export = context.scene.v3d_export

        row = layout.row()
        row.prop(v3d_export, 'copyright')

        row = layout.row()
        row.prop(v3d_export, 'export_constraints')
    
        row = layout.row()
        row.prop(v3d_export, 'bake_modifiers')

        row = layout.row()
        row.prop(v3d_export, 'bake_armature_actions')

        row = layout.row()
        row.prop(v3d_export, 'bake_text')

        row = layout.row()
        row.prop(v3d_export, 'lzma_enabled')

        row = layout.row()
        row.prop(v3d_export, 'use_hdr')

        row = layout.row()
        row.prop(v3d_export, 'use_shadows')

        row = layout.row()
        row.active = v3d_export.use_shadows
        row.prop(v3d_export, 'shadow_map_type')

        row = layout.row()
        row.active = v3d_export.use_shadows
        row.prop(v3d_export, 'shadow_map_side')

        # postprocessing

        outline = context.scene.v3d.outline

        row = layout.row()
        row.label(text='Outline:')

        row = layout.row()
        row.prop(outline, 'enabled')

        outlineActive = outline.enabled

        row = layout.row()
        row.active = outlineActive
        row.prop(outline, 'edge_strength')
        row = layout.row()
        row.active = outlineActive
        row.prop(outline, 'edge_glow')
        row = layout.row()
        row.active = outlineActive
        row.prop(outline, 'edge_thickness')
        row = layout.row()
        row.active = outlineActive
        row.prop(outline, 'pulse_period')

        row = layout.row()
        row.active = outlineActive
        row.prop(outline, 'visible_edge_color')
        row = layout.row()
        row.active = outlineActive
        row.prop(outline, 'hidden_edge_color')

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

        row = layout.row()
        row.label(text='Rendering:')

        row = layout.row()
        row.prop(v3d, 'render_order')

        row = layout.row()
        row.prop(v3d, 'frustum_culling')

        if bpy.app.version >= (2,80,0):
            row = layout.row()
            row.prop(v3d, 'use_shadows')

            row = layout.row()
            row.prop(v3d, 'use_cast_shadows')

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

        row = layout.row()
        row.prop(v3d, 'enable_pan')
        
        row = layout.row()
        row.prop(v3d, 'rotate_speed')

        row = layout.row()
        row.prop(v3d, 'move_speed')
        
        if v3d.controls == 'ORBIT':
            col = layout.column()
            col.prop(v3d, 'orbit_target')

            row = layout.row()
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

    poll_datablock = 'light' if bpy.app.version >= (2,80,0) else 'lamp'

    def draw(self, context):
        layout = self.layout

        light = context.light if bpy.app.version >= (2,80,0) else context.lamp
        type = light.type
        shadow = light.v3d.shadow

        if bpy.app.version < (2,80,0):
            row = layout.row()
            row.label(text='Shadow:')

            if type == 'POINT' or type == 'SPOT' or type == 'SUN':

                if not super().checkRenderInternal(context):
                    row = layout.row()
                    row.prop(light, 'shadow_method', expand=True)

                shadowOn = light.shadow_method != 'NOSHADOW'

                row = layout.row()
                row.active = shadowOn
                row.prop(shadow, 'map_size')

                row = layout.row()
                row.active = shadowOn
                if type == 'SUN':
                    row.prop(shadow, 'camera_size')
                elif type == 'SPOT':
                    row.prop(shadow, 'camera_fov')

                row = layout.row()
                row.active = shadowOn
                row.prop(shadow, 'camera_near')
                row.prop(shadow, 'camera_far')

                row = layout.row()
                row.active = shadowOn
                row.prop(shadow, 'radius')
                row.prop(shadow, 'bias')
            else:
                row = layout.row()
                row.label(text='Not available for this light type')
        else:
            layout.active = light.use_shadow if type != 'HEMI' else False 

            if type == 'SUN' or type == 'AREA':
                row = layout.row()
                row.prop(shadow, 'camera_size', text='Shadow Size')


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

        if bpy.app.version < (2,80,0):

            row = layout.row()
            row.prop(material.game_settings, 'use_backface_culling')


            if not super().checkRenderInternal(context):
                row = layout.row()
                row.prop(material, "use_transparency")

                row = layout.row()
                row.active = material.use_transparency
                row.prop(material, "transparency_method", expand=True)

            row = layout.row()
            row.active = material.use_transparency
            row.prop(material.v3d, 'alpha_add')
        else:
            layout.use_property_split = True

            blend_back = utils.material_has_blend_backside(material)

            if blend_back:
                row = layout.row()
                row.label(text='Overridden by the "Options->Show Backside" option.', icon='INFO')
            
            row = layout.row()
            row.prop(material.v3d, 'render_side')
            row.active = not blend_back

            row = layout.row()
            row.prop(material.v3d, 'depth_write')
            row.active = not blend_back

        row = layout.row()
        row.prop(material.v3d, 'dithering')

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
        return node is not None and isinstance(node, bpy.types.ShaderNodeTexImage)

    def draw(self, context):
        layout = self.layout

        node = context.active_node

        row = layout.row()
        row.label(text='Anisotropic Filtering:')

        row = layout.row()
        row.prop(node.v3d, 'anisotropy', text='Ratio')


def exec_browser(url):
    # always try to run server before starting browers
    # fixes several issues with closed Blender
    verge3d.V3DServer.start()

    try:
        webbrowser.open(url)
    except BaseException:
        print("Failed to open URL: " + url)

class V3D_OT_AppManager(bpy.types.Operator):
    bl_idname = "v3d.app_manager"
    bl_label = "Open App Manager"
    bl_description = "Open Verge3D App Manager"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        exec_browser(APP_MANAGER_HOST)
        return {"FINISHED"}


class V3D_OT_SneakPeek(bpy.types.Operator):
    bl_idname = "v3d.sneak_peek"
    bl_label = "Sneak Peek"
    bl_description = "Export to temporary location and preview the scene in Verge3D"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        prev_dir = join(verge3d.get_root(), "player", "preview")

        if os.path.exists(prev_dir):
            shutil.rmtree(prev_dir)
        os.mkdir(prev_dir)

        bpy.ops.export_scene.v3d_gltf(
                filepath=join(prev_dir, "sneak_peek.gltf"), export_sneak_peek = True)

        exec_browser(APP_MANAGER_HOST +
                "player/player.html?load=preview/sneak_peek.gltf")

        return {"FINISHED"}

@persistent
def loadHandler(dummy):
    printLog('INFO', 'Reexporting ' + V3D_OT_ReexportAll.currBlend)
    bpy.ops.export_scene.v3d_gltf(filepath=V3D_OT_ReexportAll.currGLTF)

    V3D_OT_ReexportAll.reexportNext()

class V3D_OT_ReexportAll(bpy.types.Operator):
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
        apps = join(verge3d.get_root(), 'applications')

        for root, dirs, files in os.walk(apps):
            for name in files:
                if fnmatch.fnmatch(name, '*.blend'):
                    blendpath = norm(join(root, name))

                    # use file utility to check .blend version
                    if sys.platform.startswith('linux'):
                        fileinfo = subprocess.check_output(['file', '--uncompress', blendpath]).decode()
                        ver = re.search('\d\.\d\d', fileinfo).group(0)
                        verMaj, verMin = [int(n) for n in ver.split('.')]

                        # ignore uncompatible blender 2.80 files
                        if bpy.app.version < (2,80,0) and (verMaj > 2 or verMin >= 80):
                            continue

                    gltfpath = os.path.splitext(blendpath)[0] + '.gltf'

                    if os.path.exists(gltfpath):
                        self.__class__.exported.append((blendpath, gltfpath))

            self.__class__.reexportNext()


        return {"FINISHED"}

def v3d_sneak_peek(self, context):
    self.layout.operator('v3d.sneak_peek', text='Sneak Peek')

def v3d_app_manager(self, context):
    self.layout.operator('v3d.app_manager', text='App Manager')

def v3d_menu_help(self, context):

    if context.scene.render.engine in V3DPanel.COMPAT_ENGINES:
        self.layout.separator()
        self.layout.operator("wm.url_open", text="Verge3D User Manual", icon='URL').url = MANUAL_URL

def register():
    bpy.types.VIEW3D_HT_header.append(v3d_sneak_peek)
    bpy.types.VIEW3D_HT_header.append(v3d_app_manager)

    if bpy.app.version < (2,80,0):
        bpy.types.INFO_MT_help.append(v3d_menu_help)
    else:
        bpy.types.TOPBAR_MT_help.append(v3d_menu_help)

    bpy.utils.register_class(V3D_PT_RenderSettings)
    bpy.utils.register_class(V3D_PT_RenderLayerSettings)
    bpy.utils.register_class(V3D_PT_ObjectSettings)
    bpy.utils.register_class(V3D_PT_CameraSettings)
    bpy.utils.register_class(V3D_PT_LightSettings)
    bpy.utils.register_class(V3D_PT_MaterialSettings)
    bpy.utils.register_class(V3D_PT_CurveSettings)
    bpy.utils.register_class(V3D_PT_TextureSettings)
    bpy.utils.register_class(V3D_PT_MeshSettings)
    bpy.utils.register_class(V3D_PT_NodeSettings)

    bpy.utils.register_class(V3D_OT_AppManager)
    bpy.utils.register_class(V3D_OT_SneakPeek)
    bpy.utils.register_class(V3D_OT_ReexportAll)

def unregister():

    bpy.utils.unregister_class(V3D_PT_NodeSettings)
    bpy.utils.unregister_class(V3D_PT_TextureSettings)
    bpy.utils.unregister_class(V3D_PT_MaterialSettings)
    bpy.utils.unregister_class(V3D_PT_LightSettings)
    bpy.utils.unregister_class(V3D_PT_CurveSettings)
    bpy.utils.unregister_class(V3D_PT_CameraSettings)
    bpy.utils.unregister_class(V3D_PT_ObjectSettings)
    bpy.utils.unregister_class(V3D_PT_RenderLayerSettings)
    bpy.utils.unregister_class(V3D_PT_RenderSettings)
    bpy.utils.unregister_class(V3D_PT_MeshSettings)

    bpy.utils.unregister_class(V3D_OT_ReexportAll)
    bpy.utils.unregister_class(V3D_OT_SneakPeek)
    bpy.utils.unregister_class(V3D_OT_AppManager)

    bpy.types.VIEW3D_HT_header.remove(v3d_app_manager)
    bpy.types.VIEW3D_HT_header.remove(v3d_sneak_peek)
