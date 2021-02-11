# GLSL Generator

import binascii, collections, inspect, os, re, sys

from pyosl.ast import Node

variables = {}
functions = {}

STDLIB_FUNCTIONS = {
    'radians': ('type', 'type'),
    'degrees': ('type', 'type'),
    'cos': ('type', 'type'),
    'sin': ('type', 'type'),
    'tan': ('type', 'type'),
    'sincos': ('type', '', 'type'),
    'acos': ('type', 'type'),
    'asin': ('type', 'type'),
    'atan': ('type', 'type'),
    'atan2': ('type', 'type', 'type'),
    'cosh': ('type', 'type'),
    'sinh': ('type', 'type'),
    'tanh': ('type', 'type'),
    'pow': ('type', 'type', 'type'),
    'exp': ('type', 'type'),
    'exp2': ('type', 'type'),
    'expm1': ('type', 'type'),
    'log': ('type', 'type'),
    'log2': ('type', 'type'),
    'log10': ('type', 'type'),
    'log': ('type', 'type', 'float'),
    'logb': ('type', 'type'),
    'sqrt': ('type', 'type'),
    'inversesqrt': ('type', 'type'),
    'hypot': ('float', 'float', 'float', 'float'),
    'abs': ('type', 'type'),
    'fabs': ('type', 'type'),
    'sign': ('type', 'type'),
    'floor': ('type', 'type'),
    'ceil': ('type', 'type'),
    'round': ('type', 'type'),
    'trunc': ('type', 'type'),
    'fmod': ('type', 'type', 'type'),
    'mod': ('type', 'type', 'type'),
    'min': ('type', 'type', 'type'),
    'max': ('type', 'type', 'type'),
    'clamp': ('type', 'type', 'type', 'type'),
    'mix': ('type', 'type', 'type', 'type'),
    'select': ('type', 'type', 'type', ''),
    'isnan': ('int', 'float'),
    'isinf': ('int', 'float'),
    'isfinite': ('int', 'float'),
    'erf': ('float', 'float'),
    'erfc': ('float', 'float'),

    'dot': ('float', 'vector', 'vector'),
    'cross': ('vector', 'vector', 'vector'),
    'length': ('float', ''),
    'distance': ('float', 'point', 'point', 'point'),
    'normalize': ('', ''),
    'faceforward': ('vector', 'vector', 'vector', 'vector'),
    'reflect': ('vector', 'vector', 'vector'),
    'refract': ('vector', 'vector', 'vector', 'float'),
    'fresnel': ('void', 'vector', 'normal', 'float', 'float', 'float', 'vector', 'vector'),
    'rotate': ('point', 'point', 'float', 'point', 'point'),
    'transform': ('', '', '', ''),
    'transformu': ('float', 'string', '', 'float'),

    'color': ('color', '', '', '', ''),
    'luminance': ('float', 'color'),
    'blackbody': ('color', 'float'),
    'wavelength_color': ('color', 'float'),
    'transformc': ('color', 'string', '', 'color'),

    'matrix': ('matrix', '', '', '', '',
                         '', '', '', '',
                         '', '', '', '',
                         '', '', '', '', ''),
    'getmatrix': ('int', 'string', 'string', 'matrix'),
    'determinant': ('float', 'matrix'),
    'transpose': ('matrix', 'matrix'),

    'step': ('type', 'type', 'type'),
    'linearstep': ('type', 'type', 'type', 'type'),
    'smoothstep': ('type', 'type', 'type', 'type'),
    'smooth_linearstep': ('type', 'type', 'type', 'type', 'type'),
    'noise': ('', 'string', 'type', 'float'), # not for gabor noise
    'pnoise': ('', 'string', 'type', 'type', 'type', 'float'),
    'snoise': None, # deprecated, converted to noise
    'psnoise': None, # deprecated, converted to pnoise
    'cellnoise': None, # deprecated, converted to noise
    'hashnoise': ('', 'type', 'type'),
    'spline': ('', 'string', 'float', '', '', '', '', ''), # ...
    'splineinverse': ('', 'string', 'float', '', '', '', '', ''), # ...

    'Dx': ('', ''),
    'Dy': ('', ''),
    'Dz': ('', ''),
    'filterwidth': ('', ''),
    'area': ('float', 'point'),
    'calculatenormal': ('vector', 'point'),
    'aastep': ('float', 'float', 'float', 'float'),

    'displace': ('void', '', ''),
    'bump': ('void', '', ''),

    'printf': ('void', 'string', '', '', '', '', ''), # ...
    'format': ('string', 'string', '', '', '', '', ''), # ...
    'error': ('void', 'string', '', '', '', '', ''), # ...
    'warning': ('void', 'string', '', '', '', '', ''), # ...
    'fprintf': ('void', 'string', 'string', '', '', '', '', ''), # ...
    'concat': ('string', 'string', 'string', 'string', 'string'), # ...
    'strlen': ('int', 'string'),
    'startswith': ('int', 'string', 'string'),
    'endswith': ('int', 'string', 'string'),
    'stoi': ('int', 'string'),
    'stof': ('float', 'string'),
    'split': ('int', 'string', 'string', 'string', 'int'),
    'substr': ('string', 'string', 'int', 'int'),
    'getchar': ('int', 'string', 'int'),
    'hash': ('int', 'string'),
    'regex_search': ('int', 'string', '', 'string'),
    'regex_match': ('int', 'string', 'float', 'float', '', '', '', '', ''), # ...

    'texture': ('color', 'string', 'float', 'float', '', '', '', '', ''), # + float
    'texture3d': ('color', 'string', 'point', '', '', '', '', ''), # + float
    'environment': ('color', 'string', 'vector', '', '', '', '', ''), # + float
    'gettextureinfo': ('int', 'string', 'string', ''),
    'pointcloud_search': ('int', 'string', 'point', 'float', 'int', '', '', '', '', ''), # ...
    'pointcloud_get': ('int', 'string', 'int', 'int', 'string', ''),
    'pointcloud_write': ('int', 'string', 'point', 'string', ''),

    'diffuse': ('color', 'normal'),
    'phong': ('color', 'normal', 'float'),
    'oren_nayar': ('color', 'normal', 'float'),
    'ward': ('color', 'normal', 'vector', 'float', 'float'),
    'microfacet': ('color', 'string', 'normal', '', '', '', '', ''),
    'reflection': ('color', 'normal', 'float'),
    'refraction': ('color', 'normal', 'float'),
    'transparent': ('color'),
    'translucent': ('color'),

    'isotropic': ('color'),
    'henyey greenstein': ('color', 'float'),
    'absorption': ('color'),

    'emission': ('color'),
    'background': ('color'),

    'holdout': ('color'),
    'debug': ('color', 'string'),

    'getattribute': ('int', 'string', '', '', ''),
    'setmessage': ('void', 'string', ''),
    'getmessage': ('int', 'string', '', ''),
    'surfacearea': ('float'),
    'raytype': ('int', 'string'),
    'backfacing': ('int'),
    'isconnected': ('int', ''),
    'isconstant': ('int', ''),

    'dict_find': ('int', '', 'string'),
    'dict_next': ('int', 'int'),
    'dict_value': ('int', 'int', 'string', ''),
    'trace': ('int', 'point', 'vector', '', '', '', '', ''), # ...

    'arraylength': ('int', ''),
    'exit': ('void')
}

