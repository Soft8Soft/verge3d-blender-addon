import os, pathlib, platform, shutil, subprocess, sys, time

from .log import getLogger
from .path import getRoot, getAppManagerHost

log = getLogger('V3D-PU')

from http.client import HTTPConnection

join = os.path.join

APP_MANAGER_FORCE_ALL = True

MANUAL_URL_DEFAULT = 'https://www.soft8soft.com/docs/manual/en/index.html'


class AppManagerConn():
    root = None
    modPackage = None
    isThreaded = False

    servers = [] # for threaded only
    subThreads = []

    @classmethod
    def init(cls, root, modPackage):
        cls.root = root
        cls.modPackage = modPackage

    @classmethod
    def isAvailable(cls):
        if os.path.isfile(join(cls.root, 'manager', 'server.py')):
            return True
        else:
            return False

    @classmethod
    def ping(cls):
        conn = HTTPConnection(getAppManagerHost(cls.modPackage, False))

        try:
            conn.request('GET', '/ping')
        except ConnectionRefusedError:
            return False

        response = conn.getresponse()

        if response.status == 200:
            return True
        else:
            return False

    @classmethod
    def getPreviewDir(cls, cleanup=False):
        conn = HTTPConnection(getAppManagerHost(cls.modPackage, False))

        try:
            conn.request('GET', '/get_preview_dir')
        except ConnectionRefusedError:
            log.warning('App Manager connection error, wait a bit')
            time.sleep(0.3)
            # NOTE: repeated error will cause crash
            conn = HTTPConnection(getAppManagerHost(cls.modPackage, False))
            conn.request('GET', '/get_preview_dir')

        response = conn.getresponse()

        if response.status != 200:
            log.error('App Manager connection error: ' + response.reason)
            return None

        path = response.read().decode('utf-8')

        if cleanup:
            shutil.rmtree(path, ignore_errors=True)
            os.makedirs(path, exist_ok=True)

        log.info('Performing export to preview dir: {}'.format(path))

        return path

    @classmethod
    def getEnginePath(cls):
        conn = HTTPConnection(getAppManagerHost(cls.modPackage, False))

        # decent fallback in case of connection errors
        enginePathDefault = getRoot(True) / 'build' / 'v3d.js'

        try:
            conn.request('GET', '/get_engine_path')
        except ConnectionRefusedError:
            log.error('App Manager connection refused, using fallback engine path')
            return enginePathDefault

        response = conn.getresponse()

        if response.status != 200:
            log.error('App Manager connection error, using fallback engine path: ' + response.reason)
            return enginePathDefault

        return pathlib.Path(response.read().decode('utf-8'))

    @classmethod
    def getManualURL(cls):
        conn = HTTPConnection(getAppManagerHost(cls.modPackage, False))

        try:
            conn.request('GET', '/settings/get_manual_url')
        except ConnectionRefusedError:
            log.warning('App Manager connection refused')
            return MANUAL_URL_DEFAULT

        response = conn.getresponse()

        if response.status != 200:
            log.warning('App Manager connection error: ' + response.reason)
            return MANUAL_URL_DEFAULT

        manualURL = response.read().decode('utf-8')
        return manualURL

    @classmethod
    def start(cls):
        system = platform.system()

        if system == 'Windows':
            pythonPath = join(cls.root, 'python', 'windows', 'pythonw.exe')
        elif system == 'Darwin':
            # NOTE: Blender, in Maya sys.executable points to modelling suite executable
            pythonPath = sys.executable

            try:
                import maya.cmds
                pythonPath = join(os.getenv('MAYA_LOCATION'), 'bin', 'mayapy')
            except ImportError:
                pass
        else:
            pythonPath = 'python3'

        modPackage = 'ALL' if APP_MANAGER_FORCE_ALL else cls.modPackage
        args = [pythonPath, join(cls.root, 'manager', 'server.py'), modPackage]
        subprocess.Popen(args)

    @classmethod
    def stop(cls):
        conn = HTTPConnection(getAppManagerHost(cls.modPackage, False))
        conn.request('GET', '/stop')
        response = conn.getresponse()
        if response.status != 200 and response.status != 302:
            log.error('App Manager connection error: ' + response.reason)

