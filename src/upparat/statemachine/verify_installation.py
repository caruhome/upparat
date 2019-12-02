import logging
import threading

from pysm import pysm

from upparat.config import settings
from upparat.events import HOOK_MESSAGE
from upparat.events import HOOK_RESULT
from upparat.events import JOB_INSTALLATION_COMPLETE
from upparat.hooks import run_hook
from upparat.jobs import job_failed
from upparat.jobs import job_succeeded
from upparat.jobs import JobInternalStatus
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)


class VerifyInstallationState(JobProcessingState):
    name = "verify_installation"
    stop_version_hook = threading.Event()
    stop_ready_hook = threading.Event()

    def on_enter(self, state, event):
        if settings.hooks.version:
            # Start version check
            run_hook(
                settings.hooks.version,
                self.stop_version_hook,
                self._version_hook_event,
                args=[self.job.meta],
            )
        else:
            self._installation_successful()

    def on_exit(self, state, event):
        self.stop_version_hook.set()
        self.stop_ready_hook.set()

    def on_job_cancelled(self, state, event):
        self.stop_version_hook.set()
        self.stop_ready_hook.set()
        self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))

    def _version_hook_event(self, event):
        if event.name == HOOK_RESULT:
            version = event.cargo[HOOK_MESSAGE]
            # Check if we do not already run on the version to be installed
            if self.job.version == version:
                if settings.hooks.ready:
                    # Start ready check
                    run_hook(
                        settings.hooks.ready,
                        self.stop_ready_hook,
                        self._ready_hook_event,
                        args=[self.job.meta],
                    )
                else:
                    return self._installation_successful()
            else:
                self._installation_failed()
        else:
            self._installation_failed()

    def _ready_hook_event(self, event):
        if event.name == HOOK_RESULT:
            self._installation_successful()
        else:
            self._installation_failed()

    def _installation_successful(self):
        job_succeeded(
            self.mqtt_client,
            settings.broker.thing_name,
            self.job.id_,
            JobInternalStatus.SUCCESS_COMPLETE.value,
        )
        self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))

    def _installation_failed(self):
        job_failed(
            self.mqtt_client,
            settings.broker.thing_name,
            self.job.id_,
            JobInternalStatus.INSTALLATION_FAILED.value,
        )
        self.publish(pysm.Event(JOB_INSTALLATION_COMPLETE))
