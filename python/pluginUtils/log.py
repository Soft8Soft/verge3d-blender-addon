from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

from builtins import (ascii, bytes, chr, dict, filter, hex, input,
                      int, map, next, oct, open, pow, range, round,
                      str, super, zip)

import sys, traceback

outputFile = sys.stdout
outputLevels = ['ERROR', 'WARNING', 'INFO', 'PROFILE', 'DEBUG', 'VERBOSE']
outputLevel = 'INFO'

def printLog(level, output):

    global outputFile
    global outputLevels
    global outputLevel

    if outputLevels.index(level) > outputLevels.index(outputLevel):
        return

    print('V3D-' + level + ': ' + output, file=outputFile)
    if level == 'ERROR':
        traceback.print_stack(file=outputFile)

    if outputFile != sys.stdout:
        outputFile.flush()

def setOutputLevel(level):

    global outputLevels
    global outputLevel

    if outputLevels.index(level) < 0:
        return

    outputLevel = level

def setOutputFile(path):
    global outputFile
    if path:
        outputFile = open(path, 'a')
    else:
        outputFile = sys.stdoutopen(path, 'a')
