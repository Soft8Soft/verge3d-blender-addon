#!/usr/bin/env python

import os, platform, re, shutil, sys

SUPPORTED_BLENDER_VERSIONS = ['2.80', '2.81', '2.82', '2.83']

def copyPlugin(blendConfDir):

    rootDir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))

    srcPluginPath = os.path.join(rootDir, 'addons', 'verge3d')
    dstPluginPath = os.path.join(blendConfDir, 'scripts', 'addons', 'verge3d')

    if os.path.exists(dstPluginPath):
        shutil.rmtree(dstPluginPath)

    shutil.copytree(srcPluginPath, dstPluginPath)

    # set root path in addon init script

    srcInitScript = os.path.join(srcPluginPath, '__init__.py')
    dstInitScript = os.path.join(dstPluginPath, '__init__.py')

    with open(srcInitScript, 'r') as fin:
        with open(dstInitScript, 'w') as fout:
            for line in fin:
                fout.write(re.sub('(ROOT_DIR) *=.*', 'ROOT_DIR = r\'{}\''.format(rootDir.replace('\\', '\\\\')), line))


def traverseBlenderDirs():
    system = platform.system()

    if system == 'Windows':
        blendDir = os.path.expandvars(r'%USERPROFILE%\AppData\Roaming\Blender Foundation\Blender')
    elif system == 'Darwin':
        blendDir = os.path.expandvars(r'$HOME/Library/Application Support/Blender')
    else:
        blendDir = os.path.expandvars(r'$HOME/.config/blender')

    if os.path.exists(blendDir):
        for blendVer in SUPPORTED_BLENDER_VERSIONS:
            blendVerDir = os.path.join(blendDir, blendVer)
            if os.path.exists(blendVerDir):
                print('Copy plugin path for Blender {}'.format(blendVer))
                copyPlugin(blendVerDir)

if __name__ == '__main__':
    traverseBlenderDirs()
