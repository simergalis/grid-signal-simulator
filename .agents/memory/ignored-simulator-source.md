---
name: Ignored simulator source tracking
description: Repository tracking constraint for simulator code stored under attached_assets.
---

Simulator source placed below `attached_assets` is ignored by the workspace Git rules, even when it is part of the active application. New source files in that tree must be explicitly added to version control after creation.

**Why:** A new scheduler module existed on disk and passed runtime tests but was absent from ordinary status output because the parent asset path is ignored.

**How to apply:** After adding a new source module below `attached_assets`, verify it with `git check-ignore` and force-add only that file if the ignore rule would otherwise omit it.