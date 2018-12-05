# Copyright (c) 2017 The Khronos Group Inc.
# Modifications Copyright (c) 2017-2018 Soft8Soft LLC
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
import threading

from bpy.app.handlers import persistent

join = os.path.join

if 'bpy' in locals():
    import imp
    if 'gltf2_animate' in locals():
        imp.reload(gltf2_animate)
    if 'gltf2_create' in locals():
        imp.reload(gltf2_create)
    if 'gltf2_debug' in locals():
        imp.reload(gltf2_debug)
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

    if 'node_material_wrapper' in locals():
        imp.reload(node_material_wrapper)
    if 'utils' in locals():
        imp.reload(utils)


bl_info = {
    "name": "Verge3D",
    "description": "Verge3D glTF Exporter",
    "author": "Soft8Soft LLC",
    "version": (2, 9, 1),
    "blender": (2, 79, 0),
    "location": "File > Import-Export",
    "category": "Verge3D"
}

if bpy.app.version > (2, 80, 0):
    bl_info['blender'] = (2, 80, 0)

APP_MANAGER_HTTP_HOST="localhost:8668"

from bpy.props import (CollectionProperty,
                       StringProperty,
                       BoolProperty,
                       EnumProperty,
                       FloatProperty)

from bpy_extras.io_utils import (ExportHelper)

