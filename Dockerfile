ARG PYTHON_VERSION='3.12'

FROM python:${PYTHON_VERSION}-alpine AS base
LABEL version='0.13'
ENV SALT_USERNAME="salt_box_core"
EXPOSE 8000

RUN \
  --mount=type=bind,source=requirements.txt,target=/mnt/requirements.txt\
  --mount=type=cache,target=/root/.cache/pip/ \
  pip3 install --upgrade --requirement /mnt/requirements.txt
COPY --chmod=644 docker/shell_init.sh /etc/
COPY --chmod=755 \
  docker/celery-beat.sh \
  docker/celery-worker.sh \
  docker/entrypoint.sh \
  docker/uvicorn.sh \
  /usr/local/bin/

ENV BASE_URL_ROOT_PATH=/
ENV TIMEOUT_GRACEFUL_SHUTDOWN=5
ENV SALT_EAUTH=file

ENV REDIS_CELERY_PASSWORD_SECRET=/run/secrets/redis_celery_password
ENV REDIS_CELERY_USERNAME=
ENV REDIS_CELERY_HOST=redis
ENV REDIS_CELERY_PORT=6379
ENV REDIS_CELERY_DB=0

WORKDIR /
ENTRYPOINT ["/usr/local/bin/uvicorn.sh"]


################
## Dev image ##
################

## Mount Core repository dir to /mnt/salt_box_core to serve with the container.

FROM base AS dev
LABEL name='salt-box-core-dev' version='0.12'
# Install Core as editable package
WORKDIR /mnt/salt_box_core/
VOLUME /mnt/salt_box_core/
RUN \
  --mount=type=bind,target=/mnt/salt_box_core/,readwrite \
  pip3 install --no-deps --editable .
CMD ["dev"]


################
## Main image ##
################

FROM base AS main
LABEL name='salt-box-core' version='0.11'
# Install Core as usual package
RUN \
  --mount=type=bind,target=/mnt/salt_box_core/,readwrite \
  --mount=type=cache,target=/root/.cache/pip/ \
  pip3 install --no-deps /mnt/salt_box_core/
CMD ["start"]
