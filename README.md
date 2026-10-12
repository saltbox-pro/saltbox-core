<div align = right>

&ensp;[<kbd> <br> EN <br> </kbd>](./README.md)&ensp;
&ensp;[<kbd> <br> RU <br> </kbd>](./README_RU.md)&ensp;

</div>

---

# Salt.Box Core

## Table of Contents

- **[About](#about)**
- **[Project layout](#project-layout)**
- **[Processes](#processes)**
- **[Development](#development)**
  - [Environment](#environment)
  - [Verifying your setup](#verifying-your-setup)
  - [Testing](#testing)
  - [Run](#run)


## About

**Salt.Box Core** is the main [FastAPI](https://fastapi.tiangolo.com/) backend
of Salt.Box. It stores the system's own domain data in MongoDB, jobs, tasks,
task templates, minion collections, pillars and masters, and drives Salt
itself through the Salt event bus to run those jobs and collect their
results.

To consult the SLS package format look at [`sls_package.md`](./sls_package.md).

For a description of common inner flows consult
[`common_flows.md`](./common_flows.md).

## Project layout

The domain packages under [`saltbox_core/`](./saltbox_core) follow the same
layering: `routers` expose the FastAPI endpoints, `services` hold the
business logic, `repositories` talk to MongoDB, `schemas` define the
pydantic request/response models, and `migrations` hold data migrations for
that domain.

- [`jobs`](./saltbox_core/jobs) – individual Salt job runs and their returns
- [`tasks`](./saltbox_core/tasks) – recurring or policy-driven groups of jobs,
  including policy ordering across a collection
- [`task_templates`](./saltbox_core/task_templates) – source and template
  management: local, URL and archive sources, mounted repos, SSHFS file
  operations, and the schema endpoints templates are validated against
- [`minion_collections`](./saltbox_core/minion_collections) – minions,
  collections of minions, and the extra data categories attached to them
- [`masters`](./saltbox_core/masters) – registered Salt masters and their
  status
- [`pillars`](./saltbox_core/pillars) – pillar data access and the pillar
  working schema
- [`salt`](./saltbox_core/salt) – Salt event handling, the Salt key routers,
  and the buffer manager that absorbs Salt events while Core is unavailable
- [`scheduler`](./saltbox_core/scheduler) – scheduled task templates and
  their TaskIQ handlers
- [`db`](./saltbox_core/db) – MongoDB bootstrap and shared base schemas
- [`event_bus`](./saltbox_core/event_bus) – the Redis and RabbitMQ FastStream
  apps consuming Salt events
- [`module_init`](./saltbox_core/module_init) – one-shot bootstrap stages run
  on deploy, see [Run](#run)
- [`utilities`](./saltbox_core/utilities) – shared helpers: the HTTPX client
  singleton, Redis cache and locker, Mongo query to Salt target conversion,
  and others

Additional runtime settings are passed as environment variables, check
[`saltbox_core/config.py`](saltbox_core/config.py) for the full list.

## Processes

The same image runs as several separate processes, selected by the first
argument to [`docker/entrypoint.sh`](./docker/entrypoint.sh):

- `uvicorn` – the FastAPI HTTP API
- `taskiq-worker`, `taskiq-salt-worker`, `taskiq-notify-worker` – three
  separate TaskIQ worker pools over Redis, each consuming its own queue
- `taskiq-scheduler` – the TaskIQ scheduler process
- `saltbox-module-init` – one-shot bootstrap: pre-init checks, DB migrations,
  scheduler template sync and task template bootstrap, run once before the
  other processes start
- `saltbox-faststream-redis`, `saltbox-faststream-rabbit` – FastStream apps
  consuming Salt events from Redis and RabbitMQ respectively
- `saltbox-tasks-watcher`, `saltbox-jobs-watcher` – background watchers that
  react to stale tasks and jobs
- `saltbox-salt-buffer-manager` – flushes Salt events buffered while Core was
  unavailable

Use [Salt.Box Compose](https://gitlab.com/saltbox/saltbox-compose) to run all
of them together with their dependencies.

## Development

This project uses the following tools:

- [pytest](https://docs.pytest.org/) for writing tests
- [ruff](https://astral.sh/ruff) for Python source linting and formatting
- [mypy](https://mypy.readthedocs.io/en/stable/) for static type checking
- [pre-commit](https://pre-commit.com/) for Git hooks

### Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip3 install -e .[dev]  # pip install -e .\[dev\]  in some cases
```

After deploying the dev environment, install pre-commit hooks with the
`pre-commit install` command.

### Verifying your setup

To verify that your setup is working, run the following commands:

```bash
SALTBOX_ENV_FILE=tests/test.env pytest
ruff check
mypy .
pre-commit run --all-files
```

If any of the above processes fail, please reach out to the project
maintainers for support.

### Testing

To run tests use:

```bash
SALTBOX_ENV_FILE=tests/test.env pytest
```

### Run

To build the Core image:

```bash
sudo docker build --target=main --tag saltbox-core:dev .
```

Additional settings need to be passed as environment variables to start,
check [`saltbox_core/config.py`](saltbox_core/config.py).

Use [Salt.Box Compose](https://gitlab.com/saltbox/saltbox-compose) repo to
run the whole system.
