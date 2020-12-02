import logging
import socket
import stat
from pathlib import Path

import pytest

from upparat.config import Settings


EXAMPLE_CONFIG_KWARGS = {
    "service": {"log_level": "WARNING", "sentry": "sentry.dsn.com"},
    "broker": {"host": "host.com"},
    "hooks": {"version": "./version.sh"},
}

EXPECTED_SAMPLE_CONFIG = """
[service]
log_level=WARNING
sentry=sentry.dsn.com

[broker]
host=host.com

[hooks]
version=./version.sh
"""


def build_config_content(service=None, broker=None, hooks=None):
    def build_section(name, settings):
        section = "\n[{}]\n".format(name)
        section += "\n".join([f"{key}={value}" for key, value in settings.items()])
        section += "\n"
        return section

    content = ""

    if service:
        content += build_section("service", service)

    if broker:
        content += build_section("broker", broker)

    if hooks:
        content += build_section("hooks", hooks)

    return content


@pytest.fixture
def create_config_file(tmpdir):
    def _create_config_file(service=None, broker=None, hooks=None):
        path = Path(tmpdir / "upparat.conf")

        with open(path, "w") as config_file:
            content = build_config_content(service, broker, hooks)
            config_file.write(content)

        return str(path)

    return _create_config_file


@pytest.fixture
def create_settings(create_config_file):
    def _create_settings(verbose=False, thing_name=None, **config):
        arguments = []

        if config:
            arguments.append("-c")
            arguments.append(create_config_file(**config))

        if thing_name:
            arguments.append("-t")
            arguments.append(thing_name)

        if verbose:
            arguments.append("-v")

        return Settings(arguments)

    return _create_settings


def test_build_config_file_test_helper():
    assert build_config_content(**EXAMPLE_CONFIG_KWARGS) == EXPECTED_SAMPLE_CONFIG
    assert build_config_content() == ""


def test_create_config_file_test_helper(tmpdir, create_config_file):
    path = create_config_file(**EXAMPLE_CONFIG_KWARGS)

    with open(path, "r") as config_file:
        assert config_file.read() == EXPECTED_SAMPLE_CONFIG


def test_thing_name_default(create_settings):
    settings = create_settings()
    assert settings.broker.thing_name == socket.gethostname()


def test_thing_name_config_file(create_settings):
    thing = "my_thing"
    settings = create_settings(broker={"thing_name": thing})
    assert settings.broker.thing_name == thing


def test_thing_name_override(create_settings):
    thing = "_"
    thing_override = "override"
    settings = create_settings(broker={"thing_name": thing}, thing_name=thing_override)

    assert settings.broker.thing_name == thing_override


def test_log_level_default(create_settings):
    settings = create_settings()
    assert settings.service.log_level == logging.getLevelName(logging.WARNING)


def test_log_level_config_file(create_settings):
    settings = create_settings(service={"log_level": "DEBUG"})
    assert settings.service.log_level == logging.getLevelName(logging.DEBUG)


def test_download_location_default(create_settings):
    settings = create_settings()
    assert settings.service.download_location == Path("/tmp/upparat")


def test_download_location_config_file(tmpdir, create_settings):
    download_location = Path(tmpdir / "download_here")
    settings = create_settings(service={"download_location": str(download_location)})
    assert settings.service.download_location == download_location / "upparat"


def test_download_location_creation(tmpdir, create_settings):
    download_location = Path(tmpdir / "download_here")
    assert not download_location.is_dir()

    create_settings(service={"download_location": str(download_location)})
    assert download_location.is_dir()


def test_download_location_permission_errors(tmpdir, create_settings):
    # TODO add test for permissions
    #
    # download_location = Path(tmpdir / "download_here")
    # read_only = stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH
    # download_location.mkdir(read_only)
    # with pytest.raises(PermissionError):
    #     create_settings(service={"download_location": str(download_location)})
    #
    pass


def test_sentry_default(create_settings):
    settings = create_settings()
    assert not settings.service.sentry


def test_sentry_config_file(tmpdir, create_settings):
    sentry = "https://sentry.dsn.com"
    settings = create_settings(service={"sentry": sentry})
    assert settings.service.sentry == sentry


def test_host_default(create_settings):
    settings = create_settings()
    assert settings.broker.host == "127.0.0.1"


def test_host_config_file(create_settings):
    host = "broker.aws.com"
    settings = create_settings(broker={"host": host})
    assert settings.broker.host == host


def test_port_default(create_settings):
    settings = create_settings()
    assert settings.broker.port == 1883


def test_port_config_file(create_settings):
    port = 443
    settings = create_settings(broker={"port": port})
    assert settings.broker.port == port


def test_no_certs_config_file(create_settings):
    settings = create_settings(broker={})

    assert settings.broker.cafile is None
    assert settings.broker.certfile is None
    assert settings.broker.keyfile is None


def test_certs_config_file(create_settings):
    cafile = "ca.pem"
    certfile = "cert.pem.key"
    keyfile = "private.pem.key"

    settings = create_settings(
        broker={"cafile": cafile, "certfile": certfile, "keyfile": keyfile}
    )

    assert settings.broker.cafile == cafile
    assert settings.broker.certfile == certfile
    assert settings.broker.keyfile == keyfile


def test_hooks_default(create_settings):
    settings = create_settings()
    assert not settings.hooks.version
    assert not settings.hooks.download
    assert not settings.hooks.ready
    assert not settings.hooks.install
    assert not settings.hooks.restart
    assert settings.hooks.retry_interval == 60
    assert settings.hooks.max_retries == 60


def test_hooks_file_exists_with_x_permission(tmpdir, create_settings):
    hooks = {
        "version": tmpdir / "version.sh",
        "download": tmpdir / "download.sh",
        "ready": tmpdir / "ready.sh",
        "install": tmpdir / "install.sh",
        "restart": tmpdir / "restart.sh",
    }

    for hook, command in hooks.items():

        # 0: does not exist → fail
        with pytest.raises(PermissionError):
            create_settings(hooks={hook: command})

        # 1: exists, but not executable → fail
        with pytest.raises(PermissionError):
            path = Path(hooks[hook])
            path.touch()
            create_settings(hooks={hook: command})

        # 2: exists and executable → good
        path = Path(hooks[hook])
        path.chmod(stat.S_IRWXO)
        create_settings(hooks={hook: command})


def test_foo():
    assert True
