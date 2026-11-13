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
        return None


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
