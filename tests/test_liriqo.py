import io
import json
import urllib.error

import pytest

from followthelyrics.lyrics import cache
from followthelyrics.lyrics import model
from followthelyrics.lyrics import providers


def _word(text, start, end):
    return {"text": text, "start": start, "end": end}


def _track(level="word"):
    return {
        "syncLevel": level,
        "provider": "test",
        "timed": [
            {
                "text": "Monte le son",
                "start": 1000,
                "end": 2500,
                "words": [
                    _word("Monte", 1000, 1500),
                    _word("le", 1500, 1800),
                    _word("son", 1800, 2500),
                ],
            },
            {
                "text": "Encore plus fort",
                "start": 3000,
                "end": 4500,
                "words": [
                    _word("En", 3000, 3200),
                    _word("core", 3200, 3500),
                    _word("plus", 3500, 4000),
                    _word("fort", 4000, 4500),
                ],
            },
            {"text": "", "start": 5000, "end": 6000, "isInstrumental": True},
            {"text": "Jusqu'au matin", "start": 7000, "end": 8000},
        ],
    }


def _answer(monkeypatch, payload=None, error=None):
    def fake(request, timeout):
        if error is not None:
            raise error
        return io.BytesIO(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake)


def test_word_timing_is_spread_over_the_letters():
    lines = providers.parse_liriqo(_track())

    assert [line.text for line in lines] == [
        "Monte le son",
        "Encore plus fort",
        "Jusqu'au matin",
    ]
    first = lines[0]
    assert first.time == 1.0
    assert first.end == 2.5
    assert first.chars is not None
    assert len(first.chars) == len(first.text)
    assert first.chars[0][0] == pytest.approx(1.0)
    assert first.chars[-1][1] == pytest.approx(2.5)


def test_syllables_of_a_word_are_not_separated():
    lines = providers.parse_liriqo(_track("syllable"))

    assert lines[1].text == "Encore plus fort"


def test_line_level_track_has_no_word_timing():
    lines = providers.parse_liriqo(_track("line"))

    assert not providers.has_words(lines)
    assert lines[0].time == 1.0


def test_words_can_come_from_the_top_level_list():
    track = _track()
    track["words"] = [line.pop("words", []) for line in track["timed"]]

    assert providers.has_words(providers.parse_liriqo(track))


def test_fetch_returns_word_lines(monkeypatch):
    _answer(
        monkeypatch,
        {
            "metadata": {"title": "Monte le son", "duration": "200"},
            "primary": _track(),
        },
    )

    lines, settled = providers.fetch_liriqo("Monte le son", "Groupe", 200)

    assert settled
    assert providers.has_words(lines)


def test_fetch_rejects_another_song(monkeypatch):
    _answer(
        monkeypatch,
        {
            "metadata": {"title": "Autre chose", "duration": "200"},
            "primary": _track(),
        },
    )

    assert providers.fetch_liriqo("Monte le son", "Groupe", 200) == (
        None,
        True,
    )


def test_fetch_rejects_another_duration(monkeypatch):
    _answer(
        monkeypatch,
        {
            "metadata": {"title": "Monte le son", "duration": "320"},
            "primary": _track(),
        },
    )

    assert providers.fetch_liriqo("Monte le son", "Groupe", 200) == (
        None,
        True,
    )


def test_line_level_answer_is_useless_when_words_are_wanted(monkeypatch):
    payload = {"metadata": {"title": "Monte le son"}, "primary": _track("line")}
    _answer(monkeypatch, payload)

    assert providers.fetch_liriqo("Monte le son", "Groupe")[0] is None
    lines, _ = providers.fetch_liriqo(
        "Monte le son", "Groupe", want_words=False
    )
    assert lines


def test_nothing_found_is_a_settled_answer(monkeypatch):
    _answer(monkeypatch, {"primary": None, "tracks": [], "count": 0})

    assert providers.fetch_liriqo("Monte le son", "Groupe") == (None, True)


@pytest.mark.parametrize(
    ("code", "settled"), [(503, False), (429, False), (404, True)]
)
def test_busy_server_asks_for_a_retry(monkeypatch, code, settled):
    error = urllib.error.HTTPError("u", code, "x", None, None)  # type: ignore[arg-type]
    _answer(monkeypatch, error=error)

    assert providers.fetch_liriqo("Monte le son", "Groupe") == (None, settled)


def test_cache_remembers_a_final_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", str(tmp_path))
    lines = [model.Line(1.0, "Monte le son")]

    cache.cache_save("Song", "Artist", 200.0, lines)
    assert not cache.cache_is_final("Song", "Artist")

    cache.cache_save("Song", "Artist", 200.0, lines, final=True)
    assert cache.cache_is_final("Song", "Artist")
    assert not cache.cache_is_final("Other", "Artist")
