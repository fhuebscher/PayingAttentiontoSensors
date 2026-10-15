#!/usr/bin/env bash
# Fetch + byte-verify the overnight runs of 2026-09-27 (Hotel r7 on srv4, TeaStore 17 on srv5), read-only on the hosts.
# Same method as #16: host-side sha256 manifest, tar stream, local extract, shasum -c against the host manifest.
# Usage: bash scratchpad/gate-drivers/fetch_overnight.sh hotel|teastore
set -euo pipefail
cd "$(dirname "$0")/../.."
case "${1:?case}" in
  teastorerep3r1) H=fb14srv5; B=/home/stig/.local/share/observability-placement/candidate-v4/teastore/results
            ID=dcc8b664a9d0602e019a45322d93dbf1; O=tmp/teastore-offpath-evidence/rep3r1-fetch ;;   # R1 relaunch 1 (102a8cf), complete 30/30
  *) echo "unknown case"; exit 2 ;;
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
