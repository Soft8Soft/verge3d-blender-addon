#!/usr/bin/env python3

import getopt, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import pyosl.glslgen, pyosl.oslparse

def usage():
    print('Usage: osl2glsl [-ognh] shader.ost')

if __name__ == "__main__":

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ognh')
    except getopt.GetoptError as err:
        usage()
        sys.exit(1)

    print_osl_ast = False
    print_glsl_ast = False
    no_glsl = False

    for o, _ in opts:
        if o == '-o':
            print_osl_ast = True
        elif o == '-g':
            print_glsl_ast = True
        elif o == '-n':
            no_glsl = True
        elif o == '-h':
            usage()
            sys.exit()

    try:
        filename = args[0]
        with open(filename) as f:
            data = f.read()
    except IndexError:
        sys.stdout.write('Reading from standard input (type EOF to end):\n')
        data = sys.stdin.read()

    ast_osl = pyosl.oslparse.get_ast(data)
    if print_osl_ast:
        ast_osl.print_tree()

    ast_glsl = pyosl.glslgen.osl_to_glsl(ast_osl)
    if print_glsl_ast:
        ast_glsl.print_tree()

    if not no_glsl:
        print(pyosl.glslgen.generate(ast_glsl))
