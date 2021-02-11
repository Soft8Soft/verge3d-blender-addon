# OSL Parser

from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import re, os, sys

from . import osllex

from .ast import Node

import ply.yacc as yacc

# Get the token map
tokens = osllex.tokens

precedence = (
    ('left', 'OR'),
    ('left', 'AND'),
    ('left', 'BITOR'),
    ('left', 'XOR'),
    ('left', 'BITAND'),
    ('left', 'EQ', 'NE'),
    ('left', 'LT', 'LE', 'GT', 'GE'),
    ('left', 'LSHIFT', 'RSHIFT'),
    ('left', 'PLUS', 'MINUS'),
    ('left', 'TIMES', 'DIVIDE', 'MOD'),
    ('right', 'UNARY')
)

# overall structure

def p_shader_file(p):
    '''shader-file : shader-file global-declaration
                   | global-declaration'''
    if len(p) > 2:
        p[0] = p[1]
        p[0].append(p[2])
    else:
        p[0] = Node('shader-file', p[1])

def p_global_declaration(p):
    '''global-declaration : function-declaration
                          | struct-declaration
                          | shader-declaration'''
    p[0] = p[1]

def p_shader_declaration(p):
    '''shader-declaration : shadertype identifier metadata-block-opt LPAREN shader-formal-params RPAREN LBRACE statement-list RBRACE'''
    p[0] = Node('shader-declaration', p[1], p[2], p[3], p[5], p[8])

def p_shadertype(p):
    '''shadertype : DISPLACEMENT
                  | SHADER
                  | SURFACE
                  | VOLUME'''
    p[0] = p[1]

def p_shader_formal_params(p):
    '''shader-formal-params : shader-formal-params COMMA shader-formal-param
                            | shader-formal-param'''
    if len(p) > 2:
        p[0] = p[1]
        p[0].append(p[3])
    else:
        p[0] = Node('shader-formal-params', p[1])

def p_shader_formal_param(p):
    '''shader-formal-param : outputspec typespec identifier initializer metadata-block-opt
                           | outputspec typespec identifier arrayspec initializer-list metadata-block-opt
                           | empty'''
    if len(p) == 6:
        p[0] = Node('shader-formal-param', p[1], p[2], p[3], p[4], p[5])
    elif len(p) == 7:
        p[0] = Node('shader-formal-param', p[1], p[2], p[3], p[4], p[5], [6])
    else:
        p[0] = None

def p_metadata_block_opt(p):
    '''metadata-block-opt : metadata-block
                          | empty'''
    if len(p) > 1:
        p[0] = p[1]
    else:
        p[0] = None

def p_metadata_block(p):
    '''metadata-block : METABEGIN metadata-list RBRACKET RBRACKET'''
    p[0] = p[2]

def p_metadata_list(p):
    '''metadata-list : metadata-list COMMA metadata
                     | metadata'''
    if len(p) > 2:
        p[0] = p[1]
        p[0].append(p[3])
    else:
        p[0] = Node('metadata-list', p[1])

# NOTE: simple-typespec in spec
def p_metadata(p):
    '''metadata : simple-typename identifier initializer
                | empty'''

    if len(p) > 2:
        p[0] = Node('metadata', p[1], p[2], p[3])
    else:
        p[0] = None

# declarations

def p_function_declaration(p):
    '''function-declaration : typespec identifier LPAREN function-formal-params-opt RPAREN LBRACE statement-list RBRACE'''
    p[0] = Node('function-declaration', p[1], p[2], p[4], p[7])

def p_function_formal_params_opt(p):
    '''function-formal-params-opt : function-formal-params
                                  | empty'''
    if len(p) > 1:
        p[0] = p[1]
    else:
        p[0] = None

def p_function_formal_params(p):
    '''function-formal-params : function-formal-params COMMA function-formal-param
                              | function-formal-param'''
    if len(p) > 2:
        p[0] = p[1]
        p[0].append(p[3])
    else:
        p[0] = Node('function-formal-params', p[1])

def p_function_formal_param(p):
    '''function-formal-param : outputspec typespec identifier arrayspec
                             | outputspec typespec identifier'''
    if len(p) == 5:
        p[0] = Node('function-formal-param', p[1], p[2], p[3], p[4])
    else:
        p[0] = Node('function-formal-param', p[1], p[2], p[3])

