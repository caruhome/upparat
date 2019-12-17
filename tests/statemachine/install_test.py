from queue import Queue

import pytest

from ..utils import create_mqtt_message_event  # noqa: F401
from ..utils import create_mqtt_subscription_event  # noqa: F401
from upparat.config import settings
from upparat.events import INSTALLATION_INTERRUPTED
from upparat.events import JOB
from upparat.jobs import Job
from upparat.jobs import JobStatus
from upparat.statemachine import UpparatStateMachine
from upparat.statemachine.install import InstallState

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


@pytest.fixture
def create_enter_event(mocker):
    def _create_enter_event(job):
        source_event = mocker.Mock()
        source_event.cargo = {JOB: JOB_}

        event = mocker.Mock()
        event.cargo = {"source_event": source_event}

        return event

    return _create_enter_event


def test_on_enter_missing_installation_hook(install_state, create_enter_event):
    state, inbox, mqtt_client, statemachine, _ = install_state

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


def test_on_enter_installation_hook(install_state, create_enter_event):
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
