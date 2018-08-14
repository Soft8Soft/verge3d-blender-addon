import bpy
from bpy.app.handlers import persistent

import fnmatch, os
import shutil
import webbrowser

import verge3d

from .gltf2_debug import *

join = os.path.join
norm = os.path.normpath

APP_MANAGER_HOST="http://localhost:8668/"
MANUAL_URL="https://www.soft8soft.com/docs/"

class V3DPanel():
    COMPAT_ENGINES = ['VERGE3D', 'CYCLES']

    @classmethod
    def poll(cls, context):

        if (hasattr(context, cls.poll_datablock) and
                getattr(context, cls.poll_datablock) and 
                context.scene.render.engine in cls.COMPAT_ENGINES):
            return True
        else:
            return False

class V3DExportSettingsPanel(bpy.types.Panel, V3DPanel):
    """Located on render panel"""
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    bl_label = 'Verge3D Export Settings'

    poll_datablock = 'scene'

    def draw(self, context):
        layout = self.layout

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
        row.prop(v3d_export, 'use_shadows')

        row = layout.row()
        row.active = v3d_export.use_shadows
        row.prop(v3d_export, 'shadow_map_type')

        row = layout.row()
        row.active = v3d_export.use_shadows
        row.prop(v3d_export, 'shadow_map_side')

