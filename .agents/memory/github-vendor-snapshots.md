---
name: GitHub vendor snapshots
description: How to retrieve pinned public GitHub source snapshots in this workspace when connector endpoints fail.
---

For this workspace, the GitHub App connector successfully verifies commit metadata and recursive trees, but the repository zipball endpoint can return 403 and concurrent per-file content requests can return 429. A public Git CLI clone through Replit's secure GitHub proxy worked for pinned snapshots; verify the exact checkout and file hashes before removing `.git`.

**Why:** During a vendor-reference import, the connector's archive and content routes did not support transferring the complete tree, while the Git client route worked.

**How to apply:** Use the connector to confirm the requested commit and tree. If bulk connector retrieval is blocked or rate-limited, clone the public repository with Git, checkout the exact requested commit, compare protected files such as README and LICENSE, and only then remove the imported folder's `.git` directory.
