import lzma, os, platform, subprocess, sys, tempfile

from .path import getRoot, getPlatformBinDirName
from .log import printLog

COMPRESSION_THRESHOLD = 3

from subprocess import CompletedProcess

def runCMD(params):
    if platform.system().lower() == 'windows':
        # disable popup console window
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        app = subprocess.run(params, capture_output=True, startupinfo=si)
    else:
        app = subprocess.run(params, capture_output=True)

    return app


class CompressionFailed(Exception):
    pass

def compressLZMA(srcPath, dstPath=None):

    dstPath = dstPath if dstPath else srcPath + '.xz'

    printLog('INFO', 'Compressing {} to LZMA'.format(os.path.basename(srcPath)))

    with open(srcPath, 'rb') as fin:
        data = fin.read()
        with lzma.open(dstPath, 'wb') as fout:
            fout.write(data)

def removeICCChunk(srcPath):
    import pypng.png

    def removeChunksGen(chunks, delete):
        for type, v in chunks:
            if type.decode('ascii') in delete:
                continue
            yield type, v

    try:
        tmpImg = tempfile.NamedTemporaryFile(delete=False)

        reader = pypng.png.Reader(srcPath)
        chunks = removeChunksGen(reader.chunks(), ['iCCP'])
        pypng.png.write_chunks(tmpImg, chunks)

        tmpImg.close()
        dstPath = tmpImg.name

        return dstPath

    except Exception as e:
        printLog('WARNING', 'ICC chunk removal failed\n' + str(e))
        return None

def compressKTX2(srcPath='', srcData=None, dstPath='-', method='AUTO'):
    """
    srcPath/srcData are mutually exclusive
    """

    if srcData:
        # NOTE: toktx does not support stdin at the moment
        tmpImg = tempfile.NamedTemporaryFile(delete=False)
        tmpImg.write(srcData)
        tmpImg.close()
        srcPath = tmpImg.name

    params = [os.path.join(getRoot(), 'ktx', getPlatformBinDirName(), 'toktx')]

    params.append('--encode')
    if method == 'UASTC' or method == 'AUTO':
        params.append('uastc')
        params.append('--zcmp')
    else:
        params.append('etc1s')
        params.append('--clevel')
        params.append('2')
        params.append('--qlevel')
        params.append('255')

    params.append('--genmipmap')
    params.append(dstPath)
    params.append(srcPath)

    printLog('INFO', 'Compressing {0} to {1}'.format(os.path.basename(srcPath), params[2].upper()))

    app = runCMD(params)

    if app.stderr:
        msg = app.stderr.decode('utf-8').strip()

        if 'PNG file has an ICC profile chunk' in msg:
            printLog('WARNING', 'PNG with ICC profile chunk detected, stripping the chunk')

            srcPathRemICC = removeICCChunk(srcPath)

            if srcPathRemICC is not None:
                # replace src path and run compression again
                params[-1] = srcPathRemICC
                app = runCMD(params)

                if app.stderr:
                    msg = app.stderr.decode('utf-8').strip()
                else:
                    msg = 'Successfully compressed PNG with ICC profile chunk removed'

                os.unlink(srcPathRemICC)

        printLog('WARNING', msg)

        # allow non-critical warnings
        if app.returncode > 0:
            if srcData:
                os.unlink(srcPath)
            raise CompressionFailed

    if srcData:
        os.unlink(srcPath)

    if method == 'AUTO':
        if srcData:
            srcSize = len(srcData)
        else:
            srcSize = os.path.getsize(srcPath)

        if dstPath == '-':
            dstSize = len(app.stdout)
        else:
            dstSize = os.path.getsize(dstPath)

        if dstSize > COMPRESSION_THRESHOLD * srcSize:
            printLog('WARNING', 'Compressed image is too large, keeping original file as is')

            if dstPath != '-':
                os.unlink(dstPath)

            raise CompressionFailed

    return app.stdout
