import subprocess
from _signal import SIGQUIT
from unittest.mock import MagicMock

import freezegun

from upparat.config import settings
from upparat.events import HOOK_MESSAGE
from upparat.events import HOOK_RESULT
from upparat.hooks import run_hook


def freeze_time_threading(*args, **kwargs):
    f = freezegun.freeze_time(*args, **kwargs)
    f.ignore = tuple(set(f.ignore) - {"threading"})
    return f


def test_args_clean(mocker):
    mock = mocker.patch("upparat.hooks.threading.Thread")
    run_hook("dummy", None, [1, None, 2])

    _, kwargs = mock.call_args

    assert kwargs["kwargs"]["args"] == ["1", "", "2"]


def test_stop_event(mocker):
    mock = mocker.patch("upparat.hooks._hook")
    stop_event = run_hook("dummy", None)

    _, kwargs = mock.call_args

    stop_event.set()
    assert kwargs["stop_event"].is_set()


def test_subprocess_args(mocker):
    mock = mocker.patch("upparat.hooks.subprocess.run")

    command = "noop"
    start_time = 1520294400  # "2018-03-06"
    retry_count = 0

    with freeze_time_threading("2018-03-06"):
        run_hook(command, MagicMock(), args=None, join=True)
    mock.assert_called_once_with(
        [command, start_time, retry_count],
        check=True,
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )


def test_retry(mocker):
    command = "noop"
    retry_count = 2
    return_value = "0.1.1"

    subprocess_result = MagicMock()
    subprocess_result.stdout = return_value

    mock = mocker.patch("upparat.hooks.subprocess.run")
    mock.side_effect = [
        subprocess.CalledProcessError(cmd=command, returncode=SIGQUIT),
        subprocess_result,
    ]

    cb = MagicMock()

    settings.hooks.retry_interval = 0

    run_hook("dummy", cb, join=True)

    assert mock.call_count == retry_count

    args, _ = cb.call_args

    event = args[0]
    assert event.name == HOOK_RESULT
    assert event.cargo[HOOK_MESSAGE] == return_value
