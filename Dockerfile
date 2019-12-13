FROM python:3.8.0-alpine as builder
WORKDIR /app/upparat

RUN apk add --no-cache bash

COPY ./src ./src
COPY ./setup.py ./setup.py
COPY ./setup.cfg ./setup.cfg

RUN pip install -e ".[dev,sentry]"

ENTRYPOINT ["upparat"]
