#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# MAX Messenger — Webhook Health Diagnostics
# ═══════════════════════════════════════════════════════════════════════
# Usage:
#   ./diagnose.sh          # basic (no E2E send)
#   ./diagnose.sh --send   # full + sends test message
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
SKIP=0

check() {
    local num=$1 desc=$2 result=$3
    if [ "$result" = "pass" ]; then
        echo -e "  ${GREEN}✅${NC} $num. $desc"
        PASS=$((PASS + 1))
    elif [ "$result" = "skip" ]; then
        echo -e "  ${YELLOW}⏭️${NC} $num. $desc"
        SKIP=$((SKIP + 1))
    else
        echo -e "  ${RED}❌${NC} $num. $desc"
        FAIL=$((FAIL + 1))
    fi
}

# ── Config ────────────────────────────────────────────────────────────
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/max-platform"
ENV_FILE="$HERMES_HOME/.env"
CONFIG_FILE="$HERMES_HOME/config.yaml"
GATEWAY_LOG="$HERMES_HOME/logs/gateway.log"
MAX_API="https://platform-api.max.ru"

# Source MAX_BOT_TOKEN from .env (parse only KEY=VALUE lines, skip others)
if [ -f "$ENV_FILE" ]; then
    while IFS='=' read -r key val; do
        # Skip comments, blank lines, and lines without '='
        if [ -n "$key" ] && [ -n "$val" ] && [ "${key#\#}" = "$key" ]; then
            # Trim whitespace
            key="${key%% *}"
            key="${key## }"
            val="${val%%\#*}"
            val="${val%% }"
            val="${val## }"
            export "$key=$val" 2>/dev/null || true
        fi
    done < "$ENV_FILE"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   MAX Messenger — Webhook Health Diagnostics               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Plugin installed & enabled ────────────────────────────────────
desc="Plugin installed & enabled"
if command -v hermes &>/dev/null; then
    plugin_line=$(hermes plugins list 2>/dev/null | grep "max-platform")
    if echo "$plugin_line" | grep -q "enabled"; then
        version=$(echo "$plugin_line" | sed 's/.*│ *//; s/ *│.*//')
        check 1 "$desc ($version)" "pass"
    else
        check 1 "$desc" "fail"
    fi
else
    check 1 "$desc (hermes CLI not found)" "fail"
fi

# ── 2. Gateway logs: MAX connected ────────────────────────────────────
desc="Gateway log: MAX connected"
if [ -f "$GATEWAY_LOG" ]; then
    last_conn=$(grep "MAX: connected" "$GATEWAY_LOG" 2>/dev/null | tail -1)
    if [ -n "$last_conn" ]; then
        echo -e "       Last: $last_conn"
        check 2 "$desc" "pass"
    else
        echo -e "       No 'MAX: connected' entries found"
        check 2 "$desc" "fail"
    fi
else
    check 2 "$desc (log file not found)" "fail"
fi

# ── 3. Webhook port listening ────────────────────────────────────────
desc="Webhook port :8646 listening"
if ss -tlnp 2>/dev/null | grep -q "8646"; then
    pid=$(ss -tlnp 2>/dev/null | grep "8646" | sed 's/.*pid=//;s/,.*//')
    echo -e "       PID: $pid"
    check 3 "$desc" "pass"
else
    check 3 "$desc" "fail"
fi

