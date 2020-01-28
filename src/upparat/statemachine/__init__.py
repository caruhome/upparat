import json
import logging
import sys

from paho.mqtt.client import topic_matches_sub
from pysm import State
from pysm import StateMachine

from upparat.config import NAME
from upparat.config import settings
from upparat.events import ENTER
from upparat.events import EXIT
from upparat.events import EXIT_SIGNAL_SENT
from upparat.events import JOB
from upparat.events import MQTT_EVENT_PAYLOAD
from upparat.events import MQTT_EVENT_TOPIC
from upparat.events import MQTT_MESSAGE_RECEIVED
from upparat.jobs import get_in_progress_job_ids
from upparat.jobs import job_update
from upparat.jobs import JobStatus
from upparat.jobs import pending_jobs_response
from upparat.mqtt import MQTT

logger = logging.getLogger(__name__)


class UpparatStateMachine(StateMachine):
    def __init__(self, inbox, mqtt_client):
        self.inbox = inbox
        self.mqtt_client = mqtt_client
        super().__init__(NAME)

    def dispatch(self, event):
        state_before = self.state
        super().dispatch(event)
        state_after = self.state

        if state_after != state_before:
            logger.info(
                f"State changed from {state_before.name} to {state_after.name}."
            )

    def print_uml(self):
        """
        todo: Extract to a dev/test only function. No need to be included in production.
        :return:
        """
        print("@startuml")
        for state in self.states:
            if state.initial:
                print("[*] --> " + state.name)
            print("state " + state.name)

        for key, values in self._transitions._transitions.items():
            event = key[1]
            for value in values:
                from_state = value["from_state"].name
                to_state = value["to_state"].name
                condition = (
                    " [" + value["condition"].__name__ + "]"
                    if value["condition"].__name__ != "_nop"
                    else ""
                )
                action = (
                    " / " + value["action"].__name__ + "()"
                    if value["action"].__name__ != "_nop"
                    else ""
                )
                print(f"    {from_state} --> {to_state}: {event}{condition}{action}")

        print("@enduml")


class BaseState(State):
    def __init__(self):
        super().__init__(self.name)

    def on_enter(self, state, event):
        pass

    def on_exit(self, state, event):
        pass

    def on_exit_signal(self, state, event):
        logger.info("Shutting down...")
        self.mqtt_client.disconnect()
        sys.exit()

    def register_handlers(self):
        self.handlers = {
            ENTER: self.on_enter,
            EXIT: self.on_exit,
            EXIT_SIGNAL_SENT: self.on_exit_signal,
        }

        self.handlers.update(self.event_handlers())

    def event_handlers(self):
        return {}

    @property
    def root_machine(self):
        """Get the root state machine in a states hierarchy.

        :returns: Root state in the states hierarchy
        :rtype: |StateMachine|

        """
        machine = self
        while machine.parent:
            machine = machine.parent
        return machine

    @property
    def mqtt_client(self) -> MQTT:
        return self.root_machine.mqtt_client

    def publish(self, event):
        self.root_machine.inbox.put(event)


class JobProcessingState(BaseState):
    job = None
    pending_jobs_response = None

    def job_succeeded(self, state, message=None):
        job_update(
            self.mqtt_client,
            settings.broker.thing_name,
            self.job.id_,
            JobStatus.SUCCEEDED.value,
            state,
            message,
        )

    def job_failed(self, state, message=None):
        job_update(
            self.mqtt_client,
            settings.broker.thing_name,
            self.job.id_,
            JobStatus.FAILED.value,
            state,
            message,
        )

    def job_progress(self, state, message=None):
        job_update(
            self.mqtt_client,
            settings.broker.thing_name,
            self.job.id_,
            JobStatus.IN_PROGRESS.value,
            state,
            message,
        )

    def _setup_job_processing(self, state, event):
        self.job = event.cargo["source_event"].cargo[JOB]

        # Watch for job updates → canceled
        self.pending_jobs_response = pending_jobs_response(settings.broker.thing_name)
        self.mqtt_client.subscribe(self.pending_jobs_response, qos=1)

        self.on_enter(state, event)

    def _cleanup_job_processing(self, state, event):
        self.mqtt_client.unsubscribe(self.pending_jobs_response)
        self.on_exit(state, event)

    def _handle_job_cancel(self, state, event, mqtt_message_handler=None):
        topic = event.cargo[MQTT_EVENT_TOPIC]

        # if our job is not in progress anymore it has been
        # canceled / deleted and we should stop now.
        if topic_matches_sub(self.pending_jobs_response, topic):
            payload = json.loads(event.cargo[MQTT_EVENT_PAYLOAD])

            if self.job.id_ not in get_in_progress_job_ids(payload):
                logger.info(f"Job {self.job.id_} got canceled.")
                return self.on_job_cancelled(state, event)

        if mqtt_message_handler:
            mqtt_message_handler(state, event)

    def on_job_cancelled(self, state, event):
        pass

    def register_handlers(self):
        self.handlers = {
            ENTER: self._setup_job_processing,
            EXIT: self._cleanup_job_processing,
            EXIT_SIGNAL_SENT: self.on_exit_signal,
            MQTT_MESSAGE_RECEIVED: self._handle_job_cancel,
        }

        event_handlers = self.event_handlers()

        # Wrap the original MQTT_MESSAGE_RECEIVED handler
        if MQTT_MESSAGE_RECEIVED in event_handlers:

            def _wrapper(state, event):
                return self._handle_job_cancel(
                    state, event, event_handlers[MQTT_MESSAGE_RECEIVED]
                )

            event_handlers[MQTT_MESSAGE_RECEIVED] = _wrapper

        self.handlers.update(event_handlers)