STRING_CONSTANTS = {
    'alpha': 'OSL_ALPHA',
    'anisotropic': 'OSL_ANISOTROPIC',
    'averagealpha': 'OSL_AVERAGEALPHA',
    'averagecolor': 'OSL_AVERAGECOLOR',
    'bandwidth': 'OSL_BANDWIDTH',
    'black': 'OSL_BLACK',
    'bezier': 'OSL_BEZIER',
    'blur': 'OSL_BLACK',
    'bspline': 'OSL_BSPLINE',
    'camera': 'OSL_CAMERA',
    'camera:resolution': 'OSL_CAMERA_RESOLUTION',
    'camera:pixelaspect': 'OSL_CAMERA_PIXELASPECT',
    'camera:projection': 'OSL_CAMERA_PROJECTION',
    'camera:fov': 'OSL_CAMERA_FOV',
    'camera:clip_near': 'OSL_CAMERA_CLIP_NEAR',
    'camera:clip_far': 'OSL_CAMERA_CLIP_FAR',
    'camera:clip': 'OSL_CAMERA_CLIP',
    'camera:shutter_open': 'OSL_CAMERA_SHUTTER_OPEN',
    'camera:shutter_close': 'OSL_CAMERA_SHUTTER_CLOSE',
    'camera:shutter': 'OSL_CAMERA_SHUTTER',
    'camera:screen_window': 'OSL_CAMERA_SCREEN_WINDOW',
    'catmull-rom': 'OSL_CATMULL_ROM',
    'cell': 'OSL_CELL',
    'channels': 'OSL_CHANNELS',
    'clamp': 'OSL_CLAMP',
    'color': 'OSL_COLOR',
    'constant': 'OSL_CONSTANT',
    'common': 'OSL_COMMON',
    'datawindow': 'OSL_DATAWINDOW',
    'default': 'OSL_DEFAULT',
    'displaywindow': 'OSL_DISPLAYWINDOW',
    'distance': 'OSL_DISTANCE',
    'diffuse': 'OSL_DIFFUSE',
    'direction': 'OSL_DIRECTION',
    'do_filter': 'OSL_DO_FILTER',
    'errormessage': 'OSL_ERRORMESSAGE',
    'exists': 'OSL_EXISTS',
    'fill': 'OSL_FILL',
    'firstchannel': 'OSL_FIRSTCHANNEL',
    'gabor': 'OSL_GABOR',
    'geom:name': 'OSL_GEOM_NAME',
    'glossy': 'OSL_GLOSSY',
    'hash': 'OSL_HASH',
    'hermite': 'OSL_HERMITE',
    'hit': 'OSL_HIT',
    'hitdist': 'OSL_HITDIST',
    'hsl': 'OSL_HSL',
    'hsv': 'OSL_HSV',
    'impulses': 'OSL_IMPULSES',
    'index': 'OSL_INDEX',
    'interp': 'OSL_INTERP',
    'linear': 'OSL_LINEAR',
    'mirror': 'OSL_MIRROR',
    'missingalpha': 'OSL_MISSINGALPHA',
    'missingcolor': 'OSL_MISSINGCOLOR',
    'NDC': 'OSL_NDC',
    'normal': 'OSL_NORMAL',
    'object': 'OSL_OBJECT',
    'osl:version': 'OSL_OSL_VERSION',
    'periodic': 'OSL_PERIODIC',
    'perlin': 'OSL_PERLIN',
    'position': 'OSL_POSITION',
    'raster': 'OSL_RASTER',
    'reflection': 'OSL_REFLECTION',
    'refraction': 'OSL_REFRACTION',
    'resolution': 'OSL_RESOLUTION',
    'rgb': 'OSL_RGB',
    'rwrap': 'OSL_RWRAP',
    'screen': 'OSL_SCREEN',
    'shader': 'OSL_SHADER',
    'shadow': 'OSL_SHADOW',
    'shader:groupname': 'OSL_SHADER_GROUPNAME',
    'shader:layername': 'OSL_SHADER_LAYERNAME',
    'shader:shadername': 'OSL_SHADER_SHADERNAME',
    'simple': 'OSL_SIMPLEX',
    'subimage': 'OSL_SUBIMAGE',
    'subimages': 'OSL_SUBIMAGES',
    'swrap': 'OSL_SWRAP',
    'textureformat': 'OSL_TEXTUREFORMAT',
    'time': 'OSL_TIME',
    'trace': 'OSL_TRACE',
    'type': 'OSL_TYPE',
    'twrap': 'OSL_TWRAP',
    'uperlin': 'OSL_UPERLIN',
    'usimplex': 'OSL_USIMPLEX',
    'width': 'OSL_WIDTH',
    'world': 'OSL_WORLD',
    'worldtocamera': 'OSL_WORLDTOCAMERA',
    'worldtoscreen': 'OSL_WORLDTOSCREEN',
    'wrap': 'OSL_WRAP',
    'YIQ': 'OSL_YIQ',
    'XYZ': 'OSL_XYZ',
    'xyY': 'OSL_XYY',
    '': 'OSL_EMPTY',
    ' ': 'OSL_EMPTY'
}

