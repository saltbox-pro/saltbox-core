# Copyright 2025 Alexey Baikov, Anton Karmanov

# Licensed under the Apache License, Version 2.0.
# See LICENSE.txt file in the project root for license information.

# This file is a part of Salt.Box system.

ARG BASE_IMAGE="registry.altlinux.org/alt/alt:p11"
FROM "$BASE_IMAGE" AS python
LABEL version='1.0'

RUN \
  --mount=type=cache,target=/var/cache/apt,sharing=locked,id=apt \
  --mount=type=cache,target=/var/lib/apt/lists,sharing=locked,id=apt-lists \
<<EOF
set -e
mkdir --parents /var/cache/apt/archives/partial/ /var/lib/apt/lists/partial/
apt-get update
apt-get install --yes glibc-pthread python3 git
EOF


FROM python AS uv
LABEL version='1.0'

RUN \
  --mount=type=cache,target=/var/cache/apt,sharing=locked,id=apt \
  --mount=type=cache,target=/var/lib/apt/lists,sharing=locked,id=apt-lists \
<<EOF
set -e
mkdir --parents /var/cache/apt/archives/partial/ /var/lib/apt/lists/partial/
apt-get update
apt-get install --yes uv
EOF


FROM uv AS venv
LABEL version='2.0'

WORKDIR /srv/saltbox-core/
COPY . /srv/saltbox-core/
ARG UV_CACHE_DIR=/root/.cache/uv/
RUN --mount=type=cache,target="$UV_CACHE_DIR",id=uv \
  uv sync \
    --python=/usr/bin/python3 \
    --no-dev \
    --no-sources \
    --no-editable \
  ;


FROM python AS prod
LABEL name='saltbox-core' version='2.0'

ENV CORE_VENV='/srv/saltbox-core/.venv'
ENV PATH="${CORE_VENV}/bin:${PATH}"
COPY --from=venv /srv/saltbox-core/.venv "$CORE_VENV"
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
ENV TASKIQ_WORKERS=3

WORKDIR /
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
EXPOSE 8000


# TODO Fix dev mode
FROM prod AS dev
LABEL name='saltbox-core-dev' version='2.0'
RUN \
  --mount=type=cache,target=/var/cache/apt,sharing=locked,id=apt \
  --mount=type=cache,target=/var/lib/apt/lists,sharing=locked,id=apt-lists \
<<EOF
set -e
mkdir --parents /var/cache/apt/archives/partial/ /var/lib/apt/lists/partial/
apt-get update
apt-get install --yes uv
EOF
WORKDIR /mnt/saltbox-core/
ENV DEV_MODE=1
# User MUST mount respective repositories to run the image
VOLUME /mnt/saltbox-core/
VOLUME /mnt/saltbox-bridge-messages/
ENV SALTBOX_BRIDGE_MESSAGES_SRC_PATH /mnt/saltbox-bridge-messages/
VOLUME /mnt/saltbox-sdk/
ENV SALTBOX_SDK_SRC_PATH /mnt/saltbox-sdk/
RUN git config --global --add safe.directory '/mnt/*'
