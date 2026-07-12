#!/usr/bin/env bash
# run.sh — one command from a fresh checkout to a running Simulation Labs demo.
#
#   ./run.sh              preflight + self-heal, then start everything (foreground; ctrl-C stops it)
#   ./run.sh --background same, but detached; PIDs land in .run/; stop with `./run.sh stop`
#   ./run.sh --restart    if a ghostpanel server already owns the port, replace it
#   ./run.sh stop         stop background servers previously started by this script
#   ./run.sh doctor       preflight checks + contract tests; starts nothing
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/.run"
VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"
FIXTURES_PORT=8137

# --- pretty output (tput-guarded) ---------------------------------------------
if [[ -t 1 ]] && command -v tput >/dev/null 2>&1 && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
  GREEN="$(tput setaf 2)"; RED="$(tput setaf 1)"; YELLOW="$(tput setaf 3)"; BOLD="$(tput bold)"; RESET="$(tput sgr0)"
else
  GREEN=""; RED=""; YELLOW=""; BOLD=""; RESET=""
fi
ok()   { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '%s!%s %s\n' "$YELLOW" "$RESET" "$*"; }
bad()  { printf '%s✗%s %s\n' "$RED" "$RESET" "$*"; }
die()  { bad "$*"; exit 1; }

usage() { sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

# --- args ----------------------------------------------------------------------
CMD=run BACKGROUND=0 RESTART=0
for arg in "$@"; do
  case "$arg" in
    doctor) CMD=doctor ;;
    stop) CMD=stop ;;
    --background) BACKGROUND=1 ;;
    --restart) RESTART=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "unknown argument: $arg" ;;
  esac
done

# --- preflight (each check self-heals; returns 1 only when it can't) -----------
PY=""
find_python() {
  if [[ -x /opt/homebrew/bin/python3.12 ]]; then PY=/opt/homebrew/bin/python3.12
  elif command -v python3.12 >/dev/null 2>&1; then PY="$(command -v python3.12)"
  else
    bad "python3.12 not found — install it first:  brew install python@3.12"
    return 1
  fi
  ok "python3.12: $PY"
}

ensure_venv() {
  if [[ ! -x "$VENV_PY" ]]; then
    warn ".venv missing — creating with $PY"
    "$PY" -m venv "$VENV" || { bad "venv creation failed"; return 1; }
  fi
  ok "venv: $VENV"
}

ensure_deps() {
  if "$VENV_PY" -c 'import ghostpanel, daltonlens' >/dev/null 2>&1; then
    ok "python deps installed (ghostpanel + dev extras)"
  else
    warn "installing python deps: pip install -e \".[dev]\""
    (cd "$ROOT" && "$VENV_PY" -m pip install --quiet -e ".[dev]") \
      || { bad "pip install failed"; return 1; }
    ok "python deps installed"
  fi
}

ensure_chromium() {
  local exe
  exe="$("$VENV_PY" - <<'PY' 2>/dev/null || true
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    print(p.chromium.executable_path)
PY
)"
  if [[ -n "$exe" && -x "$exe" ]]; then
    ok "playwright chromium present"
  else
    warn "installing playwright chromium"
    "$VENV_PY" -m playwright install chromium || { bad "playwright install failed"; return 1; }
    ok "playwright chromium installed"
  fi
}

ensure_web() {
  local dist="$ROOT/web/dist/index.html"
  if [[ ! -d "$ROOT/web/node_modules" ]]; then
    command -v npm >/dev/null 2>&1 || { bad "npm not found — install Node.js (brew install node)"; return 1; }
    warn "web/node_modules missing — npm install"
    (cd "$ROOT/web" && npm install --silent) || { bad "npm install failed"; return 1; }
  fi
  # Rebuild when dist is missing or any source file is newer than the built index.
  if [[ ! -f "$dist" ]] || [[ -n "$(find "$ROOT/web/src" "$ROOT/web/index.html" -newer "$dist" -print -quit 2>/dev/null)" ]]; then
    warn "building frontend (web/dist)"
    (cd "$ROOT/web" && npm run --silent build) || { bad "web build failed"; return 1; }
    ok "web/dist built"
  else
    ok "web/dist up to date"
  fi
}

load_env() {
  if [[ ! -f "$ROOT/.env" ]]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    warn ".env was missing — copied from .env.example"
    printf '%s\n' "${BOLD}${YELLOW}>>> Edit .env and fill in your keys (HAI_API_KEY, GRADIUM_API_KEY, ...) <<<${RESET}"
  fi
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
  HOST="${GHOSTPANEL_HOST:-127.0.0.1}"
  PORT="${GHOSTPANEL_PORT:-8000}"
  case "${HAI_API_KEY:-}" in
    ""|*xxxx*) warn "HAI_API_KEY is empty/placeholder — keyless mode: live Holo runs disabled, the Offline demo still works" ;;
    *) ok "HAI_API_KEY set" ;;
  esac
}

