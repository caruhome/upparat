import json
import logging

from paho.mqtt.client import topic_matches_sub
from pysm import Event

from upparat.config import settings
from upparat.events import (
    MQTT_SUBSCRIBED,
    MQTT_MESSAGE_RECEIVED,
    NO_JOBS_PENDING,
    MQTT_EVENT_TOPIC,
    MQTT_EVENT_PAYLOAD,
    JOB_EXECUTION_SUMMARIES,
    JOB_EXECUTION_SUMMARIES_PROGRESS,
    JOB_EXECUTION_SUMMARIES_QUEUED,
    JOB_RESOURCE_NOT_FOUND,
    JOB_SELECTED,
    JOB,
)
from upparat.jobs import (
    JOB_ID,
    job_failed,
    JOB_DOCUMENT,
    JobInternalStatus,
    describe_job_execution,
    describe_job_execution_response,
    JOB_STATUS,
    JOB_DOCUMENT_FILE,
    EXECUTION,
    JOB_DOCUMENT_VERSION,
    JOB_DOCUMENT_FORCE,
    JOB_DOCUMENT_META,
    JOB_ACCEPTED,
    JOB_REJECTED,
    JOB_MESSAGE,
    Job,
    JOB_STATUS_DETAILS,
)
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
                nice_job_ids = ", ".join(job_ids)
                logger.error(f"More than one job IN PROGRESS: {nice_job_ids}")
                # Mark all in progress jobs as failed
                for job_id in job_ids:
                    job_failed(
                        self.mqtt_client,
                        settings.broker.thing_name,
                        job_id,
                        JobInternalStatus.ERROR_MULTIPLE_IN_PROGRESS.value,
                    )
                return self.publish(Event(NO_JOBS_PENDING))
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
            return self.publish(Event(NO_JOBS_PENDING))

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
            self.publish(Event(JOB_RESOURCE_NOT_FOUND))

    def event_handlers(self):
        return {
            MQTT_SUBSCRIBED: self.on_subscription,
            MQTT_MESSAGE_RECEIVED: self.on_message,
        }
