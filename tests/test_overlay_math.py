import numpy as np
import pytest

from followthelyrics.lyrics import analysis
from followthelyrics.lyrics import model
from followthelyrics.overlay import animation
from followthelyrics.overlay import colors
from followthelyrics.playback import audio


def test_easing_bounds():
    assert animation.clamp(2.0) == 1.0
    assert animation.clamp(-1.0) == 0.0
    assert animation.ease_out(0.0) == 0.0
    assert animation.ease_out(1.0) == pytest.approx(1.0)
    assert animation.lerp(0.0, 10.0, 0.25) == 2.5


def test_held_fx_is_neutral_outside_the_word():
    neutral = (1.0, 0.0, 0.0, 0.0, 1.0)

    assert animation.held_fx(None, 1.0) == neutral
    assert animation.held_fx((2.0, 3.0, 1.0), 1.0) == neutral
    assert animation.held_fx((2.0, 3.0, 1.0), 4.0) == neutral
    assert animation.held_fx((2.0, 3.0, 1.0), 2.5)[0] > 1.0


@pytest.mark.parametrize(
    "rgb", [(255, 255, 255), (0, 0, 0), (200, 30, 30), (20, 120, 220)]
)
def test_lch_round_trip(rgb):
    back = colors.lch_to_rgb(*colors.rgb_to_lch(rgb))

    assert all(abs(a - b) <= 2 for a, b in zip(back, rgb, strict=True))


def test_hue_diff_wraps_around():
    assert colors.hue_diff(350, 10) == pytest.approx(20)


def test_palette_falls_back_to_white_for_grey_covers():
    grey = np.full((64, 3), 128, dtype=np.uint8)

    palette = colors.palette_rgb(grey)

    assert len(palette) == 3
    assert all(min(c) > 230 for c in palette)


def test_palette_follows_a_coloured_cover():
    red = np.tile(np.array([[200, 30, 30]], dtype=np.uint8), (64, 1))

    palette = colors.palette_rgb(red)

    r, g, b = palette[0]
    assert r > g and r > b


def test_palette_handles_missing_pixels():
    assert colors.palette_rgb(None) is None


def test_mark_chorus_flags_lines_sung_twice():
    lines = [
        model.Line(0.0, "This is the chorus"),
        model.Line(1.0, "A first verse line"),
        model.Line(2.0, "A second verse line"),
        model.Line(3.0, "A third verse line"),
        model.Line(4.0, "this is the CHORUS!"),
    ]

    analysis.mark_chorus(lines)

    assert [line.chorus for line in lines] == [True, False, False, False, True]


def test_mark_chorus_needs_three_repeats_in_repetitive_songs():
    lines = [model.Line(float(i), "around the world") for i in range(2)]
    lines.append(model.Line(2.0, "something else"))

    analysis.mark_chorus(lines)

    assert not any(line.chorus for line in lines)


def sung(text, start, per_char):
    chars, t = [], start
    for ch in text:
        step = 0.0 if ch == " " else per_char
        chars.append((t, t + step))
        t += step
    return model.Line(start, text, chars=chars)


def test_compute_word_meta_marks_held_words():
    verses = [sung("quick words sung fast", i * 5.0, 0.05) for i in range(4)]
    held = sung("so heyy", 30.0, 0.05)
    held.chars[-1] = (held.chars[-1][0], held.chars[-1][0] + 2.5)

    analysis.compute_word_meta([*verses, held])

    assert all(meta[2] == 0.0 for meta in verses[0].word_meta.values())
    assert held.word_meta[0][2] == 0.0
    assert held.word_meta[3][2] > 0.5


def test_word_key_folds_accents():
    assert analysis.word_key("Été!") == "ete"


def test_beat_detector_fires_on_a_bass_hit_after_silence():
    rate = 48000
    det = audio.BeatDetector(rate)
    t = np.arange(audio.BLOCK) / rate
    quiet = (0.001 * np.sin(2 * np.pi * 80 * t)).astype(np.float32)
    hit = (0.9 * np.sin(2 * np.pi * 80 * t)).astype(np.float32)

    for i in range(30):
        assert det.feed(quiet, i * 0.02) == 0.0

    assert det.feed(hit, 1.0) > 0.0
    assert det.feed(hit, 1.05) == 0.0
