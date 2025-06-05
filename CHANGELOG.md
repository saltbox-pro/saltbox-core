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

### Changed

- Default value for `salt_func_repo_url` in config
- `end_datetime` field is required in job schemas
- `LOG_LEVEL` setting instead of `DEBUG` flag

### Fixed

- More straight init of `sshfs_tmp_dir`: respect `cache_dir` value and delete
  only old files (currently older than 1 day).
- Correct path normalization for GitFS root from manifest

### Removed

## [0.0.1] - 2025-05-16

## Added

- Initial version tag.
