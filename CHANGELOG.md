# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `SALTBOX_CORE_ENV_FILE` environment variable support to override dotenv location.
- Allow running jobs as tasks
- Base support for tree structures
- Add tree structure to collections
- Master `last_sync_status` and `last_sync_timestamp` fields
- Add `/pillar/validate` endpoint for validating import pillars data

### Changed

- Default value for `salt_func_repo_url` in config
- `end_datetime` field is required in job schemas
- `LOG_LEVEL` setting instead of `DEBUG` flag
- Rsync based synchronization of SLS files
- Common Core-Bridge message classes moved to `saltbox-bridge-messages` library
- Shorten Master authentication process

### Fixed

- More straight init of `sshfs_tmp_dir`: respect `cache_dir` value and delete
  only old files (currently older than 1 day).
- Possibly incorrect state name on directory names duplicates in an SLS file
path.
- Task Templates respect Manifest root value.

### Removed

## [0.0.1] - 2025-05-16

## Added

- Initial version tag.
