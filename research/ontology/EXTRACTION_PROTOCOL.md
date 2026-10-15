# Fixed extraction procedure for the system ontology (preregistered, 2026-10-14)

**Status: preregistered before the procedure is run on any system.** (Commit note, 2026-10-14 ~04:05Z: this file first entered git inside a concurrent worker's commit `14a72c7` (sensitivity curves), which staged it while it was untracked; its content there equals this text minus this note. This commit records it alone; no stage of the procedure has run.) Authority: user, 2026-10-14: the ontology must come from one fixed procedure,
applied identically to TeaStore, Hotel Reservation and the OpenTelemetry Demo ("AST + 2 Claude models + judge"). Base vocabulary: OMSAC (Morais, Bork, Adda,
MEDES'21, doi 10.1145/3444757.3485108) plus the operations/observability module `research/ontology/ops.ttl` (TBox only; no per-system content is written
by hand). Scope of every extracted fact: instance (one system at one pinned commit).

## Budget and stop rule
Procedure built and dry-run on one service of each system by 2026-10-14 12:00Z; all three systems extracted, checked, judged and converted by 18:00Z.
A missed deadline stops the step; the paper then reports the ontology as method only (no predicted-vs-measured table). Changes to this procedure after its
first run on any system are amendments committed alone, and every system is re-run under the amended procedure (never one system alone).

## Inputs (pinned; hashed into the run record)
| system | source tree (commit) | deployment files (as the harness deploys them) |
|---|---|---|
| TeaStore | `../observability-placement-runtime-teastore-protocol/upstream/teastore` (`34b37f7e7be4`) | the harness worktree's `modules/teastore/deployment/compose/docker-compose_kieker.yaml` at `f74b29b` |
| Hotel Reservation | `../observability-placement-runtime-hotel-protocol/upstream/deathstarbench/hotelReservation` (`6ecb09706140`) | its `docker-compose.yml` + the harness overlay `modules/hotel-reservation/deployment/compose.observability-placement.yml` at the hotel worktree HEAD (recorded) |
| OpenTelemetry Demo | `../observability-placement-runtime-otel-protocol/upstream/opentelemetry-demo` (`2d4661e4897a`, 1.12.0) | its `docker-compose.yml`, `.env` and `src/otelcollector/otelcol-config.yml` + the harness overlay `modules/otel-demo/deployment/compose.candidate-postures.yml` at `715d57b` |
File globs per system: the deployment files above; every source file of a service the compose files build or run (by the build context), excluding tests,
docs, generated protobuf/gRPC stubs and vendored dependencies. The run record lists every file with its sha256.

## Stage 1: deterministic layer (no model)
- Compose/YAML parser: services, images/build contexts, containers, `depends_on`, `deploy.replicas`/`scale` (default 1), environment variables whose values
  name another service (host or host:port) -> candidate sync edges, healthchecks, the host (one per system, `research/host-topology.json`).
- AST layer (tree-sitter, all languages present): call sites of known client libraries (gRPC stubs, HTTP clients, Kafka producer/consumer, registry and
  consul clients) and the configuration literals passed to them, each with file:line.
- Output: `stage1.json` per system in the extraction schema (`research/ontology/extraction.schema.json`).

## Stage 2: model layer (fixed prompt, two independent extractors)
The same prompt, below, is given per service to **Sonnet 5.5** (extractor A) and **Haiku 5.5** (extractor B), each run independently, each receiving only
the service's files, the deployment files and `stage1.json`. Its sha256 is recorded in the run record; any change is an amendment.

```
You extract facts about one service of a microservice system for an ontology. Use only the files you are given. For every fact you report, give the file
path, the line number and a token copied exactly from that line. If a fact is not stated in the files, do not report it; if a library default applies
because a setting is absent, report the absence (file:line of the configuration block) and say "library default, not in these files".
Report, in the JSON schema provided: (1) synchronous calls this service makes (callee service, protocol); (2) messages it publishes or consumes (topic,
consumer group); (3) any registry, discovery or coordinator it registers with or is tracked by, with heartbeat interval, failure timeout and cleanup
interval if stated, and whether its heartbeat runs independently of request processing; (4) its container, replica count and health check; (5) where it
sends telemetry (traces, metrics, logs) and how often if stated. Report nothing else. Do not infer from names alone.
```

## Stage 3: mechanical checks
1. Citation checker: for every fact, the cited file at the pinned commit contains `quotedToken` on the cited line (+-2 lines). A fact that fails is dropped
   and logged (count per extractor and system).
2. Merge: facts that both extractors report (same subject, relation, object) are **agreed**; facts from one extractor only, or from stage 1 only, are
   **contested**. Agreement per system and per relation type is reported (agreed / (agreed + contested)).

## Stage 4: judge (contested facts only)
**Opus 5.5** receives each contested fact with its cited lines (+-10 lines of context) and answers supported / not supported / not decidable from these
lines, with a one-sentence reason. Supported facts enter the ontology; the rest are logged. Every judge decision is appended to
`research/ontology/ADJUDICATION_LOG.md` (append-only). No fact is added, removed or edited by hand; a wrong fact found later is an amendment that re-runs
the whole procedure. The judge is same-provider; a cross-provider judge is added if the judge server is reconnected (recorded as such).

## Stage 5: ontology and checks
Convert agreed + supported facts to Turtle per system (`research/ontology/out/<system>.ttl`), validate with `research/ontology/shapes.ttl` (SHACL), run the
competency questions (`research/ontology/cq/`). SHACL violations are reported, not repaired.

## Stage 6: predictions
Competency-question answers (lanes per fault kind and target, predicted coordinator detection window, coordinator-failure class, blast radius, shared-fate
groups) are committed **before** any comparison. For campaigns already read (the pooled 175 episodes, `585da7e`) the comparison is a **post-hoc
consistency check**. The predictions declared before their campaigns ran (F-L2 in `DECLARATION_F_OTEL.md`, T-L2 in `DECLARATION_TEASTORE_OFFPATH.md`) are
compared with their frozen reads as the only genuine predictions.

## Outputs (new paths only; committed unedited)
`research/ontology/runs/<run-id>/` per system: inputs manifest, stage1.json, extractor A/B raw outputs, citation-check log, merge with agreement, judge
log, `<system>.ttl`, SHACL report, CQ answers.

## Amendment 1 (2026-10-14 ~05:00Z, committed alone, after the permitted dry run and before stage 2 runs on any system)
The builder's engineering defaults, recorded here because three go beyond this file's text (all apply identically to the three systems):
1. Extractor output is validated against a fragment of `extraction.schema.json` without the keys the prompt does not ask for (architecture, host,
   service role); those, and container and replicas, come from stage 1 only and therefore always go to the judge. The final spec is validated against the
   full schema.
2. Build contexts: TeaStore's compose file names images only, so images map to source folders through upstream `tools/build_docker.sh` (base image folder
   included); shared Maven modules enter every dependent service's bundle by pom dependency. Hotel's services share one image, so each bundle is narrowed to
   the Go imports reachable from its entrypoint.
