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
from upparat.jobs import job_update
from upparat.jobs import JobProgressStatus
from upparat.jobs import JobStatus
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

        in_progress_jobs = job_execution_summaries[JOB_EXECUTION_SUMMARIES_PROGRESS]
        queued_jobs = job_execution_summaries[JOB_EXECUTION_SUMMARIES_QUEUED]

        # Check if there is an in-progress job. This means we are in an ongoing
        # update process
        if in_progress_jobs:
            in_progress_jobs_count = len(in_progress_jobs)
            if in_progress_jobs_count != 1:
                job_ids = [job[JOB_ID] for job in in_progress_jobs]
                error_description = (
                    f"More than one job IN PROGRESS: {', '.join(job_ids)}"
                )
                logger.error(error_description)

                # Mark all in progress jobs as failed
                for job_id in job_ids:
                    job_update(
                        self.mqtt_client,
                        settings.broker.thing_name,
                        job_id,
                        JobStatus.FAILED.value,
                        JobProgressStatus.ERROR_MULTIPLE_IN_PROGRESS.value,
                        error_description,
                    )
                return self.publish(Event(SELECT_JOB_INTERRUPTED))
            else:
                self.current_job_id = in_progress_jobs[0][JOB_ID]
                logger.debug(f"Job execution in progress: {self.current_job_id}")
        elif queued_jobs:
            # Get oldest queued job
            queued_jobs.sort(key=lambda summary: summary["queuedAt"])
            self.current_job_id = queued_jobs[0][JOB_ID]
            logger.debug(f"Start queued job execution: {self.current_job_id}")
        # No pending job executions
        else:
            logger.error("No job executions available.")
            return self.publish(Event(SELECT_JOB_INTERRUPTED))

        # Subscribe to current job description
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
                force=job_document.get(JOB_DOCUMENT_FORCE, "False"),
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
