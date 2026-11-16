import pytest

from followthelyrics.lyrics import model
from followthelyrics.lyrics import parsing
from followthelyrics.lyrics import providers

YRC = "\n".join(
    f"[{1000 * i},900](0,400,0)Monte (400,400,0)le son" for i in range(1, 5)
)
OTHER = "\n".join(
    f"[{1000 * i},900](0,400,0)Autre (400,400,0)chose" for i in range(1, 5)
)


class FakeSession(providers._Session):
    def __init__(self, songs, lyrics):
        super().__init__()
        self.songs = songs
        self.lyrics = lyrics
        self.asked = []

    def get_json(self, url, headers):
        if "/search/get" in url:
            return {"result": {"songs": self.songs}}
        if "/song/lyric" in url:
            sid = int(url.split("id=")[1].split("&")[0])
            self.asked.append(sid)
            return {"yrc": {"lyric": self.lyrics.get(sid, "")}}
        if "lrclib.net" in url:
            return self.lrclib_hit
        return None

    lrclib_hit = None


def song(sid, name, artist, seconds):
    return {
        "id": sid,
        "name": name,
        "artists": [{"name": artist}],
        "duration": seconds * 1000,
    }


def test_cover_by_another_artist_is_not_taken_on_duration_alone():
    session = FakeSession(
        [
            song(1, "Tourne (Comme un disque)", "Une Autre", 197),
            song(2, "Tourne (Comme un disque)", "Le Groupe", 195),
        ],
        {1: OTHER, 2: YRC},
    )
    lines = providers._fetch(
        session,
        "Le Groupe - Tourne (Comme un disque) (Official Video)",
        "Le Groupe",
        "",
        197,
    )
    assert lines and lines[0].text.startswith("Monte")
    assert 1 not in session.asked


def test_channel_name_glued_together_still_matches_the_artist():
    assert providers._same_artist("legroupevevo", ["le groupe"])
    assert not providers._same_artist("une autre", ["le groupe"])
    assert not providers._same_artist("", ["le groupe"])


def test_closest_duration_wins_between_equal_matches():
    session = FakeSession(
        [
            song(9, "Tourne", "Le Groupe", 203),
            song(3, "Tourne", "Le Groupe", 200),
        ],
        {},
    )
    hits = providers._netease_search(session, "Tourne", "Le Groupe", 200)
    assert [sid for _, sid in hits] == [3, 9]


def test_unknown_artist_needs_exact_title_and_duration():
    session = FakeSession(
        [
            song(1, "Tourne encore", "Une Autre", 200),
            song(2, "Tourne", "Une Autre", 200),
            song(3, "Tourne", "Une Autre", 205),
        ],
        {},
    )
    hits = providers._netease_search(session, "Tourne", "Chaine", 200)
    assert hits == [(False, 2)]


def test_header_lines_are_not_lyrics():
    lines = parsing.parse_lrc(
        "[00:00.10]Artist: Le Groupe\n[00:00.40]Album : Disque\n"
        "[00:05.00]Monte le son\n"
    )
    assert [line.text for line in lines] == ["Monte le son"]


MASKED = "\n".join(
    f"[{1000 * i},900](0,300,0)Monte (300,300,0)le (600,300,0)s*n"
    for i in range(1, 5)
)
CLEAR = "\n".join(f"[00:0{i}.00]Monte le son" for i in range(1, 5))


def test_masked_words_are_restored_from_the_other_source():
    session = FakeSession([song(2, "Tourne", "Le Groupe", 195)], {2: MASKED})
    session.lrclib_hit = {"syncedLyrics": CLEAR}

    lines = providers._fetch(session, "Tourne", "Le Groupe", "", 195)

    assert lines and all(
        line.text == "Monte le son" for line in lines if line.text
    )
    first = lines[0]
    assert first.chars and len(first.chars) == len(first.text)
    assert first.chars[-1][1] == pytest.approx(0.9)


def test_masked_words_stay_when_the_other_source_has_nothing():
    session = FakeSession([song(2, "Tourne", "Le Groupe", 195)], {2: MASKED})

    lines = providers._fetch(session, "Tourne", "Le Groupe", "", 195)

    assert lines and lines[0].text == "Monte le s*n"


def test_restore_keeps_case_punctuation_and_word_timing():
    line = model.build_line(
        [(1.0, 0.4, "MONTE "), (1.4, 0.4, "LE "), (1.8, 0.6, "****!")]
    )
    reference = [model.Line(1.2, "Monte le son")]

    parsing.restore_masked([line], reference)

    assert line.text == "MONTE LE SON!"
    assert line.chars[9][0] == pytest.approx(1.8)
    assert line.chars[-1][1] == pytest.approx(2.4)


def test_restore_ignores_a_line_that_does_not_match():
    line = model.build_line(
        [(1.0, 0.4, "Monte "), (1.4, 0.4, "le "), (1.8, 0.6, "s*n")]
    )
    far = [model.Line(40.0, "Monte le son")]
    other = [model.Line(1.0, "Autre chose ici")]

    parsing.restore_masked([line], far)
    parsing.restore_masked([line], other)

    assert line.text == "Monte le s*n"


def _texts(lines):
    return [line.text for line in lines]


def test_credits_at_both_ends_are_removed():
    lines = [
        model.Line(0.0, "Tourne - Le Groupe"),
        model.Line(0.5, "Synced by quelquun"),
        model.Line(1.0, "Lyrics provided by exemple.com"),
        model.Line(5.0, "Monte le son"),
        model.Line(8.0, "Encore une fois"),
        model.Line(11.0, ""),
        model.Line(12.0, "www.exemple.com"),
    ]

    kept = parsing.strip_credits(lines, "Tourne", "Le Groupe")

    assert _texts(kept) == ["Monte le son", "Encore une fois", ""]


def test_credit_words_inside_the_song_are_kept():
    lines = [
        model.Line(1.0, "Monte le son"),
        model.Line(4.0, "Written by the stars above"),
        model.Line(7.0, "Encore une fois"),
    ]

    assert parsing.strip_credits(lines, "Tourne", "Le Groupe") == lines


def test_a_song_made_only_of_matching_lines_is_left_alone():
    lines = [
        model.Line(1.0, "Written by you"),
        model.Line(3.0, "Produced by me"),
    ]

    assert parsing.strip_credits(lines, "Tourne", "Le Groupe") == lines
