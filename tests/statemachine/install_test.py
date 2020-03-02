import json
from queue import Queue

import pytest

from ..utils import create_hook_event  # noqa: F401
from upparat.config import settings
from upparat.events import HOOK
from upparat.events import HOOK_STATUS_COMPLETED
from upparat.events import HOOK_STATUS_FAILED
from upparat.events import HOOK_STATUS_OUTPUT
from upparat.events import HOOK_STATUS_TIMED_OUT
from upparat.events import INSTALLATION_DONE
from upparat.events import INSTALLATION_INTERRUPTED
from upparat.jobs import Job
from upparat.jobs import JobFailedStatus
from upparat.jobs import JobProgressStatus
from upparat.jobs import JobStatus
from upparat.statemachine import UpparatStateMachine
from upparat.statemachine.install import InstallState

JOB_ = Job(
    "42",
    JobStatus.IN_PROGRESS,
    "http://foo.bar/baz.bin",
    "1.0.0",
    False,
    "meta",
    "details",
)


@pytest.fixture
def install_state(mocker):
    run_hook = mocker.patch("upparat.statemachine.install.run_hook")
    settings.broker.thing_name = "bobby"

    state = InstallState()
    state.job = JOB_

    inbox = Queue()
    mqtt_client = mocker.Mock()

    statemachine = UpparatStateMachine(inbox=inbox, mqtt_client=mqtt_client)
    statemachine.add_state(state)

    return state, inbox, mqtt_client, statemachine, run_hook


def test_on_enter_missing_installation_hook(install_state):
    state, inbox, mqtt_client, _, _ = install_state

    # should not have a default hook
    # → must be provided by Upparat user
    assert not settings.hooks.install

    state.on_enter(None, None)

    published_event = inbox.get_nowait()
    assert published_event.name == INSTALLATION_INTERRUPTED

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{JOB_.id_}/update",
        '{"status": "SUCCEEDED", "statusDetails": {"state": "no_installation_hook_provided", "message": "none"}}',  # noqa
    )


def test_on_enter_installation_hook(install_state):
    state, inbox, mqtt_client, _, run_hook = install_state
    settings.hooks.install = "./install.sh"

    state.on_enter(None, None)

    assert inbox.empty()

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{JOB_.id_}/update",
        '{"status": "IN_PROGRESS", "statusDetails": {"state": "installation_start", "message": "none"}}',  # noqa
    )

    run_hook.assert_called_once_with(
        settings.hooks.install, inbox, args=[JOB_.meta, JOB_.filepath]
    )


def test_on_job_cancelled(install_state):
    state, inbox, _, _, _ = install_state
    settings.hooks.install = "./install.sh"

    state.on_job_cancelled(None, None)

    published_event = inbox.get_nowait()
    assert published_event.name == INSTALLATION_INTERRUPTED
    assert state.stop_install_hook.is_set()


def test_hook_completed(install_state, create_hook_event):
    state, inbox, _, _, _ = install_state
    settings.hooks.install = "./install.sh"

    event = create_hook_event(settings.hooks.install, HOOK_STATUS_COMPLETED)
    state.on_install_hook_event(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == INSTALLATION_DONE


def test_hook_completed(install_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = install_state
    settings.hooks.install = "./install.sh"

    output = "> 100% DONE <"
    event = create_hook_event(settings.hooks.install, HOOK_STATUS_OUTPUT, output)
    state.on_install_hook_event(None, event)

    assert inbox.empty()

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{JOB_.id_}/update",
        json.dumps(
            {
                "status": JobStatus.IN_PROGRESS.value,
                "statusDetails": {
                    "state": JobProgressStatus.INSTALLATION_PROGRESS.value,
                    "message": output,
                },
            }
        ),
    )


def test_hook_failed(install_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = install_state
    settings.hooks.install = "./install.sh"

    failure = HOOK_STATUS_FAILED

    output = "_failed_"
    event = create_hook_event(settings.hooks.install, failure, output)
    state.on_install_hook_event(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == INSTALLATION_INTERRUPTED

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{JOB_.id_}/update",
        json.dumps(
            {
                "status": JobStatus.FAILED.value,
                "statusDetails": {
                    "state": JobFailedStatus.INSTALLATION_HOOK_FAILED.value,
                    "message": output,
                },
            }
        ),
    )


def test_hook_timedout(install_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = install_state
    settings.hooks.install = "./install.sh"

    failure = HOOK_STATUS_TIMED_OUT

    output = "_timeout_"
    event = create_hook_event(settings.hooks.install, failure, output)
    state.on_install_hook_event(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == INSTALLATION_INTERRUPTED

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{JOB_.id_}/update",
        json.dumps(
            {
                "status": JobStatus.FAILED.value,
                "statusDetails": {
                    "state": JobFailedStatus.INSTALLATION_HOOK_FAILED.value,
                    "message": output,
                },
            }
        ),
    )


def test_event_handlers_handle_hook(install_state):
    state, _, _, _, _ = install_state
    event_handlers = state.event_handlers()

    assert HOOK in event_handlers
