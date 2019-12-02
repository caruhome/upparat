import logging
import threading

from pysm import Event

from upparat.config import settings
from upparat.events import HOOK_RESULT
from upparat.events import INSTALLATION_ABORTED
from upparat.events import RESTART_ABORTED
from upparat.hooks import run_hook
from upparat.jobs import job_failed
from upparat.jobs import JobInternalStatus
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)


class RestartState(JobProcessingState):
    name = "restart"
    stop_restart_hook = threading.Event()

    def on_enter(self, state, event):
        if settings.hooks.restart:
            logger.info("start installation")
            run_hook(
                settings.hooks.restart,
                self.stop_restart_hook,
                self._restart_hook_event,
                args=[self.job.meta, str(self.job.file_path)],
            )
        else:
            # todo: What make sense here? mark job as success? Or is this a
            #  misconfiguration?
            self.publish(Event(RESTART_ABORTED))

    def on_job_cancelled(self, state, event):
        self.stop_restart_hook.set()
        self.publish(Event(INSTALLATION_ABORTED))

    def on_exit(self, state, event):
        self.stop_restart_hook.set()

    def _restart_hook_event(self, event):
        if event.name == HOOK_RESULT:
            # todo: Do we need to handle this case? We should be restarting...
            pass
        else:
            job_failed(
                self.mqtt_client,
                settings.broker.thing_name,
                self.job.id_,
                JobInternalStatus.REBOOT_BLOCKED.value,
            )
            self.publish(Event(RESTART_ABORTED))