MATH_CONSTANTS = {
    'M_PI': 'float',
    'M_PI_2': 'float',
    'M_PI_4': 'float',
    'M_2_PI': 'float',
    'M_2PI': 'float',
    'M_4PI': 'float',
    'M_2_SQRTPI': 'float',
    'M_E': 'float',
    'M_LN2': 'float',
    'M_LN10': 'float',
    'M_LOG2E': 'float',
    'M_LOG10E': 'float',
    'M_SQRT2': 'float',
    'M_SQRT1_2': 'float'
}

# to preserve shader parameters order
GLOBAL_VARIABLES = collections.OrderedDict([
    ('P', 'point'),
    ('I', 'vector'),
    ('N', 'normal'),
    ('Ng', 'normal'),
    ('u', 'float'),
    ('v', 'float'),
    ('dPdu', 'vector'),
    ('dPdv', 'vector'),
    ('Ps', 'point'),
    ('time', 'float'),
    ('dtime', 'float'),
    ('dPdtime', 'vector'),
    ('Ci', 'color')
])

def join_toks(array, sep=''):
    array = list(filter(lambda i: i != '', array))
    return sep.join(array)

def indent_lines(string, indent=4):

    ind_lines = []
    for l in string.splitlines():
        ind_lines.append(' ' * indent + l)

    return '\n'.join(ind_lines)

