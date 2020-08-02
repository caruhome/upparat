import logging
import signal
import ssl
from pathlib import Path
from queue import Queue

from pysm import Event

from upparat import config
from upparat.config import settings
from upparat.events import EXIT_SIGNAL_SENT
from upparat.mqtt import MQTT
from upparat.statemachine.machine import create_statemachine

BASE = Path(__file__).parent

logger = logging.getLogger(__name__)


def cli(inbox=None):

    if not inbox:
        inbox = Queue()

    if settings.service.sentry:
        import sentry_sdk

        sentry_sdk.init(settings.service.sentry)

    # Graceful shutdown
    def _exit(_, __):
        inbox.put(Event(EXIT_SIGNAL_SENT))

    signal.signal(signal.SIGINT, _exit)
    signal.signal(signal.SIGTERM, _exit)

    client = MQTT(client_id=settings.broker.client_id, queue=inbox)

    cafile = settings.broker.cafile
    certfile = settings.broker.certfile
    keyfile = settings.broker.keyfile

    host = settings.broker.host
    port = settings.broker.port

    # for client certificate authentication use the TLS
    # APLN extension which requires 443 or 8883.
    if cafile or certfile or keyfile:
        try:
            if port not in [443, 8883]:
                raise Exception(
                    "Port must be 443/8883 for TLS APLN client certificate authentication."  # noqa
                )
            ssl_context = ssl.create_default_context()
            ssl_context.set_alpn_protocols(["x-amzn-mqtt-ca"])
            ssl_context.load_verify_locations(cafile=cafile)
            ssl_context.load_cert_chain(certfile=certfile, keyfile=keyfile)
            client.tls_set_context(context=ssl_context)
        except Exception as e:
            logger.exception("Error in TLS ALPN extension setup.")
            raise e

    client.run(host, port)
    state_machine = create_statemachine(inbox, client)

    while True:
        event = inbox.get()
        logger.debug(f"---> Event in inbox {event}")
        state_machine.dispatch(event)


def main():
    config.USE_SYS_ARGV = True
    cli()


if __name__ == "__main__":
    main()
