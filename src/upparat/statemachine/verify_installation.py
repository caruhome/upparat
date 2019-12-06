import logging

from pysm import pysm

from upparat.config import settings
from upparat.events import HOOK_MESSAGE
from upparat.events import HOOK_RESULT
from upparat.events import JOB_INSTALLATION_COMPLETE
from upparat.hooks import run_hook
from upparat.jobs import JobFailedStatus
from upparat.jobs import JobSuccessStatus
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)


class VerifyInstallationState(JobProcessingState):
    name = "verify_installation"

    def __init__(self):
        self.stop_version_hook = None
        self.stop_ready_hook = None
        super().__init__()

    def on_enter(self, state, event):
        if self.job.force or not settings.hooks.version:
            logger.info("Skip version check")
            self.job_succeeded(JobSuccessStatus.COMPLETE_NO_VERSION_CHECK.value)
            self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))
        else:
            # Start version check
            logger.debug("Start version check")
            self.stop_version_hook = run_hook(
                settings.hooks.version, self._version_hook_event, args=[self.job.meta]
            )

    def on_exit(self, state, event):
        self._stop_hooks()

    def on_job_cancelled(self, state, event):
        self._stop_hooks()
        self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))

    def _stop_hooks(self):
        if self.stop_version_hook:
            self.stop_version_hook.set()
        if self.stop_ready_hook:
            self.stop_ready_hook.set()

    def _version_hook_event(self, event):
        if event.name == HOOK_RESULT:
            version = event.cargo[HOOK_MESSAGE]
            if self.job.version == version:
                if settings.hooks.ready:
                    logger.debug("Start ready hook")
                    # Start ready check
                    self.stop_ready_hook = run_hook(
                        settings.hooks.ready,
                        self._ready_hook_event,
                        args=[self.job.meta],
                    )
                else:
                    logger.info("Skip ready hook")
                    self.job_succeeded(JobSuccessStatus.COMPLETE_NO_READY_CHECK.value)
                    self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))
            else:
                self.job_failed(JobFailedStatus.VERSION_MISMATCH.value, message=version)
                self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))
        else:
            error_message = event.cargo[HOOK_MESSAGE]
            logger.error(f"Version hook failed: {error_message}")
            self.job_failed(
                JobFailedStatus.VERSION_HOOK_FAILED.value, message=error_message
            )
            self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))

    def _ready_hook_event(self, event):
        if event.name == HOOK_RESULT:
            logger.info("Ready hook done")
            self.job_succeeded(JobSuccessStatus.COMPLETE_READY.value)
            self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))
        else:
            error_message = event.cargo[HOOK_MESSAGE]
            logger.error(f"Ready hook failed: {error_message}")
            self.job_failed(
                JobFailedStatus.READY_HOOK_FAILED.value, message=error_message
            )
            self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))
