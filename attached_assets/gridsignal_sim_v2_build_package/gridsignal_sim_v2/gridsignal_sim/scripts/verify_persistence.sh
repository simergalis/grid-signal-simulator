#!/usr/bin/env bash
# verify_persistence.sh — Task-97 publish-cycle persistence check.
#
# Verifies that operator accounts survive a Replit publish by querying the
# live production API before and after a deploy.  Run it twice:
#
#   Step 1 (before publish):
#     bash verify_persistence.sh snapshot
#     → prints the current user list and saves IDs to /tmp/gs_pre_publish_ids.txt
#
#   Step 2 (after publish):
#     bash verify_persistence.sh verify
#     → queries the API again and confirms every pre-publish ID is still present
#
# Usage:
#   BASE_URL  — production URL (default: https://app.gridsgnl.com)
#   ADMIN_KEY — value of the ADMIN_SECRET environment variable
#
# The script exits non-zero if any pre-publish account is missing post-publish.
# ---------------------------------------------------------------------------
set -euo pipefail

BASE_URL="${BASE_URL:-https://app.gridsgnl.com}"
ADMIN_KEY="${ADMIN_KEY:-${ADMIN_SECRET:-}}"
SNAPSHOT_FILE="/tmp/gs_pre_publish_ids.txt"

if [ -z "$ADMIN_KEY" ]; then
    echo "ERROR: set ADMIN_KEY (or ADMIN_SECRET) before running" >&2
    exit 1
fi

_fetch_users() {
    curl -sf "${BASE_URL}/api/admin/users" \
         -H "X-Admin-Key: ${ADMIN_KEY}" \
         -H "Accept: application/json"
}

_fetch_db_info() {
    curl -sf "${BASE_URL}/api/admin/db-info" \
         -H "X-Admin-Key: ${ADMIN_KEY}" \
         -H "Accept: application/json"
}

CMD="${1:-help}"

case "$CMD" in
  snapshot)
    echo "=== PRE-PUBLISH SNAPSHOT ==="
    DB_INFO="$(_fetch_db_info)"
    echo "DB backend : $DB_INFO"
    echo ""
    USERS="$(_fetch_users)"
    echo "Users      : $USERS"
    # Save IDs so the verify step can compare
    echo "$USERS" | python3 -c "
import sys, json
users = json.load(sys.stdin)
ids = [str(u['id']) for u in users]
print(' '.join(ids))
" > "$SNAPSHOT_FILE"
    echo ""
    echo "Snapshot saved → $SNAPSHOT_FILE  ($(cat "$SNAPSHOT_FILE"))"
    echo ""
    echo "Now publish the app, then run:  bash verify_persistence.sh verify"
    ;;

  verify)
    echo "=== POST-PUBLISH VERIFICATION ==="

    # 1. DB backend must be postgresql
    DB_INFO="$(_fetch_db_info)"
    echo "DB backend : $DB_INFO"
    BACKEND="$(echo "$DB_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin)['backend'])")"
    if [ "$BACKEND" != "postgresql" ]; then
        echo "FAIL: backend=$BACKEND — expected postgresql" >&2
        exit 1
    fi
    echo "PASS: backend=postgresql"
    echo ""

    # 2. All pre-publish accounts must still be present
    if [ ! -f "$SNAPSHOT_FILE" ]; then
        echo "ERROR: no snapshot found — run 'snapshot' first" >&2
        exit 1
    fi
    PRE_IDS="$(cat "$SNAPSHOT_FILE")"
    echo "Pre-publish IDs : $PRE_IDS"

    USERS="$(_fetch_users)"
    echo "Post-publish    : $USERS"
    echo ""

    MISSING=""
    for ID in $PRE_IDS; do
        if ! echo "$USERS" | python3 -c "
import sys, json
users = json.load(sys.stdin)
ids = [str(u['id']) for u in users]
sys.exit(0 if '${ID}' in ids else 1)
"; then
            MISSING="$MISSING $ID"
        fi
    done

    if [ -n "$MISSING" ]; then
        echo "FAIL: missing account IDs after publish:$MISSING" >&2
        exit 1
    fi

    # 3. email-check must still pass
    EMAIL_CHECK="$(curl -sf "${BASE_URL}/api/admin/email-check" \
                        -H "X-Admin-Key: ${ADMIN_KEY}" \
                        -H "Accept: application/json")"
    echo "email-check : $EMAIL_CHECK"
    OK="$(echo "$EMAIL_CHECK" | python3 -c "import sys,json; print(json.load(sys.stdin)['ok'])")"
    if [ "$OK" != "True" ]; then
        echo "FAIL: email-check returned ok=False" >&2
        exit 1
    fi
    echo "PASS: email-check ok=True"
    echo ""
    echo "ALL CHECKS PASSED — operator accounts survived the publish."
    ;;

  *)
    echo "Usage: $0 snapshot | verify"
    echo "  snapshot — capture pre-publish user list"
    echo "  verify   — confirm all accounts survived after publish"
    exit 1
    ;;
esac
