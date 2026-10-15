#!/bin/zsh
# OTel Demo offpath launcher (fb14srv6, direction (c)): launch_otel.sh with the worktree, epoch,
# plan and cell count changed. Declaration research/otel-offpath/DECLARATION.md (8194d74; errata
# 24d3b5f, ff65eea). Harness: branch otel-offpath-20261001 in tmp/otel-offpath (frozen at 92be2b7 after the review fixes).
# NO LAUNCH UNTIL THE USER APPROVES THE BUILT HARNESS AND THE DECLARATION (declaration header), and
# erratum 2 defers the fault redesign (hold, scenario, export interval) to the user: a non-dry run
# also needs OFFPATH_APPROVED=1, which only the user's go sets. A redesign changes the descriptor and
# so EXPECTED_PLAN: re-derive it (candidate_pilot.py --emit-offpath-descriptor) and pass it here.
# Guards carried over from launch_otel.sh / launch_otel_run3.sh / launch_hotel.sh:
#   - HEAD of the runtime worktree must equal the frozen commit passed as $2 (drivers read ROOT = that tree)
#   - tracked files clean and none missing (tmp/ reaping); untracked files tolerated, as in runs 1-3
#   - the pure compiler must reproduce EXPECTED_PLAN with RUN_COUNT cells for OTEL_CANDIDATE_ATTEMPT,
#     computed in memory (no plan dir is written before the first mutation)
#   - host: no campaign unit, 0 containers, srv6 lease unheld, >= 40 GB free, and the v3 one-shot host
#     paths absent; stdout only, never parse ssh stderr (the login banner)
#   - the posture-probe receipt must be PROBE OK (bound to probe-script bytes + upstream pin; unchanged by v3)
#   - stranded run-phase state (run 3's gate-run.json etc.) archived via gate_run.py archive-run, and the
#     previous plan dir moved aside (materialize() refuses a retained plan that differs)
#   - SETUP-CAMPAIGN renewed if expired/drifted, but only onto EXPECTED_PLAN (OTel's shared driver is
#     fail-closed; renewal typed by Claude under the TEMP delegation, like launch_otel_run3.sh)
#   - auto -> oneshot --reuse-install -> watcher; cap = run_window_hours + 1 (11 + 1 = 12 h for 36 cells)
#   - the campaign itself stops before any fault cell if the first no-fault full cell's traced
#     checkout paths differ from the selected literal (workload-path-check.json at the artifact root)
#   - DRY_RUN=1 runs every guard (local and read-only ssh) and stops before the first mutation
# Starting this script without DRY_RUN IS the human authorization for the run (CLAUDE.md).
# ponytail: env overrides for the OTel traffic sweep (2026-10-03, research/traffic-sweep/HARNESS_CHANGE_OTEL.md);
# defaults stay offpath. COMPILER = the compiler file the plan check runs (candidate_sweep.py for the sweep);
# LOG_PREFIX names the log; LAUNCH_APPROVED=1 is the non-offpath spelling of OFFPATH_APPROVED=1. The drivers'
# study must equal $CAMPAIGN (the selector in the tree decides it), checked before any host contact.
# Sweep:  DRY_RUN=1 OTEL_WORKTREE=$M/../observability-placement-runtime-otel-protocol COMPILER=candidate_sweep.py \
#           EXPECTED_PLAN=<plan> RUN_COUNT=12 CAMPAIGN=otel-traffic-sweep-v1 LOG_PREFIX=otel-sweep \
#           zsh scratchpad/gate-drivers/launch_otel_offpath.sh sweepdry <frozen-commit>
# Test:   DRY_RUN=1 zsh scratchpad/gate-drivers/launch_otel_offpath.sh offdry <frozen-commit>
# Start:  OFFPATH_APPROVED=1 nohup caffeinate -i zsh scratchpad/gate-drivers/launch_otel_offpath.sh offr1 <frozen-commit> \
#           > scratchpad/gate-drivers/otel-offr1.out 2>&1 &
set -u
LABEL=${1:?usage: launch_otel_offpath.sh <label> <frozen 40-hex commit>}
FROZEN=${2:?usage: launch_otel_offpath.sh <label> <frozen 40-hex commit>}
DRY_RUN=${DRY_RUN:-0}
OFFPATH_APPROVED=${OFFPATH_APPROVED:-0}
LAUNCH_APPROVED=${LAUNCH_APPROVED:-0}
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
WT=${OTEL_WORKTREE:-$M/tmp/otel-offpath}
# Defaults: offpath attempt 1, the declared fault design (fraud-pause 15 s at 45 s, frontend-pause control).
export OTEL_CANDIDATE_ATTEMPT=${OTEL_CANDIDATE_ATTEMPT:-1}
EXPECTED_PLAN=${EXPECTED_PLAN:-168699c4d78a50766655254a58612b9ef0caf1ad91480b79852752bc933a47cc}
RUN_COUNT=${RUN_COUNT:-36}
CAMPAIGN=${CAMPAIGN:-otel-demo-offpath-v1}
COMPILER=${COMPILER:-candidate_pilot.py}
LOG_PREFIX=${LOG_PREFIX:-otel-offpath}
HOST=fb14srv6
D=$WT/modules/otel-demo/drivers
G=$WT/.local/candidate-v4/otel-demo/gates
P=$WT/.local/candidate-v4/otel-demo/plan
ARUNS=/home/stig/observability-placement-candidate-v4-runs
RELS=/home/stig/observability-placement-candidate-v4-otel-srv6
LOG=$M/scratchpad/gate-drivers/$LOG_PREFIX-$LABEL-launch.log
PY=/opt/homebrew/bin/python3.13
export PYTHONPATH=$WT/src
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
log(){ echo "$(date -u +%H:%M:%SZ) $*" >> "$LOG"; }
remote(){ ssh -o BatchMode=yes -o ConnectTimeout=15 root@$HOST "$@" 2>/dev/null; }

