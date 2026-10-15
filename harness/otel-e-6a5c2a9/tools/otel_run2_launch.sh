#!/bin/zsh
# OTel Demo run 2 launcher (attempt 2, fb14srv6). Modelled on
# scratchpad/gate-drivers/launch_teastore14.sh in the main repository.
#
#   nohup caffeinate -i zsh tools/otel_run2_launch.sh <frozen-commit> \
#     > .local/candidate-v4/otel-demo/driver-scratch/run2-launch.out 2>&1 &
#
# Starting this script IS the human authorization for run 2 (CLAUDE.md: auto
# re-derives SETUP-CAMPAIGN, oneshot derives GATE-RUN). It must only be started
# after (1) the run-2 freeze and the user-approved prediction are committed, and
# (2) tools/otel_run1_archive_reset.sh --archive has moved run 1's host paths.
# It refuses rather than doing (2) itself.
#
# ponytail: order and guards, each one bought by a lost attempt elsewhere:
#   - HEAD must equal the frozen commit passed as $1 (drivers read ROOT = this tree)
#   - attempt 2 by default, never 1 (the driver refuses a spent attempt anyway)
#   - host idle, lease unheld, >= 40 GB free, run-1 paths already archived:
#     stdout only, never parse ssh stderr (the login banner)
#   - archive stranded run-phase state (gate-run.json, run-authorization*,
#     campaign-result) via gate_run.py archive-run, and the attempt-1 plan dir,
#     which materialize() would otherwise refuse as "retained compiled plan differs"
#   - auto -> oneshot -> watcher; the watcher cap is 5 h: run 1 took 3.91 h for 18
#     cells, run 2 adds the unrotated carrier (~120-210 MB of otelcol.log per cell,
#     an estimate), and the GATE-RUN window is 5 h (gate_driver_config.run_window_hours)
set -u
FROZEN=${1:?usage: otel_run2_launch.sh <frozen 40-hex commit>}
export OTEL_CANDIDATE_ATTEMPT=${OTEL_CANDIDATE_ATTEMPT:-2}
HOST=fb14srv6
WT=${0:A:h:h}
D=$WT/modules/otel-demo/drivers
G=$WT/.local/candidate-v4/otel-demo/gates
P=$WT/.local/candidate-v4/otel-demo/plan
SCRATCH=$WT/.local/candidate-v4/otel-demo/driver-scratch
mkdir -p "$SCRATCH"
LOG=$SCRATCH/run2-launch-$(date -u +%Y%m%dT%H%M%SZ).log
PY=/opt/homebrew/bin/python3.13
export PYTHONPATH=$WT/src
log(){ echo "$(date -u +%H:%M:%SZ) $*" >> "$LOG"; }
remote(){ ssh -o BatchMode=yes -o ConnectTimeout=15 root@$HOST "$@" 2>/dev/null; }

