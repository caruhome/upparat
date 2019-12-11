import logging
import subprocess
import threading
import time
from queue import Queue

import pysm

from upparat.config import settings
from upparat.events import HOOK
from upparat.events import HOOK_COMMAND
from upparat.events import HOOK_MESSAGE
from upparat.events import HOOK_STATUS
from upparat.events import HOOK_STATUS_COMPLETED
from upparat.events import HOOK_STATUS_FAILED
from upparat.events import HOOK_STATUS_OUTPUT
from upparat.events import HOOK_STATUS_TIMED_OUT

logger = logging.getLogger(__name__)

RETRY_EXIT_CODE = 3


def _publish(inbox, hook, status, message):
    inbox.put(
        pysm.Event(
            HOOK, **{HOOK_COMMAND: hook, HOOK_STATUS: status, HOOK_MESSAGE: message}
        )
    )


def _hook(hook, stop_event, inbox: Queue, args: list):
    retry = 0
    max_retries = settings.hooks.max_retries
    retry_interval = settings.hooks.retry_interval

    first_call = int(time.time())

    while retry < max_retries and not stop_event.is_set():
        # universal_newlines=True and bufsize 1 means line buffered
        with subprocess.Popen(
            [hook, str(first_call), str(retry)] + args,
            stdout=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
        ) as process:
            last_line = None
            try:
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        last_line = line
                        _publish(inbox, hook, HOOK_STATUS_OUTPUT, line)
            except:  # noqa
                process.kill()
                process.wait()
                raise

            return_code = process.poll()

            if return_code == RETRY_EXIT_CODE:
                logger.debug(f"Retry '{hook}'")
                time.sleep(retry_interval)
                retry += 1
                if retry == max_retries:
                    _publish(
                        inbox,
                        hook,
                        HOOK_STATUS_TIMED_OUT,
                        f"Timeout after {max_retries * retry_interval}s",
                    )
                    logger.warning(
                        f"Giving up on command '{hook}' after {max_retries * retry_interval}s"
                    )
                    break
            elif return_code:
                _publish(inbox, hook, HOOK_STATUS_FAILED, f"Exit code: {return_code}")
                logger.error(f"Command '{hook}' failed with code: {return_code}")
                break
            else:
                _publish(inbox, hook, HOOK_STATUS_COMPLETED, last_line)
                break


def run_hook(hook, inbox, args=None, join=False):
    if not hook:
        return

    if not args:
        args = []
    else:
        args = [str(arg) if arg else "" for arg in args]

    logger.debug(f"Run hook: {hook} {' '.join(args)}")
    stop_event = threading.Event()

    hook_runner = threading.Thread(
        daemon=True,
        target=_hook,
        kwargs={"hook": hook, "args": args, "stop_event": stop_event, "inbox": inbox},
    )
    hook_runner.start()

    if join:
        hook_runner.join()

    return stop_event
