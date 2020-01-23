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
from upparat.events import JOB
from upparat.jobs import JobProgressStatus
from upparat.statemachine import JobProcessingState

logger = logging.getLogger(__name__)

# TODO double check what makes sense here
# https://stackoverflow.com/questions/28695448/
READ_CHUNK_SIZE_BYTES = 1024 * 100  # 100 kib
REQUEST_TIMEOUT_SEC = 30


@backoff.on_exception(
    backoff.expo,
    (URLError, HTTPError, RemoteDisconnected, socket.timeout),
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

                    update_job_progress(
                        JobProgressStatus.DOWNLOAD_PROGRESS.value,
                        message=json.dumps(
                            {"downloaded_bytes": os.fstat(destination.fileno()).st_size}
                        ),
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
            # TODO review this decision:
            # right now we don't want to pass additional file
            # meta data through the job so if we get an error
            # due to an unsatisfiable ranger header, it's
            # likely because we already have all bytes.
            publish(pysm.Event(DOWNLOAD_COMPLETED, **{JOB: job}))
        elif http_error.status == 403:
            logger.warning("URL has expired. Starting over.")
            update_job_progress(JobProgressStatus.DOWNLOAD_INTERRUPT.value)
            publish(pysm.Event(DOWNLOAD_INTERRUPTED))
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

    def on_exit(self, state, event):
        self.stop_download.set()

    def on_job_cancelled(self, state, event):
        self.stop_download.set()
        self.publish(pysm.Event(DOWNLOAD_INTERRUPTED))
