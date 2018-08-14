import bpy, math

NO_ANIM_OPTS = set()

class V3DExportSettings(bpy.types.PropertyGroup):
    bake_modifiers = bpy.props.BoolProperty(
        name = 'Bake Modifiers',
        description = 'Apply mesh modifiers (except armature modifers) before export ',
        default = False,
        options = NO_ANIM_OPTS
    )

    copyright = bpy.props.StringProperty(
        name = 'Copyright',
        description = 'Assign if you want your copyright info to be present in all exported files',
        default = ''
    )

    export_constraints = bpy.props.BoolProperty(
        name = 'Export Constraints',
        description = 'Export object constraints',
        default = True,
        options = NO_ANIM_OPTS
    )

    lzma_enabled = bpy.props.BoolProperty(
        name = 'Enable LZMA Compression',
        description = 'Enable LZMA Compression',
        default = False,
        options = NO_ANIM_OPTS
    )

    use_shadows = bpy.props.BoolProperty(
        name = 'Enable Shadows',
        description = 'Enable shadows, use lamp settings to confiure shadow params',
        default = False,
        options = NO_ANIM_OPTS
    )

    shadow_map_type = bpy.props.EnumProperty(
        name='Map Type',
        description = 'Shadow Map Type',
        default = 'PCFSOFT',
        items = [
            ('PCFSOFT', 'Soft PCF', 'Use soft PCF shadow maps (best quality, slowest)'),
            ('PCF', 'PCF', 'Use percentage-closer filtering shadow maps (average quality)'),
            ('BASIC', 'Basic', 'Use unfiltered shadow maps (fastest)'),
        ],
        options = NO_ANIM_OPTS
    )

    shadow_map_side = bpy.props.EnumProperty(
        name='Map Side',
        description = 'Which side of the objects will be rendered to shadow maps',
        default = 'FRONT',
        items = [
            ('BOTH', 'Double-sided', 'Render both sides (slower, requires proper bias assignment)'),
            ('BACK', 'Back Side', 'Render back side (prevents some self-shadow artefacts)'),
            ('FRONT', 'Front Side', 'Render front side (more intuitive, requires proper bias assignment)'),
        ],
        options = NO_ANIM_OPTS
    )

    bake_armature_actions = bpy.props.BoolProperty(
        name = 'Bake Armature Actions',
        description = '',
        default = False,
        options = NO_ANIM_OPTS
    )

    bake_text = bpy.props.BoolProperty(
        name = 'Bake Text',
        description = 'Export Font objects as meshes',
        default = False,
        options = NO_ANIM_OPTS
    )

class V3DWorldSettings(bpy.types.PropertyGroup):
    pass

class V3DOutlineSettings(bpy.types.PropertyGroup):
    """Outline settings are part of scene settings"""

    enabled = bpy.props.BoolProperty(
        name = 'Enabled',
        description = 'Enable outline effect',
        default = False,
        options = NO_ANIM_OPTS
    )

    edge_strength = bpy.props.FloatProperty(
        name = 'Edge Strength',
        description = 'Outline Edge Strength',
        default = 3,
        min = 0,
        options = NO_ANIM_OPTS
    )
    edge_glow = bpy.props.FloatProperty(
        name = 'Edge Glow',
        description = 'Outline edge glow',
        default = 0,
        min = 0,
        options = NO_ANIM_OPTS
    )
    edge_thickness = bpy.props.FloatProperty(
        name = 'Edge Thickness',
        description = 'Outline edge thickness',
        default = 1,
        min = 0,
        options = NO_ANIM_OPTS
    )

    pulse_period = bpy.props.FloatProperty(
        name = 'Pulse Period',
        description = 'Outline pulse period',
        default = 0,
        min = 0,
        options = NO_ANIM_OPTS
    )

    visible_edge_color = bpy.props.FloatVectorProperty(
        name = 'Visible Edge Color',
        description = 'Outline visible edge color',
        default = (1.0, 1.0, 1.0, 1.0),
        subtype = 'COLOR',
        size = 4,
        min = 0,
        soft_max = 1,
        options = NO_ANIM_OPTS
    )
    hidden_edge_color = bpy.props.FloatVectorProperty(
        name = 'Hidden Edge Color',
        description = 'Outline hidden edge color',
        default = (0.1, 0.1, 0.1, 1.0),
        subtype = 'COLOR',
        size = 4,
        min = 0,
        soft_max = 1,
        options = NO_ANIM_OPTS
    )
    

