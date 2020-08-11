import argparse
import configparser
import logging
import os
import socket
import sys
import tempfile
from pathlib import Path

NAME = "upparat"

USE_SYS_ARGV = False

# settings
SERVICE_SECTION = "service"
LOG_LEVEL = "log_level"
DOWNLOAD_LOCATION = "download_location"
SENTRY = "sentry"

# broker
BROKER_SECTION = "broker"
HOST = "host"
PORT = "port"
THING_NAME = "thing_name"
CLIENT_ID = "client_id"
CAFILE = "cafile"
CERTFILE = "certfile"
KEYFILE = "keyfile"

# hooks
HOOKS_SECTION = "hooks"
VERSION = "version"
DOWNLOAD = "download"
READY = "ready"
INSTALL = "install"
RESTART = "restart"
RETRY_INTERVAL = "retry_interval"
MAX_RETRIES = "max_retries"

HOOKS = (VERSION, DOWNLOAD, READY, INSTALL, RESTART)

logger = logging.getLogger(__name__)

empty = object()


def _argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v",
        "--verbose",
        help="Use verbose logging. This is equivalent to setting log_level to DEBUG "
        "in the configuration file. "
        "This overrides any logging options given in the configuration file.",
        action="store_true",
    )
    parser.add_argument("-c", "--config-file", help="Load configuration from a file.")
    parser.add_argument("-t", "--thing-name", help="AWS thing name")
    return parser


class Service:
    download_location: str
    log_level: str
    sentry: str  # todo: remove for release


class Broker:
    host: str
    port: int
    thing_name: str
    client_id: str
    cafile: str
    certfile: str
    keyfile: str


class Hooks:
    version: str
    download: str
    ready: str
    install: str
    restart: str
    retry_interval: int
    max_retries: int


def _service_section(config, verbose):
    service = Service()

    if verbose:
        log_level = logging.getLevelName(logging.DEBUG)
    else:
        log_level = config.get(
            SERVICE_SECTION, LOG_LEVEL, fallback=logging.getLevelName(logging.WARNING)
        )

    service.log_level = log_level

    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s", level=log_level
    )

    # Append service name to be able to easily cleanup this whole directory
    download_location = config.get(
        SERVICE_SECTION, DOWNLOAD_LOCATION, fallback=tempfile.gettempdir()
    )
    download_location = str((download_location / Path(NAME)).resolve())

    try:
        os.makedirs(download_location, exist_ok=True)
    except PermissionError:
        raise PermissionError(
            f"Unable to create download location: {download_location}"
        )

    if not os.access(download_location, os.W_OK | os.X_OK):
        raise PermissionError(
            f"Insufficient permissions to write to download location: {download_location}"
        )

    service.download_location = Path(download_location)
    service.sentry = config.get(SERVICE_SECTION, SENTRY, fallback=None)
    return service


def _broker_section(config, thing_name=None):
    broker = Broker()

    if thing_name:
        broker.thing_name = thing_name
    else:
        broker.thing_name = config.get(
            BROKER_SECTION, THING_NAME, fallback=socket.gethostname()
        )

    broker.host = config.get(BROKER_SECTION, HOST, fallback="127.0.0.1")
    broker.port = config.getint(BROKER_SECTION, PORT, fallback=1883)
    broker.client_id = config.get(BROKER_SECTION, CLIENT_ID, fallback=NAME)

    broker.cafile = config.get(BROKER_SECTION, CAFILE, fallback=None)
    broker.certfile = config.get(BROKER_SECTION, CERTFILE, fallback=None)
    broker.keyfile = config.get(BROKER_SECTION, KEYFILE, fallback=None)

    set_files_count = sum(
        filepath is None
        for filepath in [broker.cafile, broker.certfile, broker.keyfile]
    )

    # optional, but if one is giving all are expected
    if set_files_count not in [0, 3]:
        raise Exception(
            "Invalid config: Either set all (cafile|certfile|keyfile) or none."
        )

    return broker


def _hooks_section(config):
    hooks = Hooks()
    for hook in HOOKS:
        command = config.get(HOOKS_SECTION, hook, fallback=None)
        if command and not os.access(command, os.X_OK):
            raise PermissionError(
                f"Invalid command for {hook} hook: {command}. Check that command is executable (x)."  # noqa
            )
        setattr(hooks, hook, command)

    hooks.retry_interval = config.getint(HOOKS_SECTION, RETRY_INTERVAL, fallback=60)
    hooks.max_retries = config.getint(HOOKS_SECTION, MAX_RETRIES, fallback=60)

    return hooks


class Settings:
    def __init__(self, args=None):
        config_file = None
        thing_name = None
        verbose = False

        config = configparser.ConfigParser()

        if args:
            args = _argument_parser().parse_args(args)
            config_file = args.config_file
            thing_name = args.thing_name
            verbose = args.verbose

        if config_file:
            # Logger is not yet configured
            print(f"Loading config from file: {config_file}")
            config.read(config_file)

        self.broker = _broker_section(config, thing_name)
        self.hooks = _hooks_section(config)
        self.service = _service_section(config, verbose)


class LazySettings:
    def __init__(self):
        self._wrapped = empty

    def _setup(self):
        args = None
        if USE_SYS_ARGV:
            args = sys.argv[1:]
        self._wrapped = Settings(args)

    def __getattr__(self, name):
        """Return the value of a setting and cache it in self.__dict__."""
        if self._wrapped is empty:
            self._setup()
        val = getattr(self._wrapped, name)
        self.__dict__[name] = val
        return val


settings = LazySettings()
