import json
import socket
from http.client import RemoteDisconnected
from pathlib import Path
from queue import Queue
from urllib.error import HTTPError
from urllib.error import URLError

import pytest

from ..utils import create_hook_event  # noqa: F401
from upparat.config import settings
from upparat.events import DOWNLOAD_COMPLETED
from upparat.events import DOWNLOAD_INTERRUPTED
from upparat.events import HOOK_STATUS_COMPLETED
from upparat.events import HOOK_STATUS_FAILED
from upparat.events import HOOK_STATUS_TIMED_OUT
from upparat.jobs import Job
from upparat.jobs import JobFailedStatus
from upparat.jobs import JobProgressStatus
from upparat.jobs import JobStatus
from upparat.statemachine import UpparatStateMachine
from upparat.statemachine.download import DownloadState

TIMEOUT = 1.5


def create_http_error(status):
    error = HTTPError(None, None, None, None, None)
    error.status = status
    return error


@pytest.fixture
def urllib_urlopen_mock(mocker):
    def urllib_urlopen_mock_with_side_effect(side_effect=None):
        if not side_effect:
            side_effect = [b"some-bytes", b"some-more-bytes", b""]

        context_manager = mocker.MagicMock()
        context_manager.read.side_effect = side_effect
        context_manager.__enter__.return_value = context_manager
        return mocker.MagicMock(return_value=context_manager)

    return urllib_urlopen_mock_with_side_effect


@pytest.fixture
def download_state(mocker, tmpdir):
    run_hook = mocker.patch("upparat.statemachine.download.run_hook")

    settings.service.download_location = tmpdir
    settings.hooks.download = None

    state = DownloadState()

    state.job = Job(
        id_="424242",
        status=JobStatus.IN_PROGRESS,
        file_url="https://foo.bar/baz",
        version="1.1.1",
        force=False,
        meta="",
        status_details="",
    )

    inbox = Queue()
    mqtt_client = mocker.Mock()

    statemachine = UpparatStateMachine(inbox=inbox, mqtt_client=mqtt_client)
    statemachine.add_state(state)

    return state, inbox, mqtt_client, statemachine, run_hook


def test_download_completed_on_http_416(mocker, download_state, urllib_urlopen_mock):
    side_effect = create_http_error(416)
    urlopen_mock = urllib_urlopen_mock(side_effect)
    mocker.patch("urllib.request.urlopen", urlopen_mock)

    state, inbox, _, _, _ = download_state
    state.on_enter(None, None)

    event = inbox.get(timeout=TIMEOUT)
    assert event.name == DOWNLOAD_COMPLETED


def test_download_interrupted_on_http_403(mocker, download_state, urllib_urlopen_mock):
    side_effect = create_http_error(403)
    urlopen_mock = urllib_urlopen_mock(side_effect)
    mocker.patch("urllib.request.urlopen", urlopen_mock)

    state, inbox, _, _, _ = download_state
    state.on_enter(None, None)

    event = inbox.get(timeout=TIMEOUT)
    assert event.name == DOWNLOAD_INTERRUPTED