class V3DSceneSettings(bpy.types.PropertyGroup):
    outline = bpy.props.PointerProperty(
        name = 'Outline settings',
        type = V3DOutlineSettings
    )

    export_layers = bpy.props.BoolVectorProperty(
        name = 'Export Layers',
        description = 'Exported layers - Shift-Click/Drag to select multple',
        size = 20,
        default = [True] * 20,
        subtype = 'LAYER',
        options = NO_ANIM_OPTS
    )

class V3DObjectSettings(bpy.types.PropertyGroup):
    anim_auto = bpy.props.BoolProperty(
        name = 'Auto Start',
        description = 'Auto start animation',
        default = True,
        options = NO_ANIM_OPTS
    )

    anim_loop = bpy.props.EnumProperty(
        name='Loop Mode',
        description = 'Animation looping mode',
        default = 'REPEAT',
        items = [
            ('ONCE', 'Once', 'Play the clip once'),
            ('REPEAT', 'Repeat', 'Repeat numerous times'),
            ('PING_PONG', 'Ping Pong', 'Repeat numerous times playing forward and backward'),
        ],
        options = NO_ANIM_OPTS
    )

    anim_repeat_infinite = bpy.props.BoolProperty(
        name = 'Repeat Infinitely',
        description = 'Repeat animation infinite',
        default = True,
        options = NO_ANIM_OPTS
    )

    anim_repeat_count = bpy.props.FloatProperty(
        name = 'Repeat Count',
        description = 'Animation repeat count',
        default = 1,
        options = NO_ANIM_OPTS
    )

    anim_offset = bpy.props.FloatProperty(
        name = 'Offset',
        description = 'Animation offset, frames',
        default = 0,
        options = NO_ANIM_OPTS
    )

    render_order = bpy.props.IntProperty(
        name = 'Rendering Order',
        description = ('The rendering-order index. The smaller the index, the ' 
                + 'earlier the object will be rendered. Useful for sorting' 
                + ' transparent objects.'),
        default = 0,
        options = NO_ANIM_OPTS
    )

    frustum_culling = bpy.props.BoolProperty(
        name = 'Frustum Culling',
        description = 'Perform frustum culling for this object.',
        default = True,
        options = NO_ANIM_OPTS
    )

class V3DCameraSettings(bpy.types.PropertyGroup):

    controls = bpy.props.EnumProperty(
        name = 'Controls',
        description = 'Camera controls type',
        default = 'ORBIT',
        items = [
            ('NONE', 'No controls', 'Disable camera controls'),
            ('FLYING', 'Flying', 'Flying camera'),
            ('ORBIT', 'Orbit', 'Move camera around a target')
        ],
        options = NO_ANIM_OPTS
    )

    enable_pan = bpy.props.BoolProperty(
        name = 'Allow Panning',
        description = 'Allow camera panning',
        default = True,
        options = NO_ANIM_OPTS
    )

    rotate_speed = bpy.props.FloatProperty(
        name = 'Rotation Speed',
        description = 'Camera rotation speed factor',
        default = 1,
        options = NO_ANIM_OPTS
    )

    move_speed = bpy.props.FloatProperty(
        name = 'Movement Speed',
        description = 'Camera movement speed factor',
        default = 1,
        options = NO_ANIM_OPTS
    )

    orbit_min_distance = bpy.props.FloatProperty(
        name = 'Min Dist',
        description = 'Orbit camera minimum distance',
        default = 0,
        options = NO_ANIM_OPTS
    )

    orbit_max_distance = bpy.props.FloatProperty(
        name = 'Max Dist',
        description = 'Orbit camera maximum distance',
        default = 100,
        options = NO_ANIM_OPTS
    )

    orbit_min_polar_angle = bpy.props.FloatProperty(
        name = 'Min Angle',
        description = 'Orbit camera minimum polar (vertical) angle',
        default = 0,
        subtype = 'ANGLE',
        unit = 'ROTATION',
        options = NO_ANIM_OPTS
    )

    orbit_max_polar_angle = bpy.props.FloatProperty(
        name = 'Max Angle',
        description = 'Orbit camera maximum polar (vertical) angle',
        default = math.pi,
        subtype = 'ANGLE',
        unit = 'ROTATION',
        options = NO_ANIM_OPTS
    )

    orbit_min_azimuth_angle = bpy.props.FloatProperty(
        name = 'Min Angle',
        description = 'Orbit camera minimum azimuth (horizontal) angle',
        default = 0,
        subtype = 'ANGLE',
        unit = 'ROTATION',
        options = NO_ANIM_OPTS
    )

    orbit_max_azimuth_angle = bpy.props.FloatProperty(
        name = 'Max Angle',
        description = 'Orbit camera maximum azimuth (horizontal) angle',
        default = 2 * math.pi,
        subtype = 'ANGLE',
        unit = 'ROTATION',
        options = NO_ANIM_OPTS
    )

    orbit_target = bpy.props.FloatVectorProperty(
        name = 'Target',
        description = 'Target point for orbit camera',
        default = (0.0, 0.0, 0.0),
        precision = 3,
        subtype = 'XYZ',
        size = 3,
        options = NO_ANIM_OPTS
    )

