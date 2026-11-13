import json

import pytest

from followthelyrics.lyrics import cache
from followthelyrics.lyrics import model


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", str(tmp_path))
    return tmp_path


def test_round_trip_keeps_every_field():
    line = model.Line(
        1.5,
        "Hello",
        singer="Ana",
        chars=[(1.5, 1.6)] * 5,
        end=3.0,
        adlib="yeah",
        adlib_time=2.0,
        translation="Bonjour",
    )
    cache.cache_save("Song", "Artist", 200.0, [line])

    found, lines = cache.cache_load("song", "ARTIST", 200.0)

    assert found
    assert lines == [line]


def test_load_misses_when_duration_differs_a_lot():
    cache.cache_save("Song", "Artist", 200.0, [model.Line(0.0, "x")])

    assert cache.cache_load("Song", "Artist", 240.0) == (False, None)
    assert cache.cache_load("Song", "Artist", 203.0)[0]


def test_known_missing_lyrics_are_remembered_until_ttl(monkeypatch):
    cache.cache_save("Song", "Artist", 0, None)

    assert cache.cache_load("Song", "Artist") == (True, None)

    monkeypatch.setattr(cache, "MISSING_TTL", -1)
    assert cache.cache_load("Song", "Artist") == (False, None)


def test_load_ignores_other_versions_and_corrupt_files(isolated_cache):
    cache.cache_save("Song", "Artist", 0, [model.Line(0.0, "x")])
    (path,) = isolated_cache.iterdir()

    path.write_text(json.dumps({"v": 0, "lines": []}), encoding="utf-8")
    assert cache.cache_load("Song", "Artist") == (False, None)

    path.write_text("{not json", encoding="utf-8")
    assert cache.cache_load("Song", "Artist") == (False, None)


def test_save_leaves_no_temporary_file(isolated_cache):
    cache.cache_save("Song", "Artist", 0, [model.Line(0.0, "x")])

    assert [p.suffix for p in isolated_cache.iterdir()] == [".json"]
    assert not any(p.name.startswith(".tmp-") for p in isolated_cache.iterdir())