# --- ports ----------------------------------------------------------------------
listener_pids() { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null || true; }

check_app_port() {
  local pids pid cmd
  pids="$(listener_pids "$PORT")"
  if [[ -z "$pids" ]]; then ok "port $PORT free"; return 0; fi
  for pid in $pids; do
    cmd="$(ps -o command= -p "$pid" 2>/dev/null || true)"
    if [[ "$cmd" == *ghostpanel* ]]; then
      if [[ "$RESTART" -eq 1 ]]; then
        warn "--restart: stopping existing ghostpanel server (pid $pid)"
        kill "$pid" 2>/dev/null || true
      else
        die "a ghostpanel server already listens on port $PORT (pid $pid). It may already be serving http://$HOST:$PORT/ — or rerun with:  ./run.sh --restart"
      fi
    else
      die "port $PORT is held by a non-ghostpanel process (pid $pid: ${cmd:-unknown}). Refusing to kill it — free the port or change GHOSTPANEL_PORT in .env."
    fi
  done
  for _ in $(seq 1 20); do
    [[ -z "$(listener_pids "$PORT")" ]] && { ok "port $PORT free"; return 0; }
    sleep 0.25
  done
  die "port $PORT is still busy after --restart"
}

# --- servers ----------------------------------------------------------------------
FIXTURES_PID=""   # set only when WE start the fixtures server
SERVER_PID=""

start_fixtures() {
  if [[ -n "$(listener_pids "$FIXTURES_PORT")" ]]; then
    warn "port $FIXTURES_PORT already has a listener — reusing it for fixtures (not ours to stop)"
    return 0
  fi
  if [[ "$BACKGROUND" -eq 1 ]]; then
    nohup "$VENV_PY" -m http.server "$FIXTURES_PORT" --bind 127.0.0.1 --directory "$ROOT" \
      >>"$RUN_DIR/fixtures.log" 2>&1 &
    FIXTURES_PID=$!
    echo "$FIXTURES_PID" >"$RUN_DIR/fixtures.pid"
  else
    "$VENV_PY" -m http.server "$FIXTURES_PORT" --bind 127.0.0.1 --directory "$ROOT" \
      >>"$RUN_DIR/fixtures.log" 2>&1 &
    FIXTURES_PID=$!
  fi
  ok "fixtures server: http://127.0.0.1:$FIXTURES_PORT (pid $FIXTURES_PID)"
}

start_server() {
  if [[ "$BACKGROUND" -eq 1 ]]; then
    (cd "$ROOT" && exec nohup "$VENV_PY" -m ghostpanel.server.main) >>"$RUN_DIR/server.log" 2>&1 &
    SERVER_PID=$!
    echo "$SERVER_PID" >"$RUN_DIR/server.pid"
  else
    (cd "$ROOT" && exec "$VENV_PY" -m ghostpanel.server.main) &
    SERVER_PID=$!
  fi
}

wait_healthy() {
  for _ in $(seq 1 60); do
    if curl -fsS -m 2 "http://$HOST:$PORT/healthz" >/dev/null 2>&1; then
      ok "server healthy: http://$HOST:$PORT/healthz"
      return 0
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      if [[ "$BACKGROUND" -eq 1 ]]; then die "server exited during startup — see $RUN_DIR/server.log"; fi
      die "server exited during startup (see output above)"
    fi
    sleep 0.5
  done
  die "server did not answer /healthz within 30s"
}

banner() {
  local policy_line lb_count
  policy_line="$(POLICY_JSON="$(curl -fsS -m 3 "http://$HOST:$PORT/policy" 2>/dev/null || true)" "$VENV_PY" - <<'PY'
import json, os
try:
    d = json.loads(os.environ.get("POLICY_JSON", ""))
    name = ((d.get("policy") or {}).get("preset") or {}).get("name") or "policy loaded"
    print(f"{name} ({'ENFORCED' if d.get('enforced') else 'NOT enforced'})")
except Exception:
    print("unavailable")
PY
)"
  lb_count="$(LB_JSON="$(curl -fsS -m 3 "http://$HOST:$PORT/leaderboard" 2>/dev/null || true)" "$VENV_PY" - <<'PY'
import json, os
try:
    print(len(json.loads(os.environ.get("LB_JSON", ""))))
except Exception:
    print("?")