class V3DShadowSettings(bpy.types.PropertyGroup):
    """Shadow settings are part of lamp settngs"""
    bias = bpy.props.FloatProperty(
        name = 'Bias',
        description = 'Shadow map bias',
        default = 0.0015,
        precision = 4,
        step = 0.01,
        options = NO_ANIM_OPTS
    )

    map_size = bpy.props.EnumProperty(
        name = 'Map Size',
        description = 'Shadow map size in pixels',
        default = '1024',
        items = [
            ('4096', '4096', '4096 pixels'),
            ('2048', '2048', '2048 pixels'),
            ('1024', '1024', '1024 pixels'),
            ('512', '512', '512 pixels'),
            ('256', '256', '256 pixels'),
            ('128', '128', '128 pixels')
        ],
        options = NO_ANIM_OPTS
    )

    radius = bpy.props.FloatProperty(
        name = 'Radius',
        description = 'Shadow map blur radius',
        default = 1,
        min = 0,
        options = NO_ANIM_OPTS
    )

    camera_near = bpy.props.FloatProperty(
        name = 'Near',
        description = 'Shadow map camera near distance',
        default = 0.2,
        min = 0,
        options = NO_ANIM_OPTS
    )
    camera_far = bpy.props.FloatProperty(
        name = 'Far',
        description = 'Shadow map camera far distance',
        default = 100,
        min = 0,
        options = NO_ANIM_OPTS
    )
    camera_size = bpy.props.FloatProperty(
        name = 'Size',
        description = 'Shadow map camera size for directional light',
        default = 10,
        min = 0,
        options = NO_ANIM_OPTS
    )
    camera_fov = bpy.props.FloatProperty(
        name = 'FOV',
        description = 'Shadow map camera field of view for spot light',
        default = math.pi/2,
        min = 0,
        subtype = 'ANGLE',
        unit = 'ROTATION',
        options = NO_ANIM_OPTS
    )

class V3DLampSettings(bpy.types.PropertyGroup):
    shadow = bpy.props.PointerProperty(
        name = 'Shadow Settings',
        type = V3DShadowSettings
    )

def alpha_add_update(self, context):
    mat = context.material
    
    if mat.v3d.alpha_add == True:
        mat.game_settings.alpha_blend = 'ADD'
    else:
        mat.game_settings.alpha_blend = 'OPAQUE'



class V3DMaterialSettings(bpy.types.PropertyGroup):
    alpha_add = bpy.props.BoolProperty(
        name = 'Alpha Add Transparency',
        description = 'Use Alpha Add transparency (disable depth write)',
        default = False,
        options = NO_ANIM_OPTS,
        update = alpha_add_update
    )

class V3DTextureSettings(bpy.types.PropertyGroup):
    anisotropy = bpy.props.EnumProperty(
        name = 'Anisotropic Filtering',
        description = 'Anisotropic filtering ratio',
        default = '1',
        items = [
            ('1', 'Off', 'Disabled'),
            ('2', '2x', 'Average quality'),
            ('4', '4x', 'Good quality'),
            ('8', '8x', 'Very good quality'),
            ('16', '16x', 'Maximum quality'),
        ],
        options = NO_ANIM_OPTS
    )

class V3DLineRenderingSettings(bpy.types.PropertyGroup):
    
    enable = bpy.props.BoolProperty(
        name = 'Enable Line Rendering',
        description = 'Render the object as constant-width lines',
        default = False,
        options = NO_ANIM_OPTS
    )

    color = bpy.props.FloatVectorProperty(
        name = 'Line Color',
        description = 'Line color',
        default = (1.0, 1.0, 1.0),
        subtype = 'COLOR',
        size = 3,
        min = 0,
        soft_max = 1,
        options = NO_ANIM_OPTS
    )

    width = bpy.props.FloatProperty(
        name = 'Line Width (px)',
        description = 'Line width in pixels',
        default = 1,
        min = 0,
        options = NO_ANIM_OPTS
    )

