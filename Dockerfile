ARG PYTHON_VERSION='3.12'

FROM python:${PYTHON_VERSION}-alpine AS base
LABEL name='fastms-core' version='0.8'
ENV SALT_USERNAME="fastms_core"
EXPOSE 8000

RUN \
  --mount=type=bind,source=requirements.txt,target=/mnt/requirements.txt,readwrite \
  --mount=type=cache,target=/root/.cache/pip/ \
  pip3 install --upgrade --requirement /mnt/requirements.txt
COPY docker/entrypoint.sh /usr/local/bin/

ENV BASE_URL_ROOT_PATH=/
ENV TIMEOUT_GRACEFUL_SHUTDOWN=5
ENV SALT_EAUTH=file

WORKDIR /
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]


################
## Main image ##
################

FROM base AS main
# Install Core as usual package
RUN \
  --mount=type=bind,target=/mnt/fastms_core/,readwrite \
  --mount=type=cache,target=/root/.cache/pip/ \
  pip3 install --no-deps /mnt/fastms_core/
CMD ["start"]


################
## Dev image ##
################

## Mount Core repository dir to /mnt/fastms_core to serve with the container.

FROM base AS dev
# Install Core as editable package
WORKDIR /mnt/fastms_core/
VOLUME /mnt/fastms_core/
RUN \
  --mount=type=bind,target=/mnt/fastms_core/,readwrite \
  pip3 install --no-deps --editable .
CMD ["dev"]
