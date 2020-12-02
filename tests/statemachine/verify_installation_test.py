import json
from queue import Queue

import pytest

from ..utils import create_hook_event  # noqa: F401
from ..utils import generate_random_job_id
from upparat.config import settings
from upparat.events import HOOK
from upparat.events import HOOK_STATUS_COMPLETED
from upparat.events import HOOK_STATUS_FAILED
from upparat.events import HOOK_STATUS_TIMED_OUT
from upparat.events import JOB_INSTALLATION_COMPLETE
from upparat.jobs import Job
from upparat.jobs import JobFailedStatus
from upparat.jobs import JobStatus
from upparat.jobs import JobSuccessStatus
from upparat.statemachine import UpparatStateMachine
from upparat.statemachine.verify_installation import VerifyInstallationState


def create_job_with(
    status=JobStatus.QUEUED, force=False, version="1.0.1", status_details=None
):
    return Job(
        generate_random_job_id(),
        status.value,
        "http://foo.bar/baz.bin",
        version,
        force,
        "meta",
        status_details.value if status_details else None,
    )


@pytest.fixture
def verify_installation_state(mocker):
    run_hook = mocker.patch("upparat.statemachine.verify_installation.run_hook")

    settings.broker.thing_name = "bobby"

    state = VerifyInstallationState()
    state.job = create_job_with(JobStatus.IN_PROGRESS)

    inbox = Queue()
    mqtt_client = mocker.Mock()

    statemachine = UpparatStateMachine(inbox=inbox, mqtt_client=mqtt_client)
    statemachine.add_state(state)

    return state, inbox, mqtt_client, statemachine, run_hook


def test_on_enter_no_hook(verify_installation_state):
    state, inbox, mqtt_client, _, _ = verify_installation_state

    # should not have a default hook
    assert not settings.hooks.version

    state.on_enter(None, None)

    assert inbox.qsize() == 1
    published_event = inbox.get_nowait()
    assert published_event.name == JOB_INSTALLATION_COMPLETE

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{state.job.id_}/update",
        json.dumps(
            {
                "status": JobStatus.SUCCEEDED.value,
                "statusDetails": {
                    "state": JobSuccessStatus.COMPLETE_NO_VERSION_CHECK.value,
                    "message": "none",
                },
            }
        ),
    )


@pytest.mark.parametrize("force", [True, False])
def test_on_enter_hook_executed(verify_installation_state, force):
    state, inbox, _, _, run_hook = verify_installation_state

    settings.hooks.version = "./version.sh"
    state.job = create_job_with(force=force)

    state.on_enter(None, None)

    assert inbox.empty()
    run_hook.assert_called_once_with(
        settings.hooks.version, inbox, args=[state.job.meta]
    )


def test_on_job_cancelled(verify_installation_state):
    state, inbox, _, _, _ = verify_installation_state

    # verify before state is correct
    assert not state.stop_version_hook.is_set()
    assert not state.stop_ready_hook.is_set()

    state.on_enter(None, None)
    state.on_job_cancelled(None, None)

    assert state.stop_version_hook.is_set()
    assert state.stop_ready_hook.is_set()

    published_event = inbox.get_nowait()
    assert published_event.name == JOB_INSTALLATION_COMPLETE
    assert state.stop_version_hook.is_set()


def test_event_handlers_handle_hook(verify_installation_state):
    state, _, _, _, _ = verify_installation_state
    event_handlers = state.event_handlers()

    assert HOOK in event_handlers


# ----------------------------------------------------- #
#                  Version Hook Tests                   #
# ----------------------------------------------------- #


def test_hook_version_ready_hook_version_match(
    verify_installation_state, create_hook_event
):
    """
    If version reported by hook matches version of job this means
    installation was successful, thus we expect the ready hook to
    be started now.
    """
    state, inbox, mqtt_client, _, run_hook = verify_installation_state

    settings.hooks.version = "./version.sh"
    settings.hooks.ready = "./ready.sh"

    # hook version == job version → ✓ run_hook(ready)
    version = "1.0.1"
    state.job = create_job_with(version=version)
    event = create_hook_event(settings.hooks.version, HOOK_STATUS_COMPLETED, version)
    state.on_handle_hooks(None, event)

    assert inbox.empty()
    assert mqtt_client.publish.call_count == 0

    run_hook.assert_called_once_with(settings.hooks.ready, inbox, args=[state.job.meta])


