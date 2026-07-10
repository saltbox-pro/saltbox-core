# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [x.x.x] - YYYY-MM-DD

### Added

### Changed

### Fixed

## [0.3.0] - 2026-07-10

### Added

- New task templates module with end-to-end source and template management (local/URL/archive sources, mounted repos, SSHFS file operations, schema endpoints, bootstrap stage, and TaskIQ background workflows)
- Minion extra data subsystem: categories, list endpoints, aggregation, filtering, and event bus ingestion
- POST endpoints for job returns export in table and CSV formats
- Collection description field
- Redis masters bus helper for master-scoped pub/sub messaging

### Changed

- Refactored broker/message lifecycle to ensure proper broker initialization before handling and sending messages
- Refactored minion collections structure with dedicated repositories, services, and schemas
- Updated SDK dependencies and aligned related contracts
- Updated template/source policies and pillar working schema handling
- Updated CI pipeline: reusable Python setup and bump-version stage

### Fixed

- Fixed minion extra data collection from event bus
- Fixed template field validation and regex constraints
- Removed unused orchestrator dependency from routes
- Stabilized tests and linting configuration


## [0.2.1] - 2026-05-21

### Added

- Salt key management: list, accept, reject and delete keys; auto-delete salt key on minion removal
- Paginated response schema for salt keys list endpoint
- TaskIQ workers with named queue support; separate worker processes per queue
- Dedicated job return data endpoint; remove `data` field from job returns list response
- `JobReturnNotifySchema` for serializing job return event-bus notify messages
- `display_name` field to pillar target schemas
- Bulk delete minions endpoint
- MongoDB index on job returns for aggregations by `source` and `tgt`
- Extend Redis pub/sub channel name with master ID
- Initialize TaskIQ broker in Redis faststream app and in migration startup
- RabbitMQ and Redis credentials stub envs to test environment
- Fix missing `TaskTemplateExcludeSlsSchema` fields (hotfix)

### Changed

- Refactor services and repos to use `create`/`update` without `projection_model` argument; adopt `bulk_create`/`bulk_update` across tasks, collections and minions
- Optimize job creation and job return processing; tune MongoDB projections in salt event handlers
- Move task-filling notification to a dedicated TaskIQ task
- Split job return arguments from Salt into separate `args` and `kwargs` fields
- Replace hardcoded `rabbitmq_url` in `Settings` with `RABBIT_SETTINGS.url` from SDK
- Rename TaskIQ queue `queue_fail` → `queue_common`
- Update schemas and types across jobs, tasks, pillars, masters, collections and settings for new SDK contract
- Replace `functools.partial` monkey-patching with `_App` subclass override for `openapi()` in `main.py`
- Update SDK dependency version (multiple commits)

### Fixed

- Fix and optimize filling tasks by minions
- Fix `batch_size` usage in tasks
- Fix creating job returns for missed clients
- Fix pushing back failed salt events to buffer; add smart TaskIQ task retry
- Fix catching exceptions on task create
- Fix `bulk_create` on duplicate or empty data via SDK update
- Fix MongoDB aggregation pipeline preparation


## [0.2.0] - 2026-04-06

### Added

- Initial database migrations.
- Support for job/state execution for minion `v3005.1`.
- Job timeout support.
- `extra_pillarenv` support in job creation.
- `launch_error_type` field in jobs list response.
- Aggregated minion statistics in jobs via `minions_count`.
- WebSocket notifications for task minion create/update/delete events.

### Changed

- Job statuses updated:
  - `in_queue` → `starting`
  - `started` → `running`
  - `error` → `launch_error`
  - removed `waiting_returns`
- Renamed job field `error_type` to `launch_error_type`.
- Collections list endpoint now uses `POST` with body payload mixins.
- List endpoints switched to a universal response format.
- Task template list endpoint moved to `/list`.
- Task template description model updated:
  - removed `full_description`
  - `short_description` renamed to `description`
  - added localized `dict[str, str]` support for descriptions
