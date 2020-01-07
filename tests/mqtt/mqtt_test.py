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


def test_on_subscribe_before_subscribe_returns(mocker, mqtt):
    """
    This is the most crucial test: Check that we still get the
    MQTT_SUBSCRIBED event in case we receive the on_subscribe
    callback call before _subscribe returns, see comment (A, B).
    """

    client, queue = mqtt

    def _subscribe(*args, **kwargs):
        # on_subscribe before _subscribe returns
        client.on_subscribe(None, None, MID, None)
        return MQTT_ERR_SUCCESS, None

    client._subscribe = _subscribe

    topic = "topic"
    client.subscribe(topic)

    assert queue.qsize() == 1
    event = queue.get_nowait()
    assert event.name == MQTT_SUBSCRIBED
    assert event.cargo == {MQTT_EVENT_TOPIC: topic}


def test_on_unsubscribe_before_unsubscribe_returns(mocker, mqtt):
    """
    Same as test_on_unsubscribe_before_unsubscribe_returns,
    but for the unsubscribe case.
    """

    client, queue = mqtt

    def _unsubscribe(*args, **kwargs):
        # on_unsubscribe before _unsubscribe returns
        client.on_unsubscribe(None, None, MID)
        return MQTT_ERR_SUCCESS, None

    client._unsubscribe = _unsubscribe

    topic = "topic"
    client.unsubscribe(topic)

    assert queue.qsize() == 1
    event = queue.get_nowait()
    assert event.name == MQTT_UNSUBSCRIBED
    assert event.cargo == {MQTT_EVENT_TOPIC: topic}


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
    assert len(client._unsubscription_mid) == 0
