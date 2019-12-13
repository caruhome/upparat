import json

import pytest
from pysm import Event

from upparat.events import MQTT_EVENT_PAYLOAD
from upparat.events import MQTT_EVENT_TOPIC
from upparat.events import MQTT_MESSAGE_RECEIVED
from upparat.events import MQTT_SUBSCRIBED


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
