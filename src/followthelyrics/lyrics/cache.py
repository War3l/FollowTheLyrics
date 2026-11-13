import hashlib
import json
import logging
import os
import time

from followthelyrics.config import settings
from followthelyrics.lyrics import model

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(settings.DATA_DIR, "cache")

CACHE_VERSION = 2

MISSING_TTL = 7 * 86400


def _cache_path(title: str, artist: str) -> str:
    h = hashlib.sha1(f"{title.lower()}|{artist.lower()}".encode()).hexdigest()[
        :24
    ]
    return os.path.join(CACHE_DIR, h + ".json")


def _line_from_cache(x):
    return model.Line(
        x["t"],
        x["x"],
        x.get("s", ""),
        [tuple(c) for c in x["c"]] if x.get("c") else None,
        x.get("e"),
        x.get("a", ""),
        x.get("at"),
        x.get("tr", ""),
    )


def cache_load(title: str, artist: str, duration: float = 0):
    try:
        with open(_cache_path(title, artist), encoding="utf-8") as f:
            d = json.load(f)
        if d.get("v") != CACHE_VERSION:
            return False, None
        if (
            duration > 0
            and d.get("duration", 0) > 0
            and abs(d["duration"] - duration) > 6
        ):
            return False, None
        if d["lines"] is None:
            return (time.time() - d.get("saved", 0) < MISSING_TTL), None
        return True, [_line_from_cache(x) for x in d["lines"]]
    except (OSError, ValueError, KeyError, TypeError):
        return False, None


def cache_is_final(title: str, artist: str) -> bool:
    try:
        with open(_cache_path(title, artist), encoding="utf-8") as f:
            return bool(json.load(f).get("final"))
    except (OSError, ValueError, AttributeError):
        return False


def cache_save(
    title: str, artist: str, duration: float, lines, final: bool = False
):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        data = None
        if lines is not None:
            data = [
                {
                    "t": line.time,
                    "x": line.text,
                    "s": line.singer,
                    "c": line.chars,
                    "e": line.end,
                    "a": line.adlib,
                    "at": line.adlib_time,
                    "tr": line.translation,
                }
                for line in lines
            ]
        settings.write_json(
            _cache_path(title, artist),
            {
                "v": CACHE_VERSION,
                "title": title,
                "artist": artist,
                "duration": duration,
                "saved": time.time(),
                "final": final,
                "lines": data,
            },
            indent=None,
        )
    except (OSError, TypeError, ValueError):
        logger.warning("cache_save failed", exc_info=True)