- Pillar API and internal structure refactored:
  - deprecated pillar modules/services removed
  - Pillar v2 became the primary implementation
  - updated router prefixes and related schemas/policies
- Improved pillar handling and schema definitions.
- Optimized task creation and related DB queries.
- Added/updated MongoDB indexes for jobs, task minions, and related entities.
- Updated SDK/dependency versions for Mongo query and aggregation fixes.

### Fixed

- Task creation without template defaults.
- TTL assignment during task creation.
- Filling tasks by minions.
- Processing of job returns.
- Creating job returns for new jobs.
- Inventory collection from job returns.
- Repository lock release after repository deletion.
- Scheduler job/task creation issues and scheduler template paths.
- Incorrect list/status endpoint URLs.
- Mongo query preparation when values are `None`.
- Sorting task minions by `count_runs`.
- PEP 639 compatibility issues.
- Minor backend cleanup and argument passing issues.

## [0.1.2] - 2025-12-22

### Added
- Helpers for migrations
- Permissions for SSHFS
- Secured pillars (by GPG)

### Changed
- Minions list endpoint (removed `osfullname`, `cpu_model` and `mem_total`; added `saltversion`, `osfinger` and `efi_secure_boot`)

### Fixed
- Grains with aliases
- Job creation by tasks (when minion list is empty)


## [0.1.1] - 2025-11-15

### Added

- Cleanup AUX files not specified in existing SLS repo manifests.

### Changed

- Downloading AUX files not depends on `content-disposition` header.
- Manifest `sshfs_files` archive entry requires `unpack_as` field to contain an
archive format string. `unpack` field is deprecated.

### Fixed

- Unmatched AUX file checksum if `checksum` in Manifest has upper-case letters.
- More collision-safe temporary file names while downloading.

## [0.1.0] - 2025-09-29

### Added

- Add `salt_master` to jobs
- Add allow restart failed task on tasks with status `stopped`
- Add GET endpoint to retrieve a minion by master ID and minion ID for master-scoped lookup.
- Add GitLab API client, routes and configuration (token, base URL, group ID) with dedicated exceptions.
- Add computed Task fields `total_minions` and `minions_count_by_status`.
- Add CSV export support for custom grains and update Grains schema field titles.
- Add unique index on collections for the (`parent_id`, `title`) pair and logging for index creation.
- Add `TaskCreateSchemaValidationException` to surface task create validation errors.
- Add `source` field to Task model.
- Add RabbitMQ-based event bus and support for syncing scheduler templates over the bus.
- Add initial Inventory persistence to MongoDB: polymorphic models, inventory prototypes, bulk_update_and_create, precise indices and signal-based extraction; make inventory fields optional and warn on ignored extra fields.
- Add FastAPI metrics export endpoint.
- Create default job template during repository initialization.

### Changed

- Add cooldown when creating jobs linked to task lifespan and refactor related task/job logic.
- Replace `get_httpx_async_client` with `HttpxClientSingletoneFactory` (singleton AsyncClient) and update authentication handling for HTTPX clients.
- Refactor job creation: trim whitespace in job data and add `user` and `returning` fields; set JobReturn.success based on retcode.
- Refactor task schemas and list endpoints: improved field titles, POST-based list filtering, filter schema endpoint and sortable get_list methods.
- Move faststream scheduler handlers to the SDK and refactor scheduler task creation/run flow.
- Refactor collection and OpenAPI configuration, simplify routers and improve OpenAPI integration for job and collection endpoints.

### Fixed

- Fix operation_id and OpenAPI/schema inconsistencies for filter and collection endpoints.
- Fix task creation path from scheduler and prevent stale minion data during Inventory updates.
- Fix CSV export error handling and correct inventory model/index issues causing broken hierarchy.
- Fix multiple tests and apply linter (ruff) fixes.
- Fix route parameter naming and other small API parameter bugs.

### Removed

- Remove `SaltBoxCrypt` implementation.
- Remove obsolete endpoints `jobs_list_cursor` and `job_create_sync`.

## [0.0.1] - 2025-05-16

## Added

- Initial version tag.
