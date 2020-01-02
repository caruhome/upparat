import json
from queue import Queue

import pytest

from ..utils import create_hook_event  # noqa: F401
from upparat.config import settings
from upparat.events import HOOK
from upparat.events import HOOK_STATUS_COMPLETED
from upparat.events import HOOK_STATUS_FAILED
from upparat.events import HOOK_STATUS_TIMED_OUT
from upparat.events import RESTART_INTERRUPTED
from upparat.jobs import Job
from upparat.jobs import JobFailedStatus
from upparat.jobs import JobProgressStatus
from upparat.jobs import JobStatus
from upparat.jobs import JobSuccessStatus
from upparat.statemachine import UpparatStateMachine
from upparat.statemachine.restart import RestartState

JOB_ = Job(
    "42",
    JobStatus.IN_PROGRESS,
    "http://foo.bar/baz.bin",
    "1.0.0",
    "False",
    "meta",
    "details",
)


@pytest.fixture
def restart_state(mocker):
    run_hook = mocker.patch("upparat.statemachine.restart.run_hook")
    settings.broker.thing_name = "bobby"

    state = RestartState()
    state.job = JOB_

    inbox = Queue()
    mqtt_client = mocker.Mock()

    statemachine = UpparatStateMachine(inbox=inbox, mqtt_client=mqtt_client)
    statemachine.add_state(state)

    return state, inbox, mqtt_client, statemachine, run_hook


def test_on_enter_no_restart_hook(restart_state):
    state, inbox, mqtt_client, _, run_hook = restart_state

    # should not have a default hook
    # → must be provided by Upparat user
    assert not settings.hooks.restart

    state.on_enter(None, None)

    assert run_hook.call_count == 0

    assert inbox.qsize() == 1
    published_event = inbox.get_nowait()
    assert published_event.name == RESTART_INTERRUPTED

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{JOB_.id_}/update",
        '{"status": "SUCCEEDED", "statusDetails": {"state": "no_restart_hook_provided", "message": "none"}}',  # noqa
    )


def test_on_enter_restart_hook(restart_state):
    state, inbox, mqtt_client, _, run_hook = restart_state
    settings.hooks.restart = "./restart.sh"

    state.on_enter(None, None)

    assert inbox.empty()

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{JOB_.id_}/update",
        json.dumps(
            {
                "status": JobStatus.IN_PROGRESS.value,
                "statusDetails": {
                    "state": JobProgressStatus.REBOOT_START.value,
                    "message": "none",
                },
            }
        ),
    )

    run_hook.assert_called_once_with(settings.hooks.restart, inbox, args=[JOB_.meta])


def test_on_job_cancelled(restart_state):
    state, inbox, _, _, _ = restart_state
    settings.hooks.restart = "./restart.sh"

    state.on_enter(None, None)
    state.on_job_cancelled(None, None)

    published_event = inbox.get_nowait()
    assert published_event.name == RESTART_INTERRUPTED
    assert state.stop_restart_hook.is_set()


def test_hook_completed(restart_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = restart_state
    settings.hooks.restart = "./restart.sh"

    event = create_hook_event(settings.hooks.restart, HOOK_STATUS_COMPLETED)
    state.on_restart_hook_event(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == RESTART_INTERRUPTED

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{JOB_.id_}/update",
        json.dumps(
            {
                "status": JobStatus.SUCCEEDED.value,
                "statusDetails": {
                    "state": JobSuccessStatus.COMPLETE_SOFT_RESTART.value,
                    "message": "none",
                },
            }
        ),
    )


def test_hook_failed(restart_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = restart_state
    settings.hooks.restart = "./restart.sh"

    message = "failed"
    event = create_hook_event(settings.hooks.restart, HOOK_STATUS_FAILED, message)
    state.on_restart_hook_event(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == RESTART_INTERRUPTED

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{JOB_.id_}/update",
        json.dumps(
            {
                "status": JobStatus.FAILED.value,
                "statusDetails": {
                    "state": JobFailedStatus.RESTART_HOOK_FAILED.value,
                    "message": message,
                },
            }
        ),
    )


def test_hook_timedout(restart_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = restart_state
    settings.hooks.restart = "./restart.sh"

    message = "timedout"
    event = create_hook_event(settings.hooks.restart, HOOK_STATUS_TIMED_OUT, message)
    state.on_restart_hook_event(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == RESTART_INTERRUPTED

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{JOB_.id_}/update",
        json.dumps(
            {
                "status": JobStatus.FAILED.value,
                "statusDetails": {
                    "state": JobFailedStatus.RESTART_HOOK_FAILED.value,
                    "message": message,
                },
            }
        ),
    )


def test_event_handlers_handle_hook(restart_state):
    state, _, _, _, _ = restart_state
    event_handlers = state.event_handlers()

    assert HOOK in event_handlers
