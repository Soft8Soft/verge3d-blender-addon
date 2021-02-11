# OSL Lexer

import os, sys

import ply.lex as lex

reserved = (
    'AND', 'BREAK', 'CLOSURE', 'COLOR', 'CONTINUE', 'DO', 'ELSE', 'EMIT', 'FLOAT', 'FOR', 'IF', 'ILLUMINANCE',
    'ILLUMINATE', 'INT', 'MATRIX', 'NORMAL', 'NOT', 'OR', 'OUTPUT', 'POINT', 'PUBLIC', 'RETURN', 'STRING',
    'STRUCT', 'VECTOR', 'VOID', 'WHILE',

    # shader types
    'DISPLACEMENT', 'SHADER', 'SURFACE', 'VOLUME',

    #'BOOL', 'CASE', 'CATCH', 'CHAR', 'CLASS', 'CONST', 'DELETE', 'DEFAULT', 'DOUBLE', 'ENUM', 'EXTERN',
    #'FALSE', 'FRIEND', 'GOTO', 'INLINE', 'LONG', 'NEW', 'OPERATOR', 'PRIVATE', 'PROTECTED', 'SHORT',
    #'SIGNED', 'SIZEOF', 'STATIC', 'SWITCH', 'TEMPLATE', 'THIS', 'THROW', 'TRUE', 'TRY', 'TYPEDEF', 'UNIFORM',
    #'UNION', 'UNSIGNED', 'VARYING', 'VIRTUAL', 'VOLATILE'
)

tokens = reserved + (
    # literals (identifier, integer constant, float constant, string constant)
    'ID', 'ICONST', 'FCONST', 'SCONST',

    # operators (+,-,*,/,%, |,&,~,^,<<,>>, ||, &&, !, <, <=, >, >=, ==, !=)
    'PLUS', 'MINUS', 'TIMES', 'DIVIDE', 'MOD',
    'BITOR', 'BITAND', 'BITNOT', 'XOR', 'LSHIFT', 'RSHIFT',
    'LT', 'LE', 'GT', 'GE', 'EQ', 'NE',

    # assignment (=, *=, /=, %=, +=, -=, <<=, >>=, &=, ^=, |=)
    'EQUALS', 'TIMESEQUAL', 'DIVEQUAL', 'MODEQUAL', 'PLUSEQUAL', 'MINUSEQUAL',
    'LSHIFTEQUAL', 'RSHIFTEQUAL', 'ANDEQUAL', 'XOREQUAL', 'OREQUAL',

    # increment/decrement (++,--)
    'PLUSPLUS', 'MINUSMINUS',

    # structure dereference (->)
    'ARROW',

    # conditional operator (?)
    'CONDOP',

    # delimeters ( ) [ ] { } , . ; :
    'LPAREN', 'RPAREN',
    'LBRACKET', 'RBRACKET',
    'LBRACE', 'RBRACE',
    'COMMA', 'PERIOD', 'SEMI', 'COLON',

    'METABEGIN'

)

# completely ignored characters
t_ignore = ' \t\x0c'

# newlines

def t_NEWLINE(t):
    r'[\r\n]+'
    t.lexer.lineno += t.value.count('\n')

# operators

t_PLUS = r'\+'
t_MINUS = r'-'
t_TIMES = r'\*'
t_DIVIDE = r'/'
t_MOD = r'%'
t_BITOR = r'\|'
t_BITAND = r'&'
t_BITNOT = r'~'
t_XOR = r'\^'
t_LSHIFT = r'<<'
t_RSHIFT = r'>>'
t_OR = r'(or|\|\|)'
t_AND = r'(and|&&)'
t_NOT = r'(not|!)'
t_LT = r'<'
t_GT = r'>'
t_LE = r'<='
t_GE = r'>='
t_EQ = r'=='

# special case, make it appear before not|! regexp
def t_NE(t):
    r'!='
    return t

# assignment operators

t_EQUALS = r'='
t_TIMESEQUAL = r'\*='
t_DIVEQUAL = r'/='
t_MODEQUAL = r'%='
t_PLUSEQUAL = r'\+='
t_MINUSEQUAL = r'-='
t_LSHIFTEQUAL = r'<<='
t_RSHIFTEQUAL = r'>>='
t_ANDEQUAL = r'&='
t_OREQUAL = r'\|='
t_XOREQUAL = r'\^='

# increment/decrement
t_PLUSPLUS = r'\+\+'
t_MINUSMINUS = r'--'

# ->
t_ARROW = r'->'

# ?
t_CONDOP = r'\?'

# delimeters
t_LPAREN = r'\('
t_RPAREN = r'\)'
t_LBRACKET = r'\['
t_RBRACKET = r'\]'
t_LBRACE = r'\{'
t_RBRACE = r'\}'
t_COMMA = r','
t_PERIOD = r'\.'
t_SEMI = r';'
t_COLON = r':'
t_METABEGIN = r'\[\['

# identifiers and reserved words

reserved_map = {}
for r in reserved:
    reserved_map[r.lower()] = r


def t_ID(t):
    r'[A-Za-z_][\w_]*'
    t.type = reserved_map.get(t.value, 'ID')
    return t

# integer literal
t_ICONST = r'\d+([uU]|[lL]|[uU][lL]|[lL][uU])?'

# floating literal
t_FCONST = r'((\d*)(\.\d+)(e(\+|-)?(\d+))? | (\d+)e(\+|-)?(\d+))([lL]|[fF])?'

# string literal
t_SCONST = r'\"([^\\\n]|(\\.))*?\"'


# comments

def t_comment(t):
    r'/\*(.|\n)*?\*/'
    t.lexer.lineno += t.value.count('\n')

def t_comment2(t):
    r'//(.)*?\n'
    t.lexer.lineno += 1

# preprocessor directive (ignored)

def t_preprocessor(t):
    r'\#(.)*?\n'
    t.lexer.lineno += 1

def t_error(t):
    print('Illegal character {}'.format(repr(t.value[0])))
    t.lexer.skip(1)

lexer = lex.lex()

if __name__ == "__main__":
    lex.runmain(lexer)
