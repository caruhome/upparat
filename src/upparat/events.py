# State machine events
ENTER = "enter"
EXIT = "exit"

NO_JOBS_PENDING = "no-jobs-pending"
JOBS_AVAILABLE = "jobs-available"
JOB_SELECTED = "job-selected"
JOB_INSTALLATION_DONE = "job-installation-done"
JOB_INSTALLATION_COMPLETE = "job-installation-complete"
JOB_VERIFIED = "job-verified"
JOB_REVOKED = "job-revoked"

SELECT_JOB_INTERRUPTED = "selected-job-interrupted"

DOWNLOAD_COMPLETED = "download-completed"
DOWNLOAD_INTERRUPTED = "download-interrupted"

INSTALLATION_DONE = "installation-done"
INSTALLATION_INTERRUPTED = "installation-interrupted"

RESTART_INTERRUPTED = "restart-interrupted"

# State machine event data
JOB_EXECUTION_SUMMARIES = "job_execution_summaries"
JOB_EXECUTION_SUMMARIES_PROGRESS = "progress"
JOB_EXECUTION_SUMMARIES_QUEUED = "queued"
JOB = "job"

# MQTT
MQTT_MESSAGE_RECEIVED = "mqtt-message-received"
MQTT_SUBSCRIBED = "mqtt-subscribed"
MQTT_UNSUBSCRIBED = "mqtt-unsubscribed"

# MQTT event data
MQTT_EVENT_TOPIC = "topic"
MQTT_EVENT_PAYLOAD = "payload"

# Service
EXIT_SIGNAL_SENT = "exit-signal"

# Hooks
HOOK = "hook"
HOOK_COMMAND = "hook-command"
HOOK_STATUS = "hook-status"
HOOK_MESSAGE = "hook-message"

HOOK_STATUS_COMPLETED = "hook-completed"
HOOK_STATUS_OUTPUT = "hook-output"
HOOK_STATUS_TIMED_OUT = "hook-timed-out"
HOOK_STATUS_FAILED = "hook-failed"
