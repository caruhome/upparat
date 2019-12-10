import logging
import subprocess
import threading
import time

import pysm

from upparat.config import settings
from upparat.events import HOOK_FAILED
from upparat.events import HOOK_MESSAGE
from upparat.events import HOOK_RESULT
from upparat.events import HOOK_TIMED_OUT

logger = logging.getLogger(__name__)


def _hook(hook, stop_event, callback, args: list):
    """
    todo: should this be interruptable even during the retry_interval?
    """
    retry = 0
    max_retries = settings.hooks.max_retries
    retry_interval = settings.hooks.retry_interval

    first_call = int(time.time())

    while retry < max_retries and not stop_event.is_set():
        try:
            result = subprocess.run(
                [hook, first_call, retry] + args,
                check=True,
                stdout=subprocess.PIPE,
                universal_newlines=True,
            )
            callback(pysm.Event(HOOK_RESULT, **{HOOK_MESSAGE: result.stdout.strip()}))
            break
        except subprocess.CalledProcessError as cpe:
            if cpe.returncode == 3:
                logger.debug(f"Retry '{hook}'")
                time.sleep(retry_interval)
                retry += 1
                if retry == max_retries:
                    callback(
                        pysm.Event(
                            HOOK_TIMED_OUT,
                            **{
                                HOOK_MESSAGE: f"Timeout after {max_retries * retry_interval}s"
                            },
                        )
                    )
                    logger.warning(
                        f"Giving up on command '{hook}' after {max_retries * retry_interval}s"
                    )
                    break
            else:
                callback(
                    pysm.Event(
                        HOOK_FAILED, **{HOOK_MESSAGE: f"Exit code: {cpe.returncode}"}
                    )
                )
                logger.error(f"Command '{hook}' failed with code: {cpe.returncode}")
                break


def run_hook(hook, callback, args=None, join=False):
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
        kwargs={
            "hook": hook,
            "args": args,
            "stop_event": stop_event,
            "callback": callback,
        },
    )
    hook_runner.start()

    if join:
        hook_runner.join()

    return stop_event