# ── 4. Health endpoint ────────────────────────────────────────────────
desc="Health endpoint"
health=$(curl -s --max-time 5 http://localhost:8646/health 2>/dev/null | tr -d '[:space:]' || echo "")
if [ "$health" = '{"status":"ok"}' ]; then
    check 4 "$desc" "pass"
else
    echo -e "       Got: $health"
    check 4 "$desc" "fail"
fi

# ── 5. Subscription registered ────────────────────────────────────────
desc="Webhook subscription registered"
if [ -n "${MAX_BOT_TOKEN:-}" ]; then
    subs=$(curl -s --max-time 10 \
        -H "Authorization: $MAX_BOT_TOKEN" \
        "$MAX_API/subscriptions" 2>/dev/null || echo "")
    # Extract MAX_WEBHOOK_URL without scheme for matching
    webhook_path="${MAX_WEBHOOK_URL:-unknown}"
    if echo "$subs" | grep -q "subscriptions" && echo "$subs" | grep -qF "$webhook_path"; then
        urls=$(echo "$subs" | grep -o '"url":"[^"]*"' | sed 's/"url":"//;s/"//')
        echo -e "       URL: $urls"
        check 5 "$desc" "pass"
    elif echo "$subs" | grep -q "subscriptions" && [ -z "${MAX_WEBHOOK_URL:-}" ]; then
        check 5 "$desc (no MAX_WEBHOOK_URL — likely long polling)" "skip"
    else
        echo -e "       Response: ${subs:0:200}"
        check 5 "$desc" "fail"
    fi
else
    check 5 "$desc (MAX_BOT_TOKEN not found in .env)" "fail"
fi

# ── 6. Token valid ────────────────────────────────────────────────────
desc="Bot token valid"
if [ -n "${MAX_BOT_TOKEN:-}" ]; then
    me=$(curl -s --max-time 10 \
        -H "Authorization: $MAX_BOT_TOKEN" \
        "$MAX_API/me" 2>/dev/null || echo "")
    username=$(echo "$me" | grep -o '"username":"[^"]*"' | sed 's/"username":"//;s/"//')
    if [ -n "$username" ]; then
        echo -e "       Bot: @$username"
        check 6 "$desc" "pass"
    elif echo "$me" | grep -q "401\|Unauthorized"; then
        check 6 "$desc (401 — invalid token)" "fail"
    else
        echo -e "       Response: ${me:0:200}"
        check 6 "$desc" "fail"
    fi
else
    check 6 "$desc (MAX_BOT_TOKEN not found)" "fail"
fi

# ── 7. E2E send (optional) ───────────────────────────────────────────
desc="E2E send test"
if [ "${1:-}" = "--send" ]; then
    target_id="${MAX_HOME_CHANNEL:-${MAX_ALLOWED_USERS%%,*}}"
    if [ -n "${MAX_BOT_TOKEN:-}" ] && [ -n "$target_id" ]; then
        param="user_id"
        # If target looks like a chat ID (chat:...), extract the number
        if echo "$target_id" | grep -q ":"; then
            target_id=$(echo "$target_id" | cut -d: -f2)
        fi
        # If group chat, use chat_id instead
        if echo "$target_id" | grep -q "^[0-9]"; then
            param="user_id"
        fi
        result=$(curl -s --max-time 10 -X POST \
            "$MAX_API/messages?${param}=${target_id}" \
            -H "Authorization: $MAX_BOT_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{"text":"✅ Diagnostics: bot OK","format":"markdown"}' 2>/dev/null || echo "{}")
        mid=$(echo "$result" | grep -o '"mid":"[^"]*"' | head -1 | sed 's/"mid":"//;s/"//')
        if [ -n "$mid" ]; then
            echo -e "       mid: $mid"
            check 7 "$desc" "pass"
        else
            echo -e "       Response: ${result:0:200}"
            check 7 "$desc" "fail"
        fi
    else
        check 7 "$desc (no target user)" "skip"
    fi
else
    check 7 "$desc (use --send to test)" "skip"
fi

# ── 8. Reasoning configured ───────────────────────────────────────────
desc="Reasoning: fresh_final_after_seconds"
if [ -f "$CONFIG_FILE" ]; then
    ffas=$(grep -A3 'max:' "$CONFIG_FILE" 2>/dev/null | grep fresh_final_after_seconds || true)
    if echo "$ffas" | grep -q "10"; then
        echo -e "       Config: $ffas"
        check 8 "$desc" "pass"
    else
        echo -e "       Not found (optional — see README)"
        check 8 "$desc" "skip"
    fi
else
    check 8 "$desc (config.yaml not found)" "skip"
fi

# ── Summary ────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
printf "║  ${GREEN}✅ %d passed${NC}, ${RED}❌ %d failed${NC}, ${YELLOW}⏭️ %d skipped${NC}                  ║\n" "$PASS" "$FAIL" "$SKIP"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}Some checks failed. Check ~/.hermes/logs/gateway.log for details.${NC}"
    echo "For troubleshooting: https://gitea.rmg7.com/agent/hermes-max-integration"
    exit 1
else
    echo -e "${GREEN}All checks passed!${NC}"
    exit 0
fi
