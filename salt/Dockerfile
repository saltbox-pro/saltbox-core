ARG ALPINE_VERSION
ARG PYTHON_VERSION

FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS salt-base

ARG ALPINE_VERSION
ARG SALT_VERSION

ARG BUILD_DEPS="gcc g++ autoconf make libffi-dev libgit2-dev"

RUN \
    apk add --no-cache binutils libgit2 libffi openssl-dev && \
    addgroup -g 450 -S salt && adduser -s /bin/sh -SD -G salt salt && \
    mkdir -p /etc/pki /etc/salt/pki /etc/salt/minion.d/ /etc/salt/master.d \
        /etc/salt/proxy.d /var/cache/salt /var/log/salt /var/run/salt && \
    chmod -R 2775 /etc/pki /etc/salt /var/cache/salt /var/log/salt /var/run/salt && \
    chgrp -R salt /etc/pki /etc/salt /var/cache/salt /var/log/salt /var/run/salt

VOLUME /etc/salt/

RUN \
    echo "cython<3" > /tmp/constraint.txt && \
    apk add --no-cache $BUILD_DEPS && \
    PIP_CONSTRAINT=/tmp/constraint.txt USE_STATIC_REQUIREMENTS=1 \
        pip3 install --no-build-isolation --no-cache-dir \
        pyOpenSSL \
        salt=="${SALT_VERSION}" "$(if [ "${ALPINE_VERSION}" = "3.14" ]; \
        then echo 'pygit2<1.7'; else echo 'pygit2<1.12'; fi)" && \
    apk del $BUILD_DEPS && \
    su - salt -c 'salt-run salt.cmd tls.create_self_signed_cert'

FROM salt-base AS salt-master
COPY master.yaml /etc/salt/master.d/master.conf
COPY api.yaml /etc/salt/master.d/api.conf
COPY netapi.yaml /etc/salt/master.d/netapi.conf
COPY redis_bridge.py /srv/salt_extmod/engines/redis_bridge.py
COPY ./requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --upgrade -r /tmp/requirements.txt
EXPOSE 4505 4506 8000
COPY saltinit.py /usr/local/bin/saltinit
CMD ["/usr/local/bin/saltinit"]

FROM salt-base AS salt-minion
COPY ./minion.yaml /etc/salt/minion.d/minion.conf
# TODO Try to replace with supervisord
CMD ["/usr/local/bin/salt-minion"]
