import logging

from pysm import Event

from upparat.config import settings
from upparat.events import HOOK_MESSAGE
from upparat.events import HOOK_RESULT
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
        self.stop_install_hook = None
        super().__init__()

    def on_enter(self, state, event):
        # Start install hook
        if settings.hooks.install:
            logger.info("Start installation")
            self.job_progress(JobProgressStatus.INSTALLATION_START.value)
            self.stop_install_hook = run_hook(
                settings.hooks.install,
                self._install_hook_event,
                args=[self.job.meta, str(self.job.file_path)],
            )
        else:
            logger.info("No installation hook provided")
            self.job_succeeded(JobSuccessStatus.NO_INSTALLATION_HOOK_PROVIDED.value)
            self.publish(Event(INSTALLATION_INTERRUPTED))

    def on_job_cancelled(self, state, event):
        self._stop_hooks()
        self.publish(Event(INSTALLATION_INTERRUPTED))

    def on_exit(self, state, event):
        self._stop_hooks()

    def _stop_hooks(self):
        if self.stop_install_hook:
            self.stop_install_hook.set()

    def _install_hook_event(self, event):
        if event.name == HOOK_RESULT:
            logger.info("Installation hook done")
            self.publish(Event(INSTALLATION_DONE, **{JOB: self.job}))
        else:
            error_message = event.cargo[HOOK_MESSAGE]
            logger.error(f"Installation failed: {error_message}")
            self.job_failed(
                JobFailedStatus.INSTALLATION_HOOK_FAILED.value, message=error_message
            )
            self.publish(Event(INSTALLATION_INTERRUPTED))
