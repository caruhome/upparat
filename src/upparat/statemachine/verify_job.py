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
from upparat.events import JOB
from upparat.events import JOB_INSTALLATION_DONE
from upparat.events import JOB_REVOKED
from upparat.events import JOB_VERIFIED
from upparat.hooks import run_hook
from upparat.jobs import JobFailedStatus
from upparat.jobs import JobProgressStatus
from upparat.jobs import JobStatus
from upparat.jobs import JobSuccessStatus
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)


class VerifyJobState(JobProcessingState):
    """
    Decide what to do with the given job
    """

    name = "verify_job"

    def __init__(self):
        self.stop_version_hook = threading.Event()
        super().__init__()

    def on_enter(self, state, event):
        if self.job.status == JobStatus.QUEUED.value:
            version_hook = settings.hooks.version
            force = self.job.force

            if force or not version_hook:
                logger.info(
                    f"Skip version check [force={force}, {version_hook if version_hook else 'no-hook'}]"  # noqa
                )
                return self._job_verified()

            logger.debug("Start version check")
            self.stop_version_hook = run_hook(
                version_hook, self.root_machine.inbox, args=[self.job.meta]
            )

        elif self.job.status == JobStatus.IN_PROGRESS.value:
            # If the restart is initiated the installation is done
            if self.job.internal_state == JobProgressStatus.REBOOT_START.value:
                logger.info("Installation done")
                self.publish(pysm.Event(JOB_INSTALLATION_DONE, **{JOB: self.job}))
            # Redo the whole update process
            else:
                logger.info("Redo job process")
                return self._job_verified()
        else:
            raise Exception(f"Unexpected job status: {self.job.status}")

    def on_exit(self, state, event):
        self._stop_hooks()

    def on_job_cancelled(self, state, event):
        self._stop_hooks()
        self.publish(pysm.Event(JOB_REVOKED))

    def event_handlers(self):
        return {HOOK: self.on_version_hook_event}

    def _stop_hooks(self):
        self.stop_version_hook.set()

    def on_version_hook_event(self, _, event):
        # Only handle version hook events
        if event.cargo[HOOK_COMMAND] != settings.hooks.version:
            return

        # hook should never run on force, force == skip it
        assert not self.job.force

        status = event.cargo[HOOK_STATUS]

        if status == HOOK_STATUS_COMPLETED:
            logger.debug("Version hook done")
            version = event.cargo[HOOK_MESSAGE]
            # Check if we do not already run on the version to be installed
            if self.job.version == version:
                logger.info(f"Version {self.job.version} is already running.")
                self.job_succeeded(JobSuccessStatus.VERSION_ALREADY_INSTALLED.value)
                return self.publish(pysm.Event(JOB_REVOKED))
            else:
                logger.info(f"Running on version {version}. Install {self.job.version}")
                return self._job_verified()
        elif status in (HOOK_STATUS_FAILED, HOOK_STATUS_TIMED_OUT):
            error_message = event.cargo[HOOK_MESSAGE]
            logger.error(f"Version hook failed: {error_message}")
            self.job_failed(
                JobFailedStatus.VERSION_HOOK_FAILED.value, message=error_message
            )
            return self.publish(pysm.Event(JOB_REVOKED))

    def _job_verified(self):
        self.publish(pysm.Event(JOB_VERIFIED, **{JOB: self.job}))
