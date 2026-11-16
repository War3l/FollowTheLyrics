from types import SimpleNamespace

from followthelyrics.config import settings
from followthelyrics.overlay import screens


def fake_screen(name, model="", serial=""):
    return SimpleNamespace(
        name=lambda: name,
        model=lambda: model,
        serialNumber=lambda: serial,
    )


MSI = fake_screen("MAG 275CF X24", "MAG 275CF X24", "CE9H1")
ASUS = fake_screen("VG245", "VG245", "KALM1")


def test_each_screen_is_listed_by_its_name():
    assert list(screens.choices([MSI, ASUS]).values()) == [
        "MAG 275CF X24",
        "VG245",
    ]


def test_twin_screens_get_a_number():
    a = fake_screen("VG245", "VG245")
    b = fake_screen("VG245", "VG245")

    options = screens.choices([a, b])

    assert len(options) == 2
    assert list(options.values()) == ["VG245 1", "VG245 2"]
    assert screens.pick([a, b], a, screens.key_of([a, b], b)) is b


def test_linux_connector_name_is_used_without_a_model():
    hdmi = fake_screen("HDMI-1")

    assert screens.choices([hdmi]) == {"HDMI-1": "HDMI-1"}


def test_long_names_are_shortened():
    long = fake_screen("x", "A" * 60)

    assert len(screens.label(long)) == screens.MAX_LABEL


def test_chosen_screen_is_found_by_key():
    found = [MSI, ASUS]

    assert screens.pick(found, MSI, screens.key_of(found, ASUS)) is ASUS


def test_unplugged_or_unset_screen_falls_back_to_the_main_one():
    assert screens.pick([MSI], MSI, "KALM1") is MSI
    assert screens.pick([MSI, ASUS], MSI, "") is MSI


def test_screen_setting_is_repaired(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"screen": 3}', encoding="utf-8")
    monkeypatch.setattr(settings, "CONFIG_PATH", str(path))

    assert settings.load_config()["screen"] == ""
