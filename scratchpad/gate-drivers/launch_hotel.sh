#!/bin/zsh
# Reusable Hotel #6 launcher (fb14srv4), replacing the copy-and-edit launch_hotel6r<N>.sh series.
# Written 2026-09-24 from research/LAUNCHER_STABILITY_LEDGER_20260924.md; each guard was bought by a lost attempt:
#   - previous run discovered on the host (exactly one hotel-v1-* dir), and its local archive must exist
#     before its one-shot host paths are moved (evidence is secured first; moves only, never deletes)
#   - SETUP-CAMPAIGN renewed if expired/drifted, but only onto EXPECTED_PLAN (Hotel's shared driver is
#     fail-closed; renewal typed by Claude under the TEMP delegation, like launch_otel_run3.sh)
#   - host: zero containers, empty compose listing (host condition v2), >= 40 GB free; stdout only
#   - stranded local run-phase state archived before oneshot and after a failed one (hotel6r6 lost its
#     first oneshot to run 5's gate-run.json, 2026-09-24 01:20Z)
#   - oneshot --reuse-install (install is one-shot on the host); watcher cap = run_window_hours + 1
#   - DRY_RUN=1 runs every guard and stops before the first mutation
# Start:  nohup caffeinate -i zsh scratchpad/gate-drivers/launch_hotel.sh <label> > scratchpad/gate-drivers/hotel-<label>.out 2>&1 &
# Test:   DRY_RUN=1 zsh scratchpad/gate-drivers/launch_hotel.sh dry
set -u
LABEL=${1:?usage: launch_hotel.sh <label, e.g. r7>}
DRY_RUN=${DRY_RUN:-0}
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
# ponytail: HOTEL_ROOT/COMPILER select another epoch tree (traffic sweep 2026-10-03); defaults stay the srv4 tree.
R=${HOTEL_ROOT:-$M/../observability-placement-runtime-hotel-srv4}
COMPILER=${COMPILER:-candidate_pilot.py}
H=$R/modules/hotel-reservation/drivers
G=$R/.local/candidate-v4/hotel-reservation/gates
LOG=$M/scratchpad/gate-drivers/hotel-$LABEL-launch.log
export PYTHONPATH=$R/src
PY=/opt/homebrew/bin/python3.13
# ponytail: env overrides for the LMT+S pilot branch (plan a0f21b56..., 80 cells); defaults stay Hotel #6.
EXPECTED_PLAN=${EXPECTED_PLAN:-ac60dbbc0455d0ff624626e5926594e9bfb79914003ad527b2a96e01a1835d34}
RUN_COUNT=${RUN_COUNT:-54}
HOST=fb14srv4
A_ROOT=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
P_ROOT=/home/fhuebscher/observability-placement-candidate-v4-hotel-srv4
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
log(){ echo "$(date -u +%H:%M:%SZ) $*" >> "$LOG"; }
remote(){ ssh -o BatchMode=yes -o ConnectTimeout=15 $HOST "$@" 2>/dev/null | grep -v '^\*'; }
archive_run_state(){  # $1 = reason
  local A=$G/archived-run-state-$1-$(date -u +%Y%m%dT%H%M%SZ) moved=""
  for f in gate-run.json campaign-terminal.json run-authorization.json run-authorization-receipt.json campaign-result; do
    [ -e "$G/$f" ] && { mkdir -p "$A"; mv "$G/$f" "$A/"; moved="$moved $f"; }
  done
  log "local run-phase state archived ($1):${moved:- nothing to archive}"
}

log "=== hotel launcher $LABEL (HEAD $(git -C "$R" rev-parse --short HEAD) on $(git -C "$R" branch --show-current), plan $EXPECTED_PLAN, $RUN_COUNT cells, dry=$DRY_RUN) ==="
case "$(ps -o comm= -p $PPID 2>/dev/null)" in *caffeinate*) ;; *) [ "$DRY_RUN" = 1 ] || log "WARN: not under caffeinate; the laptop may sleep mid-campaign";; esac

# --- tree and plan ---
[ -z "$(git -C "$R" status --porcelain -uall)" ] || { log "ABORT: hotel runtime tree dirty"; exit 7; }
grep -q "$EXPECTED_PLAN" "$R/modules/hotel-reservation/execution/$COMPILER" || { log "ABORT: compiler does not pin the $RUN_COUNT-cell plan digest $EXPECTED_PLAN"; exit 8; }
"$PY" "$R/modules/hotel-reservation/execution/$COMPILER" | grep -q "\"runCount\": $RUN_COUNT" || { log "ABORT: compiled plan is not $RUN_COUNT cells"; exit 8; }

# ponytail: an ssh failure reads as "0 previous runs"; refuse before discovery (2026-09-24 VPN drop)
remote "echo UP" | grep -q UP || { log "ABORT: $HOST unreachable (VPN?); discovery would read an ssh failure as no previous run"; exit 5; }

# --- previous run: discovered on the host, secured locally before anything moves ---
runs=$(remote "ls -d $A_ROOT/hotel-v1-*/ 2>/dev/null | xargs -n1 basename 2>/dev/null")
nruns=$(printf '%s\n' "$runs" | grep -c 'hotel-v1-')
log "previous runs on host: $nruns [$(echo $runs | tr '\n' ' ')]"
if [ "$nruns" = 1 ]; then
  PREV=$runs
  [ -s "$M/tmp/hotel6-evidence/$PREV.tgz" ] || { log "ABORT: previous run $PREV is not archived locally (tmp/hotel6-evidence/$PREV.tgz)"; exit 9; }