@pytest.mark.parametrize(
    "urlopen_side_effect, expected_download",
    [
        ([b"11", create_http_error(400), b"22", b"33", b""], "112233"),
        ([b"11", create_http_error(404), b"22", b"33", b""], "112233"),
        ([b"11", RemoteDisconnected(), b"22", b"33", b""], "112233"),
        ([b"11", URLError("reason"), b"22", b"33", b""], "112233"),
        ([b"11", socket.timeout(), b"22", b"33", b""], "112233"),
    ],
)
def test_download_completed_successfully_with_retries(
    urlopen_side_effect,
    expected_download,
    urllib_urlopen_mock,
    download_state,
    mocker,
    tmpdir,
):
    urlopen_mock = urllib_urlopen_mock(side_effect=urlopen_side_effect)
    mocker.patch("urllib.request.urlopen", urlopen_mock)
    mocker.patch("time.sleep")  # to make test faster

    state, inbox, _, _, _ = download_state
    state.on_enter(None, None)

    # check if download completed
    event = inbox.get(timeout=TIMEOUT)
    assert event.name == DOWNLOAD_COMPLETED

    # check downloaded file
    with open(state.job.filepath, "r") as fd:
        assert fd.read() == expected_download

    # check range headers
    first_request = urlopen_mock.call_args_list[0][0][0]
    second_request = urlopen_mock.call_args_list[1][0][0]
    assert first_request.header_items() == [("Range", "bytes=0-")]
    assert second_request.header_items() == [("Range", "bytes=2-")]

    # check urls
    assert first_request.full_url == state.job.file_url
    assert second_request.full_url == state.job.file_url


def test_download_job_progress_updates(mocker, download_state, urllib_urlopen_mock):
    urlopen_side_effect = [b"11", b"22", b"33", b""]
    urlopen_mock = urllib_urlopen_mock(side_effect=urlopen_side_effect)
    mocker.patch("urllib.request.urlopen", urlopen_mock)

    state, inbox, mqtt_client, _, _ = download_state
    state.on_enter(None, None)

    # wait for download to complete
    event = inbox.get(timeout=TIMEOUT)
    assert event.name == DOWNLOAD_COMPLETED

    expected_job_update_topic = (
        f"$aws/things/{settings.broker.thing_name}/jobs/{state.job.id_}/update"
    )

    # expectation for given urlopen_side_effect = ["11", "22", "33", ""]:
    #
    #    ┌── job_update(DOWNLOAD_START)
    #    │  ┌── job_update(DOWNLOAD_PROGRESS),      → 2 bytes downloaded
    #    │  │  ┌── job_update(DOWNLOAD_PROGRESS),   → 4 bytes downloaded
    #    │  │  │  ┌── job_update(DOWNLOAD_PROGRESS) → 6 bytes downloaded
    #    │  │  │  │
    #    - 11 22 33 ─ done
    #
    assert mqtt_client.publish.call_count == 4
    assert mqtt_client.publish.call_args_list == [
        mocker.call(
            expected_job_update_topic,
            json.dumps(
                {
                    "status": JobStatus.IN_PROGRESS.value,
                    "statusDetails": {
                        "state": JobProgressStatus.DOWNLOAD_START.value,
                        "message": "none",
                    },
                }
            ),
        ),
        mocker.call(
            expected_job_update_topic,
            json.dumps(
                {
                    "status": JobStatus.IN_PROGRESS.value,
                    "statusDetails": {
                        "state": JobProgressStatus.DOWNLOAD_PROGRESS.value,
                        "message": json.dumps({"downloaded_bytes": 2}),
                    },
                }
            ),
        ),
        mocker.call(
            expected_job_update_topic,
            json.dumps(
                {
                    "status": JobStatus.IN_PROGRESS.value,
                    "statusDetails": {
                        "state": JobProgressStatus.DOWNLOAD_PROGRESS.value,
                        "message": json.dumps({"downloaded_bytes": 4}),
                    },
                }
            ),
        ),
        mocker.call(
            expected_job_update_topic,
            json.dumps(
                {
                    "status": JobStatus.IN_PROGRESS.value,
                    "statusDetails": {
                        "state": JobProgressStatus.DOWNLOAD_PROGRESS.value,
                        "message": json.dumps({"downloaded_bytes": 6}),
                    },
                }
            ),
        ),
    ]


def test_clean_up_old_downloads(mocker, download_state, urllib_urlopen_mock, tmpdir):
    mocker.patch("urllib.request.urlopen", urllib_urlopen_mock())
    state, _, _, _, _ = download_state

    to_be_deleted = Path(tmpdir / "old.download.delete.me")
    to_be_deleted.touch()

    state.on_enter(None, None)

    assert not to_be_deleted.exists()