PY
)"
  printf '\n%s' "$BOLD"
  printf '════════════════════════ Simulation Labs is up ════════════════════════%s\n' "$RESET"
  printf '  App           http://%s:%s/\n' "$HOST" "$PORT"
  printf '  Fixtures      hostile form   http://localhost:%s/fixtures/hostile_form.html\n' "$FIXTURES_PORT"
  printf '                fixed (Run B)  http://localhost:%s/fixtures/hostile_form_fixed.html?as=hostile_form.html\n' "$FIXTURES_PORT"
  printf '                payment/policy http://localhost:%s/fixtures/payment_form.html\n' "$FIXTURES_PORT"
  printf '  Policy        %s\n' "$policy_line"
  printf '  Leaderboard   %s run(s) scored\n' "$lb_count"
  printf '  Demo one-liners:\n'
  printf '    Offline demo:  open http://%s:%s/ and click "Offline demo" (zero keys, zero network)\n' "$HOST" "$PORT"
  printf '    Before/after:  Run A hostile_form.html, then Run B hostile_form_fixed.html?as=hostile_form.html\n'
  printf '                   (same task, personas: low-vision, tremor, power-user)\n'
  printf '%s════════════════════════════════════════════════════════════════════════%s\n\n' "$BOLD" "$RESET"
  if [[ "$BACKGROUND" -eq 1 ]]; then
    ok "running in background — logs: $RUN_DIR/server.log — stop with:  ./run.sh stop"
  else
    ok "foreground mode — ctrl-C stops the app and the fixtures server"
  fi
}

cleanup() {
  local code=$?
  trap - EXIT INT TERM
  if [[ "$BACKGROUND" -ne 1 ]]; then
    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then kill "$SERVER_PID" 2>/dev/null || true; fi
    if [[ -n "$FIXTURES_PID" ]] && kill -0 "$FIXTURES_PID" 2>/dev/null; then kill "$FIXTURES_PID" 2>/dev/null || true; fi
  fi
  exit "$code"
}

# --- subcommands ----------------------------------------------------------------
cmd_stop() {
  local any=0 f pid cmd
  for f in "$RUN_DIR/server.pid" "$RUN_DIR/fixtures.pid"; do
    [[ -f "$f" ]] || continue
    pid="$(cat "$f")"
    cmd="$(ps -o command= -p "$pid" 2>/dev/null || true)"
    # Only ever kill processes that are recognizably ours.
    if [[ "$cmd" == *ghostpanel* || "$cmd" == *http.server* ]]; then
      kill "$pid" 2>/dev/null || true
      ok "stopped pid $pid (${f##*/})"
      any=1
    elif [[ -n "$cmd" ]]; then
      warn "pid $pid from ${f##*/} is no longer ours ($cmd) — leaving it alone"
    fi
    rm -f "$f"
  done
  [[ "$any" -eq 1 ]] || warn "nothing recorded in $RUN_DIR to stop"
}

cmd_doctor() {
  local fails=0
  find_python || fails=$((fails + 1))
  if [[ -n "$PY" ]]; then
    ensure_venv || fails=$((fails + 1))
  fi
  if [[ -x "$VENV_PY" ]]; then
    ensure_deps || fails=$((fails + 1))
    ensure_chromium || fails=$((fails + 1))
  fi
  ensure_web || fails=$((fails + 1))
  load_env
  local pids
  pids="$(listener_pids "$PORT")"
  if [[ -z "$pids" ]]; then
    ok "port $PORT free"
  elif [[ "$(ps -o command= -p "${pids%%[$'\n']*}" 2>/dev/null)" == *ghostpanel* ]]; then
    warn "port $PORT: a ghostpanel server is already running (./run.sh --restart replaces it)"
  else
    bad "port $PORT: held by a non-ghostpanel process"; fails=$((fails + 1))
  fi
  if [[ -x "$VENV_PY" ]] && "$VENV_PY" -m pytest "$ROOT/tests/test_contracts.py" -q; then
    ok "contract tests PASS"
  else
    bad "contract tests FAIL"; fails=$((fails + 1))
  fi
  echo
  if [[ "$fails" -eq 0 ]]; then ok "doctor: all checks passed"; else die "doctor: $fails check(s) failed"; fi
}

cmd_run() {
  find_python || exit 1
  ensure_venv || exit 1
  ensure_deps || exit 1
  ensure_chromium || exit 1
  ensure_web || exit 1
  load_env
  check_app_port
  trap cleanup EXIT INT TERM
  start_fixtures
  start_server
  wait_healthy
  banner
  if [[ "$BACKGROUND" -eq 1 ]]; then
    trap - EXIT INT TERM   # leave the detached servers running
  else
    wait "$SERVER_PID"
  fi
}

mkdir -p "$RUN_DIR"
echo '*' >"$RUN_DIR/.gitignore"   # never commit pids/logs

case "$CMD" in
  doctor) cmd_doctor ;;
  stop) cmd_stop ;;
  run) cmd_run ;;
esac
