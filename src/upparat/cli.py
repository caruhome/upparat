import logging
import os
import signal
from pathlib import Path
from queue import Queue

from pysm import Event

from upparat.config import ENV_CONFIG_USE_SYS_ARGS
from upparat.config import settings
from upparat.events import DOWNLOAD_COMPLETED
from upparat.events import DOWNLOAD_INTERRUPTED
from upparat.events import ENTER
from upparat.events import EXIT_SIGNAL_SENT
from upparat.events import INSTALLATION_DONE
from upparat.events import INSTALLATION_INTERRUPTED
from upparat.events import JOB_INSTALLATION_COMPLETE
from upparat.events import JOB_INSTALLATION_DONE
from upparat.events import JOB_RESOURCE_NOT_FOUND
from upparat.events import JOB_REVOKED
from upparat.events import JOB_SELECTED
from upparat.events import JOB_VERIFIED
from upparat.events import JOBS_AVAILABLE
from upparat.events import NO_JOBS_PENDING
from upparat.events import RESTART_INTERRUPTED
from upparat.mqtt import MQTT
from upparat.statemachine import UpparatStateMachine
from upparat.statemachine.download import DownloadState
from upparat.statemachine.fetch_jobs import FetchJobsState
from upparat.statemachine.install import InstallState
from upparat.statemachine.monitor import MonitorState
from upparat.statemachine.restart import RestartState
from upparat.statemachine.select_job import SelectJobState
from upparat.statemachine.verify_installation import VerifyInstallationState
from upparat.statemachine.verify_job import VerifyJobState

BASE = Path(__file__).parent

logger = logging.getLogger(__name__)


def create_statemachine(event_queue, mqtt_client):
    statemachine = UpparatStateMachine(event_queue, mqtt_client)

    fetch_jobs_state = FetchJobsState()
    monitor_state = MonitorState()
    select_job_state = SelectJobState()
    verify_job_state = VerifyJobState()
    download_state = DownloadState()
    install_state = InstallState()
    restart_state = RestartState()
    verify_installation_state = VerifyInstallationState()

    statemachine.add_state(fetch_jobs_state, initial=True)
    statemachine.add_state(monitor_state)
    statemachine.add_state(select_job_state)
    statemachine.add_state(verify_job_state)
    statemachine.add_state(download_state)
    statemachine.add_state(install_state)
    statemachine.add_state(restart_state)
    statemachine.add_state(verify_installation_state)

    # No pending jobs found
    statemachine.add_transition(
        fetch_jobs_state, monitor_state, events=[NO_JOBS_PENDING]
    )

    # Pending jobs found
    statemachine.add_transition(
        fetch_jobs_state, select_job_state, events=[JOBS_AVAILABLE]
    )

    # Notified about pending jobs
    statemachine.add_transition(
        monitor_state, select_job_state, events=[JOBS_AVAILABLE]
    )

    # Found a job to process (can be queued or in_progress if not yet installed)
    statemachine.add_transition(
        select_job_state, verify_job_state, events=[JOB_SELECTED]
    )

    # Pending jobs got modified (rejected) meanwhile
    statemachine.add_transition(
        select_job_state, fetch_jobs_state, events=[JOB_RESOURCE_NOT_FOUND]
    )

    # Job is ready for process
    statemachine.add_transition(verify_job_state, download_state, events=[JOB_VERIFIED])

    # No need to process job (e.g. we already run on desired version or
    # the job got cancelled)
    statemachine.add_transition(
        verify_job_state, fetch_jobs_state, events=[JOB_REVOKED]
    )

    # Found a job to complete
    statemachine.add_transition(
        verify_job_state, verify_installation_state, events=[JOB_INSTALLATION_DONE]
    )

    # Installation complete (successfully or not) or cancelled
    statemachine.add_transition(
        verify_installation_state, fetch_jobs_state, events=[JOB_INSTALLATION_COMPLETE]
    )

    # The job gets cancelled or the download URL expired
    statemachine.add_transition(
        download_state, fetch_jobs_state, events=[DOWNLOAD_INTERRUPTED]
    )

    # Get a new signed url by starting over
    statemachine.add_transition(
        download_state, install_state, events=[DOWNLOAD_COMPLETED]
    )

    # The job gets cancelled or installation fails
    statemachine.add_transition(
        install_state, fetch_jobs_state, events=[INSTALLATION_INTERRUPTED]
    )

    # Installation is complete
    statemachine.add_transition(
        install_state, restart_state, events=[INSTALLATION_DONE]
    )

    # The job gets cancelled or restart fails
    statemachine.add_transition(
        restart_state, fetch_jobs_state, events=[RESTART_INTERRUPTED]
    )

    statemachine.initialize()

    # send initial enter event to the initial state
    statemachine.dispatch(Event(ENTER))

    return statemachine


def cli():
    inbox = Queue()

    if settings.service.sentry:
        import sentry_sdk

        logger.debug("Init sentry")
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


def execute_from_command_line():
    os.environ[ENV_CONFIG_USE_SYS_ARGS] = "True"
    cli()


if __name__ == "__main__":
    execute_from_command_line()
