# SLS package

## Description

Salt.Box uses SLS packages ("Configuration Boxes") as modules of SaltStack
config. Salt.Box SLS package is a regular Git repository to provide files for
Salt.Box connected masters. Such repository should additionally contains a
manifest file which provides some metadata for the Salt.Box system.

Connected to Salt.Box Configuration Boxes merges into one directory respecting
the `root` option (see Manifest explanation) and synchronizes to connected Salt
Masters.

Active Configuration boxes currently __must not__ proved files with same names
(starting from their roots).

## Example to create a Configuration Box

Example manifest file:

```yaml
# The file is a Salt.Box package manifest file

# SLS files directory into the repository
# Must be a relative path
root: states/

# Hash function for sshfs_files
# One of [ `md5` | `sha256` | `sha512` ], `sha256` is default
sshfs_files_checksum_type: sha256

# Auth token for `Private-Token` reaquest header if required
# Currently is GitLab tokens compatible
# `null` by default
sshfs_files_token: glpat-FF000000000000000000

# Files to download and serve with sshfs
sshfs_files:
  # Identifier is a place to put on sshfs
  migration/grub.zip:
    # GitLab requires API URL to get a Generic package file
    url: 'https://example.com/files/v0.0.1/grub-2.06.zip'
    checksum: deca000000000000000000000000000000000000000000000000000000000000
    # Override sshfs_files_checksum_type value
    checksum_type: sha256
    # Override sshfs_files_token value, `null` for no token
    token: glpat-AAAAAAAAAAAAAAAAAAAA
  migration/saltbox_livecd.iso:
    url: 'https://example.com/files/v0.0.1/saltbox_livecd.iso'
    checksum: cafe000000000000000000000000000000000000000000000000000000000000
  migration/alt_efi/:
    url: 'https://example.com/files/v0.0.1/altos-efi.zip'
    checksum: daff000000000000000000000000000000000000000000000000000000000000
    # Unpack file after downloding.
    # MUST be one of ['bztar', 'gztar', 'tar', 'xztar', 'zip'] or null (by default).
    # Archive will be unpacked to location in identifier upper.
    # Location MUST NOT be shared with other files or archives.
    unpack_as: zip
```

The example supposed repository hierarchy like following:

```
states/
|-- files/           # Subdirectory for small text files to use with states
|------ fonts.conf
|------ resolv.conf
|-- migrate.sls      # Some SaltStack state file
|-- configure.sls    # Some other states file
manifest.yaml        # The repo Manifest file
README.md            # Arbitrary documentation file etc
```

Binary files, especially big binary files are not good to be placed into Git
repository and __should be declared__ in `sshfs_files` section of the Manifest
with external links to obtain by HTTP/HTTPS.

In short following steps required to make and use a Configuration Box:

1. Put SLS state files and aux text files into Git repository.
2. Optionally put `manifest.yaml` into the repository.
3. If required upload binary files to some web server and declare then in
   `manifest.yaml`.
4. Push repository to some Git hosting. Self-hosted solutions like Gitea or
   GitLab may be used.
5. Add, enable and sync the new repository in "Configuration
   Repositories section" of Salt.Box web UI.

For step 3 [GitLab generic
packages](https://docs.gitlab.com/user/packages/generic_packages/#publish-a-package)
can be used.

## Settings glab to work with generic packages

[`glab`](https://docs.gitlab.com/editor_extensions/gitlab_cli/) is a GitLab CLI
API client. It provides many high-level commands and few to send arbitrary
request. Following aliases may be used to manage generic packages:

```yaml
# glab package-upload REMOTE_PATH LOCAL_FILE
package-upload: api projects/:id/packages/generic/$1 -X PUT --input $2

# glab package-list
package-list: api projects/:id/packages

# glab package-get PACKAGE_NUMERIC_ID
package-get: api projects/:id/packages/$1

# glab package-get PACKAGE_NUMERIC_ID PACKAGE_FILE_NAME LOCAL_FILE_NAME
package-download: '!glab api projects/:id/packages/$1/$2 > $3'

# glab package-delete PACKAGE_NUMERIC_ID
package-delete: api projects/:fullpath/packages/$1 -X DELETE
```

glab aliases may be added with `glab alias set <NAME> <COMMAND>` and also may
be directly placed into `~/.config/glab-cli/aliases.yml` file.

Example to upload `migration/saltbox_livecd.iso` from an example Manifest
above:

```bash
glab package-upload files/v0.0.1/grub-2.06.zip ~/downloads/grub-2.06.zip
```

Link to put to the Manifest will be in form of:
```
https://SERVER/api/v4/projects/PROJECT_NUMERIC_ID/packages/generic/files/v0.0.1/grub-2.06-for-windows.zip
```

Such API link can be used with a [GitLab
token](https://docs.gitlab.com/security/tokens/) in the `token` field.