class ExportGLTF2_Base():

    export_embed_buffers = BoolProperty(
        name='Embed buffers',
        description='',
        default=False
    )

    export_embed_images = BoolProperty(
        name='Embed images',
        description='',
        default=False
    )

    export_strip = BoolProperty(
        name='Strip delimiters',
        description='',
        default=False
    )

    export_indices = EnumProperty(
        name='Maximum indices',
        items=(('UNSIGNED_BYTE', 'Unsigned Byte', ''),
        ('UNSIGNED_SHORT', 'Unsigned Short', ''),
        ('UNSIGNED_INT', 'Unsigned Integer', '')),
        default='UNSIGNED_INT'
    )

    export_force_indices = BoolProperty(
        name='Force maximum indices',
        description='',
        default=False
    )

    export_custom_props = BoolProperty(
        name='Export Custom Properties',
        description='',
        default=False
    )

    export_animations = BoolProperty(
        name='Export animations',
        description='',
        default=True
    )

    export_frame_range = BoolProperty(
        name='Export within playback range',
        description='',
        default=False
    )

    export_move_keyframes = BoolProperty(
        name='Keyframes start with 0',
        description='',
        default=True
    )

    export_force_sampling = BoolProperty(
        name='Force sample animations',
        description='',
        default=False
    )

    export_skins = BoolProperty(
        name='Export skinning',
        description='',
        default=True
    )

    export_morph = BoolProperty(
        name='Export morphing',
        description='',
        default=True
    )

    export_morph_normal = BoolProperty(
        name='Export morphing normals',
        description='',
        default=True
    )

    export_morph_tangent = BoolProperty(
        name='Export morphing tangents',
        description='',
        default=True
    )

    export_displacement = BoolProperty(
        name='Export KHR_materials_displacement',
        description='',
        default=False
    )

    export_sneak_peek = BoolProperty(
        name='Sneak Peek Mode',
        description='',
        default=False
    )

    def execute(self, context):
        from . import gltf2_export

        v3d_export = bpy.data.scenes[0].v3d_export
        
        # All custom export settings are stored in this container.
        export_settings = {}

        export_settings['gltf_filepath'] = bpy.path.ensure_ext(self.filepath, self.filename_ext)
        export_settings['gltf_filedirectory'] = os.path.dirname(export_settings['gltf_filepath']) + '/'

        export_settings['gltf_format'] = self.export_format
        export_settings['gltf_copyright'] = v3d_export.copyright
        export_settings['gltf_use_shadows'] = v3d_export.use_shadows
        export_settings['gltf_shadow_map_type'] = v3d_export.shadow_map_type
        export_settings['gltf_shadow_map_side'] = v3d_export.shadow_map_side
        export_settings['gltf_embed_buffers'] = self.export_embed_buffers
        export_settings['gltf_embed_images'] = self.export_embed_images
        export_settings['gltf_strip'] = self.export_strip
        export_settings['gltf_indices'] = self.export_indices
        export_settings['gltf_force_indices'] = self.export_force_indices
        export_settings['gltf_custom_props'] = self.export_custom_props
        export_settings['gltf_bake_modifiers'] = v3d_export.bake_modifiers
        export_settings['gltf_bake_text'] = v3d_export.bake_text
        export_settings['gltf_export_constraints'] = v3d_export.export_constraints
        export_settings['gltf_lzma_enabled'] = v3d_export.lzma_enabled
        export_settings['gltf_use_hdr'] = v3d_export.use_hdr
        export_settings['gltf_animations'] = self.export_animations
        if self.export_animations:
            export_settings['gltf_frame_range'] = self.export_frame_range
            export_settings['gltf_move_keyframes'] = self.export_move_keyframes
            export_settings['gltf_force_sampling'] = self.export_force_sampling
        else:
            export_settings['gltf_frame_range'] = False
            export_settings['gltf_move_keyframes'] = False
            export_settings['gltf_force_sampling'] = False
        export_settings['gltf_skins'] = self.export_skins
        if self.export_skins:
            export_settings['gltf_bake_armature_actions'] = v3d_export.bake_armature_actions
        else:
            export_settings['gltf_bake_armature_actions'] = False
        export_settings['gltf_morph'] = self.export_morph
        if self.export_morph:
            export_settings['gltf_morph_normal'] = self.export_morph_normal
        else:
            export_settings['gltf_morph_normal'] = False
        if self.export_morph and self.export_morph_normal:
            export_settings['gltf_morph_tangent'] = self.export_morph_tangent
        else:
            export_settings['gltf_morph_tangent'] = False
        
        export_settings['gltf_displacement'] = self.export_displacement
        
        export_settings['gltf_uri_data'] = { 'uri': [], 'bl_datablocks': [] }
        export_settings['gltf_binary'] = bytearray()
        export_settings['gltf_binaryfilename'] = os.path.splitext(os.path.basename(self.filepath))[0] + '.bin' 

        export_settings['gltf_sneak_peek'] = self.export_sneak_peek
        export_settings['gltf_app_manager_host'] = APP_MANAGER_HTTP_HOST

        export_settings['temporary_meshes'] = None
        export_settings['temporary_materials'] = None

        return gltf2_export.save(self, context, export_settings)

    def draw(self, context):
        layout = self.layout

        #

        col = layout.box().column()
        col.label(text='Embedding:', icon='PACKAGE')
        if self.export_format == 'ASCII':
            col.prop(self, 'export_embed_buffers')
            col.prop(self, 'export_embed_images')
            col.prop(self, 'export_strip')

        col = layout.box().column()
        col.label(text='Nodes:', icon='PACKAGE')
        col.prop(self, 'export_custom_props')

        col = layout.box().column()
        col.label(text='Meshes:', icon='MESH_DATA')
        col.prop(self, 'export_indices')
        col.prop(self, 'export_force_indices')

        col = layout.box().column()
        col.label(text='Animation:', icon='RENDER_ANIMATION')
        col.prop(self, 'export_animations')
        if self.export_animations:
            col.prop(self, 'export_frame_range')
            col.prop(self, 'export_move_keyframes')
            col.prop(self, 'export_force_sampling')

        col.prop(self, 'export_skins')
        col.prop(self, 'export_morph')            
        if self.export_morph:
            col.prop(self, 'export_morph_normal')
            if self.export_morph_normal:
                col.prop(self, 'export_morph_tangent')

        col = layout.box().column()
        col.label(text='Experimental:', icon='QUESTION')
        col.prop(self, 'export_displacement')


class V3D_OT_ExportGLTF(bpy.types.Operator, ExportHelper, ExportGLTF2_Base):
    '''Export scene to glTF 2.0 format'''
    bl_idname = 'export_scene.v3d_gltf'
    bl_label = 'Export Verge3D glTF'

    filename_ext = '.gltf'
    filter_glob = StringProperty(default='*.gltf', options={'HIDDEN'})
    
    export_format = 'ASCII'


