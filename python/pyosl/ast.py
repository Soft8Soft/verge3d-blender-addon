# OSL Abstact Syntax Tree

from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import os, sys

class Node:
    def __init__(self, type, *children):
        self.type = type
        self.children = list(children)
        self.tmp = None

    def append(self, child):
        self.children.append(child)

    def insert(self, num, child):
        self.children.insert(num, child)

    def num_childs(self):
        return len(self.children)

    def get_child(self, type_or_idx):

        if isinstance(type_or_idx, str) or (sys.version_info[0] == 2 and isinstance(type_or_idx, unicode)):
            for c in self.children:
                if isinstance(c, Node) and c.type == type_or_idx:
                    return c
        else:
            return self.children[type_or_idx]

        return None

    def set_child(self, index, node):
        self.children[index] = node

    def traverse_nodes(self, callback, node=None):
        '''DFS'''
        if node is None:
            node = self

        callback(node)

        for c in node.children:
            if isinstance(c, Node):
                self.traverse_nodes(callback, c)

    def find_nodes(self, *types):
        '''Find all children nodes of given type(s)'''

        out = []

        def cb(node):
            # NOTE: not working in python2
            #nonlocal out
            for type in types:
                if node.type == type:
                    out.append(node)

        self.traverse_nodes(cb)

        return out

    def find_node(self, type):
        '''Find first child node of given type'''

        nodes = self.find_nodes(type)
        if len(nodes):
            return nodes[0]
        else:
            return None

    def get_ancestor(self, ast):
        '''Get nearest parent node'''

        ast.assign_tmp_parents()
        return self.tmp

    def find_ancestor_node(self, ast, type):
        '''Find parent node of the given type(s)'''

        ast.assign_tmp_parents()

        node = self

        while True:
            parent = node.tmp

            if parent:
                if parent.type == type:
                    return parent
                else:
                    node = parent
            else:
                return None

    def assign_tmp_parents(self):
        '''For internal use'''

        # root node
        self.tmp = None

        def cb(node):
            for c in node.children:
                if isinstance(c, Node):
                    # parent
                    c.tmp = node

        self.traverse_nodes(cb)


    def get_shader_name(self):
        return self.find_node('shader-declaration').get_child(1)

    def get_variables(self):
        variables = {}

        decl_nodes = self.find_nodes('variable-declaration',
                                     'function-formal-param',
                                     'shader-formal-param')

        for dn in decl_nodes:

            type = dn.get_child('typespec').get_typespec_type()

            if dn.type == 'variable-declaration':
                for expr in dn.find_nodes('def-expression'):
                    name = expr.get_child(0)
                    variables[name] = type
            else:
                name = dn.get_child(2)
                variables[name] = type

        return variables

    def get_typespec_type(self):
        assert self.type == 'typespec'

        if self.get_child('simple-typename'):
            return self.get_child('simple-typename').get_child(0)
        else:
            return self.get_child(0)

    def get_functions(self):
        functions = {}

        decl_nodes = self.find_nodes('function-declaration')

        for dn in decl_nodes:
            type = dn.get_child('typespec').get_typespec_type()
            name = dn.get_child(1)
            params = dn.get_child(2)

            spec = [type]

            if params:
                for param in params.children:
                    spec.append(param.get_child('typespec').get_typespec_type())

            functions[name] = tuple(spec)

        return functions

    def get_shader_params(self):

        inputs = []
        outputs = []

        shader_name = self.get_shader_name()

        decl_nodes = self.find_nodes('shader-formal-param')

        for dn in decl_nodes:
            is_in = True if dn.get_child('outputspec').get_child(0) is None else False
            type = dn.get_child('typespec').get_child('simple-typename').get_child(0)
            name = dn.get_child(2)

            if is_in:
                init_ast = None
                init_node = dn.get_child('initializer')
                if init_node:
                    param = dn.clone()
                    param.get_child('outputspec').set_child(0, 'output')
                    init_ast = self.create_shader(shader_name + '_init_' + str(decl_nodes.index(dn)),
                                                  [param],
                                                  [Node('statement-semi', Node('def-expression', name, init_node.clone()))])

                    uses_gl_var = False
                    for gl_var_name in ['P', 'I', 'N', 'u', 'v']:
                        if init_ast.uses_variable(gl_var_name):
                            uses_gl_var = True

                if init_ast and uses_gl_var:
                    inputs.append((type, name, init_ast))
                else:
                    inputs.append((type, name, None))
            else:
                outputs.append((type, name, None))

        return inputs, outputs

    def uses_variable(self, name):
        var_nodes = self.find_nodes('variable-ref')

        for vn in var_nodes:
            if vn.find_node('variable-lvalue').get_child(0) == name:
                return True

        return False

    def create_shader(self, name, params, statements):
        params = Node('shader-formal-params', *params)
        statements = Node('statement-list', *statements)
        return Node('shader-file', Node('shader-declaration', 'shader', name, None, params, statements))

    def clone(self):
        cloned_children = [c.clone() if isinstance(c, Node) else c for c in self.children]
        return Node(self.type, *cloned_children)

    def print_tree(self, level=0, indent=2, node=None):
        if node is None:
            node = self

        print(' ' * indent * level + node.type)

        for c in node.children:
            if isinstance(c, Node):
                self.print_tree(level+1, indent, c)
            else:
                print(' ' * indent * (level + 1) + str(c))


