import logging
import threading

from pysm import Event

from upparat.config import settings
from upparat.events import HOOK_RESULT
from upparat.events import INSTALLATION_ABORTED
from upparat.events import INSTALLATION_DONE
from upparat.events import JOB
from upparat.hooks import run_hook
from upparat.jobs import job_failed
from upparat.jobs import job_in_progress
from upparat.jobs import JobInternalStatus
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)


class InstallState(JobProcessingState):
    name = "install"
    stop_install_hook = threading.Event()

    def on_enter(self, state, event):
        # Start install hook
        if settings.hooks.install:
            logger.info("start installation")
            run_hook(
                settings.hooks.install,
                self.stop_install_hook,
                self._install_hook_event,
                args=[self.job.meta, str(self.job.file_path)],
            )
        else:
            # todo: What make sense here? mark job as success? Or is this a
            #  misconfiguration?
            self.publish(Event(INSTALLATION_ABORTED))

    def on_job_cancelled(self, state, event):
        self.stop_install_hook.set()
        self.publish(Event(INSTALLATION_ABORTED))

    def on_exit(self, state, event):
        self.stop_install_hook.set()

    def _install_hook_event(self, event):
        if event.name == HOOK_RESULT:
            job_in_progress(
                self.mqtt_client,
                settings.broker.thing_name,
                self.job.id_,
                JobInternalStatus.INSTALLATION_DONE.value,
            )
            self.publish(Event(INSTALLATION_DONE, **{JOB: self.job}))
        else:
            job_failed(
                self.mqtt_client,
                settings.broker.thing_name,
                self.job.id_,
                JobInternalStatus.INSTALLATION_FAILED.value,
            )
            self.publish(Event(INSTALLATION_ABORTED))
