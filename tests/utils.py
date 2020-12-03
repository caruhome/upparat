import json
import uuid

import pytest
from pysm import Event

from upparat.events import HOOK_COMMAND
from upparat.events import HOOK_MESSAGE
from upparat.events import HOOK_STATUS
from upparat.events import MQTT_EVENT_PAYLOAD
from upparat.events import MQTT_EVENT_TOPIC
from upparat.events import MQTT_MESSAGE_RECEIVED
from upparat.events import MQTT_SUBSCRIBED
from upparat.jobs import is_upparat_job_id
from upparat.jobs import UPPARAT_JOB_PREFIX


@pytest.fixture
def create_mqtt_message_event(mocker):
    def _create_mqtt_message_event(topic, payload=None):

        if not payload:
            payload = {}

        return Event(
            MQTT_MESSAGE_RECEIVED,
            **{MQTT_EVENT_TOPIC: topic, MQTT_EVENT_PAYLOAD: json.dumps(payload)},
        )

    return _create_mqtt_message_event


@pytest.fixture
def create_mqtt_subscription_event(mocker):
    def _create_mqtt_subscription_event(topic):
        return Event(MQTT_SUBSCRIBED, **{MQTT_EVENT_TOPIC: topic})

    return _create_mqtt_subscription_event


@pytest.fixture
def create_hook_event(mocker):
    def _create_hook_event(command, status, message=None):
        event = mocker.Mock()

        event.cargo = {
            HOOK_COMMAND: command,
            HOOK_STATUS: status,
            HOOK_MESSAGE: message,
        }

        return event

    return _create_hook_event


def generate_random_job_id():
    job_id = f"{UPPARAT_JOB_PREFIX}{str(uuid.uuid4())[0:8]}"
    assert is_upparat_job_id(job_id)
    return job_id