def g_shader_file(n):
    return join_toks(n)

def g_global_declaration(n):
    return n[0]

def g_shader_declaration(n):
    return '''void {0}({1}) {{
{2}
}}
'''.format(n[1], n[3], indent_lines(n[4]))

def g_shadertype(n):
    return ''

def g_shader_formal_params_opt(n):
    return n[0] if n[0] is not None else ''

def g_shader_formal_params(n):
    return join_toks(n, ', ')

def g_shader_formal_param(n):
    # no initializers
    if len(n) == 5:
        return join_toks(n[0:3], ' ')
    else:
        return join_toks(n[0:4], ' ')

def g_metadata_block_opt(n):
    return ''

def g_metadata_block(n):
    return ''

def g_metadata_list(n):
    return ''

def g_metadata(n):
    return ''

def g_function_declaration(n):
    return '''{0} {1}({2}) {{
{3}
}}
'''.format(n[0], n[1], n[2], indent_lines(n[3]))

def g_function_formal_params_opt(n):
    return n if n else ''

def g_function_formal_params(n):
    return join_toks(n, ', ')

def g_function_formal_param(n):
    return join_toks(n, ' ')

def g_outputspec(n):
    return n[0]

def g_struct_declaration(n):
    return '''struct {0} {{
{1}
}};
'''.format(n[0], indent_lines(n[1]))

def g_field_declarations(n):
    return join_toks(n, '\n')

def g_field_declaration(n):
    return '{0} {1};'.format(n[0], n[1])

def g_typed_field_list(n):
    return join_toks(n, ', ')

def g_typed_field(n):
    if n[1] != '':
        return '{0} {1}'.format(n[0], n[1])
    else:
        return n[0]

def g_local_declaration(n):
    return ''

def g_arrayspec_opt(n):
    return n[0] if n[0] is not None else ''

def g_arrayspec(n):
    if len(n) == 1:
        return '[{0}]'.format(n[0])
    else:
        return '[]'

def g_variable_declaration(n):
    return '{0} {1};'.format(n[0], n[1])

def g_def_expressions(n):
    return join_toks(n, ', ')

def g_def_expression(n):
    if len(n) == 2:
        if n[1] != '':
            return '{0} {1}'.format(n[0], n[1])
        else:
            return '{0}'.format(n[0])
    else:
        return '{0}{1} {2}'.format(n[0], n[1], n[2])

def g_initializer_opt(n):
    return '' if n[0] == None else n[0]

def g_initializer(n):
    return '= ' + n[0]

def g_initializer_list_opt(n):
    return n[0] if n[0] is not None else ''

def g_initializer_list(n):
    return '= ' + n[0]

def g_compound_initializer(n):
    #return 'int[]( {0} )'.format(n[0])
    return '{{ {0} }}'.format(n[0])

def g_init_expression_list(n):
    return join_toks(n, ', ')

def g_init_expression(n):
    return n[0]

def g_typespec(n):
    return n[0]

def g_simple_typename(n):
    return n[0]

def g_statement_list_opt(n):
    return n[0] if n[0] is not None else ''

def g_statement_list(n):
    return join_toks(n, '\n')

def g_statement(n):
    return n[0]

def g_statement_semi(n):
    return n[0] + ';'

def g_scoped_statements(n):
    return '''{{
{0}
}}'''.format(indent_lines(n[0]))

def g_conditional_statement(n):

    # improve indentation
    if '{' not in n[1]:
        n[1] = '\n    ' + n[1];
    else:
        n[1] = ' ' + n[1];

    if len(n) == 2:
        return 'if ({0}){1}'.format(n[0], n[1])
    else:
        # improve last 'else' indentation

        if '{' not in n[1]:
            n[1] = n[1] + '\n'
        else:
            n[1] = n[1] + ' '

        if '{' not in n[2] and 'if' not in n[2]:
            n[2] = '\n    ' + n[2];
        else:
            n[2] = ' ' + n[2];

        return 'if ({0}){1}else{2}'.format(n[0], n[1], n[2])

def g_loop_statement_while(n):
    return '''while ({0}) {1}'''.format(n[0], n[1])

def g_loop_statement_do_while(n):
    return '''do {0} while ({1});'''.format(n[0], n[1])

