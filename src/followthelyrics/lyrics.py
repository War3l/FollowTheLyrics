"""Recuperation des paroles synchronisees.

Ordre des sources :
  1. NetEase Cloud Music, format YRC : timing de CHAQUE MOT (comme Apple Music).
     API non officielle : peut changer sans prevenir.
  2. LRCLIB : timing de chaque ligne.
  3. NetEase, timing par ligne (si LRCLIB n'a rien).
"""
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

API = "https://lrclib.net/api"
HEADERS = {"User-Agent": "lyrics-overlay-prototype/0.1"}
NE_API = "https://music.163.com/api"
NE_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"}

_TS = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
_WORD_TS = re.compile(r"<\d+:\d+(?:\.\d+)?>")
_JUNK = re.compile(
    r"\s*[\(\[][^\)\]]*(official|video|audio|lyric|clip|visuali[sz]er|remaster|"
    r"live|hd|hq|4k|explicit|music)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
_YRC_LINE = re.compile(r"^\[(\d+),(\d+)\](.*)$")
_YRC_WORD = re.compile(r"\((\d+),(\d+),-?\d+\)")
# Lignes de credits chinoises de NetEase : "作词 : ...", "作曲 : ...", etc.
_CREDIT = re.compile(r"^\s*[一-鿿 ]{1,8}\s*[:：]|纯音乐|作词|作曲|编曲|制作人|混音|母带|监制|出品")
_VERSION = re.compile(r"\b(live|remix|instrumental|cover|karaoke|acoustic|sped up|slowed|"
                      r"nightcore|8d|伴奏|现场)\b", re.IGNORECASE)


@dataclass
class Line:
    time: float
    text: str
    singer: str = ""          # nom du chanteur s'il etait indique, ex. "(Jennie)"
    # Timing de chaque caractere de `text` (debut, fin) en secondes, si on l'a.
    chars: list[tuple[float, float]] | None = field(default=None, repr=False)
    end: float | None = None  # fin de la ligne chantee, si connue
    adlib: str = ""           # choeurs entre parentheses, affiches a part : "(yeah)"
    adlib_time: float | None = None
    translation: str = ""     # traduction francaise (si la chanson n'est pas en francais)


def norm_text(s: str) -> str:
    return " ".join(s.split())


_PUNCT = set(",.!?;:…")


def _squash(line: Line, idxs):
    """Garde les caracteres idxs de la ligne (avec leurs timings), espaces nettoyes."""
    text, times = [], []
    for i in idxs:
        ch = line.text[i]
        t = line.chars[i] if line.chars else None
        if ch.isspace():
            if text and text[-1] != " ":
                text.append(" ")
                times.append(t)
            continue
        if ch in _PUNCT and text and text[-1] == " ":
            text.pop()
            times.pop()
        text.append(ch)
        times.append(t)
    while text and text[-1] == " ":
        text.pop()
        times.pop()
    return "".join(text), (times if line.chars else None)


def split_adlibs(lines: list[Line]) -> list[Line]:
    """ "Je joue la nuit (oh oh), je perds" -> texte "Je joue la nuit, je perds" + choeur "oh oh".

    Si toute la ligne est entre parentheses, c'est la ligne chantee : on la garde."""
    out = []
    for l in lines:
        if "(" not in l.text:
            out.append(l)
            continue
        main, ad, depth = [], [], 0
        for i, ch in enumerate(l.text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            else:
                (ad if depth else main).append(i)
        mt, mc = _squash(l, main)
        at, ac = _squash(l, ad)
        if not mt or not at:
            txt, chars = _squash(l, sorted(main + ad))
            out.append(Line(l.time, txt, l.singer, chars, l.end, translation=l.translation))
            continue
        out.append(Line(l.time, mt, l.singer, mc, l.end, adlib=at,
                        adlib_time=(ac[0][0] if ac else None), translation=l.translation))
    return out


def translate_lines(lines: list[Line], target: str = "fr") -> str | None:
    """Traduit toutes les lignes d'un coup (Google Traduction, service gratuit non officiel).

    Remplit Line.translation. Renvoie la langue detectee, ou None si echec."""
    texts = list(dict.fromkeys(l.text for l in lines if l.text))
    if not texts:
        return None
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target}&dt=t"
    body = urllib.parse.urlencode({"q": "\n".join(texts)}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    src = data[2] if len(data) > 2 else None
    if src == target:
        return src  # deja en francais : rien a traduire
    full = "".join(seg[0] for seg in (data[0] or []) if seg and seg[0])
    parts = full.split("\n")
    if len(parts) != len(texts):
        return None
    mapping = {t: p.strip() for t, p in zip(texts, parts)}
    for l in lines:
        tr = mapping.get(l.text, "")
        # inutile d'afficher une "traduction" identique (onomatopees, noms...)
        l.translation = tr if tr and tr.lower() != l.text.lower() else ""
    return src


def build_line(segments) -> Line | None:
    """segments : [(debut_s, duree_s, texte), ...] -> Line avec timing par caractere."""
    text, times = [], []
    pending_space = False
    for start, dur, txt in segments:
        visible = [ch for ch in txt if not ch.isspace()]
        n = max(1, len(visible))
        k = 0
        for ch in txt:
            if ch.isspace():
                pending_space = bool(text)
                continue
            if pending_space:
                t = start + dur * k / n
                text.append(" ")
                times.append((t, t))
                pending_space = False
            text.append(ch)
            times.append((start + dur * k / n, start + dur * (k + 1) / n))
            k += 1
    if not text:
        return None
    first, last = segments[0], segments[-1]
    return Line(first[0], "".join(text), chars=times, end=last[0] + last[1])


# --------------------------------------------------------------------------
# Noms de chanteurs
# --------------------------------------------------------------------------
# Mots chantes qu'on trouve souvent entre parentheses : ce ne sont PAS des noms.
_INTERJ = {
    "oh", "ooh", "oooh", "ohh", "o", "ah", "ahh", "aah", "uh", "uhh", "huh", "yeah", "yeh",
    "ya", "yah", "yea", "hey", "ho", "hoo", "woo", "wooh", "whoa", "woah", "wow", "na", "nah",
    "la", "da", "di", "do", "yo", "eh", "ey", "ay", "ayy", "mm", "mmm", "hmm", "baby", "okay",
    "ok", "oui", "non", "ouais", "wee", "skrrt", "brr", "go", "come", "on", "yes", "no", "uh-huh",
    "ha", "haha", "shh", "hello", "bye", "boom", "bang", "pow", "sha", "doo", "dum", "ba", "bam",
}
# Etiquettes de structure ou de groupe : a retirer aussi.
_SECTION = re.compile(
    r"^(all|both|tous|toutes|ensemble|together|everyone|group|chorus|pre-?chorus|refrain|"
    r"pr[eé]-?refrain|verse|couplet|bridge|pont|intro|outro|hook|interlude|instrumental)\b",
    re.IGNORECASE,
)
_LEAD_TAG = re.compile(r"^\s*[\(\[]\s*([^\)\]]{1,40}?)\s*:?\s*[\)\]]\s*:?\s*(.*)$")
_LEAD_COLON = re.compile(r"^\s*([^\s:()\[\]][^:()\[\]]{0,24}?)\s*:\s+(.+)$")
_CONNECTOR = re.compile(r"\s*(?:&|,|\+|/|\band\b|\bet\b|\bx\b|\bwith\b)\s*", re.IGNORECASE)


def _name_words(x: str):
    return [w for w in _CONNECTOR.split(x.strip()) for w in w.split() if w]


def _plausible_name(x: str) -> bool:
    """Forme d'un nom : 1 a 4 mots qui commencent par une majuscule, pas une interjection."""
    words = _name_words(x)
    if not words or len(words) > 4 or len(x) > 30:
        return False
    if not all((not w[0].isalpha()) or w[0].isupper() for w in words):
        return False
    parts = [p for p in re.split(r"[\s\-,!.?'~]+", x.lower()) if p]
    return not all(p in _INTERJ for p in parts)


def _sub_line(l: Line, rest: str, singer: str) -> Line:
    """Garde seulement `rest` (la fin du texte), avec les timings qui vont avec."""
    rest = norm_text(rest)
    chars = None
    if l.chars:
        off = l.text.rfind(rest)
        if off >= 0:
            chars = l.chars[off:off + len(rest)]
    t = chars[0][0] if chars else l.time
    return Line(t, rest, singer, chars, l.end)


def extract_singers(lines: list[Line], artist: str = "") -> list[Line]:
    """Retire les noms de chanteurs "(Jennie) ...", "[Verse 2: Lisa]", "Rose: ..."
    du texte chante, et les met dans Line.singer."""
    artist_l = artist.lower()

    def candidate(text):
        """-> (etiquette, reste, forme) ou None. forme: '(' '[' ou ':'"""
        m = _LEAD_TAG.match(text)
        if m:
            return m.group(1), m.group(2).strip(), text.lstrip()[0]
        m = _LEAD_COLON.match(text)
        if m:
            return m.group(1), m.group(2).strip(), ":"
        return None

    # 1er passage : quelles etiquettes reviennent, et combien de noms differents ?
    counts: dict[str, int] = {}
    for l in lines:
        c = candidate(l.text)
        if c and _plausible_name(c[0]):
            counts[c[0].lower()] = counts.get(c[0].lower(), 0) + 1
    several = len(counts) >= 2

    def in_artist(x):
        if not artist_l:
            return False
        return x.lower() in artist_l or any(w.lower() in artist_l for w in _name_words(x) if len(w) > 2)

    def is_tag(tag, form):
        if _SECTION.match(tag) or form == "[":  # [ ... ] en debut de ligne = annotation
            return True
        if not _plausible_name(tag):
            return False
        strong = in_artist(tag) or counts.get(tag.lower(), 0) >= 2 or bool(_CONNECTOR.search(tag))
        if form == ":":  # "Nom: ..." -> on exige une preuve, sinon "Listen: ..." serait coupe
            return strong
        return strong or several

    out: list[Line] = []
    pending = ""
    for l in lines:
        c = candidate(l.text)
        tagged = bool(c and is_tag(c[0], c[2]))
        if not tagged:
            if not l.text:
                out.append(Line(l.time, "", ""))  # vraie pause instrumentale
                continue
            out.append(Line(l.time, l.text, pending, l.chars, l.end))
            pending = ""
            continue
        singer, rest = c[0], c[1]
        if ":" in singer:  # "[Verse 2: Lisa]" -> "Lisa"
            singer = singer.split(":", 1)[1].strip()
        if _SECTION.match(singer):
            singer = ""
        if not rest:
            # ligne qui ne contient que l'etiquette : on la colle a la ligne suivante
            pending = singer or pending
            continue
        out.append(_sub_line(l, rest, singer or pending))
        pending = ""
    return out


def add_pauses(lines: list[Line], min_gap: float = 4.0) -> list[Line]:
    """Avec le timing par mot on connait la fin de chaque ligne : on insere une
    ligne vide (les petits points) pendant les longues pauses instrumentales."""
    out = []
    for a, b in zip(lines, lines[1:] + [None]):
        out.append(a)
        if b and a.end and a.text and b.time - a.end > min_gap:
            out.append(Line(a.end + 0.4, ""))
    return out


# --------------------------------------------------------------------------
# Formats
# --------------------------------------------------------------------------
def parse_lrc(lrc: str) -> list[Line]:
    lines: list[Line] = []
    for raw in lrc.splitlines():
        stamps = _TS.findall(raw)
        if not stamps:
            continue
        text = norm_text(_WORD_TS.sub("", _TS.sub("", raw)))
        if _CREDIT.search(text):
            continue
        for m, s in stamps:
            lines.append(Line(int(m) * 60 + float(s), text))
    lines.sort(key=lambda l: l.time)
    return lines


def parse_yrc(yrc: str) -> list[Line]:
    """Format NetEase : [debut_ms,duree_ms](debut_ms,duree_ms,0)mot(...)mot ..."""
    lines: list[Line] = []
    for raw in yrc.splitlines():
        m = _YRC_LINE.match(raw.strip())
        if not m:
            continue  # lignes JSON de metadonnees, etc.
        body = m.group(3)
        marks = list(_YRC_WORD.finditer(body))
        segs = []
        for i, w in enumerate(marks):
            txt = body[w.end(): marks[i + 1].start() if i + 1 < len(marks) else len(body)]
            segs.append((int(w.group(1)) / 1000, int(w.group(2)) / 1000, txt))
        if not segs:
            continue
        line = build_line(segs)
        if line and not _CREDIT.search(line.text):
            lines.append(line)
    lines.sort(key=lambda l: l.time)
    return lines


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------
def clean_title(title: str) -> str:
    title = _JUNK.sub("", title)
    title = re.sub(r"\s*[\(\[]\s*(feat|ft)\.?[^\)\]]*[\)\]]", "", title, flags=re.I)
    title = re.sub(r"\s+(feat|ft)\.?\s.*$", "", title, flags=re.I)
    return title.strip()


def _simplify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^\w]+", " ", s).split())


_net = threading.local()  # pour savoir si une recherche a echoue a cause du reseau


def _http_json(url: str, headers: dict):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code >= 500 or e.code == 429:
            _net.failed = True
        return None  # 404 = vraiment pas trouve
    except Exception:
        _net.failed = True
        return None


def _get(path: str, params: dict):
    return _http_json(f"{API}/{path}?{urllib.parse.urlencode(params)}", HEADERS)


def _best(results, duration: float):
    if not isinstance(results, list):
        return None
    synced = [r for r in results if r.get("syncedLyrics")]
    if not synced:
        return None
    if duration > 0:
        synced.sort(key=lambda r: abs((r.get("duration") or 0) - duration))
        if abs((synced[0].get("duration") or 0) - duration) > 15:
            return None  # trop different : probablement pas la bonne version
    return synced[0]


def _lrclib(track: str, art: str, album: str, duration: float) -> list[Line] | None:
    if art:
        params = {"track_name": track, "artist_name": art}
        if album:
            params["album_name"] = album
        if duration > 0:
            params["duration"] = round(duration)
        hit = _get("get", params)
        if isinstance(hit, dict) and hit.get("syncedLyrics"):
            return parse_lrc(hit["syncedLyrics"])
        hit = _best(_get("search", {"track_name": track, "artist_name": art}), duration)
        if hit:
            return parse_lrc(hit["syncedLyrics"])
    hit = _best(_get("search", {"q": f"{art} {track}".strip()}), duration)
    return parse_lrc(hit["syncedLyrics"]) if hit else None


def _netease(track: str, art: str, duration: float):
    """-> (lignes mot a mot ou None, lignes par ligne ou None)"""
    q = urllib.parse.quote(f"{track} {art}".strip())
    res = _http_json(f"{NE_API}/search/get?s={q}&type=1&limit=10", NE_HEADERS)
    songs = ((res or {}).get("result") or {}).get("songs") or []
    want_t, want_a = _simplify(track), _simplify(art)
    asked_version = bool(_VERSION.search(track))
    scored = []
    for s in songs:
        name = s.get("name") or ""
        got_t = _simplify(clean_title(name))
        if not got_t or not want_t:
            continue
        exact = got_t == want_t
        close = (want_t in got_t or got_t in want_t) and \
            min(len(got_t), len(want_t)) / max(len(got_t), len(want_t)) > 0.6
        if not (exact or close):
            continue
        arts = [_simplify(a.get("name") or "") for a in s.get("artists") or []]
        art_ok = bool(want_a) and any(a and (a in want_a or want_a in a) for a in arts)
        d = (s.get("duration") or 0) / 1000
        diff = abs(d - duration) if duration > 0 and d > 0 else None
        if diff is not None and diff > 6:
            continue  # autre version du morceau : les timings seraient faux
        dur_ok = diff is not None and diff <= 3
        if not (art_ok or dur_ok):
            continue
        score = (2 if exact else 1) + (3 if art_ok else 0) + (2 if dur_ok else 0)
        if _VERSION.search(name) and not asked_version:
            score -= 4
        scored.append((score, s["id"]))
    scored.sort(reverse=True)

    line_level = None
    for _, sid in scored[:3]:
        ly = _http_json(f"{NE_API}/song/lyric/v1?id={sid}&lv=1&yv=1&tv=-1", NE_HEADERS) or {}
        yrc = (ly.get("yrc") or {}).get("lyric") or ""
        words = parse_yrc(yrc) if yrc else []
        if len(words) >= 3:
            return words, None
        lrc = (ly.get("lrc") or {}).get("lyric") or ""
        if lrc and line_level is None:
            parsed = parse_lrc(lrc)
            if len(parsed) >= 3:
                line_level = parsed
    return None, line_level


def _candidates(title: str, artist: str):
    t = clean_title(title)
    out = [(t, artist)]
    # Video YouTube classique : "Artiste - Titre" dans le titre
    if " - " in t:
        a, b = t.split(" - ", 1)
        out.append((clean_title(b), a.strip()))
    return out


def fetch_lyrics(title: str, artist: str, album: str = "", duration: float = 0) -> list[Line] | None:
    """Renvoie une liste de lignes horodatees (avec timing par mot si possible),
    ou None si rien de synchronise."""
    fallback = None
    lines = None
    for track, art in _candidates(title, artist):
        words, ne_lines = _netease(track, art, duration)
        if words:
            lines = add_pauses(words)
            break
        fallback = fallback or ne_lines
    if lines is None:
        for track, art in _candidates(title, artist):
            lines = _lrclib(track, art, album, duration)
            if lines:
                break
    lines = lines or fallback
    return split_adlibs(extract_singers(lines, artist)) if lines else None


def fetch_lyrics_ex(title: str, artist: str, album: str = "", duration: float = 0):
    """-> (lignes ou None, fiable). fiable=False : rien trouve MAIS le reseau a eu un souci,
    donc il faudra reessayer plus tard (ne pas retenir "pas de paroles")."""
    _net.failed = False
    lines = fetch_lyrics(title, artist, album, duration)
    return lines, not (lines is None and getattr(_net, "failed", False))


# --------------------------------------------------------------------------
# Titre de la chanson dans les paroles
# --------------------------------------------------------------------------
def mark_title_lines(lines: list[Line], title: str, artist: str = "", cooldown: float = 20.0):
    """Repere les lignes ou le chanteur dit le titre du morceau.

    Met line.title_span = (index du 1er mot, nb de mots) et line.title_drop = True
    pour les occurrences espacees d'au moins `cooldown` secondes (sinon un refrain
    qui repete le titre l'afficherait en geant en permanence)."""
    wanted = []
    for t, _ in _candidates(title, artist):
        w = _simplify(t).split()
        if w and w not in wanted:
            wanted.append(w)
    last = -1e9
    for l in lines:
        l.title_span, l.title_drop = None, False
        if not l.text:
            continue
        words = [_simplify(w) for w in l.text.split()]
        for tw in wanted:
            n = len(tw)
            if n > 7 or (n == 1 and len(tw[0]) < 4):
                continue  # titre trop long, ou mot trop banal ("si", "oh")
            for i in range(len(words) - n + 1):
                if words[i:i + n] == tw:
                    l.title_span = (i, n)
                    break
            if l.title_span:
                break
        if l.title_span and l.time - last >= cooldown:
            l.title_drop = True
            last = l.time


# --------------------------------------------------------------------------
# Cache sur le disque : paroles instantanees aux ecoutes suivantes, meme hors ligne
# --------------------------------------------------------------------------
try:
    from settings import DATA_DIR as _DATA_DIR
except Exception:
    _DATA_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(_DATA_DIR, "cache")
CACHE_VERSION = 1
MISSING_TTL = 7 * 86400  # un titre "sans paroles" est recherche de nouveau apres 7 jours


def _cache_path(title: str, artist: str) -> str:
    h = hashlib.sha1(f"{title.lower()}|{artist.lower()}".encode("utf-8")).hexdigest()[:24]
    return os.path.join(CACHE_DIR, h + ".json")


def cache_load(title: str, artist: str, duration: float = 0):
    """-> (trouve, lignes ou None)"""
    try:
        with open(_cache_path(title, artist), encoding="utf-8") as f:
            d = json.load(f)
        if d.get("v") != CACHE_VERSION:
            return False, None
        if duration > 0 and d.get("duration", 0) > 0 and abs(d["duration"] - duration) > 6:
            return False, None  # autre version du morceau
        if d["lines"] is None:
            return (time.time() - d.get("saved", 0) < MISSING_TTL), None
        out = []
        for x in d["lines"]:
            out.append(Line(x["t"], x["x"], x.get("s", ""),
                            [tuple(c) for c in x["c"]] if x.get("c") else None, x.get("e"),
                            x.get("a", ""), x.get("at"), x.get("tr", "")))
        return True, out
    except Exception:
        return False, None


def cache_save(title: str, artist: str, duration: float, lines):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        data = None
        if lines is not None:
            data = [{"t": l.time, "x": l.text, "s": l.singer, "c": l.chars, "e": l.end,
                     "a": l.adlib, "at": l.adlib_time, "tr": l.translation} for l in lines]
        with open(_cache_path(title, artist), "w", encoding="utf-8") as f:
            json.dump({"v": CACHE_VERSION, "title": title, "artist": artist, "duration": duration,
                       "saved": time.time(), "lines": data}, f, ensure_ascii=False)
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    res = fetch_lyrics(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "",
                       duration=float(sys.argv[3]) if len(sys.argv) > 3 else 0)
    if not res:
        print("Pas de paroles synchronisees")
    else:
        kind = "MOT A MOT" if any(l.chars for l in res) else "par ligne"
        print(f"{len(res)} lignes, timing {kind}")
