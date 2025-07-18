# Descriptions for common flows

## SLS repository syncing

The sequence is actual for Jul 2025.

```mermaid
sequenceDiagram
  actor User
  participant Core
  participant Master as Salt Master
  
  User ->> Core: [POST] Add repository
  Core ->> User: [201] Created
  User -) Core: [POST] Sync repository
  Core ->> Core: Clone/pull repo
  Core ->> Core: Get files by repo Manifest
  Core ->> Core: Merge repos to serve dir
  
  Core -) User: [200] Sync is done

  par Master sync
    Core -) Master: [FastStream] sync_saltbox
    Master -> Master: sync_salt
    Note left of Master: salt.states.rsync
    opt
        Master -> Master: sync_sshfs
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