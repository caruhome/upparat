import logging
import threading

import pysm

from upparat.config import settings
from upparat.events import HOOK
from upparat.events import HOOK_COMMAND
from upparat.events import HOOK_MESSAGE
from upparat.events import HOOK_STATUS
from upparat.events import HOOK_STATUS_COMPLETED
from upparat.events import HOOK_STATUS_FAILED
from upparat.events import HOOK_STATUS_OUTPUT
from upparat.events import HOOK_STATUS_TIMED_OUT
from upparat.events import INSTALLATION_DONE
from upparat.events import INSTALLATION_INTERRUPTED
from upparat.events import JOB
from upparat.hooks import run_hook
from upparat.jobs import JobFailedStatus
from upparat.jobs import JobProgressStatus
from upparat.jobs import JobSuccessStatus
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)


class InstallState(JobProcessingState):
    name = "install"

    def __init__(self):
        self.stop_install_hook = threading.Event()
        super().__init__()

    def on_enter(self, state, event):
        # Start install hook
        if settings.hooks.install:
            logger.info("Start installation")
            self.job_progress(JobProgressStatus.INSTALLATION_START.value)
            self.stop_install_hook = run_hook(
                settings.hooks.install,
                self.root_machine.inbox,
                args=[self.job.meta, self.job.filepath],
            )
        else:
            logger.info("No installation hook provided")
            # mark as succeeded because maybe there is no "install" step
            # necessary since we only want to distribute a file
            self.job_succeeded(JobSuccessStatus.NO_INSTALLATION_HOOK_PROVIDED.value)
            self.publish(pysm.Event(INSTALLATION_INTERRUPTED))

    def on_job_cancelled(self, state, event):
        self._stop_hooks()
        self.publish(pysm.Event(INSTALLATION_INTERRUPTED))

    def on_exit(self, state, event):
        self._stop_hooks()

    def event_handlers(self):
        return {HOOK: self.on_install_hook_event}

    def _stop_hooks(self):
        self.stop_install_hook.set()

    def on_install_hook_event(self, _, event):
        # Only handle install hook events
        if event.cargo[HOOK_COMMAND] != settings.hooks.install:
            return

        status = event.cargo[HOOK_STATUS]

        if status == HOOK_STATUS_COMPLETED:
            logger.info("Installation hook done")
            self.publish(pysm.Event(INSTALLATION_DONE, **{JOB: self.job}))
        elif status == HOOK_STATUS_OUTPUT:
            self.job_progress(
                JobProgressStatus.INSTALLATION_PROGRESS.value,
                message=event.cargo[HOOK_MESSAGE],
            )
        elif status in (HOOK_STATUS_FAILED, HOOK_STATUS_TIMED_OUT):
            error_message = event.cargo[HOOK_MESSAGE]
            logger.error(f"Installation failed: {error_message}")
            self.job_failed(
                JobFailedStatus.INSTALLATION_HOOK_FAILED.value, message=error_message
            )
            self.publish(pysm.Event(INSTALLATION_INTERRUPTED))
