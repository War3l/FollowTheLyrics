import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from followthelyrics import version
from followthelyrics.lyrics import model
from followthelyrics.lyrics import parsing

logger = logging.getLogger(__name__)

API = "https://lrclib.net/api"

HEADERS = {
    "User-Agent": (
        f"FollowTheLyrics/{version.current()} "
        f"(https://github.com/{version.REPO})"
    )
}

NE_API = "https://music.163.com/api"

NE_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"}

_VERSION = re.compile(
    r"\b(live|remix|instrumental|cover|karaoke|acoustic|sped up|slowed|"
    r"nightcore|8d|伴奏|现场)\b",
    re.IGNORECASE,
)


def translate_lines(lines: list[model.Line], target: str = "fr") -> str | None:
    texts = list(dict.fromkeys(line.text for line in lines if line.text))
    if not texts:
        return None
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target}&dt=t"
    body = urllib.parse.urlencode({"q": "\n".join(texts)}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError):
        logger.warning("translate_lines failed", exc_info=True)
        return None
    src = data[2] if len(data) > 2 else None
    if src == target:
        return src
    full = "".join(seg[0] for seg in (data[0] or []) if seg and seg[0])
    parts = full.split("\n")
    if len(parts) != len(texts):
        return None
    mapping = {t: p.strip() for t, p in zip(texts, parts, strict=False)}
    for line in lines:
        tr = mapping.get(line.text, "")
        line.translation = tr if tr and tr.lower() != line.text.lower() else ""
    return src


class _Session:
    def __init__(self):
        self.failed = False

    def get_json(self, url: str, headers: dict):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=8
            ) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code >= 500 or e.code == 429:
                self.failed = True
            return None
        except (OSError, ValueError):
            logger.warning("lyrics request failed: %s", url, exc_info=True)
            self.failed = True
            return None

    def lrclib(self, path: str, params: dict):
        query = urllib.parse.urlencode(params)
        return self.get_json(f"{API}/{path}?{query}", HEADERS)


def _best(results, duration: float):
    if not isinstance(results, list):
        return None
    synced = [r for r in results if r.get("syncedLyrics")]
    if not synced:
        return None
    if duration > 0:
        synced.sort(key=lambda r: abs((r.get("duration") or 0) - duration))
        if abs((synced[0].get("duration") or 0) - duration) > 15:
            return None
    return synced[0]


def _lrclib(
    session: _Session, track: str, art: str, album: str, duration: float
) -> list[model.Line] | None:
    if art:
        params: dict[str, str | int] = {
            "track_name": track,
            "artist_name": art,
        }
        if album:
            params["album_name"] = album
        if duration > 0:
            params["duration"] = round(duration)
        hit = session.lrclib("get", params)
        if isinstance(hit, dict) and hit.get("syncedLyrics"):
            return parsing.parse_lrc(hit["syncedLyrics"])
        hit = _best(
            session.lrclib("search", {"track_name": track, "artist_name": art}),
            duration,
        )
        if hit:
            return parsing.parse_lrc(hit["syncedLyrics"])
    hit = _best(
        session.lrclib("search", {"q": f"{art} {track}".strip()}), duration
    )
    return parsing.parse_lrc(hit["syncedLyrics"]) if hit else None


def _netease(session: _Session, track: str, art: str, duration: float):
    q = urllib.parse.quote(f"{track} {art}".strip())
    res = session.get_json(
        f"{NE_API}/search/get?s={q}&type=1&limit=10", NE_HEADERS
    )
    songs = ((res or {}).get("result") or {}).get("songs") or []
    want_t, want_a = parsing.simplify(track), parsing.simplify(art)
    asked_version = bool(_VERSION.search(track))
    scored = []
    for s in songs:
        name = s.get("name") or ""
        got_t = parsing.simplify(parsing.clean_title(name))
        if not got_t or not want_t:
            continue
        exact = got_t == want_t
        close = (want_t in got_t or got_t in want_t) and min(
            len(got_t), len(want_t)
        ) / max(len(got_t), len(want_t)) > 0.6
        if not (exact or close):
            continue
        arts = [
            parsing.simplify(a.get("name") or "")
            for a in s.get("artists") or []
        ]
        art_ok = bool(want_a) and any(
            a and (a in want_a or want_a in a) for a in arts
        )
        d = (s.get("duration") or 0) / 1000
        diff = abs(d - duration) if duration > 0 and d > 0 else None
        if diff is not None and diff > 6:
            continue
        dur_ok = diff is not None and diff <= 3
        if not (art_ok or dur_ok):
            continue
        score = (
            (2 if exact else 1) + (3 if art_ok else 0) + (2 if dur_ok else 0)
        )
        if _VERSION.search(name) and not asked_version:
            score -= 4
        scored.append((score, s["id"]))
    scored.sort(reverse=True)

    line_level = None
    for _, sid in scored[:3]:
        ly = (
            session.get_json(
                f"{NE_API}/song/lyric/v1?id={sid}&lv=1&yv=1&tv=-1", NE_HEADERS
            )
            or {}
        )
        yrc = (ly.get("yrc") or {}).get("lyric") or ""
        words = parsing.parse_yrc(yrc) if yrc else []
        if len(words) >= 3:
            return words, None
        lrc = (ly.get("lrc") or {}).get("lyric") or ""
        if lrc and line_level is None:
            parsed = parsing.parse_lrc(lrc)
            if len(parsed) >= 3:
                line_level = parsed
    return None, line_level


def _fetch(
    session: _Session, title: str, artist: str, album: str, duration: float
) -> list[model.Line] | None:
    fallback = None
    lines = None
    for track, art in parsing.candidates(title, artist):
        words, ne_lines = _netease(session, track, art, duration)
        if words:
            lines = parsing.add_pauses(words)
            break
        fallback = fallback or ne_lines
    if lines is None:
        for track, art in parsing.candidates(title, artist):
            lines = _lrclib(session, track, art, album, duration)
            if lines:
                break
    lines = lines or fallback
    return (
        parsing.split_adlibs(parsing.extract_singers(lines, artist))
        if lines
        else None
    )


def fetch_lyrics(
    title: str, artist: str, album: str = "", duration: float = 0
) -> list[model.Line] | None:
    return _fetch(_Session(), title, artist, album, duration)


def fetch_lyrics_ex(
    title: str, artist: str, album: str = "", duration: float = 0
) -> tuple[list[model.Line] | None, bool]:
    session = _Session()
    lines = _fetch(session, title, artist, album, duration)
    return lines, not (lines is None and session.failed)