def g_loop_statement_for(n):
    return '''for ({0} {1}; {2}) {3}'''.format(n[0], n[1], n[2], n[3])

def g_for_init_statement_opt(n):
    return n[0] if n[0] is not None else ''

def g_for_init_statement(n):
    return n[0]

def g_for_init_statement_semi(n):
    return '{0};'.format(n[0])

def g_loopmod_statement(n):
    return '{0};'.format(n[0])

def g_return_statement(n):
    if n[0] != '':
        return 'return {0};'.format(n[0])
    else:
        return 'return;'

def g_expression_list(n):
    return join_toks(n, ', ')

def g_expression_opt(n):
    return n[0] if n[0] is not None else ''

def g_expression(n):
    # TODO
    return join_toks(n)

def g_expression_paren(n):
    return '({0})'.format(n[0])

def g_compound_expression_opt(n):
    return n[0] if n[0] is not None else ''

def g_compound_expression(n):
    return join_toks(n, ', ')

def g_variable_lvalue(n):
    return join_toks(n)

def g_variable_lvalue_brackets(n):
    return '{0}[{1}]'.format(n[0], n[1])

def g_variable_lvalue_period(n):
    return '{0}.{1}'.format(n[0], n[1])

def g_variable_ref(n):
    return join_toks(n)

def g_binary_op(n):
    return '{0} {1} {2}'.format(n[0], n[1], n[2])

def g_unary_op(n):
    return n[0]

def g_incdec_op(n):
    return n[0]

def g_type_constructor(n):
    return '{0}({1})'.format(n[0], n[1])

def g_function_call(n):
    return '{0}({1})'.format(n[0], n[1])

def g_function_args_opt(n):
    return n[0] if n[0] is not None else ''

def g_function_args(n):
    return join_toks(n, ', ')

def g_assign_expression(n):
    return join_toks(n, '')

def g_assign_op(n):
    return ' {0} '.format(n[0])

def g_ternary_expression(n):
    return '{0} ? {1} : {2}'.format(n[0], n[1], n[2])

def g_typecast_expression(n):
    return '({0}){1}'.format(n[0], n[1])

def g_sign(n):
    return ''

def g_integer(n):
    return n[0]

def g_floating_point(n):
    return n[0]

def g_number(n):
    return n[0]

def g_stringliteral(n):
    return n[0]

def g_identifier(n):
    return n[0]

def g_empty(n):
    return ''

def g_raw_code(n):
    return n[0]

def g_default(n):
    print('Unsupported AST item:', n)
    return ''

def traverse_ast_visitors(ast, visitors):
    if isinstance(ast, Node):
        type = ast.type
        n_resolved = [traverse_ast_visitors(i, visitors) for i in ast.children]
        return visitors[type if type in visitors else 'default'](n_resolved)
    else:
        return ast if ast is not None else ''


def string_to_osl_const(s):
    s = s.strip('"')
    h = binascii.crc_hqx(s.encode(), 0)

    if s in STRING_CONSTANTS:
        return STRING_CONSTANTS[s]
    else:
        return str(h)

def get_all_string_constants():

    dest = {}

    for s in STRING_CONSTANTS:
        dest[STRING_CONSTANTS[s]] = binascii.crc_hqx(s.encode(), 0)

    return dest

def convert_types(ast):

    global variables
    variables = ast.get_variables()
    variables.update(GLOBAL_VARIABLES)
    variables.update(MATH_CONSTANTS)

    global functions
    functions = ast.get_functions()
    functions.update(STDLIB_FUNCTIONS)

    def cb_add_type_converters(node):
        type = node.type
        childs = node.children

        if type == 'assign-expression':
            lvalue_node = node.get_child(0)
            rvalue_node = node.get_child(2)

            lvalue_type = resolve_expr_type(lvalue_node)
            rvalue_type = resolve_expr_type(rvalue_node)

            if lvalue_type != rvalue_type:
                node.set_child(2, typecast(lvalue_type, rvalue_node))

        elif type == 'conditional-statement' or type == 'loop-statement-while':
            expr_node = node.get_child(0)
            if resolve_expr_type(expr_node) != 'bool':
                node.set_child(0, typecast('bool', expr_node))

        elif type == 'def-expression':
            idt = node.get_child(0)
            idt_type = variables[idt]

            if len(node.children) == 2:

                intz = node.get_child(1)

                if intz and resolve_expr_type(intz) != idt_type:
                    node_init = node.get_child('initializer')
                    node_init.set_child(0, typecast(idt_type, node_init.get_child(0)))

        elif type == 'function-call':
            resolve_expr_type(node)

        elif type == 'loop-statement-do-while':
            expr_node = node.get_child(1)
            if resolve_expr_type(expr_node) != 'bool':
                node.set_child(1, typecast('bool', expr_node))

        elif type == 'loop-statement-for':
            expr_node = node.get_child(1)
            if expr_node and resolve_expr_type(expr_node) != 'bool':
                node.set_child(1, typecast('bool', expr_node))

        elif type == 'ternary-expression':
            cond_node = node.get_child(0)
            if resolve_expr_type(cond_node) != 'bool':
                node.set_child(0, typecast('bool', cond_node))

        elif type == 'typecast-expression':
            # no need to typecast, just process children
            resolve_expr_type(node.get_child(1))

        elif type == 'type-constructor':
            # no need to typecast, just process children
            resolve_expr_type(node.get_child(1))


    ast.traverse_nodes(cb_add_type_converters)