class V3DCurveSettings(bpy.types.PropertyGroup):

    line_rendering_settings = bpy.props.PointerProperty(
        name = "Line Rendering Settings",
        type = V3DLineRenderingSettings
    )

class V3DMeshSettings(bpy.types.PropertyGroup):

    line_rendering_settings = bpy.props.PointerProperty(
        name = "Line Rendering Settings",
        type = V3DLineRenderingSettings
    )

def register():
    bpy.utils.register_class(V3DExportSettings)
    bpy.utils.register_class(V3DWorldSettings)
    bpy.utils.register_class(V3DOutlineSettings)
    bpy.utils.register_class(V3DSceneSettings)
    bpy.utils.register_class(V3DObjectSettings)
    bpy.utils.register_class(V3DCameraSettings)
    bpy.utils.register_class(V3DShadowSettings)
    bpy.utils.register_class(V3DLampSettings)
    bpy.utils.register_class(V3DMaterialSettings)
    bpy.utils.register_class(V3DTextureSettings)
    bpy.utils.register_class(V3DLineRenderingSettings)
    bpy.utils.register_class(V3DCurveSettings)
    bpy.utils.register_class(V3DMeshSettings)

    bpy.types.World.v3d = bpy.props.PointerProperty(
        name = "Verge3D world settings",
        type = V3DWorldSettings
    )
    bpy.types.Scene.v3d_export = bpy.props.PointerProperty(
        name = "Verge3D export settings",
        type = V3DExportSettings
    )
    bpy.types.Scene.v3d = bpy.props.PointerProperty(
        name = "Verge3D scene settings",
        type = V3DSceneSettings
    )
    bpy.types.Object.v3d = bpy.props.PointerProperty(
        name = "Verge3D object settings",
        type = V3DObjectSettings
    )
    bpy.types.Camera.v3d = bpy.props.PointerProperty(
        name = "Verge3D camera settings",
        type = V3DCameraSettings
    )
    bpy.types.Lamp.v3d = bpy.props.PointerProperty(
        name = "Verge3D lamp settings",
        type = V3DLampSettings
    )
    bpy.types.Material.v3d = bpy.props.PointerProperty(
        name = "Verge3D material settings",
        type = V3DMaterialSettings
    )
    bpy.types.Texture.v3d = bpy.props.PointerProperty(
        name = "Verge3D texture settings",
        type = V3DTextureSettings
    )

    bpy.types.ShaderNodeTexImage.v3d = bpy.props.PointerProperty(
        name = "Verge3D texture settings",
        type = V3DTextureSettings
    )

    bpy.types.Curve.v3d = bpy.props.PointerProperty(
        name = "Verge3D curve settings",
        type = V3DCurveSettings
    )

    bpy.types.Mesh.v3d = bpy.props.PointerProperty(
        name = "Verge3D mesh settings",
        type = V3DMeshSettings
    )


def unregister():
    bpy.utils.unregister_class(V3DTextureSettings)
    bpy.utils.unregister_class(V3DMaterialSettings)
    bpy.utils.unregister_class(V3DLampSettings)
    bpy.utils.unregister_class(V3DLineRenderingSettings)
    bpy.utils.unregister_class(V3DCurveSettings)
    bpy.utils.unregister_class(V3DMeshSettings)
    bpy.utils.unregister_class(V3DShadowSettings)
    bpy.utils.unregister_class(V3DCameraSettings)
    bpy.utils.unregister_class(V3DObjectSettings)
    bpy.utils.unregister_class(V3DSceneSettings)
    bpy.utils.unregister_class(V3DOutlineSettings)
    bpy.utils.unregister_class(V3DWorldSettings)
    bpy.utils.unregister_class(V3DExportSettings)

    del bpy.types.Material.v3d
    del bpy.types.Lamp.v3d
    del bpy.types.Curve.v3d
    del bpy.types.Mesh.v3d
    del bpy.types.Camera.v3d
    del bpy.types.Object.v3d
    del bpy.types.Scene.v3d_export
    del bpy.types.Scene.v3d
    del bpy.types.World.v3d
