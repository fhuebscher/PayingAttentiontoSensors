#!/usr/bin/env bash
# Archive-only reset of OTel run 1's host paths on fb14srv6, before run 2.
#
#   ssh root@fb14srv6 'bash -s' < tools/otel_run1_archive_reset.sh            # report only
#   ssh root@fb14srv6 'bash -s' -- --archive < tools/otel_run1_archive_reset.sh
#
# ponytail: moves, never deletes. Run 1 (2026-09-18, attempt 1) left three paths
# that make `install` fail closed for any later attempt under the same campaign id,
# because the id -- and therefore every derived path -- does not change with the
# attempt: the artifact root (run 1's 18 cells, byte-verified locally 214/214 in
# tmp/otel-shakedown-evidence, still the host original), the setup staging dir with
# its one-shot marker, and the release root at f7047ab. All three are renamed to
# .archived-<name>-run1-<stamp> beside themselves. Nothing is copied or rewritten.
#
# Refuses unless the host is idle: no running OTel/candidate unit, no containers at
# all, and nobody holding the shared lease. Guards read stdout only (a login banner
# on stderr once became a free-space number, 2026-09-15). The lease file itself is
# left in place: readiness probes it with flock and it carries no state.
set -uo pipefail
MODE=report
[ "${1:-}" = "--archive" ] && MODE=archive
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
B=/home/stig/observability-placement-candidate-v4-runs
R=/home/stig/observability-placement-candidate-v4-otel-srv6
C=otel-demo-candidate-pilot-v2
LEASE=$B/.srv6-runtime.lock

[ "$(hostname)" = fb14srv6 ] || { echo "REFUSING: not fb14srv6"; exit 2; }
units=$(systemctl list-units --state=running,activating --no-legend --plain 2>/dev/null \
  | grep -ciE 'otel_candidate|candidate-v4|teastore|hotel|boutique')
containers=$(docker ps -q 2>/dev/null | wc -l | tr -dc 0-9)
holders=$( { fuser "$LEASE" 2>/dev/null || true; } | tr -dc '0-9 ' | xargs)
echo "running campaign units=$units containers=$containers lease holders=[${holders}]"
if [ "$units" != 0 ] || [ "$containers" != 0 ] || [ -n "$holders" ]; then
  echo "REFUSING: host is not idle"; exit 3
fi

targets=()
[ -e "$B/$C" ] && targets+=("$B/$C")
[ -e "$B/.setup-$C" ] && targets+=("$B/.setup-$C")
for d in "$R/$C"-*; do
  [ -e "$d" ] || continue
  case "${d##*/}" in .archived-*) continue ;; esac
  targets+=("$d")
done
if [ ${#targets[@]} -eq 0 ]; then echo "nothing to archive (run 1 paths already absent)"; exit 0; fi

for t in "${targets[@]}"; do
  echo "run-1 path: $t ($(du -sh "$t" 2>/dev/null | cut -f1), $(find "$t" -type f 2>/dev/null | wc -l | tr -dc 0-9) files)"
done
[ "$MODE" = archive ] || { echo "report only; re-run with --archive to move these aside"; exit 0; }

for t in "${targets[@]}"; do
  dest="$(dirname "$t")/.archived-$(basename "$t")-run1-$STAMP"
  [ -e "$dest" ] && { echo "REFUSING: $dest exists"; exit 4; }
  mv -- "$t" "$dest" && echo "archived $t -> $dest" || { echo "FAILED moving $t"; exit 5; }
done
for t in "${targets[@]}"; do [ -e "$t" ] && { echo "FAILED: $t still present"; exit 6; }; done
echo "reset complete: ${#targets[@]} path(s) archived, 0 deleted"
