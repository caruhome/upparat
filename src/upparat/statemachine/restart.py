import logging

from pysm import Event

from upparat.config import settings
from upparat.events import HOOK_MESSAGE
from upparat.events import HOOK_RESULT
from upparat.events import RESTART_INTERRUPTED
from upparat.hooks import run_hook
from upparat.jobs import job_failed
from upparat.jobs import job_in_progress
from upparat.jobs import job_succeeded
from upparat.jobs import JobFailedStatus
from upparat.jobs import JobProgressStatus
from upparat.jobs import JobSuccessStatus
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)


class RestartState(JobProcessingState):
    name = "restart"

    def __init__(self):
        self.stop_restart_hook = None
        super().__init__()

    def on_enter(self, state, event):
        if settings.hooks.restart:
            logger.info("Initiate restart")
            job_in_progress(
                self.mqtt_client,
                settings.broker.thing_name,
                self.job.id_,
                JobProgressStatus.REBOOT_START.value,
            )
            self.stop_restart_hook = run_hook(
                settings.hooks.restart,
                self._restart_hook_event,
                args=[self.job.meta, str(self.job.file_path)],
            )
        else:
            logger.info("No restart hook provided")
            job_succeeded(
                self.mqtt_client,
                settings.broker.thing_name,
                self.job.id_,
                JobSuccessStatus.NO_RESTART_HOOK_PROVIDED.value,
            )
            self.publish(Event(RESTART_INTERRUPTED))

    def on_job_cancelled(self, state, event):
        self._stop_hooks()
        self.publish(Event(RESTART_INTERRUPTED))

    def on_exit(self, state, event):
        self._stop_hooks()

    def _stop_hooks(self):
        if self.stop_restart_hook:
            self.stop_restart_hook.set()

    def _restart_hook_event(self, event):
        if event.name == HOOK_RESULT:
            logger.warning("Restart hook done")
            self.publish(Event(RESTART_INTERRUPTED))
        else:
            error_message = event.cargo[HOOK_MESSAGE]
            logger.error(f"Restart failed: {error_message}")
            job_failed(
                self.mqtt_client,
                settings.broker.thing_name,
                self.job.id_,
                JobFailedStatus.RESTART_HOOK_FAILED.value,
                message=error_message,
            )
            self.publish(Event(RESTART_INTERRUPTED))
