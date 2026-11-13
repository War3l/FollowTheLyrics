from dataclasses import dataclass
from dataclasses import field


@dataclass(slots=True)
class Line:
    time: float
    text: str
    singer: str = ""
    chars: list[tuple[float, float]] | None = field(default=None, repr=False)
    end: float | None = None
    adlib: str = ""
    adlib_time: float | None = None
    translation: str = ""
    title_span: tuple[int, int] | None = None
    title_drop: bool = False
    word_meta: dict[int, tuple[float, float, float]] | None = field(
        default=None, repr=False
    )
    chorus: bool = False


def norm_text(s: str) -> str:
    return " ".join(s.split())


def build_line(segments) -> Line | None:
    text: list[str] = []
    times: list[tuple[float, float]] = []
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