def p_outputspec(p):
    '''outputspec : OUTPUT
                  | empty'''
    if len(p) > 1:
        p[0] = Node('outputspec', p[1])
    else:
        p[0] = Node('outputspec', None)

def p_struct_declatation(p):
    'struct-declaration : STRUCT identifier LBRACE field-declarations RBRACE SEMI'
    p[0] = Node('struct-declaration', p[2], p[4])

def p_field_declarations(p):
    '''field-declarations : field-declarations field-declaration
                          | field-declaration'''
    if len(p) > 2:
        p[0] = p[1]
        p[0].append(p[2])
    else:
        p[0] = Node('field-declarations', p[1])

def p_field_declaration(p):
    '''field-declaration : typespec typed-field-list SEMI'''
    p[0] = Node('field-declaration', p[1], p[2])

def p_typed_field_list(p):
    '''typed-field-list : typed-field-list COMMA typed-field
                        | typed-field'''
    if len(p) > 2:
        p[0] = p[1]
        p[0].append(p[3])
    else:
        p[0] = Node('typed-field-list', p[1])

def p_typed_field(p):
    'typed-field : identifier arrayspec-opt'
    p[0] = Node('typed-field', p[1], p[2])

def p_local_declaration(p):
    '''local-declaration : function-declaration
                         | variable-declaration'''
    p[0] = p[1]

def p_arrayspec_opt(p):
    '''arrayspec-opt : arrayspec
                     | empty'''
    if len(p) > 1:
        p[0] = p[1]
    else:
        p[0] = None

def p_arrayspec(p):
    '''arrayspec : LBRACKET integer RBRACKET
                 | LBRACKET RBRACKET'''
    if len(p) > 3:
        p[0] = Node('arrayspec', p[2])
    else:
        p[0] = Node('arrayspec')

def p_variable_declaration(p):
    'variable-declaration : typespec def-expressions SEMI'
    p[0] = Node('variable-declaration', p[1], p[2])

def p_def_expressions(p):
    '''def-expressions : def-expressions COMMA def-expression
                       | def-expression'''
    if len(p) > 2:
        p[0] = p[1]
        p[0].append(p[3])
    else:
        p[0] = Node('def-expressions', p[1])

def p_def_expression(p):
    '''def-expression : identifier initializer-opt
                      | identifier arrayspec initializer-list-opt'''
    if len(p) == 3:
        p[0] = Node('def-expression', p[1], p[2])
    else:
        p[0] = Node('def-expression', p[1], p[2], p[3])

def p_initializer_opt(p):
    '''initializer-opt : initializer
                       | empty'''
    if len(p) > 1:
        p[0] = p[1]
    else:
        p[0] = None

def p_initializer(p):
    'initializer : EQUALS expression'
    p[0] = Node('initializer', p[2])

def p_initializer_list_opt(p):
    '''initializer-list-opt : initializer-list
                            | empty'''
    if len(p) > 1:
        p[0] = p[1]
    else:
        p[0] = None

def p_initializer_list(p):
    'initializer-list : EQUALS compound-initializer'
    p[0] = Node('initializer-list', p[2])

def p_compound_initializer(p):
    'compound-initializer : LBRACE init-expression-list RBRACE'
    p[0] = Node('compound-initializer', p[2])

def p_init_expression_list(p):
    '''init-expression-list : init-expression-list COMMA init-expression
                            | init-expression'''
    if len(p) > 2:
        p[0] = p[1]
        p[0].append(p[3])
    else:
        p[0] = Node('init-expression-list', p[1])

def p_init_expression(p):
    '''init-expression : expression
                       | compound-initializer'''
    p[0] = Node('init-expression', p[1])

# NOTE: identifier-structname in spec
def p_typespec(p):
    '''typespec : simple-typename
                | CLOSURE simple-typename
                | identifier'''
    if len(p) == 2:
        p[0] = Node('typespec', p[1])
    else:
        p[0] = Node('typespec', p[2])

def p_simple_typename(p):
    '''simple-typename : COLOR
                       | FLOAT
                       | INT
                       | MATRIX
                       | NORMAL
                       | POINT
                       | STRING
                       | VECTOR
                       | VOID'''
    p[0] = Node('simple-typename', p[1])


