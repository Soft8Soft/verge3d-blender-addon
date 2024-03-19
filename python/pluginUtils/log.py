import logging, sys

LOG_LEVEL = logging.INFO

def getLogger(name):
    log = logging.getLogger(name)
    log.setLevel(LOG_LEVEL)
    if not log.hasHandlers():
        logH = logging.StreamHandler(sys.stdout)
        logH.setFormatter(logging.Formatter('%(name)s-%(levelname)s: %(message)s'))
        log.addHandler(logH)
    return log
