import json
from queue import Queue

import pytest

from ..utils import create_mqtt_message_event  # noqa: F401
from ..utils import create_mqtt_subscription_event  # noqa: F401
from upparat.config import settings
from upparat.events import JOB_SELECTED
from upparat.events import MQTT_MESSAGE_RECEIVED
from upparat.events import MQTT_SUBSCRIBED
from upparat.events import SELECT_JOB_INTERRUPTED
from upparat.jobs import describe_job_execution_response
from upparat.jobs import Job
from upparat.jobs import JOB_ACCEPTED
from upparat.jobs import JOB_MESSAGE
from upparat.jobs import JOB_REJECTED
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
def create_enter_event(mocker):
    def _create_enter_event(jobs_queued, jobs_in_progress):
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

    return _create_enter_event


def test_no_pending_jobs(select_job_state, create_enter_event, mocker):
    state, inbox, _, __ = select_job_state

    event = create_enter_event(jobs_queued=[], jobs_in_progress=[])
    state.on_enter(None, event)

    published_event = inbox.get_nowait()

    assert published_event.name == SELECT_JOB_INTERRUPTED
    assert inbox.empty()


def test_exactly_one_job_in_progress(select_job_state, create_enter_event, mocker):
    state, _, mqtt_client, __ = select_job_state

    job_id = "424242"
    thing_name = "bobby"

    settings.broker.thing_name = thing_name
    event = create_enter_event(jobs_queued=[], jobs_in_progress=[{"jobId": job_id}])
    state.on_enter(None, event)

    assert state.current_job_id == job_id
    # check that we subscribe, so that the
    # job will eventually end up in prepare
    mqtt_client.subscribe.assert_called_once_with(
        f"$aws/things/{thing_name}/jobs/{job_id}/get/+", qos=1
    )


def test_more_than_one_job_in_progress(select_job_state, create_enter_event, mocker):
    state, inbox, mqtt_client, _ = select_job_state

    job_id_1 = "1"
    job_id_2 = "2"
    thing_name = "bobby"

    settings.broker.thing_name = thing_name

    event = create_enter_event(
        jobs_queued=[], jobs_in_progress=[{"jobId": job_id_1}, {"jobId": job_id_2}]
    )

    state.on_enter(None, event)

    # having more than one is no valid state
    # thus we mark all the jobs in progress
    # as failed an have no pending jobs
    published_event = inbox.get_nowait()
    assert published_event.name == SELECT_JOB_INTERRUPTED
    assert inbox.empty()
    assert state.current_job_id is None

    # check that all we mark all as failed via mqtt
    assert mqtt_client.publish.call_count == 2
    assert mqtt_client.publish.call_args_list == [
        mocker.call(
            f"$aws/things/bobby/jobs/{job_id_1}/update",
            json.dumps(
                {
                    "status": JobStatus.FAILED.value,
                    "statusDetails": {
                        "state": JobProgressStatus.ERROR_MULTIPLE_IN_PROGRESS.value,
                        "message": "Invalid: More than one job is IN PROGRESS: 1, 2",
                    },
                }
            ),
        ),
        mocker.call(
            f"$aws/things/bobby/jobs/{job_id_2}/update",
            json.dumps(
                {
                    "status": JobStatus.FAILED.value,
                    "statusDetails": {
                        "state": JobProgressStatus.ERROR_MULTIPLE_IN_PROGRESS.value,
                        "message": "Invalid: More than one job is IN PROGRESS: 1, 2",
                    },
                }
            ),
        ),
    ]


def test_multiple_jobs_in_queued(select_job_state, create_enter_event, mocker):
    """ make sure oldest gets selected first """
    state, inbox, _, __ = select_job_state

    oldest_job_id = "42"

    jobs_queued = [
        {"jobId": 1, "queuedAt": 100},
        {"jobId": oldest_job_id, "queuedAt": 1},
        {"jobId": 2, "queuedAt": 101},
    ]

    event = create_enter_event(jobs_queued=jobs_queued, jobs_in_progress=[])

    state.on_enter(None, event)

    assert state.current_job_id == oldest_job_id