# statements

def p_statement_list_opt(p):
    '''statement-list-opt : statement-list
                          | empty'''
    if len(p) > 1:
        p[0] = p[1]
    else:
        p[0] = None

def p_statement_list(p):
    '''statement-list : statement-list statement
                      | statement'''
    if len(p) > 2:
        p[0] = p[1]
        p[0].append(p[2])
    else:
        p[0] = Node('statement-list', p[1])

def p_statement(p):
    '''statement : compound-expression-opt SEMI
                 | scoped-statements
                 | local-declaration
                 | conditional-statement
                 | loop-statement
                 | loopmod-statement
                 | return-statement'''
    if len(p) == 2:
        p[0] = Node('statement', p[1])
    else:
        p[0] = Node('statement-semi', p[1])

def p_scoped_statements(p):
    'scoped-statements : LBRACE statement-list-opt RBRACE'
    p[0] = Node('scoped-statements', p[2])

def p_conditional_statement(p):
    '''conditional-statement : IF LPAREN compound-expression RPAREN statement
                             | IF LPAREN compound-expression RPAREN statement ELSE statement'''
    if len(p) == 6:
        p[0] = Node('conditional-statement', p[3], p[5])
    else:
        p[0] = Node('conditional-statement', p[3], p[5], p[7])

def p_loop_statement(p):
    '''loop-statement : WHILE LPAREN compound-expression RPAREN statement
                      | DO statement WHILE LPAREN compound-expression RPAREN SEMI
                      | FOR LPAREN for-init-statement compound-expression-opt SEMI compound-expression-opt RPAREN statement'''
    if len(p) == 6:
        p[0] = Node('loop-statement-while', p[3], p[5])
    elif len(p) == 7:
        p[0] = Node('loop-statement-do-while', p[2], p[5])
    else:
        p[0] = Node('loop-statement-for', p[3], p[4], p[6], p[8])

def p_for_init_statement(p):
    '''for-init-statement : expression-opt SEMI
                          | variable-declaration'''
    if len(p) != 2:
        p[0] = Node('for-init-statement-semi', p[1])
    else:
        p[0] = Node('for-init-statement', p[1])

def p_loopmod_statement(p):
    '''loopmod-statement : BREAK SEMI
                         | CONTINUE SEMI'''
    p[0] = Node('loopmod-statement', p[1])

def p_return_statement(p):
    'return-statement : RETURN expression-opt SEMI'
    p[0] = Node('return-statement', p[2])


# expressions

def p_expression_list(p):
    '''expression-list : expression-list COMMA expression
                       | expression'''
    if len(p) > 2:
        p[0] = p[1]
        p[0].append(p[3])
    else:
        p[0] = Node('expression-list', p[1])

def p_expression_opt(p):
    '''expression-opt : expression
                      | empty'''
    if len(p) > 1:
        p[0] = p[1]
    else:
        p[0] = None

                  #| expression binary-op expression
def p_expression(p):
    '''expression : number
                  | stringliteral
                  | type-constructor
                  | incdec-op variable-ref
                  | variable-ref incdec-op
                  | unary-op expression %prec UNARY
                  | LPAREN compound-expression RPAREN
                  | binary-op
                  | function-call
                  | assign-expression
                  | ternary-expression
                  | typecast-expression
                  | variable-ref
                  | compound-initializer'''

    if len(p) == 2:
        p[0] = Node('expression', p[1])
    elif len(p) == 3:
        p[0] = Node('expression', p[1], p[2])
    else:
        p[0] = Node('expression-paren', p[2])

def p_compound_expression_opt(p):
    '''compound-expression-opt : compound-expression
                               | empty'''
    if len(p) > 1:
        p[0] = p[1]
    else:
        p[0] = None

def p_compound_expression(p):
    '''compound-expression : compound-expression COMMA expression
                           | expression'''
    if len(p) > 2:
        p[0] = p[1]
        p[0].append(p[3])
    else:
        p[0] = Node('compound-expression', p[1])


def p_variable_lvalue(p):
    '''variable-lvalue : identifier
                       | variable-lvalue LBRACKET expression RBRACKET
                       | variable-lvalue PERIOD identifier'''
    if len(p) == 2:
        p[0] = Node('variable-lvalue', p[1])
    elif len(p) == 5:
        p[0] = Node('variable-lvalue-brackets', p[1], p[3])
    else:
        p[0] = Node('variable-lvalue-period', p[1], p[3])

