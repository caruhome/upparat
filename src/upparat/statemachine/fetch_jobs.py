import json
import logging

from paho.mqtt.client import topic_matches_sub
from pysm import Event

from upparat.events import (
    MQTT_SUBSCRIBED,
    MQTT_MESSAGE_RECEIVED,
    NO_JOBS_PENDING,
    JOBS_AVAILABLE,
    JOB_EXECUTION_SUMMARIES,
    JOB_EXECUTION_SUMMARIES_PROGRESS,
    MQTT_EVENT_TOPIC,
    MQTT_EVENT_PAYLOAD,
    JOB_EXECUTION_SUMMARIES_QUEUED,
)
from upparat.jobs import get_pending_job_executions, get_pending_job_executions_response
from upparat.statemachine import BaseState
from upparat.config import settings


logger = logging.getLogger(__name__)

IN_PROGRESS_JOBS = "inProgressJobs"
QUEUED_JOBS = "queuedJobs"


class FetchJobsState(BaseState):
    """
    Get pending job executions by publishing to $aws/things/<device_id>/jobs/get.
    """

    name = "fetch_jobs"
    current_job_id = None
    get_pending_job_executions_response = None

    def on_enter(self, state, event):
        self.get_pending_job_executions_response = get_pending_job_executions_response(
            settings.broker.thing_name
        )
        self.mqtt_client.subscribe(self.get_pending_job_executions_response, qos=1)

    def on_subscription(self, state, event):
        topic = event.cargo[MQTT_EVENT_TOPIC]
        # Get pending job executions once subscribed to accepted_job_executions_topic
        if topic_matches_sub(self.get_pending_job_executions_response, topic):
            self.mqtt_client.publish(
                get_pending_job_executions(settings.broker.thing_name), qos=1
            )

    def on_message(self, state, event):
        topic = event.cargo[MQTT_EVENT_TOPIC]
        payload = json.loads(event.cargo[MQTT_EVENT_PAYLOAD])

        # Handle accepted pending jobs executions
        # todo: what do we do if we never get an answer?
        if topic_matches_sub(self.get_pending_job_executions_response, topic):
            in_progress_job_executions = payload.get(IN_PROGRESS_JOBS, [])
            queued_job_executions = payload.get(QUEUED_JOBS, [])
            # If there are jobs available go to prepare state
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
            else:
                logger.debug("No pending job executions available.")
                return self.publish(Event(NO_JOBS_PENDING))

    def event_handlers(self):
        return {
            MQTT_SUBSCRIBED: self.on_subscription,
            MQTT_MESSAGE_RECEIVED: self.on_message,
        }
