---
name: Ignored simulator source tracking
description: Ignored simulator source and automatic-checkpoint caveats for Git status reports.
---

Simulator source placed below `attached_assets` is ignored by the workspace Git rules, even when it is part of the active application. New source files in that tree must be explicitly added to version control after creation.

**Why:** A new scheduler module existed on disk and passed runtime tests but was absent from ordinary status output because the parent asset path is ignored.

**How to apply:** After adding a new source module below `attached_assets`, verify it with `git check-ignore` and force-add only that file if the ignore rule would otherwise omit it.

An automatic end-of-turn checkpoint can commit staged application changes after the agent deliberately makes a documentation-only commit. A saved report's "staged/uncommitted" statement is therefore historical, not an enduring repository status.

**Why:** A stopped implementation remained staged when its report was committed; the following automatic checkpoint committed that implementation under a different message.

**How to apply:** For later status audits, read current HEAD, its changed-file list and Git status instead of repeating the saved report's commit-state claim. Distinguish checkpointed code from a completed validation gate.

An unsuccessful staging command does not prove that the index is unchanged.

**Why:** A scoped add of an already tracked simulator file staged its edit but also returned an ignored-parent warning and a nonzero status.

**How to apply:** Inspect `git diff --cached` and short status before retrying. Do not broaden a force-add merely because the first command reported failure.

A stash made after an automatic checkpoint is a delta against that checkpoint,
not necessarily a patch containing the entire candidate implementation.

**Why:** After application files had been restored to a pre-candidate base,
applying the later stash restored only follow-on edits and produced conflicts,
rather than restoring all candidate files.

**How to apply:** Inspect the stash parent and full tree before recovery. When
restoring a complete candidate is authorized, verify the listed candidate paths
against the full stash tree; do not assume a successful delta application proves
the complete candidate is present.