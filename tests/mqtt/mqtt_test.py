from queue import Queue

import pytest
from paho.mqtt.client import MQTT_ERR_NO_CONN
from paho.mqtt.client import MQTT_ERR_SUCCESS

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


# wip:
# def test_on_connect_handler(mocker, mqtt):
#     client, queue = mqtt
#     client._subscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))
#     client._unsubscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))

#     # setup: subscribe to a topic
#     subscribe_qos = 0
#     subscribe_topic = "sub_topic"
#     client.subscribe(subscribe_topic, subscribe_qos)

#     # setup: unsubscribe from a topic
#     unsubscribe_topic = "unsub_topic"
#     client.unsubscribe(unsubscribe_topic)
#     client.on_subscribe(None, None, MID, None)

#     # reset mock (setup calls)
#     client._subscribe.reset_mock()
#     client._unsubscribe.reset_mock()

#     client.on_connect(None, None, None, MQTT_ERR_SUCCESS)

#     client._subscribe.assert_called_once_with(
#         subscribe_topic, qos=subscribe_qos, mid=MID
#     )

#     client._unsubscribe.assert_called_once_with()