def test_hook_version_ready_hook_version_mismatch(
    verify_installation_state, create_hook_event
):
    state, inbox, mqtt_client, _, run_hook = verify_installation_state

    settings.hooks.version = "./version.sh"
    settings.hooks.ready = "./ready.sh"

    # hook version != job version → ✗ job_failed(VERSION_MISMATCH)
    hook_version = "1.0.1"
    state.job = create_job_with(version="2.0.0")
    event = create_hook_event(
        settings.hooks.version, HOOK_STATUS_COMPLETED, hook_version
    )

    state.on_handle_hooks(None, event)

    assert run_hook.call_count == 0
    assert inbox.qsize() == 1
    assert mqtt_client.publish.call_count == 1

    published_event = inbox.get_nowait()
    assert published_event.name == JOB_INSTALLATION_COMPLETE

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{state.job.id_}/update",
        json.dumps(
            {
                "status": JobStatus.FAILED.value,
                "statusDetails": {
                    "state": JobFailedStatus.VERSION_MISMATCH.value,
                    "message": f"Expected version '{state.job.version}', got '{hook_version}'",
                },
            }
        ),
    )


def test_hook_version_failed(verify_installation_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = verify_installation_state
    settings.hooks.version = "./version.sh"

    failure = HOOK_STATUS_FAILED

    output = "_install_failed_"
    event = create_hook_event(settings.hooks.version, failure, output)
    state.on_handle_hooks(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == JOB_INSTALLATION_COMPLETE

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{state.job.id_}/update",
        json.dumps(
            {
                "status": JobStatus.FAILED.value,
                "statusDetails": {
                    "state": JobFailedStatus.VERSION_HOOK_FAILED.value,
                    "message": output,
                },
            }
        ),
    )


def test_hook_version_timed_out(verify_installation_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = verify_installation_state
    settings.hooks.version = "./version.sh"

    failure = HOOK_STATUS_TIMED_OUT

    output = "_install_timeout_"
    event = create_hook_event(settings.hooks.version, failure, output)
    state.on_handle_hooks(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == JOB_INSTALLATION_COMPLETE

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{state.job.id_}/update",
        json.dumps(
            {
                "status": JobStatus.FAILED.value,
                "statusDetails": {
                    "state": JobFailedStatus.VERSION_HOOK_FAILED.value,
                    "message": output,
                },
            }
        ),
    )


# ----------------------------------------------------- #
#                    Ready Hook Tests                   #
# ----------------------------------------------------- #


def test_hook_ready_conpleted(verify_installation_state, create_hook_event):
    state, inbox, mqtt_client, _, run_hook = verify_installation_state
    settings.hooks.ready = "./ready.sh"

    event = create_hook_event(settings.hooks.ready, HOOK_STATUS_COMPLETED)
    state.on_handle_hooks(None, event)

    assert inbox.qsize() == 1
    assert mqtt_client.publish.call_count == 1

    published_event = inbox.get_nowait()
    assert published_event.name == JOB_INSTALLATION_COMPLETE

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{state.job.id_}/update",
        json.dumps(
            {
                "status": JobStatus.SUCCEEDED.value,
                "statusDetails": {
                    "state": JobSuccessStatus.COMPLETE_READY.value,
                    "message": "none",
                },
            }
        ),
    )


def test_hook_ready_failed(verify_installation_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = verify_installation_state
    settings.hooks.ready = "./ready.sh"

    failure = HOOK_STATUS_FAILED

    output = "_ready_failed_"
    event = create_hook_event(settings.hooks.ready, failure, output)
    state.on_handle_hooks(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == JOB_INSTALLATION_COMPLETE

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{state.job.id_}/update",
        json.dumps(
            {
                "status": JobStatus.FAILED.value,
                "statusDetails": {
                    "state": JobFailedStatus.READY_HOOK_FAILED.value,
                    "message": output,
                },
            }
        ),
    )


def test_hook_version_timed_out(verify_installation_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = verify_installation_state
    settings.hooks.ready = "./ready.sh"

    failure = HOOK_STATUS_TIMED_OUT

    output = "_ready_timeout_"
    event = create_hook_event(settings.hooks.ready, failure, output)
    state.on_handle_hooks(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == JOB_INSTALLATION_COMPLETE

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{state.job.id_}/update",
        json.dumps(
            {
                "status": JobStatus.FAILED.value,
                "statusDetails": {
                    "state": JobFailedStatus.READY_HOOK_FAILED.value,
                    "message": output,
                },
            }
        ),
    )
