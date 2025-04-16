FROM registry.altlinux.org/alt/alt:p11 AS base
LABEL version='1.0'
EXPOSE 8000

## TODO
## Requirements related packages
#RUN \
#  --mount=type=cache,target=/var/cache/apt,sharing=locked \
#  --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
#<<EOF
#set -e
#mkdir --parents /var/cache/apt/archives/partial/ /var/lib/apt/lists/partial/
#apt-get update
#apt-get install -y \
#  python3-module-fastapi \
#  python3-module-httpx \
#  python3-module-motor \
#  python3-module-pydantic \
#  python3-module-pydantic-settings \
#  python3-module-pyjwt \
#  python3-module-python-multipart \
#  python3-module-redis \
#  python3-module-uvicorn \
#  python3-module-websockets \
#;
#EOF

RUN \
  --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
<<EOF
set -e
mkdir --parents /var/cache/apt/archives/partial/ /var/lib/apt/lists/partial/
apt-get update
apt-get install -y glibc-pthread python3-module-pip git
EOF

## Outer dependencies
## Install modules which are missing or have incompatible version in the dist repo
RUN \
  --mount=type=bind,source=requirements.txt,target=/mnt/requirements.txt\
  --mount=type=cache,target=/root/.cache/pip/ \
  pip3 install --requirement /mnt/requirements.txt

## Uncomment to debug Python dependencies with pipdeptree
# FIXME
RUN --mount=type=cache,target=/root/.cache/pip/ pip3 install pipdeptree==2.23.1

COPY --chmod=644 docker/shell_init.sh /etc/
COPY --chmod=755 \
  docker/entrypoint.sh \
  docker/uvicorn.sh \
  docker/taskiq-worker.sh \
  docker/taskiq-scheduler.sh \
  /usr/local/bin/

ENV BASE_URL_ROOT_PATH=/
ENV TIMEOUT_GRACEFUL_SHUTDOWN=5

ENV REDIS_TASKIQ_PASSWORD_SECRET=/run/secrets/redis_taskiq_password
ENV REDIS_TASKIQ_USERNAME=
ENV REDIS_TASKIQ_HOST=
ENV REDIS_TASKIQ_PORT=6379
ENV REDIS_TASKIQ_DB=0

WORKDIR /
ENTRYPOINT ["/usr/local/bin/uvicorn.sh"]


################
## Dev image ##
################

## Mount Core repository dir to /mnt/salt_box_core to serve with the container.

FROM base AS dev
LABEL name='saltbox-core-dev' version='1.1'
# Install Core as editable package
WORKDIR /mnt/salt_box_core/
VOLUME /mnt/salt_box_core/
RUN \
  --mount=type=bind,target=/mnt/salt_box_core/,readwrite \
  pip3 install --no-deps --editable .[dev]
CMD ["dev"]


################
## Main image ##
################

FROM base AS main
LABEL name='saltbox-core' version='1.1'
# Install Core as usual package
RUN \
  --mount=type=bind,target=/mnt/salt_box_core/,readwrite \
  --mount=type=cache,target=/root/.cache/pip/ \
  pip3 install --no-deps /mnt/salt_box_core/
CMD ["start"]
