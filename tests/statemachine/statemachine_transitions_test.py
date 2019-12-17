from queue import Queue

import pytest
from pysm import Event

from upparat.cli import create_statemachine
from upparat.events import DOWNLOAD_COMPLETED
from upparat.events import DOWNLOAD_INTERRUPTED
from upparat.events import INSTALLATION_DONE
from upparat.events import INSTALLATION_INTERRUPTED
from upparat.events import JOB_INSTALLATION_COMPLETE
from upparat.events import JOB_INSTALLATION_DONE
from upparat.events import JOB_REVOKED
from upparat.events import JOB_SELECTED
from upparat.events import JOB_VERIFIED
from upparat.events import JOBS_AVAILABLE
from upparat.events import NO_JOBS_PENDING
from upparat.events import RESTART_INTERRUPTED
from upparat.events import SELECT_JOB_INTERRUPTED
from upparat.statemachine.download import DownloadState
from upparat.statemachine.fetch_jobs import FetchJobsState
from upparat.statemachine.install import InstallState
from upparat.statemachine.monitor import MonitorState
from upparat.statemachine.restart import RestartState
from upparat.statemachine.select_job import SelectJobState
from upparat.statemachine.verify_installation import VerifyInstallationState
from upparat.statemachine.verify_job import VerifyJobState


@pytest.fixture
def statemachine_fixture(mocker):
    mocker.patch("upparat.cli.FetchJobsState", autospec=True)
    mocker.patch("upparat.cli.MonitorState", autospec=True)
    mocker.patch("upparat.cli.SelectJobState", autospec=True)
    mocker.patch("upparat.cli.VerifyJobState", autospec=True)
    mocker.patch("upparat.cli.DownloadState", autospec=True)
    mocker.patch("upparat.cli.InstallState", autospec=True)
    mocker.patch("upparat.cli.RestartState", autospec=True)
    mocker.patch("upparat.cli.VerifyInstallationState", autospec=True)

    inbox = Queue()
    mqtt_client = mocker.Mock()

    return create_statemachine(inbox, mqtt_client)


@pytest.fixture
def fetch_jobs_state(statemachine_fixture):
    return statemachine_fixture, statemachine_fixture.state


@pytest.fixture
def monitor_state(fetch_jobs_state):
    statemachine, _ = fetch_jobs_state
    statemachine.dispatch(Event(NO_JOBS_PENDING))
    assert isinstance(statemachine.state, MonitorState)
    return statemachine, statemachine.state


@pytest.fixture
def select_job_state(fetch_jobs_state):
    statemachine, _ = fetch_jobs_state
    statemachine.dispatch(Event(JOBS_AVAILABLE))
    assert isinstance(statemachine.state, SelectJobState)
    return statemachine, statemachine.state


@pytest.fixture
def verify_job_state(select_job_state):
    statemachine, _ = select_job_state
    statemachine.dispatch(Event(JOB_SELECTED))
    assert isinstance(statemachine.state, VerifyJobState)
    return statemachine, statemachine.state


@pytest.fixture
def download_state(mocker, verify_job_state):
    statemachine, _ = verify_job_state
    statemachine.dispatch(Event(JOB_VERIFIED))
    assert isinstance(statemachine.state, DownloadState)
    return statemachine, statemachine.state


@pytest.fixture
def install_state(mocker, download_state):
    statemachine, _ = download_state
    statemachine.dispatch(Event(DOWNLOAD_COMPLETED))
    assert isinstance(statemachine.state, InstallState)
    return statemachine, statemachine.state


@pytest.fixture
def restart_state(mocker, install_state):
    statemachine, _ = install_state
    statemachine.dispatch(Event(INSTALLATION_DONE))
    assert isinstance(statemachine.state, RestartState)
    return statemachine, statemachine.state


@pytest.fixture
def verify_installation_state(mocker, verify_job_state):
    statemachine, _ = verify_job_state
    statemachine.dispatch(Event(JOB_INSTALLATION_DONE))
    assert isinstance(statemachine.state, VerifyInstallationState)
    return statemachine, statemachine.state


def test_statemachine_initial_state(statemachine_fixture):
    assert isinstance(statemachine_fixture.state, FetchJobsState)
    assert isinstance(statemachine_fixture.initial_state, FetchJobsState)


def test_fetch_jobs_no_pending_jobs_found(fetch_jobs_state):
    statemachine, _ = fetch_jobs_state
    statemachine.dispatch(Event(NO_JOBS_PENDING))
    assert isinstance(statemachine.state, MonitorState)
    return statemachine, statemachine.state


def test_fetch_jobs_pending_jobs_found(fetch_jobs_state):
    statemachine, _ = fetch_jobs_state
    statemachine.dispatch(Event(JOBS_AVAILABLE))
    assert isinstance(statemachine.state, SelectJobState)
    return statemachine, statemachine.state


def test_select_found_job_to_processs(select_job_state):
    statemachine, _ = select_job_state
    statemachine.dispatch(Event(JOB_SELECTED))
    assert isinstance(statemachine.state, VerifyJobState)
    return statemachine, statemachine.state


def test_select_job_got_rejected(select_job_state):
    statemachine, _ = select_job_state
    statemachine.dispatch(Event(SELECT_JOB_INTERRUPTED))
    assert isinstance(statemachine.state, FetchJobsState)
    return statemachine, statemachine.state


def test_verify_job_is_download_ready(verify_job_state):
    statemachine, _ = verify_job_state
    statemachine.dispatch(Event(JOB_VERIFIED))
    assert isinstance(statemachine.state, DownloadState)
    return statemachine, statemachine.state


def test_verify_job_is_installation_ready(verify_job_state):
    statemachine, _ = verify_job_state
    statemachine.dispatch(Event(JOB_INSTALLATION_DONE))
    assert isinstance(statemachine.state, VerifyInstallationState)
    return statemachine, statemachine.state


def test_verify_job_is_revoked(verify_job_state):
    statemachine, _ = verify_job_state
    statemachine.dispatch(Event(JOB_REVOKED))
    assert isinstance(statemachine.state, FetchJobsState)
    return statemachine, statemachine.state


def test_verify_installation_complete(verify_installation_state):
    statemachine, _ = verify_installation_state
    statemachine.dispatch(Event(JOB_INSTALLATION_COMPLETE))
    assert isinstance(statemachine.state, FetchJobsState)
    return statemachine, statemachine.state


def test_download_interrupted(download_state):
    statemachine, _ = download_state
    statemachine.dispatch(Event(DOWNLOAD_INTERRUPTED))
    assert isinstance(statemachine.state, FetchJobsState)
    return statemachine, statemachine.state


def test_download_completed(download_state):
    statemachine, _ = download_state
    statemachine.dispatch(Event(DOWNLOAD_COMPLETED))
    assert isinstance(statemachine.state, InstallState)
    return statemachine, statemachine.state


def test_install_interrupted(install_state):
    statemachine, _ = install_state
    statemachine.dispatch(Event(INSTALLATION_INTERRUPTED))
    assert isinstance(statemachine.state, FetchJobsState)
    return statemachine, statemachine.state


def test_install_done(install_state):
    statemachine, _ = install_state
    statemachine.dispatch(Event(INSTALLATION_DONE))
    assert isinstance(statemachine.state, RestartState)
    return statemachine, statemachine.state


def test_restarted_failure(restart_state):
    statemachine, _ = restart_state
    statemachine.dispatch(Event(RESTART_INTERRUPTED))
    assert isinstance(statemachine.state, FetchJobsState)
    return statemachine, statemachine.state
