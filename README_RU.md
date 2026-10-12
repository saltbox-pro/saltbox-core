<div align = right>

&ensp;[<kbd> <br> EN <br> </kbd>](./README.md)&ensp;
&ensp;[<kbd> <br> RU <br> </kbd>](./README_RU.md)&ensp;

</div>

---

# Salt.Box Core

## Содержание

- **[Описание](#описание)**
- **[Структура проекта](#структура-проекта)**
- **[Процессы](#процессы)**
- **[Разработка](#разработка)**
  - [Окружение](#окружение)
  - [Проверка окружения](#проверка-окружения)
  - [Тестирование](#тестирование)
  - [Запуск](#запуск)


## Описание

**Salt.Box Core** – основной backend Salt.Box на [FastAPI](https://fastapi.tiangolo.com/).
Он хранит собственные доменные данные системы в MongoDB, джобы, таски, шаблоны
тасков, коллекции миньонов, пилларов и мастеров, а также управляет самим Salt
через событийную шину соли, запуская джобы и собирая их результаты.

Формат SLS-пакетов описан в [`sls_package.md`](./sls_package.md).

Описание основных внутренних процессов находится в
[`common_flows.md`](./common_flows.md).

## Структура проекта

Доменные пакеты в [`saltbox_core/`](./saltbox_core) устроены по одной схеме:
`routers` объявляют эндпоинты FastAPI, `services` содержат бизнес-логику,
`repositories` работают с MongoDB, `schemas` определяют pydantic-модели
запросов и ответов, а `migrations` содержат миграции данных для этого
домена.

- [`jobs`](./saltbox_core/jobs) – отдельные запуски джоб Salt и их результаты
- [`tasks`](./saltbox_core/tasks) – повторяющиеся или управляемые политиками
  группы джоб, включая упорядочивание политик в рамках коллекции
- [`task_templates`](./saltbox_core/task_templates) – управление источниками
  и шаблонами: локальные, URL и архивные источники, смонтированные
  репозитории, операции с файлами через SSHFS, и эндпоинты схем, по которым
  валидируются шаблоны
- [`minion_collections`](./saltbox_core/minion_collections) – миньоны,
  коллекции миньонов и категории дополнительных данных, привязанные к ним
- [`masters`](./saltbox_core/masters) – зарегистрированные мастера Salt и их
  статус
- [`pillars`](./saltbox_core/pillars) – доступ к данным pillar и рабочая
  схема pillar
- [`salt`](./saltbox_core/salt) – обработка событий Salt, роутеры ключей, и буфер-менеджер
- [`scheduler`](./saltbox_core/scheduler) – запланированные шаблоны тасков и
  их обработчики TaskIQ
- [`db`](./saltbox_core/db) – инициализация MongoDB и общие базовые схемы
- [`event_bus`](./saltbox_core/event_bus) – приложения FastStream на Redis и
  RabbitMQ, использующие события Salt
- [`module_init`](./saltbox_core/module_init) – одноразовые этапы загрузки
  при деплое, см. [Запуск](#запуск)
- [`utilities`](./saltbox_core/utilities) – общие хелперы: singleton
  HTTPX-клиента, кэш и locker Redis, преобразование Mongo-запроса в таргет
  Salt и другие

Дополнительные настройки окружения передаются переменными среды, полный
список – в [`saltbox_core/config.py`](saltbox_core/config.py).

## Процессы

Один и тот же образ запускается как несколько отдельных процессов, которые
выбираются первым аргументом [`docker/entrypoint.sh`](./docker/entrypoint.sh):

- `uvicorn` – HTTP API на FastAPI
- `taskiq-worker`, `taskiq-salt-worker`, `taskiq-notify-worker` – три
  отдельных пула воркеров TaskIQ над Redis, каждый обслуживает свою очередь
- `taskiq-scheduler` – процесс планировщика TaskIQ
- `saltbox-module-init` – одноразовая загрузка: проверки pre-init, миграции
  базы данных, синхронизация шаблонов планировщика и загрузка шаблонов
  тасков, выполняется один раз перед стартом остальных процессов
- `saltbox-faststream-redis`, `saltbox-faststream-rabbit` – приложения
  FastStream, потребляющие события Salt из Redis и RabbitMQ соответственно
- `saltbox-tasks-watcher`, `saltbox-jobs-watcher` – фоновые процессы,
  реагирующие на зависшие таски и джобы
- `saltbox-salt-buffer-manager` – сбрасывает буферизованные события Salt,
  пока Core был недоступен

Для совместного запуска всех процессов с их зависимостями используйте
[Salt.Box Compose](https://gitlab.com/saltbox/saltbox-compose).

## Разработка

В проекте используются следующие инструменты:

- [pytest](https://docs.pytest.org/) для написания тестов
- [ruff](https://astral.sh/ruff) для линтинга и форматирования Python-кода
- [mypy](https://mypy.readthedocs.io/en/stable/) для статической проверки типов
- [pre-commit](https://pre-commit.com/) для Git-хуков

### Окружение

```bash
python -m venv .venv
source .venv/bin/activate
pip3 install -e .[dev]  # pip install -e .\[dev\]  в некоторых случаях
```

После разворачивания dev-окружения установите pre-commit хуки командой
`pre-commit install`.

### Проверка окружения

Чтобы убедиться, что окружение настроено корректно, выполните:

```bash
SALTBOX_ENV_FILE=tests/test.env pytest
ruff check
mypy .
pre-commit run --all-files
```

Если что-то из перечисленного не проходит, обратитесь к поддержке
мейнтейнеров проекта.

### Тестирование

Для запуска тестов используйте:

```bash
SALTBOX_ENV_FILE=tests/test.env pytest
```

### Запуск

Чтобы собрать образ Core:

```bash
sudo docker build --target=main --tag saltbox-core:dev .
```

Дополнительные настройки передаются переменными окружения при старте,
полный список – в [`saltbox_core/config.py`](saltbox_core/config.py).

Для запуска всей системы используйте репозиторий
[Salt.Box Compose](https://gitlab.com/saltbox/saltbox-compose).
