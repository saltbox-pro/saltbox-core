ARG PYTHON_VERSION='3.12'

FROM python:${PYTHON_VERSION}-alpine
LABEL name='fastms-core' version='0.3'
ENV SALT_USERNAME="salt_api_user"
EXPOSE 8000

RUN \
  --mount=type=bind,source=requirements.txt,target=/mnt/requirements.txt,readwrite \
  --mount=type=cache,target=/root/.cache/pip/ \
  pip3 install --upgrade --requirement /mnt/requirements.txt
RUN \
  --mount=type=bind,target=/mnt/fastms_core/,readwrite \
  --mount=type=cache,target=/root/.cache/pip/ \
  pip3 install --no-deps /mnt/fastms_core/
RUN <<EOF
set -e
PASSWORD="$(tr -dc A-Za-z0-9 </dev/urandom | head -c 32)"
mkdir -p /etc/fastms/
echo "SALT_PASSWORD='${PASSWORD}'" >> /etc/fastms/core.env
EOF

CMD [\
  "uvicorn",\
  "fastms_core.main:APP",\
  "--env-file=/etc/fastms/core.env",\
  "--host=0.0.0.0",\
  "--port=8000",\
  "--timeout-graceful-shutdown=5"\
]
