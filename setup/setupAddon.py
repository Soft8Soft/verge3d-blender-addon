#!/usr/bin/env python

import os, platform, re, shutil, sys

SUPPORTED_BLENDER_VERSIONS = ['2.80', '2.81', '2.82', '2.83']

def copyAddon(blendConfDir):

    rootDir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))

    srcAddonPath = os.path.join(rootDir, 'addons', 'verge3d')

    dstAddonsPath = os.path.join(blendConfDir, 'scripts', 'addons')
    os.makedirs(dstAddonsPath, exist_ok=True)

    dstAddonPath = os.path.join(dstAddonsPath, 'verge3d')

    if os.path.isdir(dstAddonPath):
        shutil.rmtree(dstAddonPath)

    shutil.copytree(srcAddonPath, dstAddonPath)

    # set root path in addon init script

    srcInitScript = os.path.join(srcAddonPath, '__init__.py')
    dstInitScript = os.path.join(dstAddonPath, '__init__.py')

    with open(srcInitScript, 'r', encoding='utf-8') as fin:
        with open(dstInitScript, 'w', encoding='utf-8') as fout:
            for line in fin:
                fout.write(re.sub('(ROOT_DIR) *=.*', 'ROOT_DIR = r\'{}\''.format(rootDir.replace('\\', '\\\\')), line))

def removeAddon(blendConfDir):
    dstAddonPath = os.path.join(blendConfDir, 'scripts', 'addons', 'verge3d')

    if os.path.isdir(dstAddonPath):
        shutil.rmtree(dstAddonPath)

        return True

    return False

def traverseBlenderDirs(doInstall=True):
    system = platform.system()

    if system == 'Windows':
        blendDir = os.path.expandvars(r'%USERPROFILE%\AppData\Roaming\Blender Foundation\Blender')
    elif system == 'Darwin':
        blendDir = os.path.expandvars(r'$HOME/Library/Application Support/Blender')
    else:
        blendDir = os.path.expandvars(r'$HOME/.config/blender')

    for blendVer in SUPPORTED_BLENDER_VERSIONS:
        blendVerDir = os.path.join(blendDir, blendVer)

        if doInstall:
            print('Installing Verge3D addon for Blender {}'.format(blendVer))
            copyAddon(blendVerDir)
        else:
            if removeAddon(blendVerDir):
                print('Removed Verge3D addon for Blender {}'.format(blendVer))

if __name__ == '__main__':

    if len(sys.argv) <= 1 or sys.argv[1].upper() == 'INSTALL':
        traverseBlenderDirs(True)
    elif len(sys.argv) > 1 and sys.argv[1].upper() == 'UNINSTALL':
        traverseBlenderDirs(False)
    else:
        print('Wrong script arguments')
