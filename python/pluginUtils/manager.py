from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

from builtins import (ascii, bytes, chr, dict, filter, hex, input,
                      int, map, next, oct, open, pow, range, round,
                      str, super, zip)

import atexit, os, platform, subprocess, sys, threading

from .log import printLog
from .path import getAppManagerHost

join = os.path.join

if sys.version_info[0] < 3:
    from httplib import HTTPConnection
else:
    from http.client import HTTPConnection

class AppManagerConn():
    subProcs = []
    root = None
    modPackage = None
    isThreaded = False

    @classmethod
    def isAvailable(cls, root):
        if os.path.isfile(join(root, 'manager', 'server.py')):
            return True
        else:
            return False

    @classmethod
    def runServerProc(cls):
        sys.path.insert(0, join(cls.root, 'manager'))

        if cls.isThreaded:
            import server
            srv = server.AppManagerServer()
            srv.start(cls.modPackage)
        else:
            system = platform.system()

            if system == 'Windows':
                pythonPath = join(cls.root, 'python', 'windows', 'pythonw.exe')
            elif system == 'Darwin':
                pythonPath = 'python3'
            else:
                pythonPath = 'python3'

            args = [pythonPath, join(cls.root, 'manager', 'server.py'), cls.modPackage]
            cls.subProcs.append(subprocess.Popen(args))
            atexit.register(cls.killSubProcs)

    @classmethod
    def start(cls, root, modPackage, isThreaded):
        cls.root = root
        cls.modPackage = modPackage
        cls.isThreaded = isThreaded

        if isThreaded:
            thread = threading.Thread(target=cls.runServerProc)
            thread.daemon = True
            thread.start()
        else:
            cls.runServerProc()

    @classmethod
    def stop(cls):
        cls.killSubProcs()

    @classmethod
    def killSubProcs(cls):
        for proc in cls.subProcs:
            if proc.poll() is None:
                printLog('INFO', 'Terminating app manager server')
                proc.terminate()

        cls.subProcs = []

    @classmethod
    def compressLZMA(cls, path):
        # improves console readability
        path = os.path.normpath(path)

        printLog('INFO', 'Compressing file: ' + path)

        with open(path, 'rb') as fin:
            conn = HTTPConnection(getAppManagerHost(False))
            headers = {'Content-type': 'application/octet-stream'}
            conn.request('POST', '/storage/lzma/', body=fin, headers=headers)
            response = conn.getresponse()

            if response.status != 200:
                printLog('ERROR', 'LZMA compression error: ' + response.reason)

            with open(path + '.xz', 'wb') as fout:
                fout.write(response.read())
