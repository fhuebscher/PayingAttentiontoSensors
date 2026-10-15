#!/usr/bin/env bash
# Fetch + byte-verify the overnight runs of 2026-09-27 (Hotel r7 on srv4, TeaStore 17 on srv5), read-only on the hosts.
# Same method as #16: host-side sha256 manifest, tar stream, local extract, shasum -c against the host manifest.
# Usage: bash scratchpad/gate-drivers/fetch_overnight.sh hotel|teastore
set -euo pipefail
cd "$(dirname "$0")/../.."
case "${1:?hotel|teastore}" in
  hoteloff2) H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20261015t080538z-cb803aec; O=tmp/hotel-offpath-evidence/off2-fetch ;;   # R3 Hotel off-path placement test (DECLARATION_HOTEL_OFFPATH_PLACEMENT)
  hoteloff1) H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20261014t225950z-36b91d24; O=tmp/hotel-offpath-evidence/off1-fetch ;;   # Hotel off-path (consul pause, DECLARATION_HOTEL_OFFPATH 4945293), 30/30 valid
  hotel)    H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20260927t114506z-9a428b0c; O=tmp/hotel7-evidence ;;
  hotel8)   H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20260928t062728z-28ce4896; O=tmp/hotel8-evidence ;;   # r8, launched 2026-09-28 06:27:53Z
  hotellmt1) H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20260928t114413z-a49116ba; O=tmp/hotellmt1-evidence ;;   # LMT pilot lmt1, stopped on cell 1 (LOG_LEVEL=disabled)
  hotellmt2) H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20260928t133750z-e6a3bc45; O=tmp/hotellmt2-evidence ;;   # LMT pilot lmt2, 80/80 valid (plan e1e61746)
  hotelsel1) H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20260929t072735z-065bb893; O=tmp/hotelsel1-evidence ;;   # Hotel selected run 1 (plan 189604cc)
  hotelint1) H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20260930t024033z-e6a99784; O=tmp/hotelint1-evidence ;;   # Hotel interior run 1 (plan 59545e14)
  hotelrep1) H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20261001t064703z-a10e879e; O=tmp/hotelrep1-evidence ;;   # Hotel selected replication 1 (plan 189604cc)
  hotelrep2) H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20261001t111022z-1e6003bc; O=tmp/hotelrep2-evidence ;;   # Hotel selected replication 2 (plan 189604cc)
  hotelsweep3) H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20261003t134611z-db51eb9e; O=tmp/hotelsweep3-evidence ;;   # traffic sweep relaunch 3 (64 cells, plan 766063c5, harness ca58974)
  teastoresweep2) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=a291bcd7c45cc1d85d18e8d2e5b55e06; O=tmp/teastoresweep2-evidence ;;   # TeaStore traffic sweep relaunch 2 (12 cells, plan 88a3017a, harness 0588a41)
  hotelquiet1) H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20261004t082015z-b71377d4; O=tmp/hotelquiet1-evidence ;;   # quiet calibration run A (40 no-fault cells, plan 554a7a1e, harness e9d35f7)
  teastorequiet1) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=cedad730e9b5c219d53dabd22cd1f6c1; O=tmp/teastorequiet1-evidence ;;   # TeaStore quiet calibration run A (40 no-fault cells, plan 879a81ab, harness 91c4967)
  hotelquiet2) H=fb14srv4; B=/home/fhuebscher/observability-placement-candidate-v4-runs/hotel-candidate-v1
            ID=hotel-v1-20261009t110251z-624fdf55; O=tmp/hotelquiet2-evidence ;;   # quiet calibration run A2 (decision 68; same plan 554a7a1e as A)
  teastoreb1) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=9184b8efaf7351dd70d05e95961bdd4c; O=tmp/teastoreb1-evidence ;;   # campaign B (36 cells, plan aa346970, harness bbb6b11)
  teastorequiet2) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=dc4e26ada1250e9c42037d88bfeebf43; O=tmp/teastorequiet2-evidence ;;   # TeaStore quiet run A2 attempt (decision 68; plan 879a81ab, harness bb3717e), stopped at cell 18: readiness failed, 17 valid
  teastorequiet2r1) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=69abdc8922d0ac493b507eb2914dc97f; O=tmp/teastorequiet2r1-evidence ;;   # TeaStore quiet run A2 relaunch 1 (declaration 6936347; plan 879a81ab, harness bb3717e), 40/40 valid
  teastorec1) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=d8cac67e766ce920d8edb1c17650df8a; O=tmp/teastorec1-evidence ;;   # TeaStore campaign C attempt (declaration cd747c7, plan e55b4f59, harness 3b4a513), stopped at cell 2: readiness failed, 1 valid
  teastorerep3) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=416ea06f6b87f7ba0291fd2823c83d53; O=tmp/teastore-offpath-evidence/rep3-fetch ;;   # R1 TeaStore off-path placement test (DECLARATION_TEASTORE_OFFPATH_PLACEMENT 42c04f3)
  teastorerep2) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=cbe9920a4b95f47d60054186641e754c; O=tmp/teastore-offpath-evidence/rep2-fetch ;;   # TeaStore off-path replication 2 (barrier-fixed harness 04254228, 5b9236f), complete 30/30
  teastorerep1r1) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=d61bfea75d299b17c17104c2578bf7b8; O=tmp/teastore-offpath-evidence/rep1r1-fetch ;;   # TeaStore off-path replication 1 relaunch 1 (3760a6c), stopped at cell 18 (queue at barrier), 17 valid; not read
  teastorerep1) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=887a7838e73019806ed39607be69992f; O=tmp/teastore-offpath-evidence/rep1-fetch ;;   # TeaStore off-path replication 1 (256ae13), stopped at cell 9 (queue non-empty at barrier), 8 valid
  teastoreo1r1) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=def272fd4c9050f8226b88d756115e79; O=tmp/teastore-offpath-evidence/r1-fetch ;;   # TeaStore off-path relaunch 1 (DECLARATION_TEASTORE_OFFPATH_RELAUNCH1 3dd0221), the only cells read
  teastoreo1) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=c88ed29d91c6e8e889c0dd0f54157089; O=tmp/teastore-offpath-evidence/o1-fetch2 ;;   # TeaStore off-path attempt 1 (DECLARATION_TEASTORE_OFFPATH f40e786), stopped at cell 3 (readiness race), 2 valid
  teastorec1r1) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=8cafbe550f9b5d38272aa97f2b345347; O=tmp/teastorec1r1-evidence ;;   # TeaStore campaign C relaunch 1 (declaration RELAUNCH1, setup 53b7c5b2), terminal complete 07:45:33Z, 36 rows
  otelc1) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-repeat-episodes-c-v1; O=tmp/otel-c-evidence/c1-fetch2 ;;   # OTel campaign C (declaration DECLARATION_C_OTEL, 36/36 valid, terminal 2026-10-11 03:56Z on srv6)
  otelpilot1) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-load-pilot-v1; O=tmp/otel-load-pilot-evidence/p1-fetch ;;   # OTel load pilot 50/100 req/s (DECLARATION_PILOT_LOAD_OTEL.md, plan aea94eb9)
  otelpilot2) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-pilot-v1; O=tmp/otel-offpath-pilot-evidence/p1-fetch ;;   # OTel off-path pilot v1 (DECLARATION_PILOT_OFFPATH_OTEL.md, plan 8b3d7aa8; stopped at cell 2)
  otelpilot3) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-pilot-v2; O=tmp/otel-offpath-pilot-v2-evidence/p1-fetch ;;   # OTel off-path pilot v2, 25/50 req/s (plan a929b4d9, S8 order)
  otelNL1) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-f-nolag-v1; O=tmp/otel-f-evidence/nolag1-fetch ;;   # F no-lag ablation (DECLARATION_F_NOLAG_OTEL, harness 4ab4433, plan 858bbcd3)
  otelF3b) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-f-v1; O=tmp/otel-f-evidence/f3-fetch2 ;;   # F attempt 3 re-fetch (f3-fetch interrupted by a VPN drop at ~02:10Z, rc 255, kept unverified)
  otelNF1) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-f-v1; O=tmp/otel-f-evidence/nf1-fetch ;;   # R4 no-fault price check (F plan, attempt 6, plan 0c7a9cdb)
  otelFS1b) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-f-v1; O=tmp/otel-f-evidence/fs1-fetch2 ;;   # R2 re-fetch after a VPN drop interrupted fs1-fetch (kept, unverified, unused)
  otelFS1) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-f-v1; O=tmp/otel-f-evidence/fs1-fetch ;;   # R2: F with a new seed (attempt 4, harness f08ba1d, plan 6bc8c84a)
  otelF3) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-f-v1; O=tmp/otel-f-evidence/f3-fetch ;;   # F replication relaunch (attempt 3, 7f4382e, plan 56bdaa62)
  otelF2b) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs/archive-f-attempt2-20261014
            ID=otel-offpath-f-v1; O=tmp/otel-f-evidence/f2-fetch2 ;;   # F-rep1 attempt 2 (stopped at cell 13, 12 valid), re-fetched from its archive dir after f2-fetch was interrupted unverified
  otelF2) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-f-v1; O=tmp/otel-f-evidence/f2-fetch ;;   # OTel F replication 1 (attempt 2, DECLARATION_F_OTEL_REP1 d0ef902, plan 373a1ece)
  otelF1) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-f-v1; O=tmp/otel-f-evidence/f1-fetch ;;   # OTel campaign F (DECLARATION_F_OTEL.md, plan 30aa2484, 25 cells, lanes)
  otelE1) H=fb14srv6; B=/home/stig/observability-placement-candidate-v4-runs
            ID=otel-offpath-e-v1; O=tmp/otel-e-evidence/e1-fetch ;;   # OTel campaign E (DECLARATION_E_OTEL.md, plan 503bf014, 25 req/s, fraud+accounting+frontend pause)
  teastore19) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=e73b771c9eb6323d5a06cbb2ce02c681; O=tmp/teastore19-evidence ;;   # campaign 19 (2026-10-01, aborted: queue non-empty at barrier)
  teastore) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=02a71ff60f7a449129d080d4bf2fa4d3   # campaign 17, created 2026-09-27 11:54Z (88b56231… beside it is empty)
            O=tmp/teastore17-evidence ;;
  teastore18) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=9a74157b31b8880ca2dbc7a51df88de7; O=tmp/teastore18-evidence ;;   # campaign 18, aborted 01:25Z
  *) echo "usage: $0 hotel|hotel8|hotellmt1|hotellmt2|hotelsel1|hotelint1|hotelrep1|hotelrep2|teastore|teastore18"; exit 2 ;;
