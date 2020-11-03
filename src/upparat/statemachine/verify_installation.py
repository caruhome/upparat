import logging
import threading

from pysm import pysm

from upparat.config import settings
from upparat.events import HOOK
from upparat.events import HOOK_COMMAND
from upparat.events import HOOK_MESSAGE
from upparat.events import HOOK_STATUS
from upparat.events import HOOK_STATUS_COMPLETED
from upparat.events import HOOK_STATUS_FAILED
from upparat.events import HOOK_STATUS_TIMED_OUT
from upparat.events import JOB_INSTALLATION_COMPLETE
from upparat.hooks import run_hook
from upparat.jobs import JobFailedStatus
from upparat.jobs import JobSuccessStatus
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)


class VerifyInstallationState(JobProcessingState):
    name = "verify_installation"

    def __init__(self):
        self.stop_version_hook = threading.Event()
        self.stop_ready_hook = threading.Event()
        super().__init__()

    def on_enter(self, state, event):
        if not settings.hooks.version:
            logger.info("Skip version check")
            self.job_succeeded(JobSuccessStatus.COMPLETE_NO_VERSION_CHECK.value)
            self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))
        else:
            # Start version check
            logger.debug("Start version check")
            self.stop_version_hook = run_hook(
                settings.hooks.version, self.root_machine.inbox, args=[self.job.meta]
            )

    def on_exit(self, state, event):
        self._stop_hooks()

    def on_job_cancelled(self, state, event):
        self._stop_hooks()
        self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))

    def event_handlers(self):
        return {HOOK: self.on_handle_hooks}

    def _stop_hooks(self):
        self.stop_version_hook.set()
        self.stop_ready_hook.set()

    def on_handle_hooks(self, _, event):
        command = event.cargo[HOOK_COMMAND]
        if command == settings.hooks.version:
            self.on_version_hook_event(event)
        elif command == settings.hooks.ready:
            self.on_ready_hook_event(event)

    def on_version_hook_event(self, event):
        status = event.cargo[HOOK_STATUS]

        if status == HOOK_STATUS_COMPLETED:
            version = event.cargo[HOOK_MESSAGE]
            if self.job.version == version:
                if settings.hooks.ready:
                    logger.debug("Start ready hook")
                    # Start ready check
                    self.stop_ready_hook = run_hook(
                        settings.hooks.ready,
                        self.root_machine.inbox,
                        args=[self.job.meta],
                    )
                else:
                    logger.info("Skip ready hook")
                    self.job_succeeded(JobSuccessStatus.COMPLETE_NO_READY_CHECK.value)
                    self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))
            else:
                message = f"Expected version '{self.job.version}', got '{version}'"
                logger.warning(message)
                self.job_failed(JobFailedStatus.VERSION_MISMATCH.value, message=message)
                self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))
        elif status in (HOOK_STATUS_FAILED, HOOK_STATUS_TIMED_OUT):
            error_message = event.cargo[HOOK_MESSAGE]
            logger.error(f"Version hook failed: {error_message}")
            self.job_failed(
                JobFailedStatus.VERSION_HOOK_FAILED.value, message=error_message
            )
            self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))

    def on_ready_hook_event(self, event):
        status = event.cargo[HOOK_STATUS]
        if status == HOOK_STATUS_COMPLETED:
            logger.info("Ready hook done")
            self.job_succeeded(JobSuccessStatus.COMPLETE_READY.value)
            self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))
        elif status in (HOOK_STATUS_FAILED, HOOK_STATUS_TIMED_OUT):
            error_message = event.cargo[HOOK_MESSAGE]
            logger.error(f"Ready hook failed: {error_message}")
            self.job_failed(
                JobFailedStatus.READY_HOOK_FAILED.value, message=error_message
            )
            self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))
