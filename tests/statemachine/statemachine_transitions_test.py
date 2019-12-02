from queue import Queue

import pytest
from pysm import Event

from upparat.cli import create_statemachine
from upparat.events import DOWNLOAD_COMPLETED
from upparat.events import DOWNLOAD_INTERRUPTED
from upparat.events import JOB
from upparat.events import JOB_RESOURCE_NOT_FOUND
from upparat.events import JOB_SELECTED
from upparat.events import JOB_VERIFIED
from upparat.events import JOBS_AVAILABLE
from upparat.events import NO_JOBS_PENDING
from upparat.jobs import Job
from upparat.jobs import JobStatus
from upparat.statemachine.download import DownloadState
from upparat.statemachine.fetch_jobs import FetchJobsState
from upparat.statemachine.install import InstallState
from upparat.statemachine.monitor import MonitorState
from upparat.statemachine.select_job import SelectJobState
from upparat.statemachine.verify_job import VerifyJobState

TEST_PAYLOAD_QUEUED_JOB = {
    "job_execution_summaries": {
        "progress": [],
        "queued": [
            {
                "jobId": "9d98f352-2ce9-49cd-9193-031ae527a0fe",
                "queuedAt": 1574218753,
                "lastUpdatedAt": 1574218753,
                "executionNumber": 1,
                "versionNumber": 1,
            }
        ],
    }
}

TEST_PAYLOAD_INITIALIZED_JOB = {
    JOB: Job(
        id_="9d98f352-2ce9-49cd-9193-031ae527a0fe",
        status=JobStatus.QUEUED.value,
        status_details=None,
        file_url="https://somesingeds3url.aws.com",
        version="0.0.1",
        force="False",
        meta="",
    )
}


@pytest.fixture
def statemachine_fixture(mocker):
    inbox = Queue()
    mqtt_client = mocker.Mock()
    return create_statemachine(inbox, mqtt_client)


@pytest.fixture
def fetch_jobs_state(statemachine_fixture):
    return statemachine_fixture, statemachine_fixture.state


@pytest.fixture
def monitor_state(fetch_jobs_state):
    statemachine, _ = fetch_jobs_state
    statemachine.dispatch(Event(NO_JOBS_PENDING))
    assert isinstance(statemachine.state, MonitorState)
    return statemachine, statemachine.state


@pytest.fixture
def select_job_state(fetch_jobs_state):
    statemachine, _ = fetch_jobs_state
    statemachine.dispatch(Event(JOBS_AVAILABLE, **TEST_PAYLOAD_QUEUED_JOB))
    assert isinstance(statemachine.state, SelectJobState)
    return statemachine, statemachine.state


@pytest.fixture
def verify_job_state(select_job_state):
    statemachine, _ = select_job_state
    statemachine.dispatch(Event(JOB_SELECTED, **TEST_PAYLOAD_INITIALIZED_JOB))
    assert isinstance(statemachine.state, VerifyJobState)
    return statemachine, statemachine.state


@pytest.fixture
def download_state(verify_job_state):
    statemachine, _ = verify_job_state
    statemachine.dispatch(Event(JOB_VERIFIED, **TEST_PAYLOAD_INITIALIZED_JOB))
    assert isinstance(statemachine.state, DownloadState)
    return statemachine, statemachine.state


def test_statemachine_initial_state(statemachine_fixture):
    statemachine = statemachine_fixture
    assert isinstance(statemachine.state, FetchJobsState)


def test_transition_fetch_to_monitor_on_no_jobs(monitor_state):
    statemachine, _ = monitor_state
    statemachine.dispatch(Event(NO_JOBS_PENDING))
    assert isinstance(statemachine.state, MonitorState)


def test_transition_monitor_to_prepare_on_jobs(monitor_state):
    statemachine, _ = monitor_state
    statemachine.dispatch(Event(JOBS_AVAILABLE, **TEST_PAYLOAD_QUEUED_JOB))
    assert isinstance(statemachine.state, SelectJobState)


# this can happen if the job gets deleted after we have requested
# the job description, then we get an "resource not found" response.
def test_transition_prepare_to_fetch_on_job_deleted(select_job_state):
    statemachine, _ = select_job_state
    statemachine.dispatch(Event(JOB_RESOURCE_NOT_FOUND))
    assert isinstance(statemachine.state, FetchJobsState)


# this can happen if the download takes longer than how long
# the singed url is valid for, the maximum is 3600 seconds.
def test_transition_download_to_fetch_on_expired_signed_url(download_state):
    statemachine, _ = download_state
    statemachine.dispatch(Event(DOWNLOAD_INTERRUPTED))
    assert isinstance(statemachine.state, FetchJobsState)


def test_transition_download_to_install_on_complete(download_state):
    statemachine, _ = download_state
    statemachine.dispatch(Event(DOWNLOAD_COMPLETED, **TEST_PAYLOAD_INITIALIZED_JOB))
    assert isinstance(statemachine.state, InstallState)
