import json
from pathlib import Path
from queue import Queue
from urllib.error import HTTPError

import pytest

from upparat.config import settings
from upparat.events import JOB_RESOURCE_NOT_FOUND
from upparat.jobs import JobProgressStatus
from upparat.jobs import JobStatus
from upparat.statemachine import UpparatStateMachine
from upparat.statemachine.select_job import SelectJobState


@pytest.fixture
def select_job_state(mocker):
    state = SelectJobState()

    inbox = Queue()
    mqtt_client = mocker.Mock()

    statemachine = UpparatStateMachine(inbox=inbox, mqtt_client=mqtt_client)
    statemachine.add_state(state)

    return state, inbox, mqtt_client, statemachine


@pytest.fixture
def create_event(mocker):
    def _create_event(jobs_queued, jobs_in_progress):
        source_event = mocker.Mock()
        source_event.cargo = {
            "job_execution_summaries": {
                "progress": jobs_in_progress,
                "queued": jobs_queued,
            }
        }

        event = mocker.Mock()
        event.cargo = {"source_event": source_event}

        return event

    return _create_event


def test_no_pending_jobs(select_job_state, create_event, mocker):
    state, inbox, _, __ = select_job_state

    event = create_event(jobs_queued=[], jobs_in_progress=[])
    state.on_enter(None, event)

    published_event = inbox.get_nowait()

    assert published_event.name == JOB_RESOURCE_NOT_FOUND


def test_exactly_one_job_in_progress(select_job_state, create_event, mocker):
    state, _, mqtt_client, __ = select_job_state

    job_id = "424242"
    thing_name = "bobby"

    settings.broker.thing_name = thing_name
    event = create_event(jobs_queued=[], jobs_in_progress=[{"jobId": job_id}])
    state.on_enter(None, event)

    assert state.current_job_id == job_id
    # check that we subscribe, so that the
    # job will eventually end up in prepare
    mqtt_client.subscribe.assert_called_once_with(
        f"$aws/things/{thing_name}/jobs/{job_id}/get/+", qos=1
    )


def test_more_than_one_job_in_progress(select_job_state, create_event, mocker):
    state, inbox, mqtt_client, _ = select_job_state

    job_id_1 = "1"
    job_id_2 = "2"
    thing_name = "bobby"

    settings.broker.thing_name = thing_name

    event = create_event(
        jobs_queued=[], jobs_in_progress=[{"jobId": job_id_1}, {"jobId": job_id_2}]
    )

    state.on_enter(None, event)

    # having more than one is no valid state
    # thus we mark all the jobs in progress
    # as failed an have no pending jobs
    published_event = inbox.get_nowait()
    assert published_event.name == JOB_RESOURCE_NOT_FOUND
    assert state.current_job_id == None

    # check that all we mark all as failed via mqtt
    assert mqtt_client.publish.call_count == 2
    assert mqtt_client.publish.call_args_list == [
        mocker.call(
            f"$aws/things/bobby/jobs/{job_id_1}/update",
            f'{{"status": "{JobStatus.FAILED.value}", "statusDetails": {{"state": "{JobProgressStatus.ERROR_MULTIPLE_IN_PROGRESS.value}", "message": "More than one job IN PROGRESS: 1, 2"}}}}',
        ),
        mocker.call(
            f"$aws/things/bobby/jobs/{job_id_2}/update",
            f'{{"status": "{JobStatus.FAILED.value}", "statusDetails": {{"state": "{JobProgressStatus.ERROR_MULTIPLE_IN_PROGRESS.value}", "message": "More than one job IN PROGRESS: 1, 2"}}}}',
        ),
    ]


def test_multiple_jobs_in_queued(select_job_state, create_event, mocker):
    assert True  # nach em esse :D

