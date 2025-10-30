# Descriptions for common flows

## SLS repository syncing

> The sequence is actual on Oct 2025

```mermaid
sequenceDiagram
  actor User
  participant Core
  participant Master as Salt Master

  User ->> Core: [POST] Add repository
  Core ->> User: [201] Created
  User -) Core: [POST] Sync repository
  Core ->> Core: Clone/pull repo
  Note over Core: Repo is in<br>/var/lib/saltbox-core/repos/
  Core ->> Core: Get AUX files by repo Manifest
  Note over Core: AUX files are in /srv/sshfs/
  Core ->> Core: Merge repos to serve dir
  Note over Core: Repos merged to /srv/salt/
  Core -) Core: Cleanup orphaned AUX files

  Core -) User: [200] Sync is done

  par Master sync
    Core -) Master: [FastStream] sync_saltbox
    Note over Core,Master: Files will be syncing with salt.states.rsync
    Master ->> Master: sync_salt
    Note over Master: SLS files are in /srv/saltbox_salt/
    opt
        Master ->> Master: sync_sshfs
        Note over Master: AUX files to serve with SSH<br>are in /srv/sshfs/
    end
    Master -) Core: [FastStream] sync_saltbox_done
  and State polling
    loop
        User -->> Core: [GET] Master
        Core -->> User: [200] Master last sync status
    end
  end
```

The weak side is missing notification on full replication end: user should check last synchronization status of master of interest.

## Master auth lifecycle

The sequence is actual for Jul 2025.

```mermaid
sequenceDiagram
  actor User
  participant Core
  participant Master as Salt Master

  Note over Core,Master: FastStream bus

  loop
    Master ->> Core: [BridgeAuthRequest] Authorize!
    Core ->> Master: [CoreAuthResponse] Unaccepted
  end

  Note over User,Core: HTTP

  User ->> Core: [POST] Accept the Master
  Core ->> User: [200] OK

  Master ->> Core: [BridgeAuthRequest] Authorize!
  Core ->>+ Master: [CoreAuthResponse] Accepted
  Note left of Master: Normal sync with salt.states.rsync
  Master -) Master: Sync Salt.Box
  Master ->> Core: [BridgeSyncDoneMessage] Sync status

  User --> Core: [POST] Unaccept the Master
  deactivate Master
  Core --> User: [200] OK
  ```
