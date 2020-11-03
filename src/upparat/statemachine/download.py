import functools
import json
import logging
import os
import socket
import threading
import urllib.request
from http.client import RemoteDisconnected
from urllib.error import HTTPError
from urllib.error import URLError

import backoff
import pysm

from upparat.config import settings
from upparat.events import DOWNLOAD_COMPLETED
from upparat.events import DOWNLOAD_INTERRUPTED
from upparat.events import HOOK
from upparat.events import HOOK_COMMAND
from upparat.events import HOOK_MESSAGE
from upparat.events import HOOK_STATUS
from upparat.events import HOOK_STATUS_COMPLETED
from upparat.events import HOOK_STATUS_FAILED
from upparat.events import HOOK_STATUS_TIMED_OUT
from upparat.events import JOB
from upparat.hooks import run_hook
from upparat.jobs import JobFailedStatus
from upparat.jobs import JobProgressStatus
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)

READ_CHUNK_SIZE_BYTES = 1024 * 100  # 100 kib
REQUEST_TIMEOUT_SEC = 30
BACKOFF_EXPO_MAX_SEC = 2 ** 6  # 64

RETRYABLE_EXCEPTIONS = (
    URLError,
    HTTPError,
    RemoteDisconnected,
    socket.timeout,
    ConnectionResetError,
)


@backoff.on_exception(
    functools.partial(backoff.expo, max_value=BACKOFF_EXPO_MAX_SEC),
    RETRYABLE_EXCEPTIONS,
    jitter=backoff.full_jitter,
)
def download(job, stop_download, publish, update_job_progress):
    """
    See https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
    for more information regarding the backoff behaviour (i.e. jitter).
    """
    start_position_bytes = 0

    if os.path.exists(job.filepath):
        start_position_bytes = os.path.getsize(job.filepath)
        logger.info(f"Partial download of {start_position_bytes} bytes found.")

    if stop_download.is_set():
        logger.info(f"Download interrupted [stop event set].")

    request = urllib.request.Request(job.file_url)
    request.add_header("Range", f"bytes={start_position_bytes}-")

    logger.info(f"Downloading job to {job.filepath}.")

    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SEC
        ) as source, open(job.filepath, "ab") as destination:

            done = False

            while not done and not stop_download.is_set():
                data = source.read(READ_CHUNK_SIZE_BYTES)

                if data:
                    destination.write(data)
                    # make sure everything is written to disk now
                    # https://docs.python.org/3/library/os.html#os.fsync
                    destination.flush()
                    os.fsync(destination)

                    downloaded_bytes = os.fstat(destination.fileno()).st_size
                    logger.debug(f"Downloaded {downloaded_bytes} bytes.")

                    update_job_progress(
                        JobProgressStatus.DOWNLOAD_PROGRESS.value,
                        message=json.dumps({"downloaded_bytes": downloaded_bytes}),
                    )
                else:
                    done = True

        if stop_download.is_set():
            logger.info(f"Download stopped. Removing {job.filepath}.")
            os.remove(job.filepath)

        if done:
            logger.info(f"Download completed.")
            publish(pysm.Event(DOWNLOAD_COMPLETED, **{JOB: job}))

    except HTTPError as http_error:
        if http_error.status == 416:
            publish(pysm.Event(DOWNLOAD_COMPLETED, **{JOB: job}))
        elif http_error.status == 403:
            logger.warning("URL has expired. Starting over.")
            update_job_progress(JobProgressStatus.DOWNLOAD_INTERRUPT.value)
            publish(pysm.Event(DOWNLOAD_INTERRUPTED))
        else:
            logger.error(f"HTTPError {http_error.status}: {http_error.reason}.")
            raise http_error
    except Exception as exception:
        if type(exception) not in RETRYABLE_EXCEPTIONS:
            # see issue #19, instead of hanging on unhanded exception,
            # we try to improve the situation by just starting over
            # since we don't have any better error recovery strategy.
            logger.exception("Unhandled failure. Starting over.")
            update_job_progress(JobProgressStatus.DOWNLOAD_INTERRUPT.value)
            publish(pysm.Event(DOWNLOAD_INTERRUPTED))
        else:
            # let backoff.on_exception handle retry
            # for this exception
            raise exception


class DownloadState(JobProcessingState):
    """ State that handles the actual download. """

    name = "download"
    job = None

    def __init__(self):
        self.stop_download_hook = threading.Event()
        self.stop_download = threading.Event()
        super().__init__()

    def clean_previous_downloads(self):
        for download_file in os.listdir(settings.service.download_location):
            download_file_path = settings.service.download_location / download_file
            if not self.job.filepath == download_file_path:
                logger.info(f"Deleting previous download artifact {download_file_path}")
                os.remove(download_file_path)

    def start_download_thread(self):
        # event could still be set from the previous job
        # that has been cancelled or deleted, so clear it.
        self.stop_download.clear()
        self.clean_previous_downloads()

        logger.debug(f"Start download for job {self.job.id_}.")
        self.job_progress(JobProgressStatus.DOWNLOAD_START.value)

        threading.Thread(
            daemon=True,
            target=download,
            kwargs={
                "job": self.job,
                "stop_download": self.stop_download,
                "publish": self.publish,
                "update_job_progress": self.job_progress,
            },
        ).start()

    def on_enter(self, state, event):
        hook = settings.hooks.download
        force = self.job.force

        if hook and not force:
            self.stop_download_hook = run_hook(
                hook, self.root_machine.inbox, args=[self.job.meta]
            )
        else:
            logger.info(
                f"Skip download hook: Hook={hook if hook else 'no-hook'}, force={force}."
            )
            self.start_download_thread()

    def stop_hooks(self):
        self.stop_download_hook.set()

    def on_exit(self, state, event):
        self.stop_hooks()
        self.stop_download.set()

    def event_handlers(self):
        return {HOOK: self.on_handle_hooks}

    def on_handle_hooks(self, _, event):
        if event.cargo[HOOK_COMMAND] != settings.hooks.download:
            return

        status = event.cargo[HOOK_STATUS]

        if status == HOOK_STATUS_COMPLETED:
            logger.info("Hook successfully completed. Download now allowed.")
            self.start_download_thread()

        elif status in (HOOK_STATUS_FAILED, HOOK_STATUS_TIMED_OUT):
            error_message = event.cargo[HOOK_MESSAGE]
            logger.error(f"Version hook failed: {error_message}")

            self.job_failed(
                JobFailedStatus.DOWNLOAD_HOOK_FAILED.value, message=error_message
            )
            self.publish(pysm.Event(DOWNLOAD_INTERRUPTED))

    def on_job_cancelled(self, state, event):
        self.stop_hooks()
        self.stop_download.set()
        self.publish(pysm.Event(DOWNLOAD_INTERRUPTED))