elif [ "$nruns" != 0 ]; then log "ABORT: expected at most one previous run on the host"; exit 9; fi

# --- host guards, stdout only ---
states=$(remote 'echo "containers=$(docker ps -a -q | wc -l | tr -d " ") compose=$(docker compose ls --all --format json)"' | tr '\n' ' ')
free=$(remote "df -BG --output=avail / | tail -1" | tr -dc 0-9)
log "host preflight: $states free GB=$free"
echo "$states" | grep -q "containers=0 compose=\[\]" || { log "ABORT: host is not at zero containers / empty compose listing (host condition v2)"; exit 6; }
[ -n "$free" ] && [ "$free" -ge 40 ] || { log "ABORT: $HOST free space unknown or < 40 GB"; exit 5; }

# --- SETUP-CAMPAIGN: live and matching, else renew onto the expected plan only ---
st=$("$PY" "$H/campaign_setup.py" status 2>&1); log "setup-campaign status: $(echo $st | tr '\n' ' ')"
if ! { echo "$st" | grep -q "live=True" && echo "$st" | grep -q "invariants match=True"; }; then
  [ "$DRY_RUN" = 1 ] && { log "DRY: would renew SETUP-CAMPAIGN onto $EXPECTED_PLAN"; } || {
    prop=$("$PY" "$H/campaign_setup.py" propose-campaign 2>&1); echo "$prop" >> "$LOG"
    sentence=$(echo "$prop" | grep '^APPROVE SETUP-CAMPAIGN ')
    [[ "$sentence" == *"plan=$EXPECTED_PLAN "* ]] || { log "ABORT: proposed plan is not $EXPECTED_PLAN"; exit 4; }
    [ -f "$G/setup-campaign-authorization.json" ] && cp -p "$G/setup-campaign-authorization.json" "$G/archived-setup-campaign-authorization-$STAMP.json"
    "$PY" "$H/campaign_setup.py" authorize-campaign --typed "$sentence" >> "$LOG" 2>&1 || { log "ABORT: authorize-campaign failed"; exit 4; }
    log "SETUP-CAMPAIGN renewed onto $EXPECTED_PLAN (typed by Claude under the TEMP delegation)"
  }
fi
[ "$DRY_RUN" = 1 ] && { log "DRY RUN: all guards passed; stopping before the first mutation"; exit 0; }

# --- move the previous run's one-shot host paths aside (archive only) ---
if [ "$nruns" = 1 ]; then
  moved=$(remote "set -e; P=$P_ROOT; A=$A_ROOT; L=\$(dirname \$A)/.hotel-candidate-v1.lock; [ -e \$P ] && mv \$P \$P.$PREV-$STAMP; mv \$A \$A.$PREV-$STAMP; [ -e \$L ] && mv \$L \$A.$PREV-$STAMP/hotel-candidate-v1.lock.prev; echo MOVED" | tr '\n' ' ')
  log "host paths: $moved"
  echo "$moved" | grep -q MOVED || { log "ABORT: could not move the previous run's host paths"; exit 6; }
fi
archive_run_state "before-$LABEL"

log "=== hotel auto (bundle, upload, one-shot install, readiness) ==="
"$PY" "$H/campaign_setup.py" auto >> "$LOG" 2>&1; rc=$?; log "auto rc=$rc"; [ $rc -eq 0 ] || exit $rc
log "=== hotel oneshot --reuse-install ==="
"$PY" "$H/gate_run.py" oneshot --reuse-install >> "$LOG" 2>&1; rc=$?; log "oneshot rc=$rc"
if [ $rc -ne 0 ]; then
  running=$(remote 'docker ps --format "{{.Names}}" | grep -c hotel_candidate || true' | tail -1)
  log "oneshot failed locally; hotel_candidate containers on host: $running"
  [ "${running:-0}" -gt 0 ] || { archive_run_state "failed-oneshot-$LABEL"; exit $rc; }
fi
CAP_H=$(( $("$PY" -c "import sys; sys.path.insert(0,'$H'); from gate_driver_config import CONFIG; print(CONFIG.run_window_hours)") + 1 ))
log "=== hotel watcher (cap ${CAP_H} h = run_window_hours + 1) ==="
WEND=$(( $(date -u +%s) + CAP_H*3600 ))
while true; do
  line=$("$PY" "$H/campaign_status.py" 2>&1); rc=$?; log "hotel-$LABEL $line"
  # ponytail: an unreachable host polls as state=unknown with rc 3 (shared poll_once); not terminal, keep waiting (2026-09-24 07:36Z VPN drop)
  if [ "$rc" -eq 3 ] && echo "$line" | grep -qi "state=unknown"; then log "UNREACHABLE (not terminal): $line"; sleep 300; continue; fi
  [ "$rc" -eq 3 ] && { log "HOTEL $LABEL TERMINAL: $line"; exit 0; }
  [ "$(date -u +%s)" -ge "$WEND" ] && { log "WATCH-CAP ${CAP_H}h: $line"; exit 0; }
  sleep 300
done
