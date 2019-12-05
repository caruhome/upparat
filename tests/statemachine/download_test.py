import json
from pathlib import Path
from queue import Queue
from urllib.error import HTTPError

import pytest

from upparat.config import settings
from upparat.events import DOWNLOAD_COMPLETED
from upparat.events import DOWNLOAD_INTERRUPTED
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
def download_state(mocker):
    state = DownloadState()
    state.job = mocker.Mock()
    state.job.id_ = "4242424"
    state.job.file_url = "https://foo.bar/baz"

    inbox = Queue()
    mqtt_client = mocker.Mock()

    statemachine = UpparatStateMachine(inbox=inbox, mqtt_client=mqtt_client)
    statemachine.add_state(state)

    return state, inbox, mqtt_client, statemachine


def test_download_completed_on_http_416(mocker, download_state, urllib_urlopen_mock):
    side_effect = create_http_error(416)
    urlopen_mock = urllib_urlopen_mock(side_effect)
    mocker.patch("urllib.request.urlopen", urlopen_mock)

    state, inbox, _, _ = download_state
    state.on_enter(None, None)

    event = inbox.get(timeout=TIMEOUT)
    assert event.name == DOWNLOAD_COMPLETED


def test_download_interrupted_on_http_403(mocker, download_state, urllib_urlopen_mock):
    side_effect = create_http_error(403)
    urlopen_mock = urllib_urlopen_mock(side_effect)
    mocker.patch("urllib.request.urlopen", urlopen_mock)

    state, inbox, _, _ = download_state
    state.on_enter(None, None)

    event = inbox.get(timeout=TIMEOUT)
    assert event.name == DOWNLOAD_INTERRUPTED


# FIXME how to make this faster?
def test_download_completed_successfully_with_retries(
    mocker, download_state, urllib_urlopen_mock, tmpdir
):
    side_effect = [b"11", create_http_error(404), b"22", b"33", b""]
    urlopen_mock = urllib_urlopen_mock(side_effect=side_effect)
    mocker.patch("urllib.request.urlopen", urlopen_mock)
    settings.service.download_location = tmpdir

    state, inbox, _, _ = download_state
    state.on_enter(None, None)

    # check if download completed
    event = inbox.get(timeout=TIMEOUT)
    assert event.name == DOWNLOAD_COMPLETED

    # check downloaded file
    with open(tmpdir / state.job.id_, "r") as fd:
        assert fd.read() == "112233"

    # check range headers
    first_request = urlopen_mock.call_args_list[0][0][0]
    second_request = urlopen_mock.call_args_list[1][0][0]
    assert first_request.header_items() == [("Range", "bytes=0-")]
    assert second_request.header_items() == [("Range", "bytes=2-")]

    # check urls
    assert first_request.full_url == state.job.file_url
    assert second_request.full_url == state.job.file_url


def test_download_put_job_in_progress(mocker, download_state, urllib_urlopen_mock):
    mocker.patch("urllib.request.urlopen", urllib_urlopen_mock())
    state, inbox, mqtt_client, _ = download_state
    state.on_enter(None, None)

    expected_thing_name = settings.broker.thing_name
    expected_job_id = state.job.id_

    assert mqtt_client.publish.call_count == 1
    assert mqtt_client.publish.call_args == mocker.call(
        f"$aws/things/{expected_thing_name}/jobs/{expected_job_id}/update",
        json.dumps(
            {
                "status": "IN_PROGRESS",
                "statusDetails": {"state": "download_start", "message": "none"},
            }
        ),
    )

    event = inbox.get(timeout=TIMEOUT)
    assert event.name == DOWNLOAD_COMPLETED


def test_clean_up_old_downloads(mocker, download_state, urllib_urlopen_mock, tmpdir):
    mocker.patch("urllib.request.urlopen", urllib_urlopen_mock())
    settings.service.download_location = tmpdir
    state, _, _, _ = download_state

    to_be_deleted = Path(tmpdir / "old.download.delete.me")
    to_be_deleted.touch()

    state.on_enter(None, None)

    assert not to_be_deleted.exists()


def test_on_job_cancelled(mocker, download_state, urllib_urlopen_mock):
    state, inbox, _, _ = download_state

    state.on_job_cancelled(None, None)

    event = inbox.get(timeout=TIMEOUT)
    assert state.stop_download.is_set()
    assert event.name == DOWNLOAD_INTERRUPTED
