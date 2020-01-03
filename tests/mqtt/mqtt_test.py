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


# TODO Continue here
# def test_unsubscribe_success(mocker, mqtt):
#     client, queue = mqtt
#     client._unsubscribe = mocker.Mock(return_value=(MQTT_ERR_SUCCESS, None))

#     qos = 1
#     topic = "topic"
#     client.unsubscribe(topic, qos)

#     client._subscribe.assert_called_once_with(topic, qos=qos, mid=MID)
#     client._mid_generate.assert_called_once_with()

#     # check subscription state
#     assert client._subscriptions[topic] == qos
#     assert client._subscription_mid[MID] == topic

#     assert len(client._unsubscriptions) == 0
#     assert len(client._unsubscription_mid) == 0