def replace_types(ast):

    def cb_replace_types(node):
        type = node.type
        childs = node.children

        if type == 'simple-typename':
            if childs[0] in ['point', 'vector', 'normal', 'color']:
                childs[0] = 'vec3'
            elif childs[0] == 'string':
                childs[0] = 'int'
            elif childs[0] == 'matrix':
                childs[0] = 'mat4'

        elif type == 'outputspec':
            if childs[0] == 'output':
                childs[0] = 'out'

        elif type == 'stringliteral':
            node.type = 'integer'
            node.set_child(0, string_to_osl_const(node.get_child(0)))

        elif type == 'typecast-expression':
            node.type = 'type-constructor'

        elif type == 'compound-initializer':
            decl_node = node.find_ancestor_node(ast, 'variable-declaration')
            if decl_node:
                type = resolve_expr_type(decl_node.get_child('typespec'))

                init_expr_list = node.get_child('init-expression-list')

                node.type = 'type-constructor'
                # NOTE: hack, identifier-like argument
                node.set_child(0, Node('typespec', type + '[]'))
                node.append(init_expr_list)

    ast.traverse_nodes(cb_replace_types)


def add_shader_params(ast):

    glob_vars = find_global_variables(ast)

    for var_type, var_name in reversed(glob_vars):
        add_shader_param(ast, var_type, var_name)

    # also add texture param
    call_nodes = ast.find_nodes('function-call')

    for cn in call_nodes:
        name = cn.get_child(0)

        if name == 'texture':
            add_shader_param(ast, 'sampler2D', 'Image')


def find_global_variables(ast):

    dest = []

    sts_node = ast.get_child('shader-declaration').get_child('statement-list')

    for var_name in GLOBAL_VARIABLES:
        if sts_node.uses_variable(var_name):
            var_type = GLOBAL_VARIABLES[var_name]
            dest.append((var_type, var_name))

    return dest


def add_shader_param(ast, type, name):
    outspec_node = Node('outputspec', None)
    typespec_node = Node('typespec', Node('simple-typename', type))

    param_node = Node('shader-formal-param', outspec_node, typespec_node, name, None, None)

    params_node = ast.get_child('shader-declaration').get_child('shader-formal-params')
    params_node.insert(0, param_node)

def replace_identifiers(ast):

    def cb(node):
        for i in range(node.num_childs()):
            if node.get_child(i) == 'in':
                node.set_child(i, 'inp')

    ast.traverse_nodes(cb)

