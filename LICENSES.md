# Licences

Two licences cover this bundle. Full texts: `LICENSE-APACHE-2.0.txt` and `LICENSE-CC-BY-4.0.txt`.

| Licence | Applies to |
|---|---|
| **Apache-2.0** (code) | `src/`; all `*.py`, `*.sh`, `*.rq` files anywhere (`tests/`, `research/`, `harness/`); harness configuration and contracts (`harness/**/*.yaml`, `*.yml`, `contracts/`, `pipelines/campaigns/`); `pyproject.toml`, `uv.lock`, `pytest.ini`, `.python-version`, `papers/current/benchsoc/build.sh` |
| **CC BY 4.0** (data, derived results, documents) | `research/**` data and documents (`*.md`, `*.json`, `*.jsonl`, `*.txt`, `*.log`, `*.csv`, `*.ttl`, `*.bib`, `*.png`): protocol records, budgets, declarations, readouts, placements, lanes and ontology outputs; `tests/fixtures/` data; `papers/current/benchsoc/paper.tex`, `paper.pdf`, `refs.bib`, `figures/`; `README.md`, `README_REPOSITORY.md`, this file |

Third-party material that keeps its own terms and is **not** relicensed by the table above:

- `papers/current/benchsoc/ceurart.cls` (CEUR-WS template, LaTeX Project Public License 1.3 per its header) and `elsarticle-num-names.bst` (Elsevier, LPPL per its header).
- `harness/*/modules/<sut>/` and `harness/teastore-protocol/modules/teastore/witness/*.patch`: copies of, or patches against, upstream TeaStore, OpenTelemetry Demo and DeathStarBench Hotel Reservation code. The upstream licences govern the upstream parts. They were **not verified** while building this bundle; the author should confirm them before upload.
- Quotations of upstream source lines inside `research/ontology/runs/` (model prompts, packets, judge verdicts) and the one collector-log excerpt `tests/fixtures/online_boutique/otelcol-0.108.0-selected.log` (OpenTelemetry Collector output).
- The third-party sources vendored for the ontology extraction (`research/ontology/vendor/`) are not part of the bundle; only their `PROVENANCE.json` files are.

Copyright holder for the NOTICE line of Apache-2.0: to be confirmed by the author (not asserted here).
