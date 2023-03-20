import bpy
import re
from pluginUtils.manager import AppManagerConn

def add_verge3d_manual_map():

    manualURL = AppManagerConn.getManualURL()

    url_manual_prefix = re.sub('index.html$', '', manualURL)
    url_manual_mapping = (
        # buttons
        ('bpy.ops.view3d.v3d_sneak_peek', 'blender/Beginners-Guide.html#Sneak_Peek'),
        ('bpy.ops.view3d.v3d_app_manager', 'blender/Beginners-Guide.html#App_Manager'),
        # menus
        ('bpy.ops.export_scene.v3d_gltf', 'blender/Beginners-Guide.html#Export'),
        ('bpy.ops.export_scene.v3d_glb', 'blender/Beginners-Guide.html#Export'),
        # export settings
        ('bpy.types.v3dexportsettings.lzma_enabled', 'introduction/Asset-compression.html'),
        ('bpy.types.v3dexportsettings.compress_textures', 'introduction/Texture-Compression.html'),
        ('bpy.types.v3dexportsettings.export_animations', 'blender/Animation.html'),
        ('bpy.types.v3dexportsettings.export_frame_range', 'blender/Animation.html'),
        ('bpy.types.v3dexportsettings.export_move_keyframes', 'blender/Animation.html'),
        ('bpy.types.v3dexportsettings.bake_armature_actions', 'blender/Animation.html'),
        ('bpy.types.v3dexportsettings.use_shadows', 'blender/Shadows.html#global_settings'),
        ('bpy.types.v3dexportsettings.shadow*', 'blender/Shadows.html#global_settings'),
        ('bpy.types.v3dexportsettings.esm*', 'blender/Shadows.html#global_settings'),
        ('bpy.types.v3dexportsettings.use_oit', 'blender/Transparency.html#oit_rendering'),
        ('bpy.types.v3dexportsettings*', 'blender/Lighting-and-Rendering.html#global_rendering_properties_verge3d'),
        # outline settings
        ('bpy.types.v3doutlinesettings*', 'blender/Lighting-and-Rendering.html#outline_rendering'),
        # object settings
        ('bpy.types.v3dobjectsettings.anim*', 'blender/Animation.html#Verge3D_Per_Object_Settings'),
        ('bpy.types.v3dobjectsettings.render_order', 'blender/Lighting-and-Rendering.html#per_object_rendering_properties'),
        ('bpy.types.v3dobjectsettings.render_order', 'blender/Lighting-and-Rendering.html#per_object_rendering_properties'),
        ('bpy.types.v3dobjectsettings.frustum_culling', 'blender/Lighting-and-Rendering.html#per_object_rendering_properties'),
        ('bpy.types.v3dobjectsettings.use_shadows', 'blender/Shadows.html#per_object_material_settings'),
        ('bpy.types.v3dobjectsettings.hidpi_compositing', 'blender/Lighting-and-Rendering.html#hidpi_rendering'),
        ('bpy.types.v3dobjectsettings.canvas_break*', 'blender/Lighting-and-Rendering.html#visibility_breakpoints'),
        ('bpy.types.v3dobjectsettings.canvas_fit*', 'blender/Camera.html#fit_to_camera_edge'),
        ('bpy.types.v3dobjectsettings.fix_ortho_zoom', 'blender/Camera.html'),
        # camera settings
        ('bpy.types.v3dcamerasettings.orbit*', 'blender/Camera.html#orbit_camera_settings'),
        ('bpy.types.v3dcamerasettings.fps*', 'blender/Camera.html#firstperson_camera_settings'),
        ('bpy.types.v3dcamerasettings.enable_pointer_lock', 'blender/Camera.html#firstperson_camera_settings'),
        ('bpy.types.v3dcamerasettings*', 'blender/Camera.html#camera_settings'),
        ('bpy.ops.camera.v3d_orbit_camera_target_from_cursor', 'blender/Camera.html#orbit_camera_settings'),
        ('bpy.ops.camera.v3d_orbit_camera_update_view', 'blender/Camera.html#orbit_camera_settings'),
        # mesh,curve settings
        ('bpy.types.v3dlinerenderingsettings*', 'blender/Lighting-and-Rendering.html#line_rendering'),
        # material settings
        ('bpy.types.v3dmaterialsettings.render_side', 'blender/Lighting-and-Rendering.html#material_verge3d_panel'),
        ('bpy.types.v3dmaterialsettings.depth_write', 'blender/Transparency.html#alpha_add'),
        ('bpy.types.v3dmaterialsettings.depth_test', 'blender/Lighting-and-Rendering.html#material_verge3d_panel'),
        ('bpy.types.v3dmaterialsettings.dithering', 'blender/Lighting-and-Rendering.html#material_verge3d_panel'),
        ('bpy.types.v3dmaterialsettings.gltf_compat', 'blender/GLTF-Materials.html'),
        # light settings
        ('bpy.types.v3dshadowsettings*', 'blender/Shadows.html#per_light_settings'),
        # texture settings
        ('bpy.types.v3dtexturesettings.anisotropy', 'blender/Shader-Nodes-Reference.html#Image_Texture'),
        ('bpy.types.v3dimagesettings.compression_method', 'introduction/Texture-Compression.html#tweaking_compression'),
        ('bpy.types.v3dtexturenoisesettings*', 'blender/Shader-Nodes-Reference.html#Noise_Texture'),
        # light probe settings
        ('bpy.types.v3dlightprobesettings*', 'blender/Lighting-and-Rendering.html#light_probes'),
        # clipping plane settings
        ('bpy.types.v3dobjectsettings.clipping_plane*', 'blender/Lighting-and-Rendering.html#clipping_planes'),
        ('bpy.ops.object.add_clipping_plane', 'blender/Lighting-and-Rendering.html#clipping_planes'),
    )
    return url_manual_prefix, url_manual_mapping

def register():
    bpy.utils.register_manual_map(add_verge3d_manual_map)

def unregister():
    bpy.utils.unregister_manual_map(add_verge3d_manual_map)
