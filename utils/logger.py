import logging
import sys


def get_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        '{"time": "%(asctime)s", "level": "%(levelname)s", '
        '"module": "%(name)s", "message": "%(message)s"}'
    ))
    log.addHandler(handler)
    return log


# Default logger for backwards compat with existing imports
logger = get_logger('usaea_ad_factory')