cd "$WT" || exit 9
log "=== OTel run 2 launcher (HEAD $(git rev-parse HEAD), attempt $OTEL_CANDIDATE_ATTEMPT) ==="
[[ "$FROZEN" =~ '^[0-9a-f]{40}$' ]] || { log "ABORT: frozen commit is not 40 hex"; exit 8; }
[ "$(git rev-parse HEAD)" = "$FROZEN" ] || { log "ABORT: HEAD is not the frozen commit $FROZEN"; exit 8; }
[ "$OTEL_CANDIDATE_ATTEMPT" != 1 ] || { log "ABORT: attempt 1 is spent (run 1)"; exit 8; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { log "ABORT: tracked files dirty"; exit 7; }
[ "$(git ls-files -d | wc -l | tr -dc 0-9)" = 0 ] || { log "ABORT: tracked files missing (tmp/ reaping?)"; exit 7; }
log "untracked files (tolerated, as in run 1): $(git status --porcelain | grep -c '^??')"

# --- host guards, stdout only ---
units=$(remote "systemctl list-units --state=running,activating --no-legend --plain | grep -ciE 'otel_candidate|candidate-v4|teastore|hotel|boutique'" | tr -dc 0-9)
containers=$(remote "docker ps -q | wc -l" | tr -dc 0-9)
holders=$(remote "fuser /home/stig/observability-placement-candidate-v4-runs/.srv6-runtime.lock 2>/dev/null; true" | tr -dc '0-9 ' | xargs)
free=$(remote "df -BG --output=avail / | tail -1" | tr -dc 0-9)
run1=$(remote "ls -d /home/stig/observability-placement-candidate-v4-runs/otel-demo-candidate-pilot-v2 /home/stig/observability-placement-candidate-v4-runs/.setup-otel-demo-candidate-pilot-v2 /home/stig/observability-placement-candidate-v4-otel-srv6/otel-demo-candidate-pilot-v2-* 2>/dev/null | wc -l" | tr -dc 0-9)
log "host $HOST: running units=$units containers=$containers lease holders=[$holders] free GB=$free run-1 paths=$run1"
[ "$units" = 0 ] || { log "ABORT: a campaign unit is running on $HOST (or ssh failed)"; exit 6; }
[ "$containers" = 0 ] || { log "ABORT: containers are running on $HOST (or ssh failed)"; exit 6; }
[ -z "$holders" ] || { log "ABORT: the srv6 lease is held by [$holders]"; exit 6; }
[ -n "$free" ] && [ "$free" -ge 40 ] || { log "ABORT: $HOST free space unknown or < 40 GB"; exit 5; }
[ "$run1" = 0 ] || { log "ABORT: run 1's host paths are still present; run tools/otel_run1_archive_reset.sh --archive"; exit 4; }

# --- probe receipt must be the one taken at the frozen framework's probe bytes ---
$PY - "$G/posture-probe-receipt.json" >> "$LOG" 2>&1 <<'EOF' || { log "ABORT: posture-probe receipt is not PROBE OK"; exit 4; }
import json, sys
r = json.load(open(sys.argv[1]))
assert r["result"] == "PROBE OK" and r["disabledOtlpConnections"] == 0 and r["enabledOtlpConnections"] > 0, r
print("probe receipt", r["recordedAt"], r["frameworkCommit"][:12], r["disabledOtlpConnections"], r["enabledOtlpConnections"])
EOF

# --- archive stranded local state (archive, never delete) ---
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
$PY "$D/gate_run.py" archive-run >> "$LOG" 2>&1 || { log "ABORT: archive-run failed"; exit 3; }
if [ -d "$P" ]; then
  mv "$P" "$WT/.local/candidate-v4/otel-demo/archived-plan-$STAMP" && log "archived plan dir -> archived-plan-$STAMP"
fi
for f in gate-run.json run-authorization.json run-authorization-receipt.json; do
  [ -e "$G/$f" ] && { log "ABORT: $f survived archive-run"; exit 3; }
done
log "local run-phase state archived"

log "=== auto ==="
$PY "$D/campaign_setup.py" auto >> "$LOG" 2>&1; rc=$?; log "auto rc=$rc"; [ $rc -eq 0 ] || exit $rc
log "=== oneshot ==="
$PY "$D/gate_run.py" oneshot >> "$LOG" 2>&1; rc=$?; log "oneshot rc=$rc"
if [ $rc -ne 0 ]; then
  # A failed oneshot strands gate-run.json and the next one dies on "refusing to
  # overwrite"; archive now so the stranding cannot mislead the retry.
  $PY "$D/gate_run.py" archive-run >> "$LOG" 2>&1
  log "oneshot failed; run-phase state archived; retry only for a transport or VPN failure (stop rule)"
  exit $rc
fi
log "=== watcher (cap 5 h) ==="
WEND=$(( $(date -u +%s) + 5*3600 ))
while true; do
  line=$($PY "$D/campaign_status.py" 2>&1); rc=$?; log "otel-run2 rc=$rc $line"
  [ "$rc" -eq 3 ] && { log "OTEL RUN 2 TERMINAL: $line"; exit 0; }
  [ "$(date -u +%s)" -ge "$WEND" ] && { log "WATCH-CAP 5h reached (the campaign may still be running; check the host): $line"; exit 0; }
  sleep 300
done
