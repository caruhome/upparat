from queue import Queue

import pytest

from ..utils import create_mqtt_message_event  # noqa: F401
from ..utils import create_mqtt_subscription_event  # noqa: F401
from upparat.config import settings
from upparat.statemachine import UpparatStateMachine
from upparat.statemachine.fetch_jobs import FetchJobsState


@pytest.fixture
def fetch_jobs_state(mocker):
    state = FetchJobsState()

    inbox = Queue()
    mqtt_client = mocker.Mock()

    statemachine = UpparatStateMachine(inbox=inbox, mqtt_client=mqtt_client)
    statemachine.add_state(state)

    return state, inbox, mqtt_client, statemachine


def test_on_enter_subscribes(fetch_jobs_state):
    state, _, mqtt_client, __ = fetch_jobs_state

    settings.broker.thing_name = "bobby"
    state.on_enter(None, None)

    mqtt_client.subscribe.assert_called_once_with(
        f"$aws/things/{settings.broker.thing_name}/jobs/get/+", qos=1
    )


def test_on_subscription_topic_match(fetch_jobs_state, create_mqtt_subscription_event):
    state, inbox, mqtt_client, __ = fetch_jobs_state

    # settings.broker.thing_name = "bobby"
    # state.current_job_id = "42"
    # state.describe_job_execution_response = describe_job_execution_response(
    #     settings.broker.thing_name, state.current_job_id
    # )

    # event = create_mqtt_subscription_event(state.describe_job_execution_response)

    # state.on_subscription(None, event)

    # mqtt_client.publish.assert_called_once_with(
    #     f"$aws/things/{settings.broker.thing_name}/jobs/{state.current_job_id}/get",
    #     qos=1,
    # )
