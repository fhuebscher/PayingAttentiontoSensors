# Declared comparator sensor sets (protocol decision 78, design D-p6)

Per SUT, the sensor ids that the reference postures `selected` and `none` (Hotel: `sample-zero` and `none`) would
emit. Derived only from posture definitions (harness posture configs, aop/Kieker rendering, Jaeger sampler and
tracer config, OTel posture catalog). No outcome, detection time or readout value was read.

## Files

| file | use |
|---|---|
| `<sut>.json` | the full record: `postures`, `setSizes`, per-posture per-family `families` (state, rule, id count), `undetermined`, `sources` (file:line per rule), `idVocabulary` |
| `<sut>.declared.json` | the flat form `celf_v3.py --declared` reads: `{comparator name: [sensor ids]}`. `celf_v3.py:664,672` loads it with `json.loads`; `place_rate` iterates `.items()` and passes each list to `restrict(S, V)` (celf_v3.py:583-586, 609-619). A `null` value would mean "not declared". |

The `<sut>.json` files are not valid `--declared` input (they carry string and object values next to the posture
lists); pass the `.declared.json` files.

## How the ids were fixed

- **Vocabulary.** The id set of each readout is the union over the four rates of the key names of
  `calibration.primary.perRate[*].sensors` in `research/traffic-sweep/readout-<sut>-primary-v3.1/sweep_analysis_v3.json`
  (ledger id excluded; sha256 in `idVocabulary`). Only key names were read. A posture's set is a subset of that
  universe, chosen by a rule on the id's service and family. `celf_v3.py` intersects each set with the rate's
  ground set V_r (`restrict`), so ids that are not placeable at a rate drop out there.
- **Span ids.** Which services trace in the posture (Hotel: Jaeger tracer on or NoopTracer per service; TeaStore:
  which Java packages the rendered aop weaves; OTel: `activeApplicationServices` and `envoyTracing`).
- **Metric ids.** Hotel `cpu` comes from a collector that runs only in `SAMPLER_POSTURES`; `sys_*` from the
  cgroup sampler, always on. TeaStore `sys_*` from the cgroup probe in every cell. OTel metrics are OTLP points plus
  collector spanmetrics (`calls`, `duration~*`), emitted per active service.
- **Log ids.** Logs are the services' stdout. A posture changes them only through the log level (Hotel `none`:
  `LOG_LEVEL=fatal`) or through instrumentation's own lines. Log ids are 12-hex hashes of
  (framework, level, caller, masked message), so instrumentation-originated templates cannot be told from the id.

## Per-SUT decisions that are not obvious

- **Hotel.** `sample-zero` comes from the stock catalog (`activation/catalog.json:71-75`); the sweep epoch has no
  such rung. `none` and `selected` come from the epoch `hotel-reservation-selected-v1`
  (`execution/candidate_pilot.py:32-43`), which is also the lineage of the sweep's `full` cells. Epoch `none` is
  stricter than the stock catalog's `none`: it also sets `LOG_LEVEL=fatal` and runs no cpu collector, so its set is
  60 `sys_*` metric ids and nothing else. Under the stock `none` the 209 log ids and 10 cpu ids would be in the
  set (listed under `undetermined`). `selected` (frontend-only tracer) is not named by decision 78 for Hotel; it
  is included because the epoch defines it. `sample-zero` carries logs only: its metric family is `undetermined`.
- **TeaStore.** The harness `selected` is the `fault-qualification` selection (`operation:auth`,
  `operation:persistence`, closed under `requires`), not a journey cover: the journey-cover `selected` exists only
  as a draft (`research/uniform-postures/EPOCH_U_DESIGN_DRAFT_20260927.md`). The set follows the harness. Span ids
  were matched to the rendered includes by the package of each class in `upstream/teastore` (all 24 TeaStore span
  ids checked: 14 in `auth..*` or `persistence..*`, 10 not). `none` is `kieker.monitoring.enabled=false`.
- **OTel.** Straight from `postures/catalog.json`: a service in `activeApplicationServices` emits its spans and
  metrics, a service outside does not; `none` is empty.

## Limits

1. **Restriction estimates, not measurements (decision 80, D-p9).** Every set is scored by restricting `full` cells
   to the declared ids. `celf_v3.py` labels the result "restriction estimate (decision 78)". Protocol :102 allows
   restriction only after a posture-leak check, which cannot run on all-`full` cells; the live run of a chosen
   placement (decision 46.3) is the later check.
2. **A posture's cell is not `full` minus its ids.** Disabled services still run, load instrumentation in some
   cases and cost CPU; a silenced service changes timing and trace parentage. The restriction keeps `full`'s
   detection times for the retained ids.
3. **Log ids are an upper bound** for TeaStore and OTel (both postures keep every log id) and for Hotel
   `selected`/`sample-zero`. The instrumentation-originated subset is `undetermined` and listed per SUT.
4. **`undetermined` means left out of the set** where the family could not be decided (Hotel `sample-zero` metrics)
   and kept in where the family is decided and only a subset is unknown (logs).
5. Families the posture definitions say nothing about are not guessed; the `undetermined` array in each
   `<sut>.json` is the complete list.
6. Scope label: instance. One SUT, one harness epoch, one readout vocabulary.
