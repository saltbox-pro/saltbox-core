ARG PYTHON_VERSION='3.12'

FROM python:${PYTHON_VERSION}-alpine AS builder
LABEL name='fastms-core' version='0.1'

ENV SALT_USERNAME="salt_api_user"

WORKDIR /srv/fastms-core/

COPY requirements.txt app ./
RUN pip install --no-cache-dir --upgrade --requirement requirements.txt
RUN echo "SALT_PASSWORD='$(tr -dc A-Za-z0-9 </dev/urandom | head -c 32)'" >> .env
CMD ["uvicorn", "app.main:APP", "--host", "0.0.0.0", "--port", "8000"]

EXPOSE 8000
