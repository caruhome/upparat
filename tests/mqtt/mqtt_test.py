from queue import Queue

import pytest
from paho.mqtt.client import MQTT_ERR_NO_CONN
from paho.mqtt.client import MQTT_ERR_SUCCESS

from upparat.events import MQTT_EVENT_PAYLOAD
from upparat.events import MQTT_EVENT_TOPIC
from upparat.events import MQTT_MESSAGE_RECEIVED
from upparat.events import MQTT_SUBSCRIBED
from upparat.events import MQTT_UNSUBSCRIBED
from upparat.mqtt import MQTT

MID = 42


@pytest.fixture
def mqtt(mocker):
    queue = Queue()
    client_id = "_"
    client = MQTT(client_id, queue)

    mocker.spy(client, "connect_async")
    mocker.spy(client, "loop_start")
    mocker.spy(client, "_subscribe")
    mocker.spy(client, "_unsubscribe")

    client._mid_generate = mocker.Mock(return_value=MID)

    return client, queue


def test_run(mocker, mqtt):
    client, queue = mqtt

    port = 443
    host = "localhost"
    client.run(host, port)

    client.connect_async.assert_called_once_with(host, port)
    client.loop_start.assert_called_once_with()


def test_subscribe_success(mocker, mqtt):
    client, queue = mqtt
    client._subscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))

    qos = 1
    topic = "topic"
    client.subscribe(topic, qos)

    client._subscribe.assert_called_once_with(topic, qos=qos, mid=MID)
    client._mid_generate.assert_called_once_with()

    # check subscription state
    assert client._subscriptions[topic] == qos
    assert client._subscription_mid[MID] == topic

    assert len(client._unsubscriptions) == 0
    assert len(client._unsubscription_mid) == 0


def test_subscribe_unsuccessful(mocker, mqtt):
    client, queue = mqtt
    client._subscribe = mocker.Mock(return_value=(MQTT_ERR_NO_CONN, None))

    qos = 1
    topic = "topic"
    client.subscribe(topic, qos)

    client._subscribe.assert_called_once_with(topic, qos=qos, mid=MID)
    client._mid_generate.assert_called_once_with()

    # check subscription state
    #
    # keep, in case it's fixed on reconnect
    assert client._subscriptions[topic] == qos

    assert len(client._subscription_mid) == 0
    assert len(client._unsubscriptions) == 0
    assert len(client._unsubscription_mid) == 0


def test_unsubscribe_success(mocker, mqtt):
    client, queue = mqtt
    client._unsubscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))

    topic = "topic"
    client.unsubscribe(topic)

    client._unsubscribe.assert_called_once_with(topic, mid=MID)
    client._mid_generate.assert_called_once_with()

    # check subscription state
    assert client._unsubscription_mid[MID] == topic
    assert topic in client._unsubscriptions

    assert len(client._subscriptions) == 0
    assert len(client._subscription_mid) == 0


def test_unsubscribe_unsuccessful(mocker, mqtt):
    client, queue = mqtt
    client._unsubscribe = mocker.Mock(return_value=(MQTT_ERR_NO_CONN, None))

    topic = "topic"
    client.unsubscribe(topic)

    client._unsubscribe.assert_called_once_with(topic, mid=MID)
    client._mid_generate.assert_called_once_with()

    # check subscription state
    assert topic in client._unsubscriptions

    assert len(client._unsubscription_mid) == 0
    assert len(client._subscriptions) == 0
    assert len(client._subscription_mid) == 0


def test_on_connect_handler_resubscribe(mocker, mqtt):
    client, queue = mqtt
    client._subscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))
    client._unsubscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))

    # setup: subscribe to a topic
    topic = "sub_topic"
    client.subscribe(topic)

    # reset mock after setup calls
    client._subscribe.reset_mock()
    client._unsubscribe.reset_mock()

    client.on_connect(None, None, None, MQTT_ERR_SUCCESS)

    client._subscribe.assert_called_once_with(topic, qos=0, mid=MID)
    assert client._unsubscribe.call_count == 0


def test_on_connect_handler_unsuccessful_unsubscribe(mocker, mqtt):
    client, queue = mqtt
    client._subscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))
    client._unsubscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))

    # setup: unsubscribe from a topic
    topic = "unsub_topic"
    client.unsubscribe(topic)
    # ✗ not ok, missing on_unsubscribe

    # reset mock after setup calls
    client._subscribe.reset_mock()
    client._unsubscribe.reset_mock()

    # never got on_unsubscribe, thus re-unsubscribe
    client.on_connect(None, None, None, MQTT_ERR_SUCCESS)

    # re-unsubscribe on re-connect
    client._unsubscribe.assert_called_once_with(topic, mid=MID)
    assert client._subscribe.call_count == 0


def test_on_connect_handler_successful_unsubscribe(mocker, mqtt):
    client, queue = mqtt
    client._subscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))
    client._unsubscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))

    # setup: unsubscribe from a topic
    topic = "unsub_topic"
    client.unsubscribe(topic)
    # ✓ ok, success
    client.on_unsubscribe(None, None, MID)

    # reset mock after setup calls
    client._subscribe.reset_mock()
    client._unsubscribe.reset_mock()

    # got on_unsubscribe, thus NOT re-unsubscribe topic
    client.on_connect(None, None, None, MQTT_ERR_SUCCESS)

    assert client._unsubscribe.call_count == 0
    assert client._subscribe.call_count == 0


def test_on_message(mocker, mqtt):
    client, queue = mqtt

    message = mocker.Mock()
    message.topic = "topic"
    message.payload = "o/"

    client.on_message(None, None, message)

    assert queue.qsize() == 1

    event = queue.get_nowait()
    assert event.name == MQTT_MESSAGE_RECEIVED
    assert event.cargo == {
        MQTT_EVENT_PAYLOAD: message.payload,
        MQTT_EVENT_TOPIC: message.topic,
    }


def test_on_subscribe(mocker, mqtt):
    client, queue = mqtt
    client._subscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))

    # no subscribe with MID has been called
    client.on_subscribe(None, None, MID, None)
    assert queue.empty()

    topic = "topic"
    client.subscribe(topic)
    client.on_subscribe(None, None, MID, None)
    assert queue.qsize() == 1

    event = queue.get_nowait()
    assert event.name == MQTT_SUBSCRIBED
    assert event.cargo == {MQTT_EVENT_TOPIC: topic}


def test_on_unsubscribe(mocker, mqtt):
    client, queue = mqtt
    client._unsubscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))

    # no subscribe with MID has been called
    client.on_unsubscribe(None, None, MID)
    assert queue.empty()

    topic = "topic"
    client.unsubscribe(topic)
    client.on_unsubscribe(None, None, MID)
    assert queue.qsize() == 1

    event = queue.get_nowait()
    assert event.name == MQTT_UNSUBSCRIBED
    assert event.cargo == {MQTT_EVENT_TOPIC: topic}

    # check subscription state
    assert len(client._unsubscriptions) == 0
    assert len(client._unsubscription_mid) == 0
