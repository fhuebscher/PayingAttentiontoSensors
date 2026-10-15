#!/bin/zsh
# Reusable TeaStore launcher (fb14srv5, commit f352f8d, descriptor 76fb72a6, 27 cells), replacing the
# copy-and-edit launch_teastore<N>.sh series. Written 2026-09-24 from research/LAUNCHER_STABILITY_LEDGER_20260924.md.
#   - HEAD must be f352f8d; tree clean; previous campaign terminal; srv5 >= 40 GB free (stdout only)
#   - the previous campaign's run state is archived at start AND after a failed oneshot (stranded gate-run.json trap)
#   - `auto` re-derives an expired SETUP-CAMPAIGN itself (TeaStore's driver, recorded as auto-derived)
#   - DRY_RUN=1 runs every guard and stops before the first mutation
# Start: nohup caffeinate -i zsh scratchpad/gate-drivers/launch_teastore.sh <label> > scratchpad/gate-drivers/teastore-<label>.out 2>&1 &
# Test:  DRY_RUN=1 zsh scratchpad/gate-drivers/launch_teastore.sh dry
# ponytail: env overrides select another tree / epoch (traffic sweep 2026-10-03); unset, every default is the
# #13 launcher's. TEASTORE_ROOT is exported, so every driver (teastore_driver_root.py) reads the same tree.
#   TEASTORE_ROOT       tree the drivers read (default: tmp/observability-placement-runtime-teastore-v4-reviewed2)
#   EXPECTED_HEAD       commit TEASTORE_ROOT must be at (default: #13's f352f8d)
#   TEASTORE_PREV_ROOT  tree whose last campaign must be terminal (default: TEASTORE_ROOT's default tree)
#   TEASTORE_PREV_PACKAGE  that campaign's runtime package when its run state was archived (default: the live one)
#   COMPILER, EXPECTED_PLAN, RUN_COUNT  if COMPILER is set: the compiler must pin EXPECTED_PLAN and compile RUN_COUNT
set -u
LABEL=${1:?usage: launch_teastore.sh <label, e.g. 16>}
DRY_RUN=${DRY_RUN:-0}
M=/Users/fhuebscher/Desktop/ma_thesis/oltp-submodularity-evaluation/observability-placement
D=$M/scratchpad/gate-drivers
LOG=$D/teastore-$LABEL-launch.log
log(){ echo "$(date -u +%H:%M:%SZ) $*" >> "$LOG"; }
DEFAULT_ROOT=$M/tmp/observability-placement-runtime-teastore-v4-reviewed2
R=${TEASTORE_ROOT:-$DEFAULT_ROOT}
EXPECTED_HEAD=${EXPECTED_HEAD:-f352f8d031dbcd49280cb11d104501694a9e4a8f}
PREV_ROOT=${TEASTORE_PREV_ROOT:-$DEFAULT_ROOT}
COMPILER=${COMPILER:-}
cd "$R" || { log "ABORT: teastore worktree missing"; exit 9; }
export TEASTORE_ROOT=$R
log "=== teastore launcher $LABEL (ROOT $R, HEAD $(git rev-parse --short HEAD), dry=$DRY_RUN) ==="
case "$(ps -o comm= -p $PPID 2>/dev/null)" in *caffeinate*) ;; *) [ "$DRY_RUN" = 1 ] || log "WARN: not under caffeinate; the laptop may sleep mid-campaign";; esac
[ "$(git rev-parse HEAD)" = "$EXPECTED_HEAD" ] || { log "ABORT: HEAD is not the expected commit $EXPECTED_HEAD"; exit 8; }
ts=$(TEASTORE_ROOT=$PREV_ROOT TEASTORE_STATUS_PACKAGE=${TEASTORE_PREV_PACKAGE:-} /usr/bin/python3 "$D/campaign_status.py" 2>&1); tsrc=$?; log "previous campaign status ($PREV_ROOT ${TEASTORE_PREV_PACKAGE:-live package}): $ts"
[ "$tsrc" -eq 3 ] || { log "ABORT: previous TeaStore campaign not terminal (rc=$tsrc)"; exit 6; }
[ -z "$(git status --porcelain -uall)" ] || { log "ABORT: teastore tree dirty"; exit 7; }
if [ -n "$COMPILER" ]; then
  EXPECTED_PLAN=${EXPECTED_PLAN:?EXPECTED_PLAN is required with COMPILER}; RUN_COUNT=${RUN_COUNT:?RUN_COUNT is required with COMPILER}
  grep -q "$EXPECTED_PLAN" "$R/modules/teastore/execution/$COMPILER" || { log "ABORT: compiler does not pin the $RUN_COUNT-cell plan digest $EXPECTED_PLAN"; exit 8; }
  compiled=$(/usr/bin/python3 -I "$R/modules/teastore/execution/$COMPILER" 2>&1)
  echo "$compiled" | grep -q "\"runCount\": $RUN_COUNT" && echo "$compiled" | grep -q "\"planCanonicalSha256\": \"$EXPECTED_PLAN\"" || { log "ABORT: compiled plan is not $RUN_COUNT cells / $EXPECTED_PLAN: $compiled"; exit 8; }
  log "plan: $(echo $compiled | tr '\n' ' ')"
  drv=$(/usr/bin/python3 "$D/teastore_driver_root.py" 2>&1); log "drivers read: $(echo $drv | tr '\n' ' ')"
  echo "$drv" | grep -q "SWEEP=True" || { log "ABORT: the drivers do not see an activated sweep at $R (selector committed?)"; exit 8; }
  plan_dir=$(echo "$drv" | sed -n 's/^PLAN_DIR=//p')
  [ -f "$plan_dir/campaign.json" ] || { log "ABORT: plan directory not materialized: $plan_dir"; exit 8; }
  # read-only host facts; one campaign per host: no candidate containers may be running
  facts=$(ssh -o BatchMode=yes -o ConnectTimeout=15 fb14srv5 'echo "ncpu=$(docker info --format "{{.NCPU}}") cgroup=$(docker info --format "{{.CgroupDriver}}/{{.CgroupVersion}}") candidate_containers=$(docker ps -q --filter name=teastore_candidate | wc -l | tr -d " ") containers=$(docker ps -q | wc -l | tr -d " ")"' 2>/dev/null)
  log "srv5 host facts (stdout only): $facts"
  echo "$facts" | grep -q "candidate_containers=0" || { log "ABORT: TeaStore candidate containers running on srv5, or host facts unknown"; exit 6; }
