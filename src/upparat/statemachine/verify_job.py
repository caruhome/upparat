import logging
import threading

from pysm import Event, pysm

from upparat.config import settings
from upparat.events import (
    JOB,
    JOB_VERIFIED,
    HOOK_RESULT,
    HOOK_MESSAGE,
    JOB_REVOKED,
    JOB_INSTALLATION_DONE,
)
from upparat.hooks import run_hook
from upparat.jobs import JobStatus, JobInternalStatus, job_succeeded
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)


class VerifyJobState(JobProcessingState):
    """
    Decide what to do with the given job
    """

    name = "verify_job"
    stop_version_hook = threading.Event()

    def on_enter(self, state, event):
        if self.job.status == JobStatus.QUEUED.value:
            if self.job.force or not settings.hooks.version:
                return self._job_verified()
            # Start version check
            run_hook(
                settings.hooks.version,
                self.stop_version_hook,
                self._version_hook_event,
                args=[self.job.meta],
            )

        elif self.job.status == JobStatus.IN_PROGRESS.value:
            # If the installation is done check if the
            # ongoing installation was successful
            # todo: cleanup internal states
            if self.job.internal_status in (
                JobInternalStatus.INSTALLATION_DONE.value,
                JobInternalStatus.REBOOT_READY.value,
                JobInternalStatus.REBOOT_BLOCKED.value,
                JobInternalStatus.REBOOT_INITIATED.value,
            ):
                self.publish(Event(JOB_INSTALLATION_DONE, **{JOB: self.job}))
            # Redo the whole update process
            else:
                return self._job_verified()
        else:
            raise Exception(f"Unexpected job status: {self.job.status}")

    def on_exit(self, state, event):
        self.stop_version_hook.set()

    def on_job_cancelled(self, state, event):
        self.stop_version_hook.set()
        self.publish(pysm.Event(JOB_REVOKED))

    def _version_hook_event(self, event):
        if event.name == HOOK_RESULT:
            version = event.cargo[HOOK_MESSAGE]
            # Check if we do not already run on the version to be installed
            if self.job.version == version:
                logger.info(f"Version {self.job.version} is already running.")
                job_succeeded(
                    self.mqtt_client,
                    settings.broker.thing_name,
                    self.job.id_,
                    JobInternalStatus.SUCCESS_ALREADY_INSTALLED.value,
                )
                return self.publish(Event(JOB_REVOKED))
            else:
                return self._job_verified()
        # todo: handle hook errors

    def _job_verified(self):
        self.publish(Event(JOB_VERIFIED, **{JOB: self.job}))
