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

import math

import bpy

from . import utils

NO_ANIM_OPTS = set()

class V3DExportSettings(bpy.types.PropertyGroup):
    bake_modifiers: bpy.props.BoolProperty(
        name = 'Bake Modifiers',
        description = 'Apply mesh modifiers (except armature modifers) before export ',
        default = False,
        options = NO_ANIM_OPTS
    )

    copyright: bpy.props.StringProperty(
        name = 'Copyright',
        description = 'Assign if you want your copyright info to be present in all exported files',
        default = ''
    )

    export_constraints: bpy.props.BoolProperty(
        name = 'Export Constraints',
        description = 'Export object constraints',
        default = True,
        options = NO_ANIM_OPTS
    )

    export_custom_props: bpy.props.BoolProperty(
        name = 'Export Custom Props',
        description = 'Export object custom properties',
        default = False,
        options = NO_ANIM_OPTS
    )

    export_animations: bpy.props.BoolProperty(
        name = 'Export Animations',
        description = 'Export animations',
        default = True,
        options = NO_ANIM_OPTS
    )

    export_frame_range: bpy.props.BoolProperty(
        name = 'Export Playback Range',
        description = 'Export animation within scene playback range',
        default = False,
        options = NO_ANIM_OPTS
    )

    export_move_keyframes: bpy.props.BoolProperty(
        name = 'Keyframes Start With 0',
        description = 'Make exported animation keyframes start with 0',
        default = True,
        options = NO_ANIM_OPTS
    )

    lzma_enabled: bpy.props.BoolProperty(
        name = 'LZMA Compression',
        description = 'Enable LZMA compression for exported glTF files',
        default = False,
        options = NO_ANIM_OPTS
    )

    compress_textures: bpy.props.BoolProperty(
        name = 'Compress Textures',
        description = 'Store textures in KTX2 compression format',
        default = False,
        options = NO_ANIM_OPTS
    )

    optimize_attrs: bpy.props.BoolProperty(
        name = 'Optimize Mesh Attrs',
        description = 'Remove unused geometry attributes (such as tangents) from exported meshes',
        default = True,
        options = NO_ANIM_OPTS
    )

    aa_method: bpy.props.EnumProperty(
        name='Anti-aliasing',
        description = 'Preferred anti-aliasing method',
        default = 'AUTO',
        items = [
            ('AUTO', 'Auto', 'Use system default method'),
            ('MSAA4', 'MSAA 4x', 'Prefer 4x MSAA on supported hardware'),
            ('MSAA8', 'MSAA 8x', 'Prefer 8x MSAA on supported hardware'),
            ('MSAA16', 'MSAA 16x', 'Prefer 16x MSAA on supported hardware'),
            ('FXAA', 'FXAA', 'Prefer FXAA'),
            ('NONE', 'None', 'Disable anti-aliasing'),
        ],
        options = NO_ANIM_OPTS
    )

    use_hdr: bpy.props.BoolProperty(
        name = 'Use HDR Rendering',
        description = 'Enable HDR rendering pipeline on compatible hardware',
        default = False,
        options = NO_ANIM_OPTS
    )

    use_oit: bpy.props.BoolProperty(
        name = 'Order-Indep. Transparency',
        description = 'Enable Order-Independent Transparency rendering technique',
        default = False,
        options = NO_ANIM_OPTS
    )

    use_shadows: bpy.props.BoolProperty(
        name = 'Enable Shadows',
        description = 'Enable shadows, use lamp settings to confiure shadow params',
        default = True,
        options = NO_ANIM_OPTS
    )

    shadow_map_type: bpy.props.EnumProperty(
        name='Shadow Filtering',
        description = 'Shadow Filtering Mode',
        default = 'PCFPOISSON',
        items = [
            ('BASIC', 'Basic', 'No filtering'),
            ('BILINEAR', 'Bilinear', 'Bilinear Filtering'),
            ('PCF', 'PCF', 'Percentage Closer Filtering'),
            ('PCFSOFT', 'PCF (Bilinear)', (
                'Percentage Closer Filtering with Bilinear Interpolation. For '
                'POINT and wide (>90°) SPOT lights it is no different than '
                'simple PCF'
            )),
            ('PCFPOISSON', 'PCF (Poisson Disk)', 'Percentage Closer Filtering with Poisson Disk Sampling'),
            ('ESM', 'ESM', 'Exponential Shadow Maps'),
        ],
        options = NO_ANIM_OPTS
    )

    shadow_map_side: bpy.props.EnumProperty(
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

    esm_distance_scale: bpy.props.FloatProperty(
        name = 'ESM Distance Scale',
        description = ('Scale factor for adjusting soft shadows to scenes of '
                'various scales. It\'s generally useful to decrease this value '
                'for larger scenes, especially if shadows still look sharp no '
                'matter how big the blur radius is set'),
        default = 1,
        min = 0,
        soft_max = 10,
        max = 100,
        options = NO_ANIM_OPTS
    )

    ibl_environment_mode: bpy.props.EnumProperty(
        name = 'IBL Env. Mode',
        description = 'Preferred method of rendering the scene environment',
        default = 'PMREM',
        items = [
            ('PMREM', 'PMREM (slow)', (
                'Use PMREM (Prefiltered Mipmaped Radiance Environment map). '
                'Slower, higher quality'
            )),
            ('PROBE_CUBEMAP', 'Light Probe + Cubemap (deprecated)',
                'Deprecated, will use PMREM instead'
            ),
            ('PROBE', 'Light Probe (fast)', (
                'Use a light probe for the diffuse component, no specular. '
                'Faster, worse quality'
            )),
            ('NONE', 'None (fastest)',
                'Disable environment map. '
            ),
        ],
        options = NO_ANIM_OPTS
    )

    bake_armature_actions: bpy.props.BoolProperty(
        name = 'Bake Armature Actions',
        description = 'Bake armature actions before export',
        default = False,
        options = NO_ANIM_OPTS
    )

    bake_text: bpy.props.BoolProperty(
        name = 'Bake Text',
        description = 'Export Font objects as meshes',
        default = False,
        options = NO_ANIM_OPTS
    )

    # mandatory indices for UIList Exported Collections
    collections_exported_idx: bpy.props.IntProperty(
        default = 0,
        options = NO_ANIM_OPTS
    )

class V3DWorldSettings(bpy.types.PropertyGroup):

    dithering: bpy.props.BoolProperty(
        name = 'Dithering',
        description = 'Apply color dithering to eliminate banding artefacts',
        default = False,
        options = NO_ANIM_OPTS
    )


class V3DOutlineSettings(bpy.types.PropertyGroup):
    """Outline settings are part of scene settings"""

    enabled: bpy.props.BoolProperty(
        name = 'Enabled',
        description = 'Enable outline effect',
        default = False,
        options = NO_ANIM_OPTS
    )

    edge_strength: bpy.props.FloatProperty(
        name = 'Edge Strength',
        description = 'Outline Edge Strength',
        default = 3,
        min = 0,
        options = NO_ANIM_OPTS
    )
    edge_glow: bpy.props.FloatProperty(
        name = 'Edge Glow',
        description = 'Outline edge glow',
        default = 0,
        min = 0,
        options = NO_ANIM_OPTS
    )
    edge_thickness: bpy.props.FloatProperty(
        name = 'Edge Thickness',
        description = 'Outline edge thickness',
        default = 1,
        min = 1,
        options = NO_ANIM_OPTS
    )

    pulse_period: bpy.props.FloatProperty(
        name = 'Pulse Period',
        description = 'Outline pulse period',
        default = 0,
        min = 0,
        options = NO_ANIM_OPTS
    )

    visible_edge_color: bpy.props.FloatVectorProperty(
        name = 'Visible Edge Color',
        description = 'Outline visible edge color',
        default = (1.0, 1.0, 1.0, 1.0),
        subtype = 'COLOR',
        size = 4,
        min = 0,
        soft_max = 1,
        options = NO_ANIM_OPTS
    )
    hidden_edge_color: bpy.props.FloatVectorProperty(
        name = 'Hidden Edge Color',
        description = 'Outline hidden edge color',
        default = (0.1, 0.1, 0.1, 1.0),
        subtype = 'COLOR',
        size = 4,
        min = 0,
        soft_max = 1,
        options = NO_ANIM_OPTS
    )

    render_hidden_edge: bpy.props.BoolProperty(
        name = 'Render Hidden Edge',
        description = 'Render the hidden edge part or not',
        default = True,
        options = NO_ANIM_OPTS
    )


class V3DSceneSettings(bpy.types.PropertyGroup):
    outline: bpy.props.PointerProperty(
        name = 'Outline settings',
        type = V3DOutlineSettings
    )

class V3DObjectSettings(bpy.types.PropertyGroup):
    anim_auto: bpy.props.BoolProperty(
        name = 'Auto Start',
        description = 'Auto start animation',
        default = True,
        options = NO_ANIM_OPTS
    )

    anim_loop: bpy.props.EnumProperty(
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

    anim_repeat_infinite: bpy.props.BoolProperty(
        name = 'Repeat Infinitely',
        description = 'Repeat animation infinite',
        default = True,
        options = NO_ANIM_OPTS
    )

    anim_repeat_count: bpy.props.FloatProperty(
        name = 'Repeat Count',
        description = 'Animation repeat count',
        default = 1,
        options = NO_ANIM_OPTS
    )

    anim_offset: bpy.props.FloatProperty(
        name = 'Offset',
        description = 'Animation offset in frames',
        default = 0,
        options = NO_ANIM_OPTS
    )

    render_order: bpy.props.IntProperty(
        name = 'Render Order',
        description = ('The rendering-order index. The smaller the index, the '
                + 'earlier the object will be rendered. Useful for sorting'
                + ' transparent objects'),
        default = 0,
        options = NO_ANIM_OPTS
    )

    frustum_culling: bpy.props.BoolProperty(
        name = 'Frustum Culling',
        description = 'Perform frustum culling for this object.',
        default = True,
        options = NO_ANIM_OPTS
    )

    use_shadows: bpy.props.BoolProperty(
        name = 'Receive Shadows',
        description = 'Allow this object to receive shadows',
        default = True,
        options = NO_ANIM_OPTS
    )

    hidpi_compositing: bpy.props.BoolProperty(
        name = 'HiDPI Compositing',
        description = 'Render this object (and its children) using the separate HiDPI (Retina) compositing pass',
        default = False,
        options = NO_ANIM_OPTS
    )

    fix_ortho_zoom: bpy.props.BoolProperty(
        name = 'Fix Ortho Zoom',
        description = ('Apply inverse orthographic camera zoom as scaling factor for this object'),
        default = False,
        options = NO_ANIM_OPTS
    )

    clipping_plane: bpy.props.BoolProperty(
        name = 'Clipping Plane',
        description = 'Clipping plane object',
        default = False,
        options = NO_ANIM_OPTS
    )

    clipping_plane_collection: bpy.props.PointerProperty(
        type = bpy.types.Collection,
        name = 'Affected Objects',
        description = 'Objects affected by the clipping plane',
        options = NO_ANIM_OPTS
    )

    clipping_plane_negated: bpy.props.BoolProperty(
        name = 'Negated',
        description = 'Swap clipped and unclipped sides',
        default = False,
        options = NO_ANIM_OPTS
    )

    clipping_plane_shadows: bpy.props.BoolProperty(
        name = 'Clip Shadows',
        description = 'Clip shadows casted from the clipped objects',
        default = False,
        options = NO_ANIM_OPTS
    )

    clipping_plane_union: bpy.props.BoolProperty(
        name = 'Union Planes',
        description = 'Construct a union from all the clipping planes, affecting the object, not their intersection',
        default = True,
        options = NO_ANIM_OPTS
    )

    clipping_plane_cross_section: bpy.props.BoolProperty(
        name = 'Filled Cross-Section',
        description = 'Fill cross-section between the clipping plane and the affected objects',
        default = False,
        options = NO_ANIM_OPTS
    )

    clipping_plane_color: bpy.props.FloatVectorProperty(
        name = 'Cross-Section Color',
        description = 'Cross-section diffuse color and opacity',
        default = (0.5, 0.0, 0.0, 1.0),
        subtype = 'COLOR',
        size = 4,
        min = 0,
        soft_max = 1,
        options = NO_ANIM_OPTS
    )

    clipping_plane_size: bpy.props.FloatProperty(
        name = 'Cross-Section Plane Size',
        description = 'Cross-section plane size (increase if you use larger scene size)',
        default = 100,
        min = 0,
        soft_max = 1000,
        max = 1000000,
        options = NO_ANIM_OPTS
    )

    clipping_plane_render_side: bpy.props.EnumProperty(
        name='Cross-Section Render Side',
        description = 'Which side of clipping plane cross-section geometry will be rendered',
        default = 'FRONT',
        items = [
            ('DOUBLE', 'Double-sided', 'Render both sides (reduced performance)'),
            ('BACK', 'Back Side', 'Render back side (better performance)'),
            ('FRONT', 'Front Side', 'Render front side (better performance, default)'),
        ],
        options = NO_ANIM_OPTS
    )

    canvas_fit_x: bpy.props.EnumProperty(
        name = 'Horizontal',
        description = 'Horizontal canvas edge to fit object to',
        default = 'NONE',
        items = [
            ('NONE', 'None', 'None', 'ALIGN_FLUSH', 0),
            ('LEFT', 'Left', 'Left', 'ALIGN_LEFT', 1),
            ('RIGHT', 'Right', 'Right', 'ALIGN_RIGHT', 2),
            ('STRETCH', 'Stretch', 'Stretch', 'ALIGN_JUSTIFY', 3)
        ],
        options = NO_ANIM_OPTS
    )

    canvas_fit_y: bpy.props.EnumProperty(
        name = 'Vertical',
        description = 'Vertical canvas edge to fit object to',
        default = 'NONE',
        items = [
            ('NONE', 'None', 'None', 'ALIGN_FLUSH', 0),
            ('TOP', 'Top', 'Top', 'ALIGN_TOP', 1),
            ('BOTTOM', 'Bottom', 'Bottom', 'ALIGN_BOTTOM', 2),
            ('STRETCH', 'Stretch', 'Stretch', 'ALIGN_JUSTIFY', 3)
        ],
        options = NO_ANIM_OPTS
    )

    canvas_fit_shape: bpy.props.EnumProperty(
        name = 'Shape',
        description = 'Canvas fit shape',
        default = 'BOX',
        items = [
            ('BOX', 'Box', 'Box', 'CUBE', 0),
            ('SPHERE', 'Sphere', 'Sphere', 'SPHERE', 1),
            ('POINT', 'Point', 'Point', 'DOT', 2)
        ],
        options = NO_ANIM_OPTS
    )

    canvas_fit_offset: bpy.props.FloatProperty(
        name = 'Fit Offset',
        description = ('Canvas fit offset'),
        default = 0,
        min = 0,
        precision = 2,
        options = NO_ANIM_OPTS
    )


    canvas_break_enabled: bpy.props.BoolProperty(
        name = 'Visibility Breakpoints',
        description = 'Enable breakpoints to affect object visibility depending on canvas size and orientation',
        default = False,
        options = NO_ANIM_OPTS
    )

    canvas_break_min_width: bpy.props.FloatProperty(
        name = 'Min Width',
        description = 'Minimum canvas width the object stay visible',
        default = 0,
        min = 0,
        step = 100,
        precision = 1,
        options = NO_ANIM_OPTS,
        subtype = 'PIXEL'
    )

    canvas_break_max_width: bpy.props.FloatProperty(
        name = 'Max Width',
        description = 'Maximum canvas width the object stay visible',
        default = math.inf,
        min = 0,
        step = 100,
        precision = 1,
        options = NO_ANIM_OPTS,
        subtype = 'PIXEL'
    )

    canvas_break_min_height: bpy.props.FloatProperty(
        name = 'Min Height',
        description = 'Minimum canvas height the object stay visible',
        default = 0,
        min = 0,
        precision = 1,
        options = NO_ANIM_OPTS,
        subtype = 'PIXEL'
    )

    canvas_break_max_height: bpy.props.FloatProperty(
        name = 'Max Height',
        description = 'Maximum canvas height the object stay visible',
        default = math.inf,
        min = 0,
        precision = 1,
        options = NO_ANIM_OPTS,
        subtype = 'PIXEL'
    )

    canvas_break_orientation: bpy.props.EnumProperty(
        name = 'Orientation',
        description = 'Screen orientation the object stay visible',
        default = 'ALL',
        items = [
            ('PORTRAIT', 'Portrait', 'Portrait orientation', 2),
            ('LANDSCAPE', 'Landscape', 'Landscape orientation', 1),
            ('ALL', 'All', 'Both landscape and portrait orientation', 0)
        ],
        options = NO_ANIM_OPTS
    )

def orbitTargetUpdate(self, context):
    utils.updateOrbitCameraView(context.object, context.scene)

class V3DCameraSettings(bpy.types.PropertyGroup):

    controls: bpy.props.EnumProperty(
        name = 'Controls',
        description = 'Camera controls type',
        default = 'ORBIT',
        items = [
            ('ORBIT', 'Orbit', 'Move camera around a target', 2),
            ('FLYING', 'Flying', 'Flying camera', 1),
            ('FIRST_PERSON', 'First-Person', 'First-person control mode', 3),
            ('NONE', 'No controls', 'Disable camera controls', 0)
        ],
        options = NO_ANIM_OPTS
    )

    enable_pan: bpy.props.BoolProperty(
        name = 'Allow Panning',
        description = 'Allow camera panning',
        default = True,
        options = NO_ANIM_OPTS
    )

    rotate_speed: bpy.props.FloatProperty(
        name = 'Rotation Speed',
        description = 'Camera rotation speed factor',
        default = 1,
        options = NO_ANIM_OPTS
    )

    move_speed: bpy.props.FloatProperty(
        name = 'Movement Speed',
        description = 'Camera movement speed factor',
        default = 1,
        options = NO_ANIM_OPTS
    )

    orbit_min_distance: bpy.props.FloatProperty(
        name = 'Min Dist',
        description = 'Orbit camera minimum distance (perspective camera)',
        default = 0,
        options = NO_ANIM_OPTS
    )

    orbit_max_distance: bpy.props.FloatProperty(
        name = 'Max Dist',
        description = 'Orbit camera maximum distance (perspective camera)',
        default = 100,
        options = NO_ANIM_OPTS
    )

    orbit_min_zoom: bpy.props.FloatProperty(
        name = 'Min Zoom',
        description = 'Orbit camera minimum zoom (orthographic camera)',
        default = 0.01,
        min = 0,
        precision = 3,
        step = 1,
        options = NO_ANIM_OPTS
    )

    orbit_max_zoom: bpy.props.FloatProperty(
        name = 'Max Zoom',
        description = 'Orbit camera maximum zoom (orthographic camera)',
        default = 100,
        min = 0,
        precision = 1,
        options = NO_ANIM_OPTS
    )

    orbit_min_polar_angle: bpy.props.FloatProperty(
        name = 'Min Angle',
        description = 'Orbit camera minimum polar (vertical) angle',
        default = 0,
        subtype = 'ANGLE',
        unit = 'ROTATION',
        options = NO_ANIM_OPTS
    )

    orbit_max_polar_angle: bpy.props.FloatProperty(
        name = 'Max Angle',
        description = 'Orbit camera maximum polar (vertical) angle',
        default = math.pi,
        subtype = 'ANGLE',
        unit = 'ROTATION',
        options = NO_ANIM_OPTS
    )

    orbit_min_azimuth_angle: bpy.props.FloatProperty(
        name = 'Min Angle',
        description = 'Orbit camera minimum azimuth (horizontal) angle',
        default = 0,
        subtype = 'ANGLE',
        unit = 'ROTATION',
        options = NO_ANIM_OPTS
    )

    orbit_max_azimuth_angle: bpy.props.FloatProperty(
        name = 'Max Angle',
        description = 'Orbit camera maximum azimuth (horizontal) angle',
        default = 2 * math.pi,
        subtype = 'ANGLE',
        unit = 'ROTATION',
        options = NO_ANIM_OPTS
    )

    orbit_target_object: bpy.props.PointerProperty(
        type = bpy.types.Object,
        name = 'Target Object',
        description = "Object which center is used as the camera's target point",
        options = NO_ANIM_OPTS,
        update = orbitTargetUpdate
    )

    orbit_target: bpy.props.FloatVectorProperty(
        name = 'Target',
        description = 'Target point for orbit camera',
        default = (0.0, 0.0, 0.0),
        precision = 3,
        subtype = 'XYZ',
        size = 3,
        options = NO_ANIM_OPTS,
        update = orbitTargetUpdate
    )

    fps_collision_material: bpy.props.PointerProperty(
        type = bpy.types.Material,
        name = 'Collision Material',
        description = 'First-person control collision material (floor and walls)',
        options = NO_ANIM_OPTS
    )

    fps_gaze_level: bpy.props.FloatProperty(
        name = 'Gaze Level',
        description = 'First-person gaze (head) level',
        default = 1.7,
        options = NO_ANIM_OPTS
    )

    fps_story_height: bpy.props.FloatProperty(
        name = 'Story Height',
        description = 'First-person story height, specify proper value for multi-story buildings',
        default = 3,
        options = NO_ANIM_OPTS
    )

    enable_pointer_lock: bpy.props.BoolProperty(
        name = 'Enable PointerLock',
        description = 'Enable PointerLock to capture the mouse pointer',
        default = False,
        options = NO_ANIM_OPTS
    )


class V3DShadowSettings(bpy.types.PropertyGroup):
    """Shadow settings are part of light settings"""

    radius: bpy.props.FloatProperty(
        name = 'Radius',
        description = ('Shadow map blur radius. Doesn\'t apply to "Basic" and '
                '"Bilinear" shadow maps'),
        default = 1,
        min = 0,
        options = NO_ANIM_OPTS
    )

    esm_exponent: bpy.props.FloatProperty(
        name = 'Exponent',
        description = ('Exponential Shadow Map bias. Helps reducing light '
                'leaking artifacts. Applies only to ESM shadow maps'),
        default = 2.5,
        min = 1,
        max = 10000,
        options = NO_ANIM_OPTS
    )

class V3DLightSettings(bpy.types.PropertyGroup):
    shadow: bpy.props.PointerProperty(
        name = 'Shadow Settings',
        type = V3DShadowSettings
    )

class V3DMaterialSettings(bpy.types.PropertyGroup):

    render_side: bpy.props.EnumProperty(
        name='Render Side',
        description = 'Which side of geometry will be rendered',
        default = 'FRONT',
        items = [
            ('DOUBLE', 'Double-sided', 'Render both sides (reduced performance)'),
            ('BACK', 'Back Side', 'Render back side (better performance)'),
            ('FRONT', 'Front Side', 'Render front side (better performance, default)'),
        ],
        options = NO_ANIM_OPTS
    )

    depth_write: bpy.props.BoolProperty(
        name = 'Depth Write',
        description = 'Write to depth buffer. Disable it to fix various transparency sorting issues',
        default = True,
        options = NO_ANIM_OPTS
    )

    depth_test: bpy.props.BoolProperty(
        name = 'Depth Test',
        description = 'Perform depth test. Disable it to render the material above all objects',
        default = True,
        options = NO_ANIM_OPTS
    )

    dithering: bpy.props.BoolProperty(
        name = 'Dithering',
        description = 'Apply color dithering to eliminate banding artefacts',
        default = False,
        options = NO_ANIM_OPTS
    )

    gltf_compat: bpy.props.BoolProperty(
        name = 'glTF 2.0 compatible',
        description = 'Force material to be compatible with glTF 2.0 standard',
        default = False,
        options = NO_ANIM_OPTS
    )

class V3DTextureSettings(bpy.types.PropertyGroup):
    anisotropy: bpy.props.EnumProperty(
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

class V3DTextureNoiseSettings(bpy.types.PropertyGroup):
    falloff_factor: bpy.props.FloatProperty(
        name = 'Falloff Factor',
        description = 'How much the noise falls off with distance and for acute angles',
        min = 0,
        max = 1,
        default = 0,
        precision = 2,
        step = 0.01,
        options = NO_ANIM_OPTS
    )

    dispersion_factor: bpy.props.FloatProperty(
        name = 'Strength Factor',
        description = 'Noise strength factor',
        min = 0,
        max = 1,
        default = 1,
        precision = 2,
        step = 0.01,
        options = NO_ANIM_OPTS
    )

class V3DImageSettings(bpy.types.PropertyGroup):
    compression_method: bpy.props.EnumProperty(
        name = 'Compression Method',
        description = 'Texture compression method',
        default = 'AUTO',
        items = [
            ('AUTO', 'Auto', 'Detect and apply best compression algorithm'),
            ('UASTC', 'UASTC', 'Force UASTC compression algorithm which offers higher quality'),
            ('ETC1S', 'ETC1S', 'Use ETC1S compression algorithm which offers better compression'),
            ('DISABLE', 'Disable', 'Disable texture compression'),
        ],
        options = NO_ANIM_OPTS
    )

class V3DLineRenderingSettings(bpy.types.PropertyGroup):

    enable: bpy.props.BoolProperty(
        name = 'Enable Line Rendering',
        description = 'Render the object as constant-width lines',
        default = False,
        options = NO_ANIM_OPTS
    )

    color: bpy.props.FloatVectorProperty(
        name = 'Line Color',
        description = 'Line color',
        default = (1.0, 1.0, 1.0),
        subtype = 'COLOR',
        size = 3,
        min = 0,
        soft_max = 1,
        options = NO_ANIM_OPTS
    )

    width: bpy.props.FloatProperty(
        name = 'Line Width (px)',
        description = 'Line width in pixels',
        default = 1,
        min = 0,
        options = NO_ANIM_OPTS
    )

class V3DCurveSettings(bpy.types.PropertyGroup):

    line_rendering_settings: bpy.props.PointerProperty(
        name = "Line Rendering Settings",
        type = V3DLineRenderingSettings
    )

class V3DMeshSettings(bpy.types.PropertyGroup):

    line_rendering_settings: bpy.props.PointerProperty(
        name = "Line Rendering Settings",
        type = V3DLineRenderingSettings
    )

class V3DCollectionSettings(bpy.types.PropertyGroup):

    enable_export: bpy.props.BoolProperty(
        name = 'Enable Collection Export',
        description = 'Allow export of the collection\'s objects',
        default = True,
        options = NO_ANIM_OPTS
    )

class V3DLightProbeSettings(bpy.types.PropertyGroup):

    use_custom_influence: bpy.props.BoolProperty(
        name = 'Custom Influence',
        description = ('This group of options is used for selecting objects '
                'that will be affected by this lightprobe. The Influence '
                'Collection option (if set to a non-empty value) will be used '
                'instead of the Type and Radius/Distance general probe settings'),
        options = NO_ANIM_OPTS
    )

    influence_collection: bpy.props.PointerProperty(
        type = bpy.types.Collection,
        name = 'Influence Collection',
        description = 'Objects affected by the lightprobe',
        options = NO_ANIM_OPTS
    )

    invert_influence_collection: bpy.props.BoolProperty(
        name = 'Invert Collection',
        description = 'Invert influence collection',
        options = NO_ANIM_OPTS
    )

def register():
    bpy.utils.register_class(V3DCollectionSettings)
    bpy.utils.register_class(V3DExportSettings)
    bpy.utils.register_class(V3DWorldSettings)
    bpy.utils.register_class(V3DOutlineSettings)
    bpy.utils.register_class(V3DSceneSettings)
    bpy.utils.register_class(V3DObjectSettings)
    bpy.utils.register_class(V3DCameraSettings)
    bpy.utils.register_class(V3DShadowSettings)
    bpy.utils.register_class(V3DLightSettings)
    bpy.utils.register_class(V3DMaterialSettings)
    bpy.utils.register_class(V3DTextureSettings)
    bpy.utils.register_class(V3DTextureNoiseSettings)
    bpy.utils.register_class(V3DImageSettings)
    bpy.utils.register_class(V3DLineRenderingSettings)
    bpy.utils.register_class(V3DCurveSettings)
    bpy.utils.register_class(V3DMeshSettings)
    bpy.utils.register_class(V3DLightProbeSettings)

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

    bpy.types.Light.v3d = bpy.props.PointerProperty(
        name = "Verge3D light settings",
        type = V3DLightSettings
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

    bpy.types.ShaderNodeTexNoise.v3d = bpy.props.PointerProperty(
        name = "Verge3D noise texture settings",
        type = V3DTextureNoiseSettings
    )

    bpy.types.Image.v3d = bpy.props.PointerProperty(
        name = "Verge3D image settings",
        type = V3DImageSettings
    )

    bpy.types.Curve.v3d = bpy.props.PointerProperty(
        name = "Verge3D curve settings",
        type = V3DCurveSettings
    )

    bpy.types.Mesh.v3d = bpy.props.PointerProperty(
        name = "Verge3D mesh settings",
        type = V3DMeshSettings
    )

    bpy.types.Collection.v3d = bpy.props.PointerProperty(
        name = "Verge3D collection settings",
        type = V3DCollectionSettings
    )

    bpy.types.LightProbe.v3d = bpy.props.PointerProperty(
        name = "Verge3D lightprobe settings",
        type = V3DLightProbeSettings
    )


def unregister():
    bpy.utils.unregister_class(V3DImageSettings)
    bpy.utils.unregister_class(V3DTextureSettings)
    bpy.utils.unregister_class(V3DTextureNoiseSettings)
    bpy.utils.unregister_class(V3DMaterialSettings)
    bpy.utils.unregister_class(V3DLightSettings)
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
    bpy.utils.unregister_class(V3DCollectionSettings)
    bpy.utils.unregister_class(V3DLightProbeSettings)

    del bpy.types.Material.v3d
    del bpy.types.Light.v3d
    del bpy.types.Curve.v3d
    del bpy.types.Mesh.v3d
    del bpy.types.Camera.v3d
    del bpy.types.Object.v3d
    del bpy.types.Scene.v3d_export
    del bpy.types.Scene.v3d
    del bpy.types.World.v3d
    del bpy.types.Collection.v3d
    del bpy.types.LightProbe.v3d
