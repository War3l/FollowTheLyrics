import logging
import logging.handlers
import os

from followthelyrics import settings

LOG_DIR = os.path.join(settings.DATA_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "followthelyrics.log")
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup():
    level = logging.DEBUG if os.environ.get("FTL_DEBUG") else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=512_000, backupCount=2, encoding="utf-8"
        )
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    logging.getLogger("PIL").setLevel(logging.WARNING)