def test_on_message_rejected_job(select_job_state, create_mqtt_message_event):
    state, inbox, _, __ = select_job_state

    state.current_job_id = "42"
    settings.broker.thing_name = "bobby"

    event = create_mqtt_message_event(
        describe_job_execution_response(
            settings.broker.thing_name, state.current_job_id, state_filter=JOB_REJECTED
        ),
        {JOB_MESSAGE: "job has been rejected"},
    )

    state.on_message(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == SELECT_JOB_INTERRUPTED
    assert inbox.empty()


def test_on_message_accepted_job(select_job_state, create_mqtt_message_event):
    state, inbox, _, __ = select_job_state

    state.current_job_id = "42"
    settings.broker.thing_name = "bobby"
    status = JobStatus.IN_PROGRESS.value
    file_url = "https://foo.bar/baz.bin"
    version = "1.1.0"
    force = "yes"
    meta = "_meta_"
    status_details = "_details_"

    event = create_mqtt_message_event(
        describe_job_execution_response(
            settings.broker.thing_name, state.current_job_id, state_filter=JOB_ACCEPTED
        ),
        {
            "execution": {
                "jobId": state.current_job_id,
                "status": status,
                "statusDetails": status_details,
                "jobDocument": {
                    "version": version,
                    "file": file_url,
                    "force": force,
                    "meta": meta,
                },
            }
        },
    )

    state.on_message(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == JOB_SELECTED
    assert inbox.empty()

    job = published_event.cargo["job"]
    assert type(job) == Job
    assert job.id_ == state.current_job_id
    assert job.status == status
    assert job.status_details == status_details
    assert job.file_url == file_url
    assert job.version == version
    assert job.force is True
    assert job.meta == meta


def test_on_message_not_matching_topic(select_job_state, create_mqtt_message_event):
    state, inbox, mqtt_client, __ = select_job_state

    state.current_job_id = "42"
    settings.broker.thing_name = "bobby"

    event_rejected = create_mqtt_message_event(
        describe_job_execution_response(
            "not_bobby", "not_42", state_filter=JOB_REJECTED
        )
    )

    event_accepted = create_mqtt_message_event(
        describe_job_execution_response(
            "not_bobby", "not_42", state_filter=JOB_ACCEPTED
        )
    )

    state.on_message(None, event_rejected)
    state.on_message(None, event_accepted)

    # should do nothing
    assert inbox.empty()
    assert mqtt_client.publish.call_count == 0


def test_on_subscription_topic_match(select_job_state, create_mqtt_subscription_event):
    state, inbox, mqtt_client, __ = select_job_state

    settings.broker.thing_name = "bobby"
    state.current_job_id = "42"
    state.describe_job_execution_response = describe_job_execution_response(
        settings.broker.thing_name, state.current_job_id
    )

    event = create_mqtt_subscription_event(state.describe_job_execution_response)

    state.on_subscription(None, event)

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{state.current_job_id}/get",
        qos=1,
    )


def test_on_subscription_topic_no_match(
    select_job_state, create_mqtt_subscription_event
):
    state, inbox, mqtt_client, __ = select_job_state

    settings.broker.thing_name = "bobby"
    state.current_job_id = "42"
    state.describe_job_execution_response = describe_job_execution_response(
        settings.broker.thing_name, state.current_job_id
    )

    event = create_mqtt_subscription_event(
        describe_job_execution_response("not_bobby", "not_42")
    )

    state.on_subscription(None, event)

    assert mqtt_client.publish.call_count == 0


def test_event_handlers_handle_mqtt(select_job_state):
    state, _, __, ___ = select_job_state
    event_handlers = state.event_handlers()

    assert MQTT_SUBSCRIBED in event_handlers
    assert MQTT_MESSAGE_RECEIVED in event_handlers