esac
[ -e "$O/x" ] && { echo "refusing: $O/x exists (new evidence never overwrites old)"; exit 1; }
mkdir -p "$O/x"; echo "$H:$B/$ID" > "$O/source.txt"
S="ssh -n -o BatchMode=yes -o IdentitiesOnly=yes $H"
$S "cd $B/$ID && find . -type f -print0 | sort -z | xargs -0 sha256sum" 2>/dev/null | /usr/bin/grep -E '^[0-9a-f]{64}  ' > "$O/host.sha256"
$S "tar -C $B/$ID -cf - ." 2>/dev/null > "$O/evidence.tar"
tar -xf "$O/evidence.tar" -C "$O/x"
( cd "$O/x" && shasum -a 256 -c ../host.sha256 > ../verify-full.txt 2>&1 ) && r=0 || r=$?
echo "$ID: host files $(wc -l < "$O/host.sha256"), OK $(/usr/bin/grep -c ': OK$' "$O/verify-full.txt"), shasum rc=$r"
# ponytail: launch_hotel.sh refuses to move a previous run unless tmp/hotel6-evidence/<id>.tgz exists (r8 lost its first launch to this)
case "$1" in hotel*) T=tmp/hotel6-evidence/$ID.tgz
  [ "$r" = 0 ] && [ ! -e "$T" ] && tar -czf "$T" -C "$O" -s ",^x,$ID," x && echo "archived for the launcher guard: $T" ;; esac
