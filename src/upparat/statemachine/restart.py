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
from upparat.events import HOOK_STATUS_TIMED_OUT
from upparat.events import RESTART_INTERRUPTED
from upparat.hooks import run_hook
from upparat.jobs import JobFailedStatus
from upparat.jobs import JobProgressStatus
from upparat.jobs import JobSuccessStatus
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)


class RestartState(JobProcessingState):
    name = "restart"

    def __init__(self):
        self.stop_restart_hook = threading.Event()
        super().__init__()

    def on_enter(self, state, event):
        if settings.hooks.restart:
            logger.info("Initiate restart")
            self.job_progress(JobProgressStatus.REBOOT_START.value)
            self.stop_restart_hook = run_hook(
                settings.hooks.restart,
                self.root_machine.inbox,
                args=[self.job.meta, self.job.force],
            )
        else:
            logger.info("No restart hook provided")
            self.job_succeeded(JobSuccessStatus.NO_RESTART_HOOK_PROVIDED.value)
            self.publish(pysm.Event(RESTART_INTERRUPTED))

    def on_job_cancelled(self, state, event):
        self._stop_hooks()
        self.publish(pysm.Event(RESTART_INTERRUPTED))

    def on_exit(self, state, event):
        self._stop_hooks()

    def event_handlers(self):
        return {HOOK: self.on_restart_hook_event}

    def _stop_hooks(self):
        self.stop_restart_hook.set()

    def on_restart_hook_event(self, _, event):
        # Only handle restart hook events
        if event.cargo[HOOK_COMMAND] != settings.hooks.restart:
            return

        status = event.cargo[HOOK_STATUS]

        if status == HOOK_STATUS_COMPLETED:
            logger.info("Restart hook done")
            self.job_succeeded(JobSuccessStatus.COMPLETE_SOFT_RESTART.value)
            self.publish(pysm.Event(RESTART_INTERRUPTED))
        elif status in (HOOK_STATUS_FAILED, HOOK_STATUS_TIMED_OUT):
            message = event.cargo[HOOK_MESSAGE]
            logger.error(f"Restart failed: {message}")
            self.job_failed(JobFailedStatus.RESTART_HOOK_FAILED.value, message=message)
            self.publish(pysm.Event(RESTART_INTERRUPTED))
