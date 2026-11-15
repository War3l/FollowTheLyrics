import difflib
import re
import unicodedata

from followthelyrics.lyrics import model

_TS = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")

_WORD_TS = re.compile(r"<\d+:\d+(?:\.\d+)?>")

_JUNK = re.compile(
    r"\s*[\(\[][^\)\]]*(official|video|audio|lyric|clip|visuali[sz]er|remaster|"
    r"live|hd|hq|4k|explicit|music)[^\)\]]*[\)\]]",
    re.IGNORECASE,
)

_YRC_LINE = re.compile(r"^\[(\d+),(\d+)\](.*)$")

_YRC_WORD = re.compile(r"\((\d+),(\d+),-?\d+\)")

_CREDIT = re.compile(
    r"^\s*[一-鿿 ]{1,8}\s*[:：]"
    r"|纯音乐|作词|作曲|编曲|制作人|混音|母带|监制|出品"
    r"|^\s*(artist|song|album|title|lyrics|lyricist|composer|producer|"
    r"written by|lyrics by|composed by|produced by)\s*[:：]",
    re.IGNORECASE,
)

_PUNCT = set(",.!?;:…")


def _squash(line: model.Line, idxs: list[int]):
    text: list[str] = []
    times: list = []
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


def split_adlibs(lines: list[model.Line]) -> list[model.Line]:
    out = []
    for line in lines:
        if "(" not in line.text:
            out.append(line)
            continue
        main: list[int] = []
        ad: list[int] = []
        depth = 0
        for i, ch in enumerate(line.text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            else:
                (ad if depth else main).append(i)
        mt, mc = _squash(line, main)
        at, ac = _squash(line, ad)
        if not mt or not at:
            txt, chars = _squash(line, sorted(main + ad))
            out.append(
                model.Line(
                    line.time,
                    txt,
                    line.singer,
                    chars,
                    line.end,
                    translation=line.translation,
                )
            )
            continue
        out.append(
            model.Line(
                line.time,
                mt,
                line.singer,
                mc,
                line.end,
                adlib=at,
                adlib_time=(ac[0][0] if ac else None),
                translation=line.translation,
            )
        )
    return out


_INTERJ = {
    "oh",
    "ooh",
    "oooh",
    "ohh",
    "o",
    "ah",
    "ahh",
    "aah",
    "uh",
    "uhh",
    "huh",
    "yeah",
    "yeh",
    "ya",
    "yah",
    "yea",
    "hey",
    "ho",
    "hoo",
    "woo",
    "wooh",
    "whoa",
    "woah",
    "wow",
    "na",
    "nah",
    "la",
    "da",
    "di",
    "do",
    "yo",
    "eh",
    "ey",
    "ay",
    "ayy",
    "mm",
    "mmm",
    "hmm",
    "baby",
    "okay",
    "ok",
    "oui",
    "non",
    "ouais",
    "wee",
    "skrrt",
    "brr",
    "go",
    "come",
    "on",
    "yes",
    "no",
    "uh-huh",
    "ha",
    "haha",
    "shh",
    "hello",
    "bye",
    "boom",
    "bang",
    "pow",
    "sha",
    "doo",
    "dum",
    "ba",
    "bam",
}

_SECTION = re.compile(
    r"^(all|both|tous|toutes|ensemble|together|everyone|group|chorus|pre-?chorus|refrain|"
    r"pr[eé]-?refrain|verse|couplet|bridge|pont|intro|outro|hook|interlude|instrumental)\b",
    re.IGNORECASE,
)

_LEAD_TAG = re.compile(
    r"^\s*[\(\[]\s*([^\)\]]{1,40}?)\s*:?\s*[\)\]]\s*:?\s*(.*)$"
)

_LEAD_COLON = re.compile(r"^\s*([^\s:()\[\]][^:()\[\]]{0,24}?)\s*:\s+(.+)$")

_CONNECTOR = re.compile(
    r"\s*(?:&|,|\+|/|\band\b|\bet\b|\bx\b|\bwith\b)\s*", re.IGNORECASE
)


def _name_words(x: str):
    return [w for w in _CONNECTOR.split(x.strip()) for w in w.split() if w]


def _plausible_name(x: str) -> bool:
    words = _name_words(x)
    if not words or len(words) > 4 or len(x) > 30:
        return False
    if not all((not w[0].isalpha()) or w[0].isupper() for w in words):
        return False
    parts = [p for p in re.split(r"[\s\-,!.?'~]+", x.lower()) if p]
    return not all(p in _INTERJ for p in parts)


def _sub_line(line: model.Line, rest: str, singer: str) -> model.Line:
    rest = model.norm_text(rest)
    chars = None
    if line.chars:
        off = line.text.rfind(rest)
        if off >= 0:
            chars = line.chars[off : off + len(rest)]
    t = chars[0][0] if chars else line.time
    return model.Line(t, rest, singer, chars, line.end)


def extract_singers(
    lines: list[model.Line], artist: str = ""
) -> list[model.Line]:
    artist_l = artist.lower()

    def candidate(text):
        m = _LEAD_TAG.match(text)
        if m:
            return m.group(1), m.group(2).strip(), text.lstrip()[0]
        m = _LEAD_COLON.match(text)
        if m:
            return m.group(1), m.group(2).strip(), ":"
        return None

    counts: dict[str, int] = {}
    for line in lines:
        c = candidate(line.text)
        if c and _plausible_name(c[0]):
            counts[c[0].lower()] = counts.get(c[0].lower(), 0) + 1
    several = len(counts) >= 2

    def in_artist(x):
        if not artist_l:
            return False
        return x.lower() in artist_l or any(
            w.lower() in artist_l for w in _name_words(x) if len(w) > 2
        )

    def is_tag(tag, form):
        if _SECTION.match(tag) or form == "[":
            return True
        if not _plausible_name(tag):
            return False
        strong = (
            in_artist(tag)
            or counts.get(tag.lower(), 0) >= 2
            or bool(_CONNECTOR.search(tag))
        )
        if form == ":":
            return strong
        return strong or several

    out: list[model.Line] = []
    pending = ""
    for line in lines:
        c = candidate(line.text)
        tagged = bool(c and is_tag(c[0], c[2]))
        if not tagged:
            if not line.text:
                out.append(model.Line(line.time, "", ""))
                continue
            out.append(
                model.Line(line.time, line.text, pending, line.chars, line.end)
            )
            pending = ""
            continue
        singer, rest = c[0], c[1]
        if ":" in singer:
            singer = singer.split(":", 1)[1].strip()
        if _SECTION.match(singer):
            singer = ""
        if not rest:
            pending = singer or pending
            continue
        out.append(_sub_line(line, rest, singer or pending))
        pending = ""
    return out


def add_pauses(
    lines: list[model.Line], min_gap: float = 4.0
) -> list[model.Line]:
    out = []
    for a, b in zip(lines, [*lines[1:], None], strict=False):
        out.append(a)
        if b and a.end and a.text and b.time - a.end > min_gap:
            out.append(model.Line(a.end + 0.4, ""))
    return out


def parse_lrc(lrc: str) -> list[model.Line]:
    lines: list[model.Line] = []
    for raw in lrc.splitlines():
        stamps = _TS.findall(raw)
        if not stamps:
            continue
        text = model.norm_text(_WORD_TS.sub("", _TS.sub("", raw)))
        if _CREDIT.search(text):
            continue
        for m, s in stamps:
            lines.append(model.Line(int(m) * 60 + float(s), text))
    lines.sort(key=lambda line: line.time)
    return lines


def parse_yrc(yrc: str) -> list[model.Line]:
    lines: list[model.Line] = []
    for raw in yrc.splitlines():
        m = _YRC_LINE.match(raw.strip())
        if not m:
            continue
        body = m.group(3)
        marks = list(_YRC_WORD.finditer(body))
        segs = []
        for i, w in enumerate(marks):
            txt = body[
                w.end() : marks[i + 1].start()
                if i + 1 < len(marks)
                else len(body)
            ]
            segs.append((int(w.group(1)) / 1000, int(w.group(2)) / 1000, txt))
        if not segs:
            continue
        line = model.build_line(segs)
        if line and not _CREDIT.search(line.text):
            lines.append(line)
    lines.sort(key=lambda line: line.time)
    return lines


MASK = "*"

MASK_WINDOW = 6.0

_MASK_RUN = re.compile(r"\*+")

_EDGES = re.compile(r"^([^\w*]*)(.*?)([^\w*]*)$", re.DOTALL)


def has_masked(lines: list[model.Line]) -> bool:
    return any(MASK in line.text for line in lines)


def _core(word: str) -> str:
    m = _EDGES.match(word)
    return m.group(2) if m else word


def _unmask_word(masked: str, ref: str, shout: bool) -> str | None:
    m = _EDGES.match(masked)
    if not m:
        return None
    lead, core, trail = m.groups()
    found = _core(ref)
    if not found or MASK in found:
        return None
    pattern = "".join(
        r"[^\s*]+" if _MASK_RUN.fullmatch(part) else re.escape(part)
        for part in re.split(r"(\*+)", core)
        if part
    )
    if not re.fullmatch(pattern, found, re.IGNORECASE):
        return None
    letters = [ch for ch in core if ch.isalpha()]
    if all(ch.isupper() for ch in letters) if letters else shout:
        found = found.upper()
    return lead + found + trail


def _unmask_words(words: list[str], ref: list[str]) -> list[str] | None:
    a = [simplify(_core(w)) for w in words]
    b = [simplify(_core(w)) for w in ref]
    out = list(words)
    plain = [ch for w in words if MASK not in w for ch in w if ch.isalpha()]
    shout = bool(plain) and all(ch.isupper() for ch in plain)
    anchored = False
    done = False
    codes = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    for tag, i1, i2, j1, j2 in codes:
        if tag == "equal":
            anchored = True
        elif tag == "replace" and i2 - i1 == j2 - j1:
            for i, j in zip(range(i1, i2), range(j1, j2), strict=True):
                if MASK not in words[i]:
                    continue
                fixed = _unmask_word(words[i], ref[j], shout)
                if fixed:
                    out[i] = fixed
                    done = True
    if not done or not (anchored or len(words) == len(ref)):
        return None
    return out


def _retime(line: model.Line, words: list[str]) -> None:
    old = line.text.split(" ")
    if line.chars is None or len(line.chars) != len(line.text):
        line.text = " ".join(words)
        return
    chars: list[tuple[float, float]] = []
    at = 0
    for k, (before, after) in enumerate(zip(old, words, strict=True)):
        if k:
            chars.append(line.chars[at])
            at += 1
        span = line.chars[at : at + len(before)]
        at += len(before)
        if before == after or not span:
            chars.extend(span)
            continue
        start, end = span[0][0], span[-1][1]
        n = len(after)
        chars.extend(
            (start + (end - start) * i / n, start + (end - start) * (i + 1) / n)
            for i in range(n)
        )
    line.text = " ".join(words)
    line.chars = chars


def restore_masked(
    lines: list[model.Line], reference: list[model.Line]
) -> list[model.Line]:
    for line in lines:
        if MASK not in line.text:
            continue
        words = line.text.split(" ")
        near = sorted(
            (
                ref
                for ref in reference
                if ref.text and abs(ref.time - line.time) <= MASK_WINDOW
            ),
            key=lambda ref: abs(ref.time - line.time),
        )
        best = None
        for ref in near:
            fixed = _unmask_words(words, ref.text.split(" "))
            if fixed is None:
                continue
            left = sum(MASK in w for w in fixed)
            if best is None or left < best[0]:
                best = (left, fixed)
            if left == 0:
                break
        if best:
            _retime(line, best[1])
    return lines


def clean_title(title: str) -> str:
    title = _JUNK.sub("", title)
    title = re.sub(
        r"\s*[\(\[]\s*(feat|ft)\.?[^\)\]]*[\)\]]", "", title, flags=re.I
    )
    title = re.sub(r"\s+(feat|ft)\.?\s.*$", "", title, flags=re.I)
    return title.strip()


def simplify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^\w]+", " ", s).split())


def candidates(title: str, artist: str):
    t = clean_title(title)
    out = [(t, artist)]
    if " - " in t:
        a, b = t.split(" - ", 1)
        out.append((clean_title(b), a.strip()))
    return out


def mark_title_lines(
    lines: list[model.Line],
    title: str,
    artist: str = "",
    cooldown: float = 20.0,
):
    wanted = []
    for t, _ in candidates(title, artist):
        w = simplify(t).split()
        if w and w not in wanted:
            wanted.append(w)
    last = -1e9
    for line in lines:
        line.title_span, line.title_drop = None, False
        if not line.text:
            continue
        words = [simplify(w) for w in line.text.split()]
        for tw in wanted:
            n = len(tw)
            if n > 7 or (n == 1 and len(tw[0]) < 4):
                continue
            for i in range(len(words) - n + 1):
                if words[i : i + n] == tw:
                    line.title_span = (i, n)
                    break
            if line.title_span:
                break
        if line.title_span and line.time - last >= cooldown:
            line.title_drop = True
            last = line.time
