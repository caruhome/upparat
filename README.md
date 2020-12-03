# Upparat

![Build Status](https://github.com/caruhome/upparat/workflows/Unittests/badge.svg)

```
         __    Hi, I'm Upparat!
 _(\    |@@| /
(__/\__ \--/ __
   \___|----|  |   __
       \ }{ /\ )_ / _\
       /\__/\ \__O (__
      (--/\--)    \__/
      _)(  )(_
     `---''---`
```

The _Upparat_ is a secure and robust service that runs on your
IoT device to download and install files such as firmware updates.

[Several hooks](./docs/README.md#hooks) provide a seamless integration in your device environment and allow you
to use any software update tool such as [RAUC](https://github.com/rauc/rauc),
[SWUpdate](https://github.com/sbabic/swupdate) or a custom solution.

_Upparat_ subscribes to [AWS Iot Jobs](https://docs.aws.amazon.com/en_pv/iot/latest/developerguide/iot-jobs.html),
downloads and verifies the specified file and runs an installation command of your
choice. It handles all the nitty gritty details such as cancelled jobs,
failed downloads and progress updates.

## Installation

```
pip install upparat
```

## Getting started

- [Checkout the examples](./misc/examples/README.md)
- [Checkout the documentation](./docs/README.md)

## Development

- Create a virtualenv:

  ```
  python3 -m venv .venv
  . .venv/bin/activate
  pip3 install --upgrade pip setuptools wheel
  ```

- Install Upparat in editable mode with development and optional dependencies:

  ```
  pip install -e ".[dev,sentry]"
  ```

#### Pre-commit hooks

- Install the [pre-commit framework](https://pre-commit.com/#install).

- Install the pre-commit hooks:
  ```
  pre-commit install --install-hooks
  ```

#### Unittests & Formatter

```bash
docker-compose run test
docker-compose run format
```

#### Statemachine

- See [visual representation](https://github.com/caruhome/upparat/blob/master/docs/statemachine/statemachine.png) of the internal statemachine.
