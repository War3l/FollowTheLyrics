import pytest

from followthelyrics.system import hotkeys


def test_parse_and_make_round_trip():
    parsed = hotkeys.parse("ctrl + ALT + l")

    assert parsed is not None
    assert hotkeys.make(*parsed) == "Ctrl+Alt+L"


@pytest.mark.parametrize(
    "combo", ["", "Ctrl+Shift", "Ctrl+A+B", "Ctrl+Nope", 3]
)
def test_parse_rejects_invalid_combos(combo):
    assert hotkeys.parse(combo) is None


def test_parse_accepts_raw_virtual_key_codes():
    assert hotkeys.parse("Ctrl+VK_BA") == (hotkeys.MOD_CTRL, 0xBA)


def test_allowed_requires_ctrl_alt_or_a_function_key():
    assert hotkeys.allowed(hotkeys.MOD_CTRL, 0x41)
    assert hotkeys.allowed(0, 0x70)
    assert not hotkeys.allowed(0, 0x41)
    assert not hotkeys.allowed(hotkeys.MOD_CTRL, 0x1B)


def test_normalize_fills_defaults_and_fixes_bad_values():
    defaults = hotkeys.normalize({})
    first, second = list(defaults)[:2]

    out = hotkeys.normalize({first: "garbage", second: ""})

    assert out[first] == defaults[first]
    assert out[second] == ""


def test_normalize_clears_duplicated_bindings():
    defaults = hotkeys.normalize({})
    first, second = list(defaults)[:2]

    out = hotkeys.normalize({first: "Ctrl+Alt+K", second: "Ctrl+Alt+K"})

    assert out[first] == "Ctrl+Alt+K"
    assert out[second] == ""


def test_pretty_without_combo():
    assert hotkeys.pretty("") == "aucun raccourci"
