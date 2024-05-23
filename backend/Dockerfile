ARG PYTHON_VERSION

FROM python:${PYTHON_VERSION}-alpine AS builder
ENV SALT_USERNAME="salt_api_user"

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY ./app /code/app
RUN \
  echo "SALT_PASSWORD='$(tr -dc A-Za-z0-9 </dev/urandom | head -c 32)'" > \
    /code/.env
CMD ["uvicorn", "app.main:APP", "--host", "0.0.0.0", "--port", "8000"]
