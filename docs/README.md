## Configuration Options

The following configuration options exist
(for a minimal configuration file consult the examples).

```ini
[service]
sentry_dsn = <sentry DSN>

# Default: WARNING
log_level = <DEBUG|INFO|WARNING|ERROR|EXCEPTION>

# Default: tmpdir
download_location = <path>

[broker]
# MQTT broker host / port
host = <host>
port = <port>

# Default: hostname
thing_name = <AWS thing name>

# Default: upparat
client_id = <local client id>

# Optional for client certifacte authentication
cafile = <Amazon root certificate>
certfile = <client certificate>
keyfile = <client priviate key>

[hooks]
# Used to compare against jobDoucment.version
version = <returns the currently installed version>
download = <checks if allowed to download>
install = <installs the downloaded file>
restart = <restarts your device/service>
ready = <checks if your system is stable / update succeeded>

# Hooks can return a status code 3 to indicate
# a retry at later time after retry_interval.
# Default: 60
retry_interval = <retry in seconds>

# Default: 60
# See retry_interval if hook has reached
# max_retries the job will be set to failed
max_retries = <max_retries>
```

## Hooks

Hooks provide a way to integrate Upparat with any update system (i.e. RAUC, swupdate, etc.).

For a minimal setup you need to provide the following hooks:

- `install`: Handle the installation of the downloaded file.
- `reboot`: Handle the reboot of the device / service.

### List of all hooks with examples for RAUC

#### `version`

Return the currently installed version. Used to compare
with the provided version in the job, if equal update
is not considered necessary. Optional, if not specified
installation will always be executed.

```
#!/usr/bin/env bash
# $1: time elapsed since first call
# $2: retry count
# $3: meta from job document

# Gets the system version
cat /etc/bundle-version
```

#### `install`

Handle the installation of the downloaded file (`$4`).

```
#!/usr/bin/env bash
# $1: time elapsed since first call
# $2: retry count
# $3: meta from job document
# $4: file location

# Example of the retry mechanism:
# Only install if a certain lock file is not present
if test -f /tmp/critical.lock; then
    exit 3
else
   rauc install $4
fi
```

#### `download`

## Start

`upparat -v -c <config>`

## Systemd service & integration:

```
[Unit]
Description=Upparat AWS IoT file installer
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/upparat -c /etc/upparat/upparat.conf
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal

Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## More Tooling

- [Upparat Job Creator](../misc/scripts/README.md)

## Statemachine

![statemachine](./statemachine/statemachine.png)