def p_variable_ref(p):
    'variable-ref : variable-lvalue'
    p[0] = Node('variable-ref', p[1])

def p_binary_op(p):
    '''binary-op : expression TIMES   expression
                 | expression DIVIDE  expression
                 | expression MOD     expression
                 | expression PLUS    expression
                 | expression MINUS   expression
                 | expression LSHIFT  expression
                 | expression RSHIFT  expression
                 | expression LT      expression
                 | expression LE      expression
                 | expression GT      expression
                 | expression GE      expression
                 | expression EQ      expression
                 | expression NE      expression
                 | expression BITAND  expression
                 | expression XOR     expression
                 | expression BITOR   expression
                 | expression AND     expression
                 | expression OR      expression'''
    p[0] = Node('binary-op', p[1], p[2], p[3])

def p_unary_op(p):
    '''unary-op : MINUS
                | PLUS
                | BITNOT
                | NOT'''
    p[0] = Node('unary-op', p[1])

def p_incdec_op(p):
    '''incdec-op : PLUSPLUS
                 | MINUSMINUS'''
    p[0] = Node('incdec-op', p[1])

def p_type_constructor(p):
    'type-constructor : typespec LPAREN expression-list RPAREN'
    p[0] = Node('type-constructor', p[1], p[3])

def p_function_call(p):
    'function-call : identifier LPAREN function-args-opt RPAREN'
    p[0] = Node('function-call', p[1], p[3])

def p_function_args_opt(p):
    '''function-args-opt : function-args
                         | empty'''
    if len(p) > 1:
        p[0] = p[1]
    else:
        p[0] = None

def p_function_args(p):
    '''function-args : function-args COMMA expression
                     | expression'''
    if len(p) > 2:
        p[0] = p[1]
        p[0].append(p[3])
    else:
        p[0] = Node('function-args', p[1])

def p_assign_expression(p):
    'assign-expression : variable-lvalue assign-op expression'
    p[0] = Node('assign-expression', p[1], p[2], p[3])

def p_assign_op(p):
    '''assign-op : EQUALS
                 | TIMESEQUAL
                 | DIVEQUAL
                 | PLUSEQUAL
                 | MINUSEQUAL
                 | ANDEQUAL
                 | OREQUAL
                 | XOREQUAL
                 | LSHIFTEQUAL
                 | RSHIFTEQUAL'''
    p[0] = Node('assign-op', p[1])

def p_ternary_expression(p):
    'ternary-expression : expression CONDOP expression COLON expression'
    p[0] = Node('ternary-expression', p[1], p[3], p[5])

def p_typecast_expression(p):
    'typecast-expression : LPAREN simple-typename RPAREN expression'
    p[0] = Node('typecast-expression', p[2], p[4])

# lexical elements

def p_integer(p):
    'integer : ICONST'
    # TODO
    p[0] = Node('integer', p[1])

def p_floating_point(p):
    'floating-point : FCONST'
    p[0] = Node('floating-point', p[1])

def p_number(p):
    '''number : integer
              | floating-point'''
    p[0] = p[1]

def p_stringliteral(p):
    'stringliteral : SCONST'
    p[0] = Node('stringliteral', p[1])

def p_identifier(p):
    'identifier : ID'
    p[0] = p[1]

def p_empty(p):
    'empty : '
    if len(p) > 1:
        p[0] = p[1]
    else:
        p[0] = None

def p_error(p):
    if p:
        print('Syntax error at token', p.type, 'line', p.lineno)
    else:
        print('Syntax error at EOF')

def get_ast(data):

    # apply shader hacks before parsing

    # double "" "" string literals in metadata
    data = re.sub(r'"\s*^\s*"', '', data, flags=re.MULTILINE)
    data = re.sub(r'"([^"\n]+)" +"([^"\n]+)"', '"\\1\\2"', data)
    data = re.sub(r'"([^"\n]+)" +"([^"\n]+)"', '"\\1\\2"', data)

    parser = yacc.yacc(debug=False)
    #parser = yacc.yacc(write_tables=False,debug=False)
    return parser.parse(data, osllex.lexer, debug=False)

