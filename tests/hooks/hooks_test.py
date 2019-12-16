import subprocess
from pathlib import Path

import freezegun

from upparat.config import settings
from upparat.events import HOOK
from upparat.events import HOOK_MESSAGE
from upparat.events import HOOK_STATUS
from upparat.events import HOOK_STATUS_COMPLETED
from upparat.events import HOOK_STATUS_FAILED
from upparat.events import HOOK_STATUS_OUTPUT
from upparat.events import HOOK_STATUS_TIMED_OUT
from upparat.hooks import RETRY_EXIT_CODE
from upparat.hooks import run_hook

COMMAND_FILE = (Path(__file__).parent / "test.sh").as_posix()


def _freeze_time_threading(*args, **kwargs):
    f = freezegun.freeze_time(*args, **kwargs)
    f.ignore = tuple(set(f.ignore) - {"threading"})
    return f


def _subprocess_mock(mocker, exit_codes, stdout: list):
    mock = mocker.patch("upparat.hooks.subprocess.Popen")

    process_mock = mocker.MagicMock()
    process_mock.stdout = stdout
    process_mock.poll.side_effect = exit_codes

    mock.return_value.__enter__.return_value = process_mock

    return mock


def test_args_clean(mocker):
    mock = mocker.patch("upparat.hooks.threading.Thread")
    run_hook("dummy", None, [1, None, 2])

    _, kwargs = mock.call_args

    assert kwargs["kwargs"]["args"] == ["1", "", "2"]


def test_stop_event(mocker):
    mock = mocker.patch("upparat.hooks._hook")
    stop_event = run_hook("dummy", None, join=True)
    stop_event.set()

    _, kwargs = mock.call_args
    assert kwargs["stop_event"].is_set()


def test_subprocess_args(mocker):
    mock = _subprocess_mock(mocker, [0], [])

    command = "noop"
    start_time = 1520294400  # "2018-03-06"
    retry_count = 0

    with _freeze_time_threading("2018-03-06"):
        run_hook(command, mocker.MagicMock(), args=None, join=True)
    mock.assert_called_once_with(
        [command, str(start_time), str(retry_count)],
        bufsize=1,
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )


def test_progress(mocker):
    command = "noop"

    stdout_lines = ["1", "2", "3"]

    _subprocess_mock(mocker, [0], stdout_lines)

    queue = mocker.MagicMock()

    settings.hooks.retry_interval = 0

    run_hook(command, queue, join=True)

    calls = queue.put.call_args_list

    # All lines as progress + the completed event
    assert len(calls) == len(stdout_lines) + 1

    for line_number, line in enumerate(stdout_lines):
        args, _ = calls[line_number]
        event = args[0]
        assert event.name == HOOK
        assert event.cargo[HOOK_STATUS] == HOOK_STATUS_OUTPUT
        assert event.cargo[HOOK_MESSAGE] == line

    args, _ = calls[-1]
    event = args[0]
    assert event.name == HOOK
    assert event.cargo[HOOK_STATUS] == HOOK_STATUS_COMPLETED
    assert event.cargo[HOOK_MESSAGE] == stdout_lines[-1]


def test_retry(mocker):
    command = "noop"
    retry_count = 2
    return_value = "0.1.1"

    mock = _subprocess_mock(mocker, [RETRY_EXIT_CODE, 0], [return_value])

    queue = mocker.MagicMock()

    settings.hooks.retry_interval = 0

    run_hook(command, queue, join=True)

    assert mock.call_count == retry_count

    args, _ = queue.put.call_args

    event = args[0]
    assert event.name == HOOK
    assert event.cargo[HOOK_STATUS] == HOOK_STATUS_COMPLETED
    assert event.cargo[HOOK_MESSAGE] == return_value


def test_retry_timeout(mocker):
    command = "long"

    mock = _subprocess_mock(mocker, [RETRY_EXIT_CODE, RETRY_EXIT_CODE], [])

    queue = mocker.MagicMock()

    settings.hooks.retry_interval = 0
    settings.hooks.max_retries = 1

    run_hook(command, queue, join=True)

    assert mock.call_count == settings.hooks.max_retries

    args, _ = queue.put.call_args

    event = args[0]
    assert event.name == HOOK
    assert event.cargo[HOOK_STATUS] == HOOK_STATUS_TIMED_OUT
    assert (
        event.cargo[HOOK_MESSAGE] == f"Timeout after {settings.hooks.retry_interval}s"
    )


def test_fail(mocker):
    command = "fail"
    exit_code = 33

    mock = _subprocess_mock(mocker, [exit_code], [])

    queue = mocker.MagicMock()

    run_hook(command, queue, join=True)

    assert mock.call_count == 1

    args, _ = queue.put.call_args

    event = args[0]
    assert event.name == HOOK
    assert event.cargo[HOOK_STATUS] == HOOK_STATUS_FAILED
    assert event.cargo[HOOK_MESSAGE] == f"Exit code: {exit_code}"


def test_command(mocker):
    queue = mocker.MagicMock()
    run_hook(COMMAND_FILE, queue, join=True)
    args, _ = queue.put.call_args

    event = args[0]
    assert event.name == HOOK
    assert event.cargo[HOOK_STATUS] == HOOK_STATUS_COMPLETED
    assert event.cargo[HOOK_MESSAGE] == "timeout:12"
