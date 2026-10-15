# Traffic-sweep pilot: budget and stop rule (committed alone, before the work; 2026-10-03)

Set by the user on 2026-10-03 ("we will get there in 3 days; if not we readjust"). Pilot: Hotel `hotel-traffic-sweep-v1`,
64 cells on fb14srv4 (`research/traffic-sweep/DECLARATION.md`, frozen next).

## Budget
- **3 days**: declaration frozen, campaign terminal, evidence fetched, analysis extension committed and the first readout
  reviewed by **2026-10-06 12:00Z**.
- Host: fb14srv4 only, one campaign at a time; the campaign's own window is 6 h (21,600 s, derived from the plan).
- Estimated campaign length 4.4-4.8 h (`HARNESS_CHANGE.md` §7; `?` until the first cells run).

## Stop rules
1. **Kill date**: not terminal and reviewed by 2026-10-06 12:00Z → stop and re-plan with the user ("readjust"); no silent
   extension.
2. **Lead cell** (`search-pause-effect-r10-b01-full-a01`, first in the plan): its capture is checked read-only while the
   campaign continues (log `--timestamps`, all-services traces, ledger rows, onset and probe stamps). A capture defect →
   stop the campaign unit, fix, relaunch.
3. **Invalid cell**: the runtime stops on the first invalid cell. Diagnose for at most 30 minutes if it is on the critical
   path, otherwise a ledger row; then the user decides the relaunch.
4. **At most 2 relaunches** within the budget; a third failure → stop and re-plan.
5. A VPN drop blinds the coordinator, not the campaign: re-validate against the host before acting.