def replace_global_functions(ast):

    call_nodes = ast.find_nodes('function-call')

    for node in call_nodes:

        name = node.get_child(0)
        args = node.get_child('function-args')

        if name in ['error', 'fprintf', 'printf', 'warning']:
            name = name.replace('error', 'oslError')
            name = name.replace('fprintf', 'oslFPrintf')
            name = name.replace('printf', 'oslPrintf')
            name = name.replace('warning', 'oslWarning')

            # remove args
            node.set_child(1, None)

        elif name == 'log' and args.num_childs() == 2:

            name = 'oslLog2'

        elif name in ['noise', 'pnoise']:

            noise_type = 'float'

            par_node = node.get_ancestor(ast).get_ancestor(ast)
            if par_node:
                if par_node.type == 'typecast-expression':
                    noise_type = resolve_expr_type(par_node)
                else:
                    par_node = par_node.get_ancestor(ast)

                    if par_node.type == 'type-constructor':
                        noise_type = resolve_expr_type(par_node)

            if noise_type in ['point', 'vector', 'normal', 'color']:
                if name == 'noise':
                    name = 'oslNoise3D'
                else:
                    name = 'oslPNoise3D'
            else:
                if name == 'noise':
                    name = 'oslNoise'
                else:
                    name = 'oslPNoise'

        elif name == 'texture':
            # e.g Filename -> Image
            first_arg_var_ref = args.get_child(0).get_child('variable-ref')
            if first_arg_var_ref:
                first_arg_var_ref.find_node('variable-lvalue').set_child(0, 'Image')

            name = 'oslTexture'

        elif name == 'transform':
            last_arg_type = resolve_expr_type(args.get_child(-1))

            if last_arg_type in ['vector', 'normal']:
                name = 'oslTransformDir'
            else:
                name = 'oslTransform'

        else:
            name = name.replace('atan2', 'atan')
            name = name.replace('blackbody', 'oslBlackbody')
            name = name.replace('distance', 'oslDistance')
            name = name.replace('endswith', 'oslEndsWith')
            name = name.replace('fabs', 'abs')
            name = name.replace('fmod', 'mod')
            name = name.replace('format', 'oslFormat')
            name = name.replace('getattribute', 'oslGetAttribute')
            name = name.replace('gettextureinfo', 'oslGetTextureInfo')
            name = name.replace('hypot', 'oslHypot')
            name = name.replace('luminance', 'oslLuminance')
            name = name.replace('pow', 'oslPow')
            name = name.replace('raytype', 'oslRayType')
            name = name.replace('rotate', 'oslRotate')
            name = name.replace('startswith', 'oslStartsWith')
            name = name.replace('strlen', 'oslStrLen')
            name = name.replace('substr', 'oslSubStr')
            name = name.replace('transformc', 'oslTransformC')
            name = name.replace('wavelength_color', 'oslWaveLengthColor')

        node.set_child(0, name)

def resolve_expr_type(node):

    type = node.type

    if type == 'binary-op':

        c0 = node.get_child(0)
        c2 = node.get_child(2)

        t0 = resolve_expr_type(c0)
        t2 = resolve_expr_type(c2)

        op = node.get_child(1)

        is_bool_op = True if op in ['&&', '||'] else False
        is_int_op = True if op in ['%', '<<', '>>', '&', '|', '^'] else False

        if is_bool_op:
            if t0 != 'bool':
                node.set_child(0, typecast('bool', c0))
            if t2 != 'bool':
                node.set_child(2, typecast('bool', c2))

        elif is_int_op:
            if t0 != 'int':
                node.set_child(0, typecast('int', c0))
            if t2 != 'int':
                node.set_child(2, typecast('int', c2))

        elif t0 == 'int' and t2 in ['bool', 'float']:
            node.set_child(0, typecast(t2, c0))
        elif t0 in ['bool', 'float'] and t2 == 'int':
            node.set_child(2, typecast(t0, c2))

        elif t0 == 'float' and t2 in ['point', 'vector', 'normal', 'matrix', 'color']:
            node.set_child(0, typecast(t2, c0))
        elif t0 in ['point', 'vector', 'normal', 'matrix', 'color'] and t2 == 'float':
            node.set_child(2, typecast(t0, c2))

        if op in ['<', '<=', '>', '>=', '==', '!=', '&&', '||']:
            return 'bool'
        else:
            return resolve_expr_type(node.get_child(0))

    elif type == 'expression':
        if len(node.children) == 2:
            op = node.get_child(0)
            child = node.get_child(1)

            if (op.type == 'unary-op' and (op.get_child(0) == 'not' or op.get_child(0) == '!') and
                    resolve_expr_type(child) != 'bool'):
                node.set_child(1, typecast('bool', child))

            return resolve_expr_type(node.get_child(1))
        else:
            return resolve_expr_type(node.get_child(0))


    elif type == 'floating-point':
        return 'float'

    elif type == 'function-call':
        name = node.get_child(0)
        spec = functions[name]

        # resolve all arguments first
        args = node.get_child('function-args')
        if args:
            new_name = refactor_function_arguments(name, args)
            if new_name != name:
                node.set_child(0, new_name)
                name = new_name
                spec = functions[new_name]

        if spec[0] == 'type' or spec[0] == 'ptype':
            for i in range(args.num_childs()):
                # first argument of the same generic type
                if spec[i+1] == 'type' or spec[i+1] == 'ptype':
                    arg_node = args.get_child(i)
                    arg_type = resolve_expr_type(arg_node)
                    return arg_type
            return 'float'
        elif spec[0] == '':
            return 'float'
        else:
            return spec[0]

    elif type == 'integer':
        return 'int'

    elif type == 'simple-typename':
        return node.get_child(0)

    elif type == 'stringliteral':
        return 'string'

    elif type == 'ternary-expression':
        c1 = node.get_child(1)
        c2 = node.get_child(2)

        t1 = resolve_expr_type(c1)
        t2 = resolve_expr_type(c2)

        if t1 == 'int' and t2 in ['bool', 'float']:
            node.set_child(1, typecast(t2, c1))
        elif t1 in ['bool', 'float'] and t2 == 'int':
            node.set_child(2, typecast(t1, c2))

        elif t1 == 'float' and t2 in ['point', 'vector', 'normal', 'matrix', 'color']:
            node.set_child(1, typecast(t2, c1))
        elif t1 in ['point', 'vector', 'normal', 'matrix', 'color'] and t2 == 'float':
            node.set_child(2, typecast(t1, c2))

        return resolve_expr_type(node.get_child(1))

    elif type == 'typecast-expression':
        return node.get_child(0)

    elif type == 'typespec':
        return node.get_typespec_type()

    elif type == 'type-constructor':
        return resolve_expr_type(node.get_child(0))

    elif type == 'variable-lvalue':
        return variables[node.get_child(0)]

    elif type == 'variable-lvalue-brackets':
        lvalue_type = resolve_expr_type(node.find_node('variable-lvalue'))
        if lvalue_type in ['float', 'int']:
            return lvalue_type
        else:
            return 'float'

    elif type == 'variable-lvalue-period':
        # TODO: need proper child resolving
        return 'float'

    elif type == 'variable-ref':
        return resolve_expr_type(node.get_child(0))

    else:
        return resolve_expr_type(node.get_child(0))

