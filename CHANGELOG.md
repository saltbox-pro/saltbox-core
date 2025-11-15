# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
