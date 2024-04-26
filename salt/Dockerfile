ARG ALPINE_VERSION
ARG PYTHON_VERSION

FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS salt-base

ARG ALPINE_VERSION
ARG SALT_VERSION

RUN apk add --no-cache gcc g++ autoconf make libffi-dev openssl-dev dumb-init libgit2 libgit2-dev

RUN addgroup -g 450 -S salt && adduser -s /bin/sh -SD -G salt salt && \
    mkdir -p /etc/pki /etc/salt/pki /etc/salt/minion.d/ /etc/salt/master.d \
             /etc/salt/proxy.d /var/cache/salt /var/log/salt /var/run/salt  && \
    chmod -R 2775 /etc/pki /etc/salt /var/cache/salt /var/log/salt /var/run/salt && \
    chgrp -R salt /etc/pki /etc/salt /var/cache/salt /var/log/salt /var/run/salt

ENTRYPOINT ["/usr/bin/dumb-init"]
CMD ["/usr/local/bin/saltinit"]
ADD saltinit.py /usr/local/bin/saltinit
VOLUME /etc/salt/

RUN echo "cython<3" > /tmp/constraint.txt
RUN pip3 install --upgrade pip
RUN PIP_CONSTRAINT=/tmp/constraint.txt USE_STATIC_REQUIREMENTS=1 \
    pip3 install --no-build-isolation --no-cache-dir \
    salt=="${SALT_VERSION}" "$(if [ "${ALPINE_VERSION}" = "3.14" ]; \
    then echo 'pygit2<1.7'; else echo 'pygit2<1.12'; fi)"
RUN su - salt -c 'salt-run salt.cmd tls.create_self_signed_cert'


FROM salt-base AS salt-master
ADD master.yaml /etc/salt/master.d/master.conf
ADD api.yaml /etc/salt/master.d/api.conf
RUN mkdir -p /srv/salt_extmod/engines
ADD redis_bridge.py /srv/salt_extmod/engines/redis_bridge.py
COPY ./requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --upgrade -r /tmp/requirements.txt
EXPOSE 4505 4506 8000

FROM salt-base AS salt-minion
ADD ./minion.yaml /etc/salt/minion.d/minion.conf
