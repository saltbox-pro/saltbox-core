FROM registry.altlinux.org/alt/alt:p11
LABEL version='0.2' name='SaltBox tests'
# Change release to trigger build
LABEL release='0'

RUN \
  --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
<<EOF
set -e
mkdir --parents /var/cache/apt/archives/partial/ /var/lib/apt/lists/partial/
apt-get update
apt-get install -y \
  pytest3 \
  python3-module-httpx \
  python3-module-pydantic \
  python3-module-pytest \
  python3-module-pytest-asyncio \
  python3-module-pytest-timeout\
  python3-module-python-dotenv \
  python3-module-redis \
  python3-module-websockets \
;
EOF

COPY . /root/autotests/
WORKDIR /root/autotests/
RUN <<EOF
set -e
mv docker/entrypoint.sh /usr/local/bin/
chmod 755 /usr/local/bin/entrypoint.sh
rm -r docker/
ln --symbolic --force /usr/bin/pytest3 /usr/local/bin/pytest
EOF


ENV RESOURCE_URL=http://proxy/api/core
ENV RESOURCE_WS_URL=ws://proxy/api/core
ENV LOGGING=True
ENV USE_BASIC_AUTH=False
ENV BASIC_AUTH_LOGIN=
ENV BASIC_AUTH_PASSWORD=
ENV REDIS_HOST=redis-salt
ENV REDIS_PORT=6379
ENV REDIS_DB=0
ENV REDIS_USERNAME=redis
ENV REDIS_PASSWORD_FILE=
ENV USER_NAME=user
ENV USER_PASSWORD_FILE=
ENV CLIENT_SECRET_FILE=
ENV GET_TOKEN_ENDPOINT=


ENTRYPOINT ["entrypoint.sh", "pytest3"]
CMD ["--verbose", "--capture=no"]
