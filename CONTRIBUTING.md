# Contributing to Salt.Box

## I want to contribute

Currently Salt.Box project does not accept third party contributions.

Please use [issues](/../../issues) to report a problem.

Sorry for inconvinience.

## Git guidelines

Commit message must be short and descriptive. Body (after first line) is
optional and useful to describe complex commits.

1. Make header not longer than 50 symbols.
2. Make imperative header starting with a verb.
3. Start header with a capital letter.
4. And avoid point at the end of header.
5. Use one empty line to separate header from body.
6. Make body also descriptive and compact.
7. Use `-` to list multiple changes if have to.

E.g.:
```
Update CONTRIBUTION.md

- Add Git guidelines section
- Add Changelog section
```

A [good guide](https://cbea.ms/git-commit/) on commit messages.

Changes congregates in branches. Branches must have short descriptive names
optionally started with `US##_`, where `##` is a number of a user story from
the private desk. E.g.: `US214_git_guidelines`.

When feature is ready or bug is fixed a branch may be merged to the main branch.
The prefer way is to use `git rebase BRANCH` while Merge Request may be
optionally created. Rebasing does not create a merge commit while merging with
web UI does.

## Changelog

Changes are tracked in the [`CHANGELOG.md`](`/CHANGELOG.md`) file in root of
the repo.

Changelog based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
guidelines.

`[ Unreleased ]` section should be presented in untagged commits and should be
changed to the release title on release tags.
