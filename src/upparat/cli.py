import logging
import signal
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
    client.run(settings.broker.host, settings.broker.port)

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
