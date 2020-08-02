from queue import Queue

import pytest
from pysm import Event

from upparat.cli import cli
from upparat.config import settings
from upparat.events import EXIT_SIGNAL_SENT


@pytest.fixture
def queue_with_exit_signal():
    queue = Queue()
    queue.put(Event(EXIT_SIGNAL_SENT))
    return queue


def test_exit_on_exit_signal_event(queue_with_exit_signal):
    with pytest.raises(SystemExit):
        cli(queue_with_exit_signal)


def test_sigint_handler(mocker, queue_with_exit_signal):
    signal = mocker.patch("upparat.cli.signal")

    with pytest.raises(SystemExit):
        cli(queue_with_exit_signal)

    assert signal.signal.call_count == 2
    assert signal.signal.call_args_list[0][0][0] == signal.SIGINT

    # test that SIGINT would put EXIT_SIGNAL_SENT event in queue
    assert queue_with_exit_signal.empty()
    signal_handler = signal.signal.call_args_list[0][0][1]
    signal_handler(None, None)

    assert queue_with_exit_signal.qsize() == 1
    event = queue_with_exit_signal.get_nowait()
    assert event.name == EXIT_SIGNAL_SENT


def test_sigterm_handler(mocker, queue_with_exit_signal):
    signal = mocker.patch("upparat.cli.signal")

    with pytest.raises(SystemExit):
        cli(queue_with_exit_signal)

    assert signal.signal.call_count == 2
    assert signal.signal.call_args_list[1][0][0] == signal.SIGTERM

    # test that SIGTERM would put EXIT_SIGNAL_SENT event in queue
    assert queue_with_exit_signal.empty()
    signal_handler = signal.signal.call_args_list[1][0][1]
    signal_handler(None, None)

    assert queue_with_exit_signal.qsize() == 1
    event = queue_with_exit_signal.get_nowait()
    assert event.name == EXIT_SIGNAL_SENT


def test_mqtt_client_setup(mocker, queue_with_exit_signal):
    mqtt = mocker.patch("upparat.cli.MQTT")
    mqtt_instance = mqtt.return_value

    settings.broker.client_id = "client_id"
    settings.broker.host = "broker.aws.com"
    settings.broker.port = 8080

    with pytest.raises(SystemExit):
        cli(queue_with_exit_signal)

    assert mqtt.call_args == mocker.call(
        client_id=settings.broker.client_id, queue=queue_with_exit_signal
    )

    mqtt_instance.run.assert_called_once_with(
        settings.broker.host, settings.broker.port
    )


# def test_mqtt_client_tls_setup(mocker, queue_with_exit_signal):
#     create_default_context = mocker.patch("upparat.cli.ssl_create_default_context")
#     ssl_default_context = create_default_context.return_value

#     mqtt = mocker.patch("upparat.cli.MQTT")
#     mqtt_instance = mqtt.return_value

#     settings.broker.client_id = "client_id"
#     settings.broker.host = "broker.aws.com"
#     settings.broker.port = 8080
#     settings.broker.cafile = "/tmp/cafile"
#     settings.broker.certfile = "/tmp/certfile"
#     settings.broker.keyfile = "/tmp/keyfile"

#     with pytest.raises(SystemExit):
#         cli(queue_with_exit_signal)

#     assert mqtt.call_args == mocker.call(
#         client_id=settings.broker.client_id, queue=queue_with_exit_signal
#     )

#     mqtt_instance.run.assert_called_once_with(
#         settings.broker.host, settings.broker.port
#     )

#     mqtt_instance.run.tls_set_context.assert_called_once()


def test_state_machine_setup(mocker, queue_with_exit_signal):
    create_statemachine = mocker.patch("upparat.cli.create_statemachine")
    statemachine = create_statemachine.return_value
    statemachine.dispatch.side_effect = SystemExit

    mqtt = mocker.patch("upparat.cli.MQTT")
    mqtt_instance = mqtt.return_value

    with pytest.raises(SystemExit):
        cli(queue_with_exit_signal)

    create_statemachine.assert_called_once_with(queue_with_exit_signal, mqtt_instance)
