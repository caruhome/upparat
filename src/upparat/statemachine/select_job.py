import json
import logging

from paho.mqtt.client import topic_matches_sub
from pysm import Event

from upparat.config import settings
from upparat.events import JOB
from upparat.events import JOB_EXECUTION_SUMMARIES
from upparat.events import JOB_EXECUTION_SUMMARIES_PROGRESS
from upparat.events import JOB_EXECUTION_SUMMARIES_QUEUED
from upparat.events import JOB_SELECTED
from upparat.events import MQTT_EVENT_PAYLOAD
from upparat.events import MQTT_EVENT_TOPIC
from upparat.events import MQTT_MESSAGE_RECEIVED
from upparat.events import MQTT_SUBSCRIBED
from upparat.events import SELECT_JOB_INTERRUPTED
from upparat.jobs import describe_job_execution
from upparat.jobs import describe_job_execution_response
from upparat.jobs import EXECUTION
from upparat.jobs import Job
from upparat.jobs import JOB_ACCEPTED
from upparat.jobs import JOB_DOCUMENT
from upparat.jobs import JOB_DOCUMENT_FILE
from upparat.jobs import JOB_DOCUMENT_FORCE
from upparat.jobs import JOB_DOCUMENT_META
from upparat.jobs import JOB_DOCUMENT_VERSION
from upparat.jobs import JOB_ID
from upparat.jobs import JOB_MESSAGE
from upparat.jobs import JOB_REJECTED
from upparat.jobs import JOB_STATUS
from upparat.jobs import JOB_STATUS_DETAILS
from upparat.jobs import job_update_multiple_as_failed
from upparat.jobs import JobProgressStatus
from upparat.statemachine import BaseState

logger = logging.getLogger(__name__)


class SelectJobState(BaseState):
    """
    Select the job to run. This can be one that was already started or a queued one
    """

    name = "select_job"
    current_job_id = None
    describe_job_execution_response = None

    def on_enter(self, state, event):
        job_execution_summaries = event.cargo["source_event"].cargo[
            JOB_EXECUTION_SUMMARIES
        ]

        in_progress_jobs_ids = [
            job[JOB_ID]
            for job in job_execution_summaries[JOB_EXECUTION_SUMMARIES_PROGRESS]
        ]

        # Sorted to make sure oldest is first [0]
        queued_jobs_ids = [
            job[JOB_ID]
            for job in sorted(
                job_execution_summaries[JOB_EXECUTION_SUMMARIES_QUEUED],
                key=lambda summary: summary["queuedAt"],
            )
        ]

        # Check if there is an in-progress job
        # → this means we are in an ongoing update process.
        if in_progress_jobs_ids:
            if len(in_progress_jobs_ids) == 1:
                self.current_job_id = in_progress_jobs_ids[0]
                logger.info(f"Job execution in progress: {self.current_job_id}")
            else:
                # If we have more than one job in progress something is very wrong.
                # This this state should not happen → just fail all in progress job.
                failure_reason = f"Invalid: More than one job is IN PROGRESS: {', '.join(in_progress_jobs_ids)}"  # noqa
                logger.error(failure_reason)

                job_update_multiple_as_failed(
                    self.mqtt_client,
                    settings.broker.thing_name,
                    in_progress_jobs_ids,
                    JobProgressStatus.ERROR_MULTIPLE_IN_PROGRESS.value,
                    failure_reason,
                )

                self.publish(Event(SELECT_JOB_INTERRUPTED))

        elif queued_jobs_ids:
            self.current_job_id = queued_jobs_ids[0]
            logger.info(f"Start queued job execution: {self.current_job_id}")

        else:
            logger.warning("No job executions pending.")
            self.publish(Event(SELECT_JOB_INTERRUPTED))

        # Subscribe to current job description, if any job was selected
        if self.current_job_id:
            self.describe_job_execution_response = describe_job_execution_response(
                settings.broker.thing_name, self.current_job_id
            )
            self.mqtt_client.subscribe(self.describe_job_execution_response, qos=1)

    def on_subscription(self, state, event):
        topic = event.cargo[MQTT_EVENT_TOPIC]

        # Get the current job info once we are
        # subscribed to job_execution_update_topic
        if topic_matches_sub(self.describe_job_execution_response, topic):
            self.mqtt_client.publish(
                describe_job_execution(settings.broker.thing_name, self.current_job_id),
                qos=1,
            )

    def on_message(self, state, event):
        topic = event.cargo[MQTT_EVENT_TOPIC]
        payload = json.loads(event.cargo[MQTT_EVENT_PAYLOAD])

        accepted_topic = describe_job_execution_response(
            settings.broker.thing_name, self.current_job_id, state_filter=JOB_ACCEPTED
        )

        rejected_topic = describe_job_execution_response(
            settings.broker.thing_name, self.current_job_id, state_filter=JOB_REJECTED
        )

        if topic_matches_sub(accepted_topic, topic):
            job_execution = payload[EXECUTION]
            job_document = job_execution[JOB_DOCUMENT]

            job = Job(
                id_=job_execution[JOB_ID],
                status=job_execution[JOB_STATUS],
                file_url=job_document[JOB_DOCUMENT_FILE],
                version=job_document[JOB_DOCUMENT_VERSION],
                force=job_document.get(JOB_DOCUMENT_FORCE, False),
                meta=job_document.get(JOB_DOCUMENT_META),
                status_details=job_execution.get(JOB_STATUS_DETAILS),
            )

            self.publish(Event(JOB_SELECTED, **{JOB: job}))

        elif topic_matches_sub(rejected_topic, topic):
            logger.warning(payload[JOB_MESSAGE])
            self.publish(Event(SELECT_JOB_INTERRUPTED))

    def event_handlers(self):
        return {
            MQTT_SUBSCRIBED: self.on_subscription,
            MQTT_MESSAGE_RECEIVED: self.on_message,
        }
