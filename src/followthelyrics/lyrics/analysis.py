import re
import statistics

from followthelyrics.overlay import animation


def compute_word_meta(lines):
    per_char = []
    for line in lines:
        if not line.chars:
            continue
        c = 0
        for w in line.text.split():
            seg = line.chars[c : c + len(w)]
            if len(w) >= 2 and seg:
                d = seg[-1][1] - seg[0][0]
                if d > 0:
                    per_char.append(d / len(w))
            c += len(w) + 1
    base = statistics.median(per_char) if per_char else 0.07
    for line in lines:
        meta = {}
        if line.chars:
            c = 0
            for w in line.text.split():
                seg = line.chars[c : c + len(w)]
                if seg:
                    start, end = seg[0][0], seg[-1][1]
                    d = end - start
                    ratio = d / (len(w) * base + 0.12)
                    meta[c] = (
                        start,
                        end,
                        animation.clamp((ratio - 2.0) / 2.5)
                        if d >= 0.45
                        else 0.0,
                    )
                c += len(w) + 1
        line.word_meta = meta


def mark_chorus(lines):
    def key(t):
        return " ".join(re.sub(r"[^\w]+", " ", t.lower()).split())

    counts = {}
    for line in lines:
        k = key(line.text)
        if len(k) >= 6:
            counts[k] = counts.get(k, 0) + 1
    texts = [line for line in lines if line.text]
    rep = sum(1 for line in texts if counts.get(key(line.text), 0) >= 2)
    need = 3 if texts and rep / len(texts) > 0.6 else 2
    for line in lines:
        line.chorus = counts.get(key(line.text), 0) >= need


COMMON_WORDS = frozenset(
    [
        "avec",
        "dans",
        "pour",
        "plus",
        "mais",
        "comme",
        "tout",
        "tous",
        "toute",
        "cette",
        "elle",
        "elles",
        "nous",
        "vous",
        "leur",
        "leurs",
        "sans",
        "sous",
        "quand",
        "alors",
        "aussi",
        "encore",
        "jamais",
        "toujours",
        "etre",
        "avoir",
        "fait",
        "faire",
        "suis",
        "sont",
        "etait",
        "veux",
        "peux",
        "vais",
        "that",
        "this",
        "with",
        "from",
        "your",
        "what",
        "when",
        "where",
        "have",
        "just",
        "like",
        "dont",
        "cant",
        "youre",
        "they",
        "them",
        "then",
        "than",
        "there",
        "here",
        "were",
        "been",
        "will",
        "would",
        "could",
        "should",
        "about",
        "into",
        "over",
        "some",
        "know",
        "want",
        "gonna",
        "wanna",
        "yeah",
    ]
)


def word_key(word):
    table = str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc")
    return re.sub(r"[^a-z0-9]", "", word.lower().translate(table))


def count_word_lines(lines):
    counts = {}
    for line in lines:
        for k in {word_key(w) for w in line.text.split()}:
            if k:
                counts[k] = counts.get(k, 0) + 1
    return counts