fi
st=$(/usr/bin/python3 "$D/campaign_setup.py" status 2>&1); log "authorization (auto will re-derive if not live): $st"
free=$(ssh -o BatchMode=yes -o ConnectTimeout=15 fb14srv5 "df -BG --output=avail / | tail -1 | tr -dc 0-9" 2>/dev/null)
log "srv5 free GB (stdout only): $free"
[ -n "$free" ] && [ "$free" -ge 40 ] || { log "ABORT: srv5 free space unknown or < 40 GB"; exit 5; }
[ "$DRY_RUN" = 1 ] && { log "DRY RUN: all guards passed; stopping before the first mutation"; exit 0; }
# archive the previous campaign's run state so nothing of it can be mistaken for current (same-commit lesson, 2026-09-12)
G=$(/usr/bin/python3 -c "import sys; sys.path.insert(0,'$D'); import gate_run as gr; print(gr.GATES)")
A=$G/run-state-before-$LABEL-$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$A"
for f in run-authorization.json runtime-package.json gate-run.json campaign-terminal.json; do [ -f "$G/$f" ] && mv "$G/$f" "$A/"; done
[ -d "$G/campaign-result" ] && mv "$G/campaign-result" "$A/"
[ -f "$G/setup-campaign-authorization.json" ] && cp -p "$G/setup-campaign-authorization.json" "$A/"
log "archived previous run state -> $A"
log "=== auto ==="
/usr/bin/python3 "$D/campaign_setup.py" auto >> "$LOG" 2>&1; rc=$?; log "auto rc=$rc"; [ $rc -eq 0 ] || exit $rc
log "=== oneshot ==="
/usr/bin/python3 "$D/gate_run.py" oneshot >> "$LOG" 2>&1; rc=$?; log "oneshot rc=$rc"
if [ $rc -ne 0 ]; then
  F=$G/run-state-failed-oneshot-$LABEL-$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$F"
  for f in gate-run.json run-authorization.json runtime-package.json campaign-terminal.json; do [ -f "$G/$f" ] && mv "$G/$f" "$F/"; done
  log "oneshot failed; stranded run state archived -> $F; retry only for a transport or VPN failure"
  exit $rc
fi
CAP_H=$(( $(/usr/bin/python3 -c "import sys; sys.path.insert(0, '$D'); import teastore_driver_root as d; print(d.RUN_WINDOW_HOURS)") + 1 ))
log "=== watcher (cap ${CAP_H} h = run window + 1) ==="
WEND=$(( $(date -u +%s) + CAP_H*3600 ))
while true; do
  line=$(/usr/bin/python3 "$D/campaign_status.py" 2>&1); rc=$?; log "teastore-$LABEL $line"
  # ponytail: an unreachable host polls as state=unknown with rc 3 (shared poll_once); not terminal, keep waiting (2026-09-24 07:36Z VPN drop)
  if [ "$rc" -eq 3 ] && echo "$line" | grep -qi "state=unknown"; then log "UNREACHABLE (not terminal): $line"; sleep 300; continue; fi
  [ "$rc" -eq 3 ] && { log "TEASTORE $LABEL TERMINAL: $line"; exit 0; }
  [ "$(date -u +%s)" -ge "$WEND" ] && { log "WATCH-CAP ${CAP_H}h: $line"; exit 0; }
  sleep 300
done
