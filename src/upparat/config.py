import configparser
import logging
import os
import socket
import tempfile
from pathlib import Path

ENV_CONFIG_FILE = "UPPARAT_CONFIG_FILE"
ENV_VERBOSE = "UPPARAT_VERBOSE"

NAME = "upparat"

SERVICE_SECTION = "service"
LOG_LEVEL = "log_level"
DOWNLOAD_LOCATION = "download_location"
SENTRY = "sentry"  # todo: remove for release

BROKER_SECTION = "broker"
HOST = "host"
PORT = "port"
THING_NAME = "thing_name"
CLIENT_ID = "client_id"

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


class Service:
    download_location: str
    sentry: str  # todo: remove for release


class Broker:
    host: str
    port: int
    thing_name: str
    client_id: str


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


def _broker_section(config):
    broker = Broker()
    broker.host = config.get(BROKER_SECTION, HOST, fallback="127.0.0.1")
    broker.port = config.getint(BROKER_SECTION, PORT, fallback=1883)
    broker.thing_name = config.get(
        BROKER_SECTION, THING_NAME, fallback=socket.gethostname()
    )
    broker.client_id = config.get(BROKER_SECTION, CLIENT_ID, fallback=NAME)

    return broker


def _hooks_section(config):
    hooks = Hooks()
    for hook in HOOKS:
        command = config.get(HOOKS_SECTION, hook, fallback=None)
        if command and not os.access(command, os.X_OK):
            raise PermissionError(f"Invalid command for {hook} hook: {command}")
        setattr(hooks, hook, command)

    hooks.retry_interval = config.getint(HOOKS_SECTION, RETRY_INTERVAL, fallback=60)
    hooks.max_retries = config.getint(HOOKS_SECTION, MAX_RETRIES, fallback=60)

    return hooks


class LazySettings(object):
    def __init__(self):
        self._initialized = False

    def _setup(self):
        config_file = os.environ.get(ENV_CONFIG_FILE)
        config = configparser.ConfigParser()

        if config_file:
            config.read(config_file)

        self.broker = _broker_section(config)
        self.hooks = _hooks_section(config)
        self.service = _service_section(config, ENV_VERBOSE in os.environ)

        self._initialized = True

    def __getattr__(self, name):
        if not self._initialized:
            self._setup()
        return self.__getattribute__(name)


settings = LazySettings()
