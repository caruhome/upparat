import json
from queue import Queue

import pytest

from ..utils import create_hook_event  # noqa: F401
from upparat.config import settings
from upparat.events import HOOK
from upparat.events import HOOK_STATUS_COMPLETED
from upparat.events import HOOK_STATUS_FAILED
from upparat.events import HOOK_STATUS_TIMED_OUT
from upparat.events import INSTALLATION_DONE
from upparat.events import JOB_REVOKED
from upparat.events import JOB_VERIFIED
from upparat.jobs import Job
from upparat.jobs import JobFailedStatus
from upparat.jobs import JobProgressStatus
from upparat.jobs import JobStatus
from upparat.statemachine import UpparatStateMachine
from upparat.statemachine.verify_job import VerifyJobState


def create_job_with(
    status=JobStatus.QUEUED, force=False, version="1.0.1", status_details=None
):
    return Job(
        "42",
        status.value,
        "http://foo.bar/baz.bin",
        version,
        "True" if force else "False",
        "meta",
        status_details.value if status_details else None,
    )


@pytest.fixture
def verify_job_state(mocker):
    run_hook = mocker.patch("upparat.statemachine.verify_job.run_hook")

    settings.broker.thing_name = "bobby"
    settings.hooks.version = None

    state = VerifyJobState()
    state.job = create_job_with(JobStatus.IN_PROGRESS)

    inbox = Queue()
    mqtt_client = mocker.Mock()

    statemachine = UpparatStateMachine(inbox=inbox, mqtt_client=mqtt_client)
    statemachine.add_state(state)

    return state, inbox, mqtt_client, statemachine, run_hook


def test_on_enter_queued_no_hook(verify_job_state):
    state, inbox, _, _, _ = verify_job_state

    state.job = create_job_with(status=JobStatus.QUEUED)

    # should not have a default hook
    assert not settings.hooks.version

    state.on_enter(None, None)

    assert inbox.qsize() == 1
    published_event = inbox.get_nowait()
    assert published_event.name == JOB_VERIFIED
    assert published_event.cargo["job"] == state.job


def test_on_enter_queued_hook_not_executed_on_force_job(verify_job_state):
    state, inbox, _, _, run_hook = verify_job_state

    settings.hooks.version = "./version.sh"
    state.job = create_job_with(force=True)

    state.on_enter(None, None)

    assert inbox.qsize() == 1
    published_event = inbox.get_nowait()
    assert published_event.name == JOB_VERIFIED
    assert published_event.cargo["job"] == state.job
    assert run_hook.call_count == 0


def test_on_enter_queued_hook_executed(verify_job_state):
    state, inbox, _, _, run_hook = verify_job_state

    settings.hooks.version = "./version.sh"
    state.job = create_job_with(status=JobStatus.QUEUED)

    state.on_enter(None, None)

    assert inbox.empty()
    run_hook.assert_called_once_with(
        settings.hooks.version, inbox, args=[state.job.meta]
    )


def test_on_enter_progress_reboot_start(verify_job_state):
    state, inbox, _, _, run_hook = verify_job_state

    settings.hooks.version = "./version.sh"
    state.job = create_job_with(
        status=JobStatus.IN_PROGRESS, status_details=JobProgressStatus.REBOOT_START
    )

    state.on_enter(None, None)

    assert inbox.qsize() == 1
    published_event = inbox.get_nowait()
    assert published_event.name == INSTALLATION_DONE
    assert published_event.cargo["job"] == state.job
    assert run_hook.call_count == 0


def test_on_enter_progress_reboot_start(verify_job_state):
    state, inbox, _, _, run_hook = verify_job_state

    settings.hooks.version = "./version.sh"
    state.job = create_job_with(status=JobStatus.IN_PROGRESS)

    state.on_enter(None, None)

    assert inbox.qsize() == 1
    published_event = inbox.get_nowait()
    assert published_event.name == JOB_VERIFIED
    assert published_event.cargo["job"] == state.job
    assert run_hook.call_count == 0


def test_on_enter_raise_on_invalid_status(verify_job_state):
    """ any other state except IN_PROGRESS and QUEUED should raise """

    for status in JobStatus:

        if status in [JobStatus.QUEUED, JobStatus.IN_PROGRESS]:
            continue

        state, inbox, _, _, run_hook = verify_job_state
        state.job = create_job_with(status=status)

        with pytest.raises(Exception):
            state.on_enter(None, None)


def test_on_job_cancelled(verify_job_state):
    state, inbox, _, _, _ = verify_job_state

    settings.hooks.version = "./version.sh"
    state.job = create_job_with(status=JobStatus.QUEUED)

    state.on_enter(None, None)
    state.on_job_cancelled(None, None)

    published_event = inbox.get_nowait()
    assert published_event.name == JOB_REVOKED
    assert state.stop_version_hook.is_set()


def test_event_handlers_handle_hook(verify_job_state):
    state, _, _, _, _ = verify_job_state
    event_handlers = state.event_handlers()

    assert HOOK in event_handlers


def test_hook_completed_version_match(verify_job_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = verify_job_state
    settings.hooks.version = "./version.sh"

    version = "1.0.1"
    state.job = create_job_with(version=version)
    event = create_hook_event(settings.hooks.version, HOOK_STATUS_COMPLETED, version)
    state.on_version_hook_event(None, event)

    assert inbox.qsize() == 1
    published_event = inbox.get_nowait()
    assert published_event.name == JOB_REVOKED

    mqtt_client.publish.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/{state.job.id_}/update",
        '{"status": "SUCCEEDED", "statusDetails": {"state": "version_already_installed", "message": "none"}}',  # noqa
    )


def test_hook_completed_version_mismatch(verify_job_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = verify_job_state
    settings.hooks.version = "./version.sh"

    wanted = "1.1.1"
    actual = "2.1.1"

    state.job = create_job_with(version=wanted)
    event = create_hook_event(settings.hooks.version, HOOK_STATUS_COMPLETED, actual)
    state.on_version_hook_event(None, event)

    assert inbox.qsize() == 1
    published_event = inbox.get_nowait()
    assert published_event.name == JOB_VERIFIED
    assert published_event.cargo["job"] == state.job


def test_hook_failed(verify_job_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = verify_job_state
    settings.hooks.version = "./version.sh"

    failure = HOOK_STATUS_FAILED

    output = "_failed_"
    event = create_hook_event(settings.hooks.version, failure, output)
    state.on_version_hook_event(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == JOB_REVOKED

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


def test_hook_timedout(verify_job_state, create_hook_event):
    state, inbox, mqtt_client, _, _ = verify_job_state
    settings.hooks.version = "./version.sh"

    failure = HOOK_STATUS_TIMED_OUT

    output = "_failed_"
    event = create_hook_event(settings.hooks.version, failure, output)
    state.on_version_hook_event(None, event)

    published_event = inbox.get_nowait()
    assert published_event.name == JOB_REVOKED

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
