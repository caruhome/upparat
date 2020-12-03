import json
import logging

from paho.mqtt.client import topic_matches_sub
from pysm import Event

from upparat.config import settings
from upparat.events import JOB_EXECUTION_SUMMARIES
from upparat.events import JOB_EXECUTION_SUMMARIES_PROGRESS
from upparat.events import JOB_EXECUTION_SUMMARIES_QUEUED
from upparat.events import JOBS_AVAILABLE
from upparat.events import MQTT_EVENT_PAYLOAD
from upparat.events import MQTT_EVENT_TOPIC
from upparat.events import MQTT_MESSAGE_RECEIVED
from upparat.jobs import filter_upparat_job_exectutions
from upparat.jobs import pending_jobs_response
from upparat.statemachine import BaseState

logger = logging.getLogger(__name__)

JOBS_IN_PROGRESS = "IN_PROGRESS"
JOBS_QUEUED = "QUEUED"


class MonitorState(BaseState):
    """
    Wait for new jobs to be published to $aws/things/<device_id>/jobs/notify
    """

    name = "monitor"
    job_pending_response = None

    def on_enter(self, state, event):
        self.job_pending_response = pending_jobs_response(settings.broker.thing_name)
        self.mqtt_client.subscribe(self.job_pending_response, qos=1)

    def on_exit(self, state, event):
        self.mqtt_client.unsubscribe(self.job_pending_response)

    def on_message(self, state, event):
        topic = event.cargo[MQTT_EVENT_TOPIC]

        if topic_matches_sub(self.job_pending_response, topic):
            payload = json.loads(event.cargo[MQTT_EVENT_PAYLOAD])

            in_progress_job_executions = filter_upparat_job_exectutions(
                payload["jobs"].get(JOBS_IN_PROGRESS, [])
            )

            queued_job_executions = filter_upparat_job_exectutions(
                payload["jobs"].get(JOBS_QUEUED, [])
            )

            # If there are jobs available go to job selection state
            if in_progress_job_executions or queued_job_executions:
                logger.debug("Job executions available.")
                self.publish(
                    Event(
                        JOBS_AVAILABLE,
                        **{
                            JOB_EXECUTION_SUMMARIES: {
                                JOB_EXECUTION_SUMMARIES_PROGRESS: in_progress_job_executions,
                                JOB_EXECUTION_SUMMARIES_QUEUED: queued_job_executions,
                            }
                        }
                    )
                )

    def event_handlers(self):
        return {MQTT_MESSAGE_RECEIVED: self.on_message}
