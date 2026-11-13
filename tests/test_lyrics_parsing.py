import pytest

from followthelyrics.lyrics import model
from followthelyrics.lyrics import parsing


def test_parse_lrc_sorts_lines_and_expands_repeated_stamps():
    lrc = "[00:12.50]Hello world\n[00:01.00][00:30.00]Repeat me\nno stamp"

    lines = parsing.parse_lrc(lrc)

    assert [(line.time, line.text) for line in lines] == [
        (1.0, "Repeat me"),
        (12.5, "Hello world"),
        (30.0, "Repeat me"),
    ]


def test_parse_lrc_strips_word_stamps_and_collapses_spaces():
    lines = parsing.parse_lrc("[01:02.00]Hello   <01:02.40>world")

    assert lines[0].time == 62.0
    assert lines[0].text == "Hello world"


def test_parse_lrc_drops_credit_lines():
    lines = parsing.parse_lrc("[00:01.00]作词 : someone\n[00:02.00]Real line")

    assert [line.text for line in lines] == ["Real line"]


def test_parse_yrc_builds_per_character_timing():
    yrc = (
        "[1000,2000](1000,500,0)Hel(1500,500,0)lo (2000,1000,0)there\n"
        '{"t":0,"c":[{"tx":"metadata"}]}'
    )

    (line,) = parsing.parse_yrc(yrc)

    assert line.text == "Hello there"
    assert line.time == 1.0
    assert line.end == 3.0
    assert len(line.chars) == len(line.text)
    assert line.chars[0][0] == 1.0
    assert line.chars[-1][1] == pytest.approx(3.0)


def test_build_line_returns_none_without_visible_text():
    assert model.build_line([(0.0, 1.0, "   ")]) is None


def test_split_adlibs_moves_parenthesised_text_aside():
    lines = [model.Line(1.0, "Go go (yeah yeah) now")]

    (line,) = parsing.split_adlibs(lines)

    assert line.text == "Go go now"
    assert line.adlib == "yeah yeah"


def test_split_adlibs_keeps_a_line_made_only_of_an_adlib():
    (line,) = parsing.split_adlibs([model.Line(2.0, "(only adlib)")])

    assert line.text == "only adlib"
    assert line.adlib == ""


def test_extract_singers_reads_section_and_colon_tags():
    lines = [
        model.Line(1.0, "[Drake]"),
        model.Line(2.0, "Started from the bottom"),
        model.Line(3.0, "Rihanna: Work work"),
        model.Line(4.0, "Rihanna: dirt"),
    ]

    out = parsing.extract_singers(lines, "Drake & Rihanna")

    assert [(line.text, line.singer) for line in out] == [
        ("Started from the bottom", "Drake"),
        ("Work work", "Rihanna"),
        ("dirt", "Rihanna"),
    ]


def test_extract_singers_ignores_a_lone_interjection_with_colon():
    lines = [model.Line(1.0, "Oh: I love you")]

    out = parsing.extract_singers(lines, "Someone")

    assert out[0].text == "Oh: I love you"
    assert out[0].singer == ""


def test_add_pauses_inserts_an_empty_line_in_long_gaps():
    lines = [
        model.Line(0.0, "a", end=1.0),
        model.Line(10.0, "b", end=11.0),
        model.Line(12.0, "c", end=13.0),
    ]

    out = parsing.add_pauses(lines)

    assert [(line.time, line.text) for line in out] == [
        (0.0, "a"),
        (1.4, ""),
        (10.0, "b"),
        (12.0, "c"),
    ]


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Song (Official Video) [HD]", "Song"),
        ("Song feat. Bob", "Song"),
        ("Song (ft. Bob)", "Song"),
        ("Song (Remix)", "Song (Remix)"),
    ],
)
def test_clean_title(raw, clean):
    assert parsing.clean_title(raw) == clean


def test_candidates_splits_artist_dash_title_uploads():
    assert parsing.candidates("Artist - Song (Lyrics)", "Uploader") == [
        ("Artist - Song", "Uploader"),
        ("Song", "Artist"),
    ]


def test_simplify_folds_accents_case_and_punctuation():
    assert parsing.simplify("Été, à Paris!") == "ete a paris"


def test_mark_title_lines_respects_cooldown():
    lines = [
        model.Line(0.0, "my song is here"),
        model.Line(5.0, "My Song again"),
        model.Line(30.0, "my song"),
        model.Line(31.0, "nothing"),
    ]

    parsing.mark_title_lines(lines, "My Song")

    assert [line.title_span for line in lines] == [
        (0, 2),
        (0, 2),
        (0, 2),
        None,
    ]
    assert [line.title_drop for line in lines] == [True, False, True, False]