def refactor_function_arguments(name, args):

    new_name = name

    # deprecated noise functions
    if name in ['noise', 'pnoise'] and resolve_expr_type(args.get_child(0)) != 'string':
        args.insert(0, Node('expression', Node('stringliteral', 'uperlin')))
    elif name in ['snoise', 'psnoise']:
        args.insert(0, Node('expression', Node('stringliteral', 'perlin')))
        new_name = name.replace('snoise', 'noise')
    elif name == 'cellnoise':
        args.insert(0, Node('expression', Node('stringliteral', 'cell')))
        new_name = 'noise'

    spec = functions[new_name]

    for i in range(args.num_childs()):
        arg_node = args.get_child(i)
        arg_type = resolve_expr_type(arg_node)

        if spec[i+1] != '' and spec[i+1] != 'type' and arg_type != spec[i+1]:
            args.set_child(i, typecast(spec[i+1], arg_node))

        elif spec[i+1] == 'type' and arg_type == 'int':
            args.set_child(i, typecast('float', arg_node))

    if new_name in ['max', 'min', 'mix', 'mod']:
        c0 = args.get_child(0)
        c1 = args.get_child(1)

        t0 = resolve_expr_type(c0)
        t1 = resolve_expr_type(c1)

        if t0 == 'float' and t1 in ['point', 'vector', 'normal', 'color']:
            args.set_child(0, typecast(t1, c0))
        elif t0 in ['point', 'vector', 'normal', 'color'] and t1 == 'float':
            args.set_child(1, typecast(t0, c1))

    return new_name

def typecast(new_type, expression):
    return Node('type-constructor',
                Node('typespec', Node('simple-typename', new_type)),
                Node('expression-list', expression))

# Public API

def osl_to_glsl(ast):
    add_shader_params(ast)
    convert_types(ast)
    replace_identifiers(ast)
    replace_global_functions(ast)
    replace_types(ast)
    return ast

def generate(ast):

    visitors = {}

    for name, fun in inspect.getmembers(sys.modules[__name__]):
        if inspect.isfunction(fun) and name[:2] == 'g_':
            name = re.sub('_+', '-', re.sub('^g_', '', name))
            visitors[name] = fun

    return traverse_ast_visitors(ast, visitors)

def get_shader_name(ast):
    return ast.get_child('shader-declaration').get_child(1)

def rename_shader(ast, new_name):
    ast.get_child('shader-declaration').set_child(1, new_name)

def insert_raw_code(ast, code, where='shader-begin'):

    if where in ['shader-begin', 'shader-end']:
        smts = ast.get_child('shader-declaration').get_child('statement-list')
        node = Node('raw-code', code)

        if where == 'shader-begin':
            smts.insert(0, node)
        else:
            smts.append(node)


