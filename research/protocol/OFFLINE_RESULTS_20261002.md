# §3.1 offline work and the sudo probe: results and decisions (2026-10-02)

Steps 1 and 3 of `research/READING_SUMMARY_20261003.md` §3. All on the laptop on retained evidence, except the read-only sudo
probe. Each item was built by an Opus agent and reviewed by a separate Opus adversarial-review session (Fable was
rate-limited); its self-check or tests were re-run by the main session. Scope: instance (retained evidence, one host per
SUT), except c2 (sut, predicted from source, unexecuted).

| item | file | commit | re-run by the main session |
|---|---|---|---|
| c1 isolability + minimal sensor sets | `research/isolability/ISOLABILITY.md` | f27844e | self-check pass, 9/9 mutants caught, script sha matches output |
| c2 workload paths + greedy vs degree | `research/workload-paths/PATHS.md` | f8110bc | self-check pass (`uv run`; uses a 3.10+ call) |
| sensor representation + replay | `research/protocol/sensor_rep/README.md` | 300ca1d | 9 tests pass |
| shared gate module | `src/obsplacement/protocol_gates.py`, `research/protocol/GATES.md` | d3fc741 | self-check pass under 3.9 `-I -B`; 76 passed, 1 skipped, 3 xfailed |
| sudo probe (srv5, srv6) | `research/NEXT_STEPS_20260925.md` (ledger row) | e86918a | run by the main session |
Suite after all four: 915 passed, 2 skipped, 3 xfailed (the unbound-names scan now covers the three `-protocol` worktrees).

## Results
- **c1.** The ledger alone never separates 3 of 6 fault pairs on Hotel lmt2 and sel1 and TeaStore T16's only pair, in any of
  9 threshold settings. What separates them: one frontend log sensor (Hotel), `full`'s client spans (int1 geo vs rate), one
  auth log sensor (TeaStore). Hotel `none` separates none of them. Without by-construction catches, net-delay vs search-pause
  has no separator. Redundancy is mostly by construction (e.g. sel1 search-pause 18 → 2 minimal single-sensor sets). "Only a
  sensor can see" appears only for the int1 delays, per posture, through the ledger's posture-dependent threshold (the H4
  effect). The CPU throttle has no outside catching set anywhere.
- **c2.** A workload change alone moves the placement-problem gate on none of the three SUTs under today's switches: Hotel needs
  finer switches (greedy ≠ degree over individual services at k = 4-6, never under today's two switches); TeaStore's service
  sets are nested, so degree is optimal for any weights; OTel depends on the tie rule (service level) and on D-LG2 (operation
  level, which the per-service switches cannot realise).
- **Representation.** Under the old rules it reproduces 77/77 substantive MAP_TABLE cells and 222/222 fault episodes at
  sensor-set level; the replay discriminates on Hotel (K = 6 drops int1 to 22/28 cells) but barely on TeaStore T16 (14/14 even
  at K = 6, τ = 0.2). OTel log masking fixed by call-site keying (recommendationservice 8,665 → 2 templates). Under the new rule
  the int1 delays stay 16/16 on the ledger (per-window median spread 0.03-0.08 ms, so the 1 ms floor binds) instead of
  decision 9's 4/16 and 5/16 under the per-request rule: the two rules disagree, and which spread is meant is a decision.
- **Gates.** G1 as written in draft 3 (scheduled opportunities) can never fail once G4 passes; the module adds "≥ 1 request
  started in the window" as a switch. None of the harnesses writes per-channel record counts, a per-route readiness map, or (on
  TeaStore) a pre-command fault-onset stamp, so R1 is `—`, G4 fails on scope and TeaStore fails F1 until they do. PLAN's
  literal and line citations corrected (Hotel 6, TeaStore 21, OTel 8 count literals).
- **Sudo probe.** `stig` has no passwordless sudo on srv5 and only `tcpdump` on srv6; `nsenter`/`tc` exist; `stig` is in the
  docker group on both. Hotel's `sudo -n nsenter … tc` netem cannot run there.

## Decisions owed (all preregistration class)
1. **G1**: count actual starts with the new generator (drop-and-record, cap ≥ rate × timeout), and on the old harnesses use G2
   to separate starvation from effect (recommended); or keep "scheduled + ≥ 1 started".
2. **Caller logs of a failed call** (frontend's `CheckAvailability failed`, auth's Jersey exception warning): by construction
   or not. If by construction, those two pairs have no separator left without BC.
3. **Ledger spread**: per request (decision 9's 4/16, 5/16) or per window (16/16 under the new rule).
4. **Placement-problem gate**: tie rule (every tie-break or some); objective and partial-credit function (only sqrt credit was
   run); "worth a harness commit" = the one-path rule or the full gate.
5. **Hotel switch granularity**: give `recommendation` its own sensor and switch (the only change c2 finds that creates a
   Hotel placement problem); TeaStore as a cost-only SUT at service level.
6. **Netem on srv5/srv6**: a sidecar container in the target's network namespace (no sudo; recommended, and for Hotel too) or a
   sudoers rule (host admin change).
7. **Representation rule details**: baseline for slow level metrics; whether a single-sample spike counts; the count
   normalisation to tile length (adopted: without it an open-loop MAD of 0 fires on window length alone).
8. **Cleanup**: three superseded runs in `tmp/protocol/` (`20261002T113639Z`, `20261002T114053Z` aborted, `20261002T114140Z`);
   delete only on a yes.

## Remaining from §3.1
Representation: the TeaStore Tnew/Gold and OTel run3 MAP rows (~3-4 h), class and BC columns on catches (~1 h), planted
positives on retained evidence (~2 h), the §2b detector pool and selection rule, the floor-grid flag, debug/trace level class.
Then §3.4 (harness commits) once decisions 1, 6 and the load-generator D-LG1-8 are made.

## Decisions (user, 2026-10-02, round 4)
1. **G1**: as recommended (count actual starts with the new generator; G2 separates starvation from effect on the old
   harnesses). Re-evaluated after the first campaign.
2. **Caller logs of a failed call**: yes, by construction, as a new flag **BC-caller-log** (the caller is the service that
   logs). Reported both ways, like BC-caller-span. Example (Hotel, `services/frontend/server.go`): frontend logs
   `SearchHandler CheckAvailability failed` at error level when its call to reservation fails (`:263-272`) and
   `SearchHandler GetProfiles failed` for profile (`:279-285`), but returns HTTP 500 without any log when search.Nearby
   fails (`:241-250`). So the frontend log "separates" a reservation pause from a search pause only because the developers
   logged one error branch and not the other.
3. **Ledger spread**: per request (decision 9's rule). Re-evaluated after the first experiment.
4. **Placement-problem gate** (tie rule, objective, "worth a commit"): undecided.
5. **Hotel switch granularity**: more detail requested (call paths); see the reply of 2026-10-02 and
   `research/workload-paths/PATHS.md` "Where Hotel differs".
6. **Netem on srv5/srv6 (and Hotel)**: sidecar container in the target's network namespace, image pinned by digest.
7. **Representation details**: a single-sample spike counts as a catch if it differs from the baseline, **provided it can be
   placed on the affected call path inside the fault window** (time window plus the requests on that path, e.g. via the
   ledger's trace ids). New requirement: catches carry the window and the call path they are attributed to. The open
   question is what an observation actually maps to; noted as a generalisation challenge.
8. **Cleanup**: the three superseded runs in `tmp/protocol/` deleted (26 M, 19 M, 26 M); `20261002T115708Z` kept.
