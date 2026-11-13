import pytest

from followthelyrics import i18n


@pytest.fixture(autouse=True)
def back_to_french():
    yield
    i18n.set_language("fr")


def test_french_is_the_source_text():
    i18n.set_language("fr")

    assert i18n.tr("Accueil") == "Accueil"


@pytest.mark.parametrize(
    ("code", "expected"),
    [("en", "Home"), ("es", "Inicio"), ("zh", "首页")],
)
def test_each_language_has_its_text(code, expected):
    i18n.set_language(code)

    assert i18n.tr("Accueil") == expected


def test_unknown_text_is_left_alone():
    i18n.set_language("en")

    assert i18n.tr("Texte inconnu") == "Texte inconnu"


def test_unknown_language_falls_back_to_default():
    i18n.set_language("xx")

    assert i18n.language() == i18n.DEFAULT


def test_placeholders_survive_translation():
    for text, entry in i18n.TEXTS.items():
        for translated in entry:
            assert translated.count("{}") == text.count("{}"), text
            assert translated.strip(), text


def test_chinese_lyrics_are_asked_in_simplified_chinese():
    i18n.set_language("zh")

    assert i18n.translate_target() == "zh-CN"
