#!/usr/bin/env bash
set -euo pipefail

# Run a WPT pass against Obscura over CDP.
#
# Boots the WPT server and the Obscura CDP server, waits for both to come up,
# builds the runner, then runs wpt-runner and pipes its JSON through triage.
# Any extra args are forwarded to wpt-runner (for example a --filter).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

OBSCURA_BIN="${OBSCURA_BIN:-obscura}"
CDP_PORT="${CDP_PORT:-9222}"
WPT_DIR="$SCRIPT_DIR/wpt"
RESULTS_DIR="$SCRIPT_DIR/results"

WPT_URL="http://web-platform.test:8000/"
CDP_VERSION_URL="http://127.0.0.1:$CDP_PORT/json/version"

mkdir -p "$RESULTS_DIR"

if [ ! -d "$WPT_DIR" ]; then
  echo "[run-wpt] error: no WPT checkout at $WPT_DIR. run scripts/setup-wpt.sh first." >&2
  exit 1
fi

WPT_PID=""
OBSCURA_PID=""

cleanup() {
  echo "[run-wpt] shutting down background servers"
  if [ -n "$OBSCURA_PID" ] && kill -0 "$OBSCURA_PID" 2>/dev/null; then
    kill "$OBSCURA_PID" 2>/dev/null || true
  fi
  if [ -n "$WPT_PID" ] && kill -0 "$WPT_PID" 2>/dev/null; then
    kill "$WPT_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "[run-wpt] starting WPT server"
( cd "$WPT_DIR" && ./wpt serve ) >"$RESULTS_DIR/wpt-serve.log" 2>&1 &
WPT_PID=$!

echo "[run-wpt] starting Obscura CDP server on port $CDP_PORT"
# The WPT server is reached as web-platform.test, which resolves to 127.0.0.1.
# Obscura blocks loopback and private addresses by default (the SSRF gate), so
# --allow-private-network is required or every navigation is refused.
"$OBSCURA_BIN" serve --port "$CDP_PORT" --allow-private-network >"$RESULTS_DIR/obscura-serve.log" 2>&1 &
OBSCURA_PID=$!

# Wait for both servers, up to ~60s.
echo "[run-wpt] waiting for WPT server and CDP server to come up"
ready=0
for _ in $(seq 1 60); do
  wpt_ok=0
  cdp_ok=0
  if curl -fsS -o /dev/null "$WPT_URL" 2>/dev/null; then
    wpt_ok=1
  fi
  if curl -fsS -o /dev/null "$CDP_VERSION_URL" 2>/dev/null; then
    cdp_ok=1
  fi
  if [ "$wpt_ok" = "1" ] && [ "$cdp_ok" = "1" ]; then
    ready=1
    break
  fi
  if ! kill -0 "$WPT_PID" 2>/dev/null; then
    echo "[run-wpt] error: WPT server exited early. see $RESULTS_DIR/wpt-serve.log" >&2
    exit 1
  fi
  if ! kill -0 "$OBSCURA_PID" 2>/dev/null; then
    echo "[run-wpt] error: Obscura server exited early. see $RESULTS_DIR/obscura-serve.log" >&2
    exit 1
  fi
  sleep 1
done

if [ "$ready" != "1" ]; then
  echo "[run-wpt] error: servers did not become ready within 60s" >&2
  echo "[run-wpt] WPT log:     $RESULTS_DIR/wpt-serve.log" >&2
  echo "[run-wpt] Obscura log: $RESULTS_DIR/obscura-serve.log" >&2
  exit 1
fi

echo "[run-wpt] both servers are up"

echo "[run-wpt] building wpt-runner and triage"
( cd "$SCRIPT_DIR" && cargo build --release -p wpt-runner -p triage )

RUNNER="$SCRIPT_DIR/target/release/wpt-runner"
TRIAGE="$SCRIPT_DIR/target/release/triage"

STAMP="$(date +%s)"
RESULTS_JSON="$RESULTS_DIR/wpt-$STAMP.json"
TRIAGE_MD="$RESULTS_DIR/triage.md"

echo "[run-wpt] running tests"
# Capture JSON for triage and machine use. The runner also prints a human summary
# to stderr, which flows straight to the terminal.
"$RUNNER" --json "$@" >"$RESULTS_JSON"

echo "[run-wpt] generating triage report"
"$TRIAGE" <"$RESULTS_JSON" >"$TRIAGE_MD"

echo ""
echo "[run-wpt] done."
echo "[run-wpt] results json: $RESULTS_JSON"
echo "[run-wpt] triage report: $TRIAGE_MD"
