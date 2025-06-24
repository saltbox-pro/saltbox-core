# SLS package

Salt.Box uses SLS packages as modules of SaltStack config. Salt.Box SLS package
is a regular Git repository to provide files for Salt.Box connected masters.
Such repository should additionaly contains a manifest file which provides some
metadata.

Example of a manifest file:

```yaml
# The file is a Salt.Box package manifest file

# SLS files direcotry into the repository
# Must be a relative path
root: migration/states/

# Hash function for sshfs_files
# One of [ `md5` | `sha256` | `sha512` ], `sha256` is default
sshfs_files_checksum_type: sha256

# Auth token for `Private-Token` reaquest header if required
# `null` by default
sshfs_files_token: glpat-FF000000000000000000

# Files to download and serve with sshfs
sshfs_files:
  # Identifier is a place to put on sshfs
  migration/grub.zip:
    # GitLab requires API URL to get a Generic package file
    url: 'https://example.com/files/grub-2.06.zip'
    checksum: deca000000000000000000000000000000000000000000000000000000000000
    # Override sshfs_files_checksum_type value
    checksum_type: sha256
    # Override sshfs_files_token value, `null` for no token
    token: glpat-AAAAAAAAAAAAAAAAAAAA
  migration/saltbox_livecd.iso:
    url: 'https://example.com/files/saltbox_livecd.iso'
    checksum: cafe000000000000000000000000000000000000000000000000000000000000
  migration/alt_efi/:
    url: 'https://example.com/files/0.0.1/altos-efi.zip'
    checksum: daff000000000000000000000000000000000000000000000000000000000000
    # Unpack file after downloding.
    # `tar`, `tar.gz`, `tar.bz2`, `zip  archives are supported.
    # Check Python shutil.unpack_archive docs for precise list of formats.
    #  Archive will be unpacked to location in identifier upper.
    #  Location MUST NOT be shared with other files or archives.
    unpack: true
```