3. **Beyond the text:** minified JavaScript (and its unminified twin), tooling dotfiles and key material (`*.pem` etc.) are excluded from bundles.
4. **Beyond the text:** stage 1 also records scheduler/timer call sites (where registry heartbeat intervals are set) as observations; they never become facts.
5. Stage-1 defaults: role from a lookup on the image name; container = compose service key when no `container_name`; replicas 1 as a documented default;
   sync-edge candidates from environment variables only (so Hotel's `config.json` addresses are not parsed by stage 1; they reach the extractors in the
   bundle); `research/host-topology.json` is not given to the extractors (stage 1 carries the host).
6. Agreement is literal: a fact from stage 1 plus one extractor is contested.
Dependencies (ontology group, exact pins): rdflib 7.6.0, pyshacl 0.40.1, tree-sitter 0.26.0, tree-sitter-language-pack 1.22.1 (grammars downloaded on
first use and hashed into `run.json`), pyyaml 6.0.3. Prompt sha256 pinned by `run_record.py`: `d29393e5…`.

## Amendment 2 (2026-10-14 ~06:30Z, committed alone, after run1-20261014 stage 4 was refused; applies to all three systems)
**What happened in run1:** stages 1-4 ran on all three systems (agreement TeaStore 49/101, Hotel 65/175, OTel 124/216; 254 contested facts judged).
`apply_judge.py` refused every system: the final spec lacked the schema-required `architecture` fact. Stage-1 facts that are **derived by a documented
rule rather than stated in a line** (architecture name = system id; host from `research/host-topology.json`; role from the image-name lookup;
container = compose service key when no `container_name`; replicas 1 when unset) cannot be judged from +-10 source lines, and the judge marked most of them
not decidable. The run1 adjudication log entries were written before the refusal and are kept.
**Change:** a stage-1 fact produced by one of those five documented rules, whose citation check passes, enters the final spec as **deterministic** (labelled
so in the spec and the Turtle provenance), without the judge. Every other rule is unchanged: extractor facts and other stage-1 facts are agreed only when
both extractors report them, contested otherwise, and contested facts need the judge's `supported`. Agreement is reported both over all facts (as in run1)
and over extractor-reportable facts only.
**Re-run:** stages 3-5 for all three systems as run `run1b-20261014`, reusing run1's stage-1 and stage-2 outputs unchanged (those stages are not amended).
Judge answers from run1 are reused for packets whose `packetDigest` is unchanged (same packet, same prompt and model); any new or changed packet is judged
afresh with the same judge prompt (`b1c5099d`).

