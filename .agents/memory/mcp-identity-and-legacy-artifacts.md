---
name: MCP identity and legacy artifacts
description: Constraints for exposing the S1 executor through the MCP boundary.
---

The MCP preflight identity must apply exactly the same mode, duration, scheduler-config removal, and replay-input normalization as the executor identity. Legacy committed records may omit newer guard and trace fields, so the boundary must derive them from stored component totals and tick artifacts before comparison.

**Why:** A preflight identity that differs from the executor identity makes cache reuse silently miss, while older S1 records otherwise appear to have replay mismatches or failed fuel reconciliation even when their stored tick evidence passes.

**How to apply:** When adding or changing a run-input field, update the boundary identity and executor identity together. For committed legacy records, hydrate only evidence derivable from the record/tick artifact and keep incomplete filtered source lists explicitly typed as incomplete.