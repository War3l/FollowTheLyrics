import json
import os

import pytest

from followthelyrics.config import settings


def test_write_json_replaces_the_file_atomically(tmp_path):
    target = tmp_path / "config.json"
    target.write_text('{"old": true}', encoding="utf-8")

    settings.write_json(str(target), {"new": "é"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"new": "é"}
    assert os.listdir(tmp_path) == ["config.json"]


def test_write_json_keeps_the_old_file_when_serialising_fails(tmp_path):
    target = tmp_path / "config.json"
    target.write_text('{"old": true}', encoding="utf-8")

    with pytest.raises(TypeError):
        settings.write_json(str(target), {"bad": object()})

    assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
    assert os.listdir(tmp_path) == ["config.json"]


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(settings, "CONFIG_PATH", str(path))
    return path


def test_load_config_returns_defaults_without_a_file(config_path):
    assert settings.load_config() == settings.DEFAULTS


def test_load_config_repairs_invalid_values(config_path):
    config_path.write_text(
        json.dumps(
            {
                "mode": "nope",
                "style": "pop",
                "scale": 9,
                "sites_off": "youtube",
                "theme": "dark",
                "font": "Impact",
            }
        ),
        encoding="utf-8",
    )

    cfg = settings.load_config()

    assert cfg["mode"] == settings.DEFAULTS["mode"]
    assert cfg["style"] == "kinetic"
    assert cfg["scale"] == 1.6
    assert cfg["sites_off"] == []
    assert "theme" not in cfg
    assert cfg["font"] == "Impact"


def test_load_config_resets_unreadable_numbers(config_path):
    config_path.write_text(json.dumps({"offset": "abc"}), encoding="utf-8")

    cfg = settings.load_config()

    assert (cfg["scale"], cfg["offset"]) == (1.0, 0.0)


def test_save_then_load_round_trips(config_path):
    cfg = settings.load_config()
    cfg["position"] = "right"

    settings.save_config(cfg)

    assert settings.load_config()["position"] == "right"


@pytest.mark.parametrize(
    ("app_id", "label"),
    [
        ("Spotify.exe", "Spotify"),
        ("Chrome", "Google Chrome"),
        ("C:\\Apps\\Foobar2000.exe", "Foobar2000"),
        ("Some.App!Main", "Some.App"),
    ],
)
def test_app_label(app_id, label):
    assert settings.app_label(app_id) == label
