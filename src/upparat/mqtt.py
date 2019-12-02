import logging
import struct

from paho.mqtt.client import (
    MQTT_ERR_SUCCESS,
    CONNACK_ACCEPTED,
    connack_string,
    error_string,
    Client,
    MQTT_ERR_NO_CONN,
    UNSUBSCRIBE,
    MQTT_LOG_DEBUG,
    SUBSCRIBE,
)
from pysm import Event

from .events import (
    MQTT_SUBSCRIBED,
    MQTT_MESSAGE_RECEIVED,
    MQTT_UNSUBSCRIBED,
    MQTT_EVENT_TOPIC,
    MQTT_EVENT_PAYLOAD,
)

logger = logging.getLogger(__name__)


class MQTT(Client):
    def __init__(self, client_id, queue):
        self._queue = queue
        self._subscriptions = {}
        self._subscription_mid = {}
        self._unsubscriptions = set()
        self._unsubscription_mid = {}

        super().__init__(client_id)

        self.on_connect = self._on_connect_handler
        self.on_message = self._on_message_handler
        self.on_subscribe = self._on_subscribe_handler
        self.on_unsubscribe = self._on_unsubscribe_handler

    def run(self, host, port):
        self.enable_logger()
        logger.debug(f"Connect to {host}:{port}")
        self.connect_async(host, port)
        self.loop_start()

    def subscribe(self, topic, qos=0):
        # Remove the topic from unsubscription list
        self._unsubscriptions.discard(topic)

        message_id = self._mid_generate()
        self._subscription_mid[message_id] = topic
        result, _ = self._subscribe(topic, qos=qos, mid=message_id)
        if result != MQTT_ERR_SUCCESS:
            # Remove mid on failure
            del self._subscription_mid[message_id]
            logger.warning(
                f"Unable to subscribe to topic {topic}: {error_string(result)}"
            )
        self._subscriptions[topic] = qos
        return result, message_id

    def unsubscribe(self, topic):
        # Remove the topic from subscription list
        self._subscriptions.pop(topic, None)

        message_id = self._mid_generate()
        self._unsubscription_mid[message_id] = topic

        result, _ = self._unsubscribe(topic, mid=message_id)

        if result != MQTT_ERR_SUCCESS:
            del self._unsubscription_mid[message_id]

        return result, message_id

    def _on_connect_handler(self, _, __, ___, rc):
        message = connack_string(rc)
        if rc == CONNACK_ACCEPTED:
            logger.info(message)
        else:
            logger.error(message)

        # (Re)subscribe to topics
        for topic, qos in self._subscriptions.items():
            self.subscribe(topic, qos=qos)

        # (Re)unsubscribe to topics
        for topic in self._unsubscriptions:
            self.unsubscribe(topic)

    def _on_message_handler(self, _, __, message):
        self._queue.put(
            Event(
                MQTT_MESSAGE_RECEIVED,
                **{
                    MQTT_EVENT_TOPIC: message.topic,
                    MQTT_EVENT_PAYLOAD: message.payload,
                },
            )
        )

    def _on_subscribe_handler(self, _, __, mid, ___):
        if mid in self._subscription_mid:
            self._queue.put(
                Event(
                    MQTT_SUBSCRIBED,
                    **{MQTT_EVENT_TOPIC: self._subscription_mid.pop(mid)},
                )
            )
        else:
            logger.error(f"No topic mapping found for subscription {mid}")

    def _on_unsubscribe_handler(self, _, __, mid):
        if mid in self._unsubscription_mid:
            topic = self._unsubscription_mid.pop(mid)
            # Remove topic from unsubscribe list once we are unsubscribed. We don't
            # need to survive a disconnect.
            self._unsubscriptions.discard(topic)
            self._queue.put(Event(MQTT_UNSUBSCRIBED, **{MQTT_EVENT_TOPIC: topic}))
        else:
            logger.error(f"No topic mapping found for unsubscription {mid}")

    def _send_subscribe(self, dup, topics, mid=None):
        remaining_length = 2
        for t, _ in topics:
            remaining_length += 2 + len(t) + 1

        command = SUBSCRIBE | (dup << 3) | 0x2
        packet = bytearray()
        packet.append(command)
        self._pack_remaining_length(packet, remaining_length)
        if not mid:
            mid = self._mid_generate()
        packet.extend(struct.pack("!H", mid))
        for t, q in topics:
            self._pack_str16(packet, t)
            packet.append(q)

        self._easy_log(
            MQTT_LOG_DEBUG, "Sending SUBSCRIBE (d%d, m%d) %s", dup, mid, topics
        )
        return self._packet_queue(command, packet, mid, 1), mid

    def _subscribe(self, topic, qos=0, mid=None):
        topic_qos_list = None

        if isinstance(topic, tuple):
            topic, qos = topic

        if isinstance(topic, str):
            if qos < 0 or qos > 2:
                raise ValueError("Invalid QoS level.")
            if topic is None or len(topic) == 0:
                raise ValueError("Invalid topic.")
            topic_qos_list = [(topic.encode("utf-8"), qos)]
        elif isinstance(topic, list):
            topic_qos_list = []
            for t, q in topic:
                if q < 0 or q > 2:
                    raise ValueError("Invalid QoS level.")
                if t is None or len(t) == 0 or not isinstance(t, str):
                    raise ValueError("Invalid topic.")
                topic_qos_list.append((t.encode("utf-8"), q))

        if topic_qos_list is None:
            raise ValueError("No topic specified, or incorrect topic type.")

        if any(
            self._filter_wildcard_len_check(topic) != MQTT_ERR_SUCCESS
            for topic, _ in topic_qos_list
        ):
            raise ValueError("Invalid subscription filter.")

        if self._sock is None:
            return MQTT_ERR_NO_CONN, None

        return self._send_subscribe(False, topic_qos_list, mid)

    def _send_unsubscribe(self, dup, topics, mid=None):
        remaining_length = 2
        for t in topics:
            remaining_length += 2 + len(t)

        command = UNSUBSCRIBE | (dup << 3) | 0x2
        packet = bytearray()
        packet.append(command)
        self._pack_remaining_length(packet, remaining_length)
        if not mid:
            mid = self._mid_generate()
        packet.extend(struct.pack("!H", mid))
        for t in topics:
            self._pack_str16(packet, t)

        self._easy_log(
            MQTT_LOG_DEBUG, "Sending UNSUBSCRIBE (d%d, m%d) %s", dup, mid, topics
        )
        return self._packet_queue(command, packet, mid, 1), mid

    def _unsubscribe(self, topic, mid=None):
        """
        See parent
        """
        topic_list = None
        if topic is None:
            raise ValueError("Invalid topic.")
        if isinstance(topic, str):
            if len(topic) == 0:
                raise ValueError("Invalid topic.")
            topic_list = [topic.encode("utf-8")]
        elif isinstance(topic, list):
            topic_list = []
            for t in topic:
                if len(t) == 0 or not isinstance(t, str):
                    raise ValueError("Invalid topic.")
                topic_list.append(t.encode("utf-8"))

        if topic_list is None:
            raise ValueError("No topic specified, or incorrect topic type.")

        if self._sock is None:
            return MQTT_ERR_NO_CONN, None

        return self._send_unsubscribe(False, topic_list, mid)
