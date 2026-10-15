# Sweep analysis extension: engineering defaults and open points (2026-10-03, before any result is looked at)

Extension `research/detection-time/sweep_analysis.py` (da6c002) on `detection_time.py` at dbebcbb (byte-identical, tested).
Written blind: no sweep cell analysed; one attempt-2 cell opened for key names and types only. Not yet independently
reviewed. Run: `uv run python research/detection-time/sweep_analysis.py <fetched campaign dir> --out <new dir>`.

## Engineering defaults where `DECLARATION.md` is ambiguous
| id | default |
|---|---|
| a | Onset = the fault receipt's `startedMonotonic` (as dbebcbb); scheduled onset and lag reported per episode; P1's wait and P2's count use the same onset. No-fault windows from the contract's `scoredWindowSeconds`. |
| b | The K × floor grid floor applies to span and ledger latency only; metric floors stay per resource. Verdicts at K = 4 / 1 ms plus how many of the 9 grid points agree. |
| c | G3 per rate from one same-phase window per no-fault cell; with n = 4 only k = 0 is admissible; a rate without a valid no-fault cell is `—`. |
| d | Probe-window samples are dropped from the pre-window baseline too; for the `absent` rule they still count as the stream alive. A catch moved past the hold end is a miss. Exclusion by sample stamp. Spans dropped per trace when the frontend root has no token. |
| e | Log time = Docker receive stamp; the whole-second rule only for a cell without Docker stamps. |
| f | Ledger baseline = each cell's own pre-window (dbebcbb); brief A's pooled no-fault baseline (B9) not adopted. |
| g | P1 uses the ledger's first catch (any admissible rule, BC included); a ledger miss fails the episode; P1 holds only if every episode passes. |
| h | P2 uses the ledger's first admissible `failed` catch with `≤`; a miss counts the whole hold; < 4 episodes → `—`. |
| i | P3 per family (S), without BC catches, mean over 4 episodes with misses at the hold, for the two declared cells only. |
| j | P4 by leave-one-episode-out: lowest training mean (ties by name), scored on the held-out episode, holds if strictly faster than the ledger in ≥ 3 of 4. P4b without BC (with BC beside). False alarms beside P4 = the whole candidate pool, leave-one-cell-out. |
| k | BC-caller-log by content (a warn/error/other template in a non-target service naming the target or its gRPC methods). The caller-span flag stays pauses-only (dbebcbb). |
| l | Impact counts failed requests by scheduled time; requests in flight at onset are not counted. |

## Not computed (yet)
CELF and enumerated placements; D3/D4/D5; the 15 s re-censored hold; impact from slowed requests.

## Inputs the harness does not record (`—` in the readout)
Tokens on non-root spans (only the frontend root is tagged); individual recovery-poll stamps (the whole
[reverting, readyAt] window is excluded); metric samples' interval start (exclusion by stamp only).

## Open, for the user before the first run (append resolutions below, never edit above)
1. **Probe-window handicap (consequence of the declared rule, from code):** under search-pause the "during" readiness
   probe hangs up to its 5 s timeout (`compose_pause.route_available`, timeout 5.0), so every sensor catch is pushed to at
   least the end of that window while the ledger is untouched. P4 on search-pause starts with sensors handicapped by up to
   5 s.
2. **Caller-span BC flag for delay faults:** extend by-content flagging of caller spans from pauses to net-delay (would flag
   search's client span to `rate`)?

## Review fixes (2026-10-03; the commit that appends this section, on da6c002)
Independent Fable review of da6c002 ("run after fixes"). Still blind: nothing run on sweep evidence, synthetic fixtures
only. Each row has a test in `tests/test_sweep_analysis.py`; where da6c002 was wrong, that test fails on it (B1, M3,
m1, m4, M1, caller-span); where it was right, the planted defect it missed is now caught (M2, m2).

| id | change |
|---|---|
| B1 | A cell without `cell-terminal.json` (the one that stopped the campaign leaves a contract-only directory) or with `candidateCellValid` not true is listed as not scored, with its reason, and never parsed. A parse error in any cell is recorded as its reason; the run continues. |
| M3 | Regime and receipt must agree: a fault regime without `fault-receipt.json`, the no-fault regime with one, or a receipt target other than the regime's makes the cell not scored (it no longer becomes a no-fault window). |
| M2 | Two-rate fixture (10 and 0.05/s): P3 holds and P3 fails, and a per-rate G3 difference (a template admissible at 0.05/s, rejected at 10/s). |
| m1 | The whole-second log rule is decided per cell, not campaign-wide (default e as written). |
| m2 | Fixture rows with late actual starts (> 0.5 s) flip P1 and the impact count; `failed_before` boundary (a request scheduled exactly at the catch is counted). |
| m3 | P4 with fewer than 4 evaluable episodes stays `—` (not evaluable, never "none"); stated in the docstring and the readout. |
| m4 | JSON `provenance`: harness commit (campaign `runtime-admission.json` bindings.frameworkCommit, else `—`), plan and admission digests from the cell contracts, sha256 over sorted (relative path, size) of every file read. |
| m5 | The reference-equivalence test has a span stream, and the span floor follows the grid. |
| M1 (i, ii) | The chosen sensor's move (s) is reported per P4 fold and per episode on both P3 sides; the during-probe window length per (regime, rate, episode). |
| M1 (iii) | Probe-exclusion variants side by side at the reference point: `declared` (the declared rule), `scope` (window rule only for logs and metrics of frontend and the fault target; spans by token only), `none` (no window rule; the token rule stays; sensitivity only). The K × floor grid runs on the primary. |
| M1 (iv) | A P3/P4 verdict that differs between the primary and `none` is printed "decided by the probe rule", with both values. |
| open 2 | Caller-span BC flag in two variants side by side: `kind` (dbebcbb, stopping faults only) and `content` (the same test without the stopping condition, every fault class; a local override, detection_time.py unchanged). |

**User decisions, as two constants** in `research/detection-time/sweep_analysis.py` (top of file): `PRIMARY_PROBE = "declared"`
(one of `declared`, `scope`, `none`) and `PRIMARY_CALLER_SPAN = "kind"` (one of `kind`, `content`). They name which variant
the readout's primary tables and grid use; every variant is reported regardless. Left at the declared/dbebcbb values
until the user decides. From the code (compose_pause.py:54-62, 173-187), the during-probe window under a pause is about
[applied + 0.25, applied + 5.3] s at every rate, so under `declared` P4a on search-pause at 10 and 1/s cannot hold by
construction, and P3 search-pause compares values pinned at that window's end; the readout labels such verdicts.

Planted defects now caught (17): the 11 of da6c002 plus eps_of ignores rate; read_ledger scheduled := actual;
p1_expected on actual start; failed_before exclusive upper bound; whole-second rule campaign-wide; G3 pooled across
rates. Suite: 955 passed, 1 skipped, 3 xfailed (30 tests in test_sweep_analysis.py, 12 new).