class V3D_OT_ExportGLB(bpy.types.Operator, ExportHelper, ExportGLTF2_Base):
    '''Export scene to glTF 2.0 binary format'''
    bl_idname = 'export_scene.v3d_glb'
    bl_label = 'Export Verge3D glTF Binary'

    filename_ext = '.glb'
    filter_glob = StringProperty(default='*.glb', options={'HIDDEN'})
    
    export_format = 'BINARY'

class V3D_OT_ExportFB(bpy.types.Operator, ExportHelper, ExportGLTF2_Base):
    '''Export scene to glTF 2.0 binary format compatible with Facebook'''
    bl_idname = 'export_scene.v3d_fb'
    bl_label = 'Export Verge3D Facebook GLB'

    filename_ext = '.glb'
    filter_glob = StringProperty(default='*.glb', options={'HIDDEN'})
    
    export_format = 'FB'

def menu_func_export_v3d_gltf(self, context):
    self.layout.operator(V3D_OT_ExportGLTF.bl_idname, text='Verge3D glTF (.gltf)')

def menu_func_export_v3d_glb(self, context):
    self.layout.operator(V3D_OT_ExportGLB.bl_idname, text='Verge3D glTF Binary (.glb)')

def menu_func_export_v3d_fb(self, context):
    self.layout.operator(V3D_OT_ExportFB.bl_idname, text='Facebook GLB (.glb)')

def get_root():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return join(base_dir, "..", "..")

class V3DServer():

    proc = None

    @classmethod
    def run_server_proc(cls):
        root = get_root()
        sys.path.append(join(root, "manager"))
        import server
        srv = server.AppManagerServer()
        srv.start('BLENDER')

    @classmethod
    def start(cls):
        proc = threading.Thread(target=cls.run_server_proc)
        proc.daemon = True
        proc.start()

    @classmethod
    def stop(cls):
        pass


def register():
    from . import custom_props, custom_ui

    bpy.utils.register_class(V3D_OT_ExportGLTF)
    bpy.utils.register_class(V3D_OT_ExportGLB)
    bpy.utils.register_class(V3D_OT_ExportFB)

    custom_props.register()
    custom_ui.register()

    if bpy.app.version < (2,80,0):
        bpy.types.INFO_MT_file_export.append(menu_func_export_v3d_gltf)
        bpy.types.INFO_MT_file_export.append(menu_func_export_v3d_glb)
        bpy.types.INFO_MT_file_export.append(menu_func_export_v3d_fb)
    else:
        bpy.types.TOPBAR_MT_file_export.append(menu_func_export_v3d_gltf)
        bpy.types.TOPBAR_MT_file_export.append(menu_func_export_v3d_glb)
        bpy.types.TOPBAR_MT_file_export.append(menu_func_export_v3d_fb)

    if bpy.app.version < (2,80,0):
        bpy.app.handlers.load_post.append(apply_v3d_render_engine_fix)

    V3DServer.start()



def unregister():
    from . import custom_props, custom_ui

    bpy.utils.unregister_class(V3D_OT_ExportGLTF)
    bpy.utils.unregister_class(V3D_OT_ExportGLB)
    bpy.utils.unregister_class(V3D_OT_ExportFB)

    custom_props.unregister()
    custom_ui.unregister()

    if bpy.app.version < (2,80,0):
        bpy.types.INFO_MT_file_export.remove(menu_func_export_v3d_gltf)
        bpy.types.INFO_MT_file_export.remove(menu_func_export_v3d_glb)
        bpy.types.INFO_MT_file_export.remove(menu_func_export_v3d_fb)
    else:
        bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_v3d_gltf)
        bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_v3d_glb)
        bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_v3d_fb)

@persistent
def apply_v3d_render_engine_fix(dummy):

    # change to something, then back
    # this fixes issue with 'VERGE3D' render warning, dropped in version 2.9.0
    if bpy.context.scene.render.engine == 'BLENDER_RENDER':
        bpy.context.scene.render.engine = 'BLENDER_GAME'
        bpy.context.scene.render.engine = 'BLENDER_RENDER'

