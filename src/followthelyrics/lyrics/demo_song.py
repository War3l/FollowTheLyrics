from types import SimpleNamespace

from followthelyrics.lyrics import model
from followthelyrics.lyrics import parsing


def demo_line(t, text, singer=""):
    if not text:
        return model.Line(t, "")
    segs = [(t, 0.01, f"({singer}) ")] if singer else []
    for k, raw in enumerate(text.split()):
        held = raw.endswith("~")
        w = raw.rstrip("~")
        dur = (
            1.6 if held else 0.12 + 0.045 * len(w) + (0.25 if k % 4 == 3 else 0)
        )
        segs.append((t, dur, w + " "))
        t += dur + (0.08 if w.endswith(",") else 0.02)
    return model.build_line(segs)


DEMO_LINES = parsing.split_adlibs(
    parsing.extract_singers(
        [
            demo_line(2.0, "Les neons dansent sur l'ecran"),
            demo_line(5.5, "Je joue la nuit (oh oh), je perds le temps"),
            demo_line(9.0, "Monte le son, garde le rythme~", "Nova"),
            demo_line(12.5, "Comme un refrain qui revient~"),
            demo_line(16.0, ""),
            demo_line(19.0, "Monte le son, garde le rythme~", "Kai"),
            demo_line(22.5, "Les paroles brillent (yeah), rien ne s'arrete"),
            demo_line(
                26.5,
                "Une derniere ligne pour la route, et on relance la partie",
            ),
            demo_line(32.0, ""),
        ]
    )
)
DEMO_LENGTH = 34.0
DEMO_KEY = ("monte le son", "followthelyrics (demo)")


def demo_track(position):
    return SimpleNamespace(
        title="Monte le son",
        artist="FollowTheLyrics (demo)",
        album="Demo",
        duration=DEMO_LENGTH,
        position=position,
        playing=True,
        app="demo",
        key=DEMO_KEY,
    )
