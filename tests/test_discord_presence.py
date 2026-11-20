import json
import struct
import time

import pytest

from followthelyrics.playback import track
from followthelyrics.system import discord_presence as dp


def song(
    playing=True,
    position=30.0,
    read_at=100.0,
    duration=200.0,
    title="Monte le son",
):
    return track.NowPlaying(
        title=title,
        artist="Encore une fois",
        album="",
        duration=duration,
        position=position,
        playing=playing,
        app="spotify",
        read_at=read_at,
    )


class FakeTransport:
    def __init__(self):
        self.sent = []
        self.inbox = b""

    def reply(self, op, payload):
        data = json.dumps(payload).encode()
        self.inbox += struct.pack("<II", op, len(data)) + data

    def write(self, data):
        op, size = struct.unpack("<II", data[:8])
        self.sent.append((op, json.loads(data[8 : 8 + size])))
        if op == 0:
            self.reply(1, {"evt": "READY"})
        else:
            self.reply(1, {"evt": None, "cmd": "SET_ACTIVITY"})

    def read(self, size):
        out, self.inbox = self.inbox[:size], self.inbox[size:]
        return out

    def close(self):
        self.closed = True


def test_listening_shows_title_artist_and_progress():
    activity = dp.build_activity(song(), True, wall=1000.0, mono=110.0)

    assert activity["type"] == dp.LISTENING
    assert activity["details"] == "Monte le son"
    assert activity["state"] == "Encore une fois"
    assert activity["timestamps"] == {"start": 960_000, "end": 1_160_000}
    assert [b["url"] for b in activity["buttons"]] == [
        dp.SITE_URL,
        dp.GITHUB_URL,
    ]


def test_hiding_the_track_keeps_the_app_and_links():
    activity = dp.build_activity(song(), False, wall=1000.0, mono=110.0)

    assert activity["type"] == dp.PLAYING
    assert "timestamps" not in activity
    assert activity["details"] == "Lyrics over games"
    assert len(activity["buttons"]) == 2


def test_paused_and_idle_states():
    assert dp.build_activity(song(playing=False), True)["state"] == "Paused"
    assert dp.build_activity(None, True)["state"] == "Waiting for music"


def test_long_titles_are_cut_for_discord():
    activity = dp.build_activity(
        song(title="x" * 300), True, wall=1000.0, mono=110.0
    )

    assert len(activity["details"]) == dp.TEXT_MAX


def test_small_clock_drift_does_not_resend():
    a = dp.build_activity(song(), True, wall=1000.0, mono=110.0)
    b = dp.build_activity(song(), True, wall=1001.0, mono=110.0)
    c = dp.build_activity(song(), True, wall=1010.0, mono=110.0)

    assert dp.same_activity(a, b)
    assert not dp.same_activity(a, c)


def test_ipc_paths_per_platform():
    assert dp.candidate_paths({}, "win32")[0] == r"\\?\pipe\discord-ipc-0"
    linux = dp.candidate_paths({"XDG_RUNTIME_DIR": "/run/user/1000"}, "linux")
    assert "/run/user/1000/discord-ipc-0" in [
        p.replace("\\", "/") for p in linux
    ]
    assert any(
        "app/com.discordapp.Discord" in p.replace("\\", "/") for p in linux
    )


def test_handshake_then_activity_frames():
    t = FakeTransport()
    dp.handshake(t, "123")
    dp.send_activity(t, {"details": "x"}, pid=42)

    assert t.sent[0] == (0, {"v": 1, "client_id": "123"})
    op, payload = t.sent[1]
    assert op == 1
    assert payload["cmd"] == "SET_ACTIVITY"
    assert payload["args"] == {"pid": 42, "activity": {"details": "x"}}


def wait_for(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_presence_sends_then_clears_when_turned_off(monkeypatch):
    monkeypatch.setattr(dp, "MIN_GAP", 0.0)
    t = FakeTransport()

    def connect(app_id):
        dp.handshake(t, app_id)
        return t

    presence = dp.DiscordPresence(app_id="123", connect=connect)
    presence.update(song(), True, True)
    assert wait_for(lambda: any(op == 1 for op, _ in t.sent))

    presence.update(song(), False, True)
    assert wait_for(lambda: t.sent[-1][1]["args"]["activity"] is None)
    presence.stop()


def test_nothing_happens_without_an_app_id():
    presence = dp.DiscordPresence(app_id="")
    presence.update(song(), True, True)

    assert not presence.available
    assert presence.thread is None


def itunes(*items):
    def fetch(url):
        fetch.url = url
        return {"results": list(items)}

    return fetch


def test_cover_found_on_itunes_in_large_size():
    fetch = itunes(
        {
            "trackName": "Monte le son (Remix)",
            "artistName": "Encore une fois",
            "artworkUrl100": "https://img.example/a/100x100bb.jpg",
        }
    )

    cover = dp.find_cover("Monte le son", "Encore une fois", fetch)

    assert cover == "https://img.example/a/512x512bb.jpg"
    assert "Monte+le+son" in fetch.url


def test_wrong_song_gives_no_cover():
    fetch = itunes(
        {
            "trackName": "Autre chanson",
            "artistName": "Encore une fois",
            "artworkUrl100": "https://img.example/b/100x100bb.jpg",
        }
    )

    assert dp.find_cover("Monte le son", "Encore une fois", fetch) is None


def test_cover_goes_big_and_logo_small():
    base = dp.build_activity(song(), True, wall=1000.0, mono=110.0)

    dressed = dp.with_cover(base, "https://img.example/c.jpg", "Album")

    assert dressed["assets"] == {
        "large_image": "https://img.example/c.jpg",
        "large_text": "Album",
        "small_image": dp.LOGO_URL,
        "small_text": dp.NAME,
    }
    assert base["assets"]["large_image"] == dp.LOGO_URL


def test_player_cover_url_is_used_without_lookup():
    presence = dp.DiscordPresence(app_id="123")
    presence.find = lambda t, a: pytest.fail("no lookup expected")

    url = presence.cover_for(("t", "a", "", "https://player.example/cover.jpg"))

    assert url == "https://player.example/cover.jpg"


def test_lookups_are_cached_and_failures_keep_the_logo():
    calls = []
    presence = dp.DiscordPresence(app_id="123")

    def find(title, artist):
        calls.append(title)
        raise OSError("offline")

    presence.find = find
    base = dp.build_activity(song(), True, wall=1000.0, mono=110.0)
    dressed = presence.dressed(
        base, ("Monte le son", "Encore une fois", "", "")
    )

    assert dressed["assets"]["large_image"] == dp.LOGO_URL
    presence.find = lambda t, a: calls.append(t) or "https://img.example/d.jpg"
    presence.cover_for(("Monte le son", "Encore une fois", "", ""))
    presence.cover_for(("Monte le son", "Encore une fois", "", ""))
    assert calls == ["Monte le son", "Monte le son"]
