import logging
import os
import socket
import threading
import urllib.request
from urllib.error import HTTPError
from urllib.error import URLError

import backoff
import pysm

from upparat.config import settings
from upparat.events import DOWNLOAD_COMPLETED
from upparat.events import DOWNLOAD_INTERRUPTED
from upparat.events import JOB
from upparat.jobs import JobProgressStatus
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)

# TODO double check what makes sense here
# https://stackoverflow.com/questions/28695448/
READ_CHUNK_SIZE_BYTES = 1024 * 100
REQUEST_TIMEOUT_SEC = 30


@backoff.on_exception(
    backoff.expo, (URLError, HTTPError, socket.timeout), jitter=backoff.full_jitter
)
def download(state):
    start_position_bytes = 0

    if os.path.exists(state.job.filepath):
        start_position_bytes = os.path.getsize(state.job.filepath)
        logger.info(f"Partial download of {start_position_bytes} bytes found.")

    if state.stop_download.is_set():
        logger.info(f"Download interrupted [stop event set].")

    request = urllib.request.Request(state.job.file_url)
    request.add_header("Range", f"bytes={start_position_bytes}-")

    logger.info(f"Downloading job to {state.job.filepath}.")

    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SEC
        ) as source, open(state.job.filepath, "ab") as destination:

            done = False

            while not done and not state.stop_download.is_set():
                data = source.read(READ_CHUNK_SIZE_BYTES)
                destination.write(data)
                done = not data

        if state.stop_download.is_set():
            logger.info(f"Download stopped. Removing {state.job.filepath}.")
            os.remove(state.job.filepath)

        if done:
            logger.info(f"Download completed.")
            state.publish(pysm.Event(DOWNLOAD_COMPLETED, **{JOB: state.job}))

    except HTTPError as http_error:
        if http_error.status == 416:
            # TODO review this decision:
            # right now we don't want to pass additional file
            # meta data through the job so if we get an error
            # due to an unsatisfiable ranger header, it's
            # likely because we already have all bytes.
            state.publish(pysm.Event(DOWNLOAD_COMPLETED, **{JOB: state.job}))
        elif http_error.status == 403:
            logger.warning("URL has expired. Starting over.")
            state.job_progress(JobProgressStatus.DOWNLOAD_INTERRUPT.value)
            state.publish(pysm.Event(DOWNLOAD_INTERRUPTED))
        else:
            logger.error(f"HTTPError {http_error.status}: {http_error.reason}.")
            raise http_error


class DownloadState(JobProcessingState):
    """
    Start file download
    """

    name = "download"
    job = None
    stop_download = threading.Event()

    def on_enter(self, state, event):
        self.stop_download = threading.Event()

        for download_file in os.listdir(settings.service.download_location):
            download_file_path = settings.service.download_location / download_file
            if not self.job.filepath == download_file_path:
                logger.info(f"Deleting previous download artifact {download_file_path}")
                os.remove(download_file_path)

        logger.debug(f"Start download for job {self.job.id_}.")
        self.job_progress(JobProgressStatus.DOWNLOAD_START.value)

        threading.Thread(daemon=True, target=download, kwargs={"state": self}).start()

    def on_exit(self, state, event):
        self.stop_download.set()

    def on_job_cancelled(self, state, event):
        self.stop_download.set()
        self.publish(pysm.Event(DOWNLOAD_INTERRUPTED))
