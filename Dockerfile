# Copyright 2025-2026 Alexey Baikov, Anton Karmanov

# Licensed under the Apache License, Version 2.0.
# See LICENSE.txt file in the project root for license information.

# This file is a part of Salt.Box system.

ARG BASE_IMAGE="registry.altlinux.org/alt/alt:p11"
FROM "$BASE_IMAGE" AS base
RUN \
  --mount=type=cache,target=/var/cache/apt,sharing=locked,id=apt \
  --mount=type=cache,target=/var/lib/apt/lists,sharing=locked,id=apt-lists \
<<EOF
set -e
mkdir --parents /var/cache/apt/archives/partial/ /var/lib/apt/lists/partial/
apt-get update
apt-get install --yes glibc-pthread python3 git
EOF
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/
RUN mkdir --parents /var/lib/saltbox-core/
ENV DEV_MODE=0
ENV KEYCLOAK_CLIENT_SECRET_FILE=/run/secrets/keycloak_client_saltbox_core_password
ENV REDIS_TASKIQ_SECRET_FILE=/run/secrets/redis_taskiq_password
ENV TASKIQ_WORKERS=3
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
EXPOSE 8000


FROM base AS uv
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


FROM base AS prod
ENV VENV_PATH='/srv/saltbox-core/.venv'
ENV CORE_PATH='/srv/saltbox-core/.venv/lib/python3/site-packages'
ENV PATH="${VENV_PATH}/bin:${PATH}"
COPY --from=venv /srv/saltbox-core/.venv "$VENV_PATH"


FROM uv AS dev
ENV CORE_PATH='/mnt/saltbox-core/'
WORKDIR "$CORE_PATH"
ENV DEV_MODE=1
# User MUST mount respective repositories to run the image
VOLUME /mnt/saltbox-core/
VOLUME /mnt/saltbox-bridge-messages/
ENV SALTBOX_BRIDGE_MESSAGES_SRC_PATH /mnt/saltbox-bridge-messages/
VOLUME /mnt/saltbox-sdk/
ENV SALTBOX_SDK_SRC_PATH /mnt/saltbox-sdk/
RUN git config --global --add safe.directory '/mnt/*'
