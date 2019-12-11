import json
import os
from enum import Enum

# AWS job execution
EXECUTION = "execution"
EXECUTION_STATE = "executionState"

# AWS job notifications
JOBS = "jobs"

# AWS job document
JOB_ID = "jobId"
JOB_DOCUMENT = "jobDocument"
JOB_DOCUMENT_FILE = "file"
JOB_DOCUMENT_VERSION = "version"
JOB_DOCUMENT_META = "meta"
JOB_DOCUMENT_FORCE = "force"
JOB_MESSAGE = "message"

# AWS jobs status
JOB_STATUS = "status"
JOB_STATUS_DETAILS = "statusDetails"
JOB_ACCEPTED = "accepted"
JOB_REJECTED = "rejected"


class JobStatus(Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"
    CANCELED = "CANCELED"
    TIMED_OUT = "TIMED_OUT"
    REJECTED = "REJECTED"
    REMOVED = "REMOVED"


# Internal job state
JOB_STATUS_DETAILS_STATE = "state"
JOB_STATUS_DETAILS_MESSAGE = "message"


class JobSuccessStatus(Enum):
    VERSION_ALREADY_INSTALLED = "version_already_installed"
    NO_INSTALLATION_HOOK_PROVIDED = "no_installation_hook_provided"
    NO_RESTART_HOOK_PROVIDED = "no_restart_hook_provided"
    COMPLETE_SOFT_RESTART = "complete_soft_restart"
    COMPLETE_NO_VERSION_CHECK = "complete_no_version_check"
    COMPLETE_NO_READY_CHECK = "complete_no_ready_check"
    COMPLETE_READY = "complete_ready"


class JobFailedStatus(Enum):
    INSTALLATION_HOOK_FAILED = "installation_hook_failed"
    RESTART_HOOK_FAILED = "restart_hook_failed"
    VERSION_HOOK_FAILED = "version_hook_failed"
    READY_HOOK_FAILED = "ready_hook_failed"
    VERSION_MISMATCH = "version_mismatch"


class JobProgressStatus(Enum):
    DOWNLOAD_START = "download_start"
    DOWNLOAD_PROGRESS = "download_progress"
    DOWNLOAD_INTERRUPT = "download_interrupt"

    INSTALLATION_START = "installation_start"
    INSTALLATION_PROGRESS = "installation_progress"
    INSTALLATION_INTERRUPT = "installation_interrupt"

    REBOOT_START = "reboot_start"
    REBOOT_INTERRUPT = "reboot_interrupt"

    # TODO correct enum?
    ERROR_MULTIPLE_IN_PROGRESS = "error_multiple_in_progress"


def jobs_base(thing_name):
    return f"$aws/things/{thing_name}/jobs/"


def get_pending_job_executions(thing_name):
    return os.path.join(jobs_base(thing_name), "get")


def get_pending_job_executions_response(thing_name, state_filter=None):
    if state_filter:
        query = state_filter
    else:
        query = "+"
    return os.path.join(jobs_base(thing_name), "get", query)


def pending_jobs_response(thing_name):
    return os.path.join(jobs_base(thing_name), "notify")


def update_job_execution(thing_name, job_id):
    return os.path.join(jobs_base(thing_name), job_id, "update")


def describe_job_execution(thing_name, job_id):
    return os.path.join(jobs_base(thing_name), job_id, "get")


def describe_job_execution_response(thing_name, job_id, state_filter=None):
    if state_filter:
        query = state_filter
    else:
        query = "+"
    return os.path.join(jobs_base(thing_name), job_id, "get", query)


def job_update(mqtt_client, thing_name, job_id, status, state, message = None):
    mqtt_client.publish(
        update_job_execution(thing_name, job_id),
        json.dumps(
            {
                JOB_STATUS: status,
                JOB_STATUS_DETAILS: {
                    JOB_STATUS_DETAILS_STATE: state,
                    JOB_STATUS_DETAILS_MESSAGE: message or "none",
                },
            }
        ),
    )


def get_in_progress_job_ids(payload):
    jobs = payload.get(JOBS, {})
    jobs_in_progress = jobs.get(JobStatus.IN_PROGRESS.value, [])
    return [job[JOB_ID] for job in jobs_in_progress]


class Job:
    file_path = None

    def __init__(self, id_, status, file_url, version, force, meta, status_details):
        self.id_ = id_
        self.status = status
        self.status_details = status_details
        self.file_url = file_url
        self.version = version
        self.force = force.lower() in ("yes", "true", "on", "1")
        self.meta = meta

    @property
    def internal_state(self):
        if self.status_details:
            return self.status_details[JOB_STATUS_DETAILS_STATE]
