ARG PYTHON_VERSION='3.12'

FROM python:${PYTHON_VERSION}-alpine
LABEL name='fastms-core' version='0.7'
ENV SALT_USERNAME="fastms_core"
EXPOSE 8000

RUN \
  --mount=type=bind,source=requirements.txt,target=/mnt/requirements.txt,readwrite \
  --mount=type=cache,target=/root/.cache/pip/ \
  pip3 install --upgrade --requirement /mnt/requirements.txt
RUN \
  --mount=type=bind,target=/mnt/fastms_core/,readwrite \
  --mount=type=cache,target=/root/.cache/pip/ \
  pip3 install --no-deps /mnt/fastms_core/

ENV ROOT_PATH=/
ENV TIMEOUT_GRACEFUL_SHUTDOWN=5
ENV SALT_EAUTH=file
CMD \
  SALT_PASSWORD=$(cat /run/secrets/salt_api_password) \
  MONGO_PASSWORD=$(cat /run/secrets/mongo_admin_password) \
  uvicorn fastms_core.main:APP \
  --host=0.0.0.0\
  "--root-path=${ROOT_PATH}"\
  --port=8000\
  "--timeout-graceful-shutdown=${TIMEOUT_GRACEFUL_SHUTDOWN}"
