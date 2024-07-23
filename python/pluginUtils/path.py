import os, platform

PORTS = {
    'BLENDER': 8668,
    'MAX': 8669,
    'MAYA': 8670
}

REEXPORT_ONLY = True

def getRoot():
    baseDir = os.path.dirname(os.path.abspath(__file__))
    # NOTE: not working in python2
    #return (pathlib.Path(baseDir) / '..' / '..').resolve()
    return os.path.join(baseDir, '..', '..')

def getAppManagerHost(modPackage, includeScheme=True):
    if includeScheme:
        return 'http://localhost:{}/'.format(PORTS[modPackage])
    else:
        # HACK: fixes slowdowns in WSL
        return '127.0.0.1:{}'.format(PORTS[modPackage])

def findExportedAssetPath(srcPath):
    dirname, basename = os.path.split(srcPath)

    for ext in ['.gltf', '.glb']:

        gltfname = os.path.splitext(basename)[0] + ext

        for path in [os.path.join(dirname, gltfname),
                     os.path.join(dirname, 'export', gltfname),
                     os.path.join(dirname, 'exports', gltfname)]:

            if os.path.exists(path):
                return path

    if not REEXPORT_ONLY:
        return os.path.splitext(srcPath)[0] + '.gltf'

    return None

def getPlatformBinDirName():
    """
    linux_x86_64, windows_amd64, darwin_arm64, etc...
    """
    return platform.system().lower() + '_' + platform.machine().lower()