class V3DRenderLayerSettingsPanel(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render_layer'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'scene'

    def draw(self, context):
        layout = self.layout

        scene = context.scene

        row = layout.row()
        row.label('Export Layers:')

        row = layout.row()
        row.prop(scene.v3d, 'export_layers', text='')

class V3DSceneSettingsPanel(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'scene'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'scene'

    def draw(self, context):
        layout = self.layout

        scene = context.scene

        outline = scene.v3d.outline

        row = layout.row()
        row.label('Outline:')

        row = layout.row()
        row.prop(outline, 'enabled')

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


class V3DObjectSettingsPanel(bpy.types.Panel, V3DPanel):
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
        row.label('Animation:')

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
        row.label('Rendering:')

        row = layout.row()
        row.prop(v3d, 'render_order')

        row = layout.row()
        row.prop(v3d, 'frustum_culling')

class V3DCameraSettingsPanel(bpy.types.Panel, V3DPanel):
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
            row.label('Vertical Rotation Limits:')

            row = layout.row()
            row.prop(v3d, 'orbit_min_polar_angle')
            row.prop(v3d, 'orbit_max_polar_angle')


            row = layout.row()
            row.label('Horizontal Rotation Limits:')

            row = layout.row()
            row.prop(v3d, 'orbit_min_azimuth_angle')
            row.prop(v3d, 'orbit_max_azimuth_angle')

class V3DLampSettingsPanel(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'lamp'

    def draw(self, context):
        layout = self.layout

        lamp = context.lamp
        type = lamp.type
        shadow = lamp.v3d.shadow

        row = layout.row()
        row.label('Shadow:')

        if type == 'POINT' or type == 'SPOT' or type == 'SUN':
            row = layout.row()
            row.prop(lamp, 'shadow_method', expand=True)
            
            if lamp.shadow_method != 'NOSHADOW':
                row = layout.row()
                row.prop(shadow, 'map_size')
                row = layout.row()
                if type == 'SUN':
                    row.prop(shadow, 'camera_size')
                else:
                    row.prop(shadow, 'camera_fov')

                row = layout.row()
                row.prop(shadow, 'camera_near')
                row.prop(shadow, 'camera_far')

                row = layout.row()
                row.prop(shadow, 'radius')
                row.prop(shadow, 'bias')
        else:
            row = layout.row()
            row.label('Not available for this lamp type')

class V3DMaterialTransparencyPanel(bpy.types.Panel, V3DPanel):
    """Inspired by MATERIAL_PT_transp_game"""

    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'material'
    bl_label = "Transparency"

    poll_datablock = 'material'

    def draw_header(self, context):
        mat = context.material
        self.layout.prop(mat, "use_transparency", text="")

    def draw(self, context):
        layout = self.layout
        mat = context.material


        layout.active = mat.use_transparency

        row = layout.row()
        row.prop(mat, "transparency_method", expand=True)

        if mat.active_node_material:
            mat = mat.active_node_material

        layout.prop(mat, "alpha")
        layout.prop(mat, "specular_alpha", text="Specular")

class V3DCurveSettingsPanel(bpy.types.Panel, V3DPanel):
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

class V3DMeshSettingsPanel(bpy.types.Panel, V3DPanel):
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

class V3DMaterialSettingsPanel(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'material'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'material'

    def draw(self, context):
        layout = self.layout

        material = context.material

        row = layout.row()
        row.prop(material.game_settings, 'use_backface_culling')

        row = layout.row()
        row.active = material.use_transparency
        row.prop(material.v3d, 'alpha_add')

class V3DTextureSettingsPanel(bpy.types.Panel, V3DPanel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'texture'
    bl_label = 'Verge3D Settings'

    poll_datablock = 'texture'

    def draw(self, context):
        layout = self.layout

        texture = context.texture

        row = layout.row()
        row.label('Anisotropic Filtering:')

        row = layout.row()
        row.prop(texture.v3d, 'anisotropy', 'Ratio')

class V3DShaderNodeTexImageSettingsPanel(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'texture'
    bl_label = 'Verge3D Settings'

    @classmethod
    def poll(cls, context):
        node = context.texture_node
        return node and context.scene.render.engine == 'CYCLES'

    def draw(self, context):
        layout = self.layout

        texture = context.texture_node

        row = layout.row()
        row.label('Anisotropic Filtering:')

        row = layout.row()
        row.prop(texture.v3d, 'anisotropy', 'Ratio')

def exec_browser(url):
    # always try to run server before starting browers
    # fixes several issues with closed Blender
    verge3d.V3DServer.start()

    try:
        webbrowser.open(url)
    except BaseException:
        print("Failed to open URL: " + url)

class V3DAppManager(bpy.types.Operator):
    bl_idname = "v3d.app_manager"
    bl_label = "Open App Manager"
    bl_description = "Open Verge3D App Manager"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        exec_browser(APP_MANAGER_HOST)
        return {"FINISHED"}


class V3DSneakPeek(bpy.types.Operator):
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
    printLog('INFO', 'Reexporting ' + V3DReexportAll.currBlend)
    bpy.ops.export_scene.v3d_gltf(filepath=V3DReexportAll.currGLTF)

    V3DReexportAll.reexportNext()

class V3DReexportAll(bpy.types.Operator):
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

    bpy.types.INFO_MT_help.append(v3d_menu_help)

    bpy.utils.register_class(V3DExportSettingsPanel)
    bpy.utils.register_class(V3DRenderLayerSettingsPanel)
    bpy.utils.register_class(V3DSceneSettingsPanel)
    bpy.utils.register_class(V3DObjectSettingsPanel)
    bpy.utils.register_class(V3DCameraSettingsPanel)
    bpy.utils.register_class(V3DLampSettingsPanel)
    bpy.utils.register_class(V3DMaterialTransparencyPanel)
    bpy.utils.register_class(V3DCurveSettingsPanel)
    bpy.utils.register_class(V3DMaterialSettingsPanel)
    bpy.utils.register_class(V3DTextureSettingsPanel)
    bpy.utils.register_class(V3DShaderNodeTexImageSettingsPanel)
    bpy.utils.register_class(V3DMeshSettingsPanel)

    bpy.utils.register_class(V3DAppManager)
    bpy.utils.register_class(V3DSneakPeek)
    bpy.utils.register_class(V3DReexportAll)

def unregister():

    bpy.utils.unregister_class(V3DShaderNodeTexImageSettingsPanel)
    bpy.utils.unregister_class(V3DTextureSettingsPanel)
    bpy.utils.unregister_class(V3DMaterialSettingsPanel)
    bpy.utils.unregister_class(V3DMaterialTransparencyPanel)
    bpy.utils.unregister_class(V3DLampSettingsPanel)
    bpy.utils.unregister_class(V3DCurveSettingsPanel)
    bpy.utils.unregister_class(V3DCameraSettingsPanel)
    bpy.utils.unregister_class(V3DObjectSettingsPanel)
    bpy.utils.unregister_class(V3DSceneSettingsPanel)
    bpy.utils.unregister_class(V3DRenderLayerSettingsPanel)
    bpy.utils.unregister_class(V3DExportSettingsPanel)
    bpy.utils.unregister_class(V3DMeshSettingsPanel)

    bpy.utils.unregister_class(V3DReexportAll)
    bpy.utils.unregister_class(V3DSneakPeek)
    bpy.utils.unregister_class(V3DAppManager)

    bpy.types.VIEW3D_HT_header.remove(v3d_app_manager)
    bpy.types.VIEW3D_HT_header.remove(v3d_sneak_peek)