def test_on_job_cancelled(mocker, download_state):
    state, inbox, _, _, _ = download_state

    state.on_job_cancelled(None, None)

    event = inbox.get(timeout=TIMEOUT)
    assert state.stop_download.is_set()
    assert state.stop_download_hook.is_set()
    assert event.name == DOWNLOAD_INTERRUPTED


def test_on_job_cancelled(mocker, download_state):
    state, inbox, _, _, _ = download_state

    state.on_exit(None, None)

    assert state.stop_download.is_set()
    assert state.stop_download_hook.is_set()


def test_download_hook_completed(
    mocker, download_state, urllib_urlopen_mock, create_hook_event
):
    urlopen_side_effect = [b"_", b""]
    urlopen_mock = urllib_urlopen_mock(side_effect=urlopen_side_effect)
    mocker.patch("urllib.request.urlopen", urlopen_mock)

    state, inbox, _, _, run_hook = download_state
    settings.hooks.download = "./download.sh"

    state.on_enter(None, None)
    hook_event = create_hook_event(settings.hooks.download, HOOK_STATUS_COMPLETED)
    state.on_handle_hooks(None, hook_event)

    # run_hook should be called by on_enter
    run_hook.assert_called_once_with(settings.hooks.download, inbox, args=[""])

    # wait for download to complete
    event = inbox.get(timeout=TIMEOUT)
    assert event.name == DOWNLOAD_COMPLETED

    # check downloaded file
    with open(state.job.filepath, "r") as fd:
        assert fd.read() == "_"


def test_download_hook_with_force_flag_set(
    mocker, download_state, urllib_urlopen_mock, create_hook_event
):
    urlopen_side_effect = [b"_", b""]
    urlopen_mock = urllib_urlopen_mock(side_effect=urlopen_side_effect)
    mocker.patch("urllib.request.urlopen", urlopen_mock)

    state, inbox, _, _, run_hook = download_state
    # hook but force is also set → ignore hook
    settings.hooks.download = "./download.sh"
    state.job.force = True

    state.on_enter(None, None)

    # wait for download to complete
    event = inbox.get(timeout=TIMEOUT)
    assert event.name == DOWNLOAD_COMPLETED
    assert run_hook.call_count == 0

    # check downloaded file
    with open(state.job.filepath, "r") as fd:
        assert fd.read() == "_"


@pytest.mark.parametrize("failure", [HOOK_STATUS_FAILED, HOOK_STATUS_TIMED_OUT])
def test_download_hook_failures(
    mocker, download_state, failure, urllib_urlopen_mock, create_hook_event
):
    urlopen_side_effect = [b"_", b""]
    urlopen_mock = urllib_urlopen_mock(side_effect=urlopen_side_effect)
    mocker.patch("urllib.request.urlopen", urlopen_mock)

    state, inbox, mqtt_client, _, run_hook = download_state
    settings.hooks.download = "./download.sh"

    state.on_enter(None, None)
    hook_event = create_hook_event(settings.hooks.download, failure, ":(")
    state.on_handle_hooks(None, hook_event)

    # run_hook should be called by on_enter
    run_hook.assert_called_once_with(settings.hooks.download, inbox, args=[""])

    event = inbox.get(timeout=TIMEOUT)
    assert event.name == DOWNLOAD_INTERRUPTED
    assert not state.job.filepath.exists()

    expected_job_update_topic = (
        f"$aws/things/{settings.broker.thing_name}/jobs/{state.job.id_}/update"
    )

    mqtt_client.publish.assert_called_once_with(
        expected_job_update_topic,
        json.dumps(
            {
                "status": JobStatus.FAILED.value,
                "statusDetails": {
                    "state": JobFailedStatus.DOWNLOAD_HOOK_FAILED.value,
                    "message": ":(",
                },
            }
        ),
    )