cd "$WT" || exit 9
[ "$DRY_RUN" = 1 ] || [ "$OFFPATH_APPROVED" = 1 ] || [ "$LAUNCH_APPROVED" = 1 ] || { log "ABORT: offpath needs the user's approval (OFFPATH_APPROVED=1 or LAUNCH_APPROVED=1) before a non-dry run"; exit 10; }
[ "$WT" != "$M/tmp/otel-v2-admission" ] || { log "ABORT: refusing to drive the v3 worktree from the offpath launcher"; exit 9; }
log "=== otel offpath launcher $LABEL (HEAD $(git rev-parse HEAD) on $(git branch --show-current), compiler $COMPILER, plan $EXPECTED_PLAN, $RUN_COUNT cells, attempt $OTEL_CANDIDATE_ATTEMPT, dry=$DRY_RUN) ==="
case "$(ps -o comm= -p $PPID 2>/dev/null)" in *caffeinate*) ;; *) [ "$DRY_RUN" = 1 ] || log "WARN: not under caffeinate; the laptop may sleep mid-campaign";; esac

# --- tree and plan (local, no writes) ---
[[ "$FROZEN" =~ '^[0-9a-f]{40}$' ]] || { log "ABORT: frozen commit is not 40 hex"; exit 8; }
[ "$(git rev-parse HEAD)" = "$FROZEN" ] || { log "ABORT: HEAD is not the frozen commit $FROZEN"; exit 8; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { log "ABORT: tracked files dirty"; exit 7; }
[ "$(git ls-files -d | wc -l | tr -dc 0-9)" = 0 ] || { log "ABORT: tracked files missing (tmp/ reaping?)"; exit 7; }
log "untracked files (tolerated, as in runs 1-3): $(git status --porcelain | grep -c '^??')"
plan=$("$PY" - "$WT" "$COMPILER" <<'EOF' 2>>"$LOG"
import importlib.util, os, sys
root, compiler = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("p", f"{root}/modules/otel-demo/execution/{compiler}")
p = importlib.util.module_from_spec(spec); sys.modules["p"] = p; spec.loader.exec_module(p)
plan = p.compile_plan(p.load_descriptor(p.DEFAULT_DESCRIPTOR), p.campaign_attempt())
print(p.EPOCH, plan["runCount"], p.canonical_sha256(plan))
print("fault design", p.load_descriptor(p.DEFAULT_DESCRIPTOR)["faultDesign"], file=sys.stderr)
EOF
)
log "compiled: $plan"
[ "$plan" = "$CAMPAIGN $RUN_COUNT $EXPECTED_PLAN" ] || { log "ABORT: compiler does not reproduce $CAMPAIGN / $RUN_COUNT cells / $EXPECTED_PLAN"; exit 8; }
# The drivers read ROOT = $WT and its committed selector: their study must be the campaign compiled above.
drv=$("$PY" -c "import sys; sys.path.insert(0,'$D'); from gate_driver_config import CONFIG; print(CONFIG.study, CONFIG.campaign_id, CONFIG.run_window_hours, CONFIG.root)" 2>>"$LOG")
log "drivers: $drv"
drvw=(${=drv})
[ "${drvw[1]-}" = "$CAMPAIGN" ] && [ "${drvw[2]-}" = "$CAMPAIGN" ] && [ "${drvw[4]-}" = "$(pwd -P)" ] || { log "ABORT: drivers (study, campaign, window, ROOT) are not $CAMPAIGN at $(pwd -P): $drv"; exit 8; }

# --- probe receipt (bound to probe-script bytes and the upstream pin; must be recorded in THIS worktree's gates) ---
"$PY" - "$G/posture-probe-receipt.json" >> "$LOG" 2>&1 <<'EOF' || { log "ABORT: posture-probe receipt is not PROBE OK"; exit 4; }
import json, sys
r = json.load(open(sys.argv[1]))
assert r["result"] == "PROBE OK" and r["disabledOtlpConnections"] == 0 and r["enabledOtlpConnections"] > 0, r
print("probe receipt", r["recordedAt"], r["frameworkCommit"][:12], r["disabledOtlpConnections"], r["enabledOtlpConnections"])
EOF

# ponytail: an ssh failure reads as "0 units / 0 containers"; refuse before the host guards (2026-09-24 VPN drop)
remote "echo UP" | grep -q UP || { log "ABORT: $HOST unreachable (VPN? fail2ban?)"; exit 5; }

# --- host guards, stdout only ---
units=$(remote "systemctl list-units --state=running,activating --no-legend --plain | grep -ciE 'otel_candidate|candidate-v4|teastore|hotel|boutique'" | tr -dc 0-9)
containers=$(remote "docker ps -q | wc -l" | tr -dc 0-9)
holders=$(remote "fuser $ARUNS/.srv6-runtime.lock 2>/dev/null; true" | tr -dc '0-9 ' | xargs)
free=$(remote "df -BG --output=avail / | tail -1" | tr -dc 0-9)
mine=$(remote "ls -d $ARUNS/$CAMPAIGN $ARUNS/.setup-$CAMPAIGN $RELS/$CAMPAIGN-* 2>/dev/null | wc -l" | tr -dc 0-9)
log "host $HOST: running units=$units containers=$containers lease holders=[$holders] free GB=$free $CAMPAIGN paths=$mine"
[ "$units" = 0 ] || { log "ABORT: a campaign unit is running on $HOST"; exit 6; }
[ "$containers" = 0 ] || { log "ABORT: containers are running on $HOST"; exit 6; }
[ -z "$holders" ] || { log "ABORT: the srv6 lease is held by [$holders]"; exit 6; }
[ -n "$free" ] && [ "$free" -ge 40 ] || { log "ABORT: $HOST free space unknown or < 40 GB"; exit 5; }
[ "$mine" = 0 ] || { log "ABORT: $CAMPAIGN one-shot host paths already exist (spent attempt? archive them first)"; exit 4; }

if [ "$DRY_RUN" = 1 ]; then
  # campaign_setup.py status calls inspect_campaign, which materializes (or byte-verifies) the plan
  # dir -- a local write, and a refusal while run 3's v2 plan dir is still retained. Not read here.
  log "DRY: would archive run-phase state and the plan dir, read SETUP-CAMPAIGN status, and renew it onto $EXPECTED_PLAN if expired/drifted (worktree $WT)"
  log "DRY RUN: all guards passed; stopping before the first mutation"; exit 0
fi

# --- archive stranded local state (archive, never delete) ---
"$PY" "$D/gate_run.py" archive-run >> "$LOG" 2>&1 || { log "ABORT: archive-run failed"; exit 3; }
[ -d "$P" ] && mv "$P" "$WT/.local/candidate-v4/otel-demo/archived-plan-$STAMP" && log "archived plan dir -> archived-plan-$STAMP"
for f in gate-run.json run-authorization.json run-authorization-receipt.json; do
  [ -e "$G/$f" ] && { log "ABORT: $f survived archive-run"; exit 3; }
done

# --- SETUP-CAMPAIGN: live and matching, else renew onto the expected plan only ---
st=$("$PY" "$D/campaign_setup.py" status 2>&1); log "setup-campaign status: $(echo $st | tr '\n' ' ')"
if ! { echo "$st" | grep -q "live=True" && echo "$st" | grep -q "invariants match=True"; }; then
  prop=$("$PY" "$D/campaign_setup.py" propose-campaign 2>&1); echo "$prop" >> "$LOG"
  sentence=$(echo "$prop" | grep '^APPROVE SETUP-CAMPAIGN ')
  [[ "$sentence" == *"plan=$EXPECTED_PLAN "* ]] || { log "ABORT: proposed plan is not $EXPECTED_PLAN"; exit 4; }
  [ -f "$G/setup-campaign-authorization.json" ] && cp -p "$G/setup-campaign-authorization.json" "$G/archived-setup-campaign-authorization-$STAMP.json"
  "$PY" "$D/campaign_setup.py" authorize-campaign --typed "$sentence" >> "$LOG" 2>&1 || { log "ABORT: authorize-campaign failed"; exit 4; }
  log "SETUP-CAMPAIGN renewed onto $EXPECTED_PLAN (typed by Claude under the TEMP delegation)"
fi

log "=== auto ==="
"$PY" "$D/campaign_setup.py" auto >> "$LOG" 2>&1; rc=$?; log "auto rc=$rc"; [ $rc -eq 0 ] || exit $rc
log "=== oneshot --reuse-install ==="
"$PY" "$D/gate_run.py" oneshot --reuse-install >> "$LOG" 2>&1; rc=$?; log "oneshot rc=$rc"
if [ $rc -ne 0 ]; then
  # A failed oneshot strands gate-run.json and the next one dies on "refusing to overwrite".
  "$PY" "$D/gate_run.py" archive-run >> "$LOG" 2>&1
  log "oneshot failed; run-phase state archived; one relaunch after a fix at most (DECLARATION.md stop rule)"
  exit $rc
fi
CAP_H=$(( $("$PY" -c "import sys; sys.path.insert(0,'$D'); from gate_driver_config import CONFIG; print(CONFIG.run_window_hours)") + 1 ))
log "=== watcher (cap ${CAP_H} h = run_window_hours + 1); check the first 4 cells on the host (stop rule) ==="
WEND=$(( $(date -u +%s) + CAP_H*3600 ))
while true; do
  line=$("$PY" "$D/campaign_status.py" 2>&1); rc=$?; log "otel-$LABEL rc=$rc $line"
  # ponytail: an unreachable host polls as state=unknown with rc 3 (shared poll_once); not terminal, keep waiting (2026-09-24 07:36Z VPN drop)
  if [ "$rc" -eq 3 ] && echo "$line" | grep -qi "state=unknown"; then log "UNREACHABLE (not terminal): $line"; sleep 300; continue; fi
  [ "$rc" -eq 3 ] && { log "OTEL $LABEL TERMINAL: $line"; exit 0; }
  [ "$(date -u +%s)" -ge "$WEND" ] && { log "WATCH-CAP ${CAP_H}h reached (the campaign may still be running; check the host): $line"; exit 0; }
  sleep 300
done
