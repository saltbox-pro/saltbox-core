# Copyright 2025 Alexey Baikov, Anton Karmanov

# Licensed under the Apache License, Version 2.0.
# See LICENSE.txt file in the project root for license information.

# This file is a part of Salt.Box system.


FROM registry.altlinux.org/alt/alt:p11 AS base
LABEL version='1.3'
EXPOSE 8000

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

COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/

RUN mkdir --parents /var/lib/saltbox-core/

ENV BASE_URL_ROOT_PATH=/
ENV TIMEOUT_GRACEFUL_SHUTDOWN=5
ENV KEYCLOAK_CLIENT_SECRET_FILE=/run/secrets/keycloak_client_saltbox_core_password

ENV MONGO_USER=
ENV MONGO_USER_PASSWORD_FILE=
ENV REDIS_TASKIQ_DB=0
ENV REDIS_TASKIQ_HOST=
ENV REDIS_TASKIQ_PASSWORD_SECRET=/run/secrets/redis_taskiq_password
ENV REDIS_TASKIQ_PORT=6379
ENV REDIS_TASKIQ_USERNAME=
ENV REDIS_USER_PASSWORD_FILE=

WORKDIR /
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]


###############
## Dev image ##
###############

FROM base AS dev
LABEL name='saltbox-core-dev' version='1.4'
# Install Core as an editable package
RUN \
  --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
<<EOF
set -e
mkdir --parents /var/cache/apt/archives/partial/ /var/lib/apt/lists/partial/
apt-get update
apt-get install -y ipython3 uv
EOF
WORKDIR /mnt/saltbox-core/
ENV DEV_MODE=1
# User should mount respective repositories to run the image
VOLUME /mnt/saltbox-core/
VOLUME /mnt/saltbox-bridge-messages/
ENV SALTBOX_BRIDGE_MESSAGES_SRC_PATH /mnt/saltbox-bridge-messages/
VOLUME /mnt/saltbox-sdk/
ENV SALTBOX_SDK_SRC_PATH /mnt/saltbox-sdk/
RUN git config --global --add safe.directory '/mnt/*'


################
## Main image ##
################

FROM base AS main
LABEL name='saltbox-core' version='1.3'
# Install Core as a normal package
RUN \
  --mount=type=bind,target=/mnt/saltbox-core/,readwrite \
  --mount=type=cache,target=/root/.cache/pip/ \
  pip3 install /mnt/saltbox-core/
