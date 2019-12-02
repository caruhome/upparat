# Upparat

The _Upparat_ is a secure and robust service that runs on your
IoT device to download and install files such as firmware updates.

## How it works

The _Upparat_ subscribes to [AWS Iot Jobs](https://docs.aws.amazon.com/en_pv/iot/latest/developerguide/iot-jobs.html),
downloads and verifies the specified file and runs an installation command of your
choice. It handles all the nitty gritty details such as cancelled jobs,
failed downloads or progress updates.

Several hooks provide a seamless integration in your device environment and allow you
to use any software update tool such as [RAUC](https://github.com/rauc/rauc),
[SWUpdate](https://github.com/sbabic/swupdate) or custom solutions.

## Quickstart

### Installation
TDB

### AWS Setup
- Create an AWS Iot Thing in the console and download the certificates
- Create policy
- Create S3 bucket and upload a test file
- Create IAM role

TBD

### Configuration
```ini
[service]
sentry = <SENTRY_DNS>

# Default: WARNING
log_level = <DEBUG|INFO|WARNING|ERROR|EXCEPTION>

# Default: tmpdir
download_location = <path>

[broker]
# Default: 127.0.0.1
host = <host>

# Default: 1883
port = <port>

# Default: hostname
thing_name = <AWS thing name>

# Default: upparat
client_id = <Local client id>

# Default: false
ssl = <true|false>

cafile = <>
certfile = <>
keyfile = <>


[hooks]
version = <returns the currently installed version>
download = <checks if allowed to download>
ready = <checks if your system is ready/stable>
install = <installs the file>
restart = <restarts your device/service>

# Default: 60
retry_interval = <retry in seconds>

# Default: 60
max_retries = <>
```

### Start
`upparat -v -c <config>`

### Update
Create a job in the AWS Iot Console.

```json
{
    "version": "<test file version>",
    "file": "${aws:iot:s3-presigned-url:https://s3.<test file location>}",
    "meta": "<will be passed as an argument to your commands>",
    "force": false
}
```


## Development
- Create a virtualenv:
  ```
  python3 -m venv .venv
  . .venv/bin/activate
  ```

- Install Upparat in editable mode with development and optional sentry dependencies:
  ```
  pip install -e ".[dev,sentry]"
  ```

- Install the pre-commit framework.

- Install the pre-commit hooks:
  ```
  pre-commit install --install-hooks
  ```

### Tests

- `docker-compose run test`
