#!/usr/bin/env bash
# Archive a stranded OTel setup attempt on the target so `auto` can retry.
#
#   ssh root@fb14srv6 'bash -s' < tools/otel_reset_attempt.sh
#
# ponytail: archive, never delete. A failed attempt leaves two things that both
# fail the next run closed: the one-shot marker `.setup-attempt-started` in the
# staging dir, and the release root, which `install` requires to be absent.
# Both are moved aside with a timestamp so a post-mortem is still possible.
set -uo pipefail
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
B=/home/stig/observability-placement-candidate-v4-runs
R=/home/stig/observability-placement-candidate-v4-otel-srv6

if docker ps --format '{{.Names}}' 2>/dev/null | grep -qi 'otel\|demo'; then
  echo "REFUSING: otel containers are running; stop them before resetting"
  exit 3
fi

# BOTH spellings, deliberately. Until 2026-09-18 the campaign id was derived as
# `otel_demo_candidate_pilot_v2` (underscores); it is now `otel-demo-candidate-pilot-v2`
# (hyphens), because the shared gate-driver library's slug validator rejects an
# underscore and it is shared with TeaStore and Hotel. The underscore form survives
# only as the Compose project name, which is not a path. This script names PATHS, so
# it follows the id -- and it must keep archiving the pre-2026-09-18 underscore
# directories still sitting on fb14srv6 from the aborted 2026-09-15 attempt.
# Dropping either spelling makes this script silently archive nothing.
for C in otel-demo-candidate-pilot-v2 otel_demo_candidate_pilot_v2; do
  for d in "$B"/.setup-"$C"; do
    [ -d "$d" ] && mv "$d" "$B/.archived-setup-$C-$STAMP" && echo "archived staging ($C) -> .archived-setup-$C-$STAMP"
  done
  for d in "$R"/"$C"-*; do
    case "${d##*/}" in .archived-*) continue ;; esac
    [ -d "$d" ] && mv "$d" "$R/.archived-${d##*/}-$STAMP" && echo "archived release -> .archived-${d##*/}-$STAMP"
  done
  # The artifact root is a THIRD path, under the runs dir rather than the release
  # dir, and `install` requires it absent too. Missing it here cost one retry.
  A="$B/$C"
  [ -e "$A" ] && mv "$A" "$B/.archived-artifacts-$C-$STAMP" && echo "archived artifacts ($C) -> .archived-artifacts-$C-$STAMP"
done

echo "reset complete"
