from queue import Queue

import pytest

from ..utils import create_mqtt_message_event  # noqa: F401
from ..utils import create_mqtt_subscription_event  # noqa: F401
from upparat.config import settings
from upparat.events import JOBS_AVAILABLE
from upparat.events import MQTT_MESSAGE_RECEIVED
from upparat.statemachine import UpparatStateMachine
from upparat.statemachine.monitor import MonitorState


@pytest.fixture
def monitor_state(mocker):
    state = MonitorState()

    inbox = Queue()
    mqtt_client = mocker.Mock()

    statemachine = UpparatStateMachine(inbox=inbox, mqtt_client=mqtt_client)
    statemachine.add_state(state)

    return state, inbox, mqtt_client, statemachine


def test_on_enter_subscribes(monitor_state):
    state, _, mqtt_client, __ = monitor_state

    settings.broker.thing_name = "bobby"
    state.on_enter(None, None)

    mqtt_client.subscribe.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/notify", qos=1
    )


def test_on_exit_unsubscribes(monitor_state):
    state, _, mqtt_client, __ = monitor_state

    settings.broker.thing_name = "bobby"

    # can only unsubscribe if we subscribed (on_enter)
    state.on_enter(None, None)
    state.on_exit(None, None)

    mqtt_client.unsubscribe.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/notify"
    )


def test_on_message_no_pending_jobs(monitor_state, create_mqtt_message_event):
    state, inbox, _, __ = monitor_state

    # prepare get_pending_job_executions_response
    settings.broker.thing_name = "bobby"
    state.on_enter(None, None)

    topic = f"$aws/things/{settings.broker.thing_name}/jobs/get/+"
    payload = {"queuedJobs": [], "inProgressJobs": []}

    mqtt_message_event = create_mqtt_message_event(topic, payload)
    state.on_message(None, mqtt_message_event)

    assert inbox.empty()


def test_on_message_pending_queued_jobs(monitor_state, create_mqtt_message_event):
    state, inbox, _, __ = monitor_state

    # prepares job_pending_response
    settings.broker.thing_name = "bobby"
    state.on_enter(None, None)

    queued_job = {"jobId": "42"}
    topic = f"$aws/things/{settings.broker.thing_name}/jobs/notify"
    payload = {"jobs": {"IN_PROGRESS": [], "QUEUED": [queued_job]}}

    mqtt_message_event = create_mqtt_message_event(topic, payload)
    state.on_message(None, mqtt_message_event)

    published_event = inbox.get_nowait()
    assert published_event.name == JOBS_AVAILABLE
    assert "job_execution_summaries" in published_event.cargo

    progress = published_event.cargo["job_execution_summaries"]["progress"]
    assert len(progress) == 0

    queued = published_event.cargo["job_execution_summaries"]["queued"]
    assert queued == [queued_job]


def test_on_message_pending_progress_jobs(monitor_state, create_mqtt_message_event):
    state, inbox, _, __ = monitor_state

    # prepares job_pending_response
    settings.broker.thing_name = "bobby"
    state.on_enter(None, None)

    progress_job = {"jobId": "42"}
    topic = f"$aws/things/{settings.broker.thing_name}/jobs/notify"
    payload = {"jobs": {"IN_PROGRESS": [progress_job], "QUEUED": []}}

    mqtt_message_event = create_mqtt_message_event(topic, payload)
    state.on_message(None, mqtt_message_event)

    published_event = inbox.get_nowait()
    assert published_event.name == JOBS_AVAILABLE
    assert "job_execution_summaries" in published_event.cargo

    progress = published_event.cargo["job_execution_summaries"]["progress"]
    assert progress == [progress_job]

    queued = published_event.cargo["job_execution_summaries"]["queued"]
    assert len(queued) == 0


def test_event_handlers_handle_mqtt(monitor_state):
    state, _, __, ___ = monitor_state
    event_handlers = state.event_handlers()

    assert MQTT_MESSAGE_RECEIVED in event_handlers