## Amendment 3 (user, 2026-10-14 ~07:00Z, committed alone, after run1b's predictions and comparison were committed; applies to all three systems)
**Why:** run1b (`17b5253`, `0523282`, `d943c02`) recovered call graphs and deployment facts but lost the facts the lanes depend on, for two reasons visible
in its judge log: (1) liveness and coordinator facts that live in client-library defaults or protocol semantics (e.g. the Kafka group coordinator and the
consumer session timeout when no setting is given) have no line in the system's own repository, so the judge marked them not decidable; (2) free-text
identifiers for liveness/coordinator entities differed between extractors, so judged facts (e.g. TeaStore's 10 s alive window, `HeartbeatInfo.java:32`)
attached to records that never merged. **run1b stays the preregistered result and is reported as such.**
**Change 1, library-knowledge module (SUT-independent):** `research/ontology/library_knowledge/` holds facts about client libraries at pinned versions, each
cited to the library's own source or reference documentation at a pinned tag/commit (repository URL, commit, file, line, quoted token), vendored read-only
under `research/ontology/vendor/libs/` with sha256. Scope: only libraries that an accepted fact of run1b (or a stage-1/extractor fact from build files:
pom.xml, build.gradle.kts, *.csproj, go.mod, package.json) shows a service uses, at that version: Kafka clients (kafka-clients for Java, librdkafka via
Confluent.Kafka for .NET), the HashiCorp consul API (Go), and any registry/discovery client so found. The module is written once, by the same procedure as
stage 2 (fixed prompt, two extractors, citation check, judge) applied to the library sources instead of a service; the library prompt is recorded with its
sha256 before it runs. A library fact attaches to a system only through an accepted "service S uses library L at version V" fact.
**Change 2, identifier normalisation:** liveness, coordinator and consumer-group entities are keyed by (coordinator service name as in the compose file,
mechanism type from a fixed list: consumer-group-session, registry-heartbeat, discovery-registration), not by extractor free text.
**Re-run:** stages 3-5 as `run2-20261014` for all three systems, with the library module; stage-1 and stage-2 outputs of run1 reused unchanged; new or
changed judge packets judged with the run1 judge prompt (`b1c5099d`). Predictions committed before the comparison; every comparison is POST HOC (all
campaigns were read before this amendment).
- **Amendment 3 note (2026-10-14 ~08:00Z, committed alone, before run2's judge runs):** "service S uses library L at version V" facts
  (`runs/run2-20261014/libraries.json`, 38 facts, 38/38 citations pass) are read mechanically from build files and enter as **deterministic** (Amendment
  2's rule extended to this one documented rule), not judged. The library attachment rule is documented in `library_merge.py` (Kafka-client-family facts
  reach a system only through a uses-fact plus accepted consumes and onBroker facts; registry/discovery clients have no attachment rule in run2). The
  Kafka broker and consul server sources are not vendored (scope: client libraries); sarama is included by the Kafka-client family rule.
