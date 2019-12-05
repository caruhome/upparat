import logging
from pathlib import Path

from upparat.config import Settings

CONFIG_FILE = (Path(__file__).parent / "test.conf").as_posix()


def test_thing_name_override():
    thing_name = "veryspecialthing"
    settings = Settings(["-c", CONFIG_FILE, "-t", thing_name])

    assert settings.broker.thing_name == thing_name


def test_default_loglevel():
    settings = Settings([])
    assert settings.service.log_level == logging.getLevelName(logging.WARNING)


def test_loglevel_override():
    settings = Settings(["-c", CONFIG_FILE, "-v"])
    assert settings.service.log_level == logging.getLevelName(logging.DEBUG)
