# Harness code at the launch commits

Each directory is `git archive <commit>` of the listed paths from the one git repository that holds all worktrees (no working-tree files). Subset: `src/obsplacement`, `modules/<sut>`, `pipelines/campaigns`, `tools`, `contracts`, `tests`, `pyproject.toml`, `uv.lock`, `pytest.ini`, `.python-version`. Files excluded by the scan are listed in `SCAN_REPORT.md`; files changed by redaction in `REDACTIONS.md`.

| Directory | Commit | Subject (commit date) | Worktree holding or descending from it | Files |
|---|---|---|---|---:|
| `otel-c-8018a19/` | `8018a194892a901222b2b4e0655eef131bc776ae` | 2026-10-11 Activate otel-repeat-episodes-c-v1 (campaign C): point the study-epoch selector at it and admit it in the tombstone | observability-placement-runtime-otel-ablation (ancestor), observability-placement-runtime-otel-fseed (ancestor), observability-placement-runtime-otel-protocol (ancestor) | 235 |
| `otel-e-6a5c2a9/` | `6a5c2a997fd56e72b886043a50e151ef16c13ba3` | 2026-10-13 Re-pin OTel v2 governance source binding of candidate_runtime_adapter.py to the pilot v2 attempt-1 spent commit | observability-placement-runtime-otel-ablation (ancestor), observability-placement-runtime-otel-fseed (ancestor), observability-placement-runtime-otel-protocol (ancestor) | 247 |
| `otel-f-715d57b/` | `715d57b5f06ea32d47466acccae927da8e350a2c` | 2026-10-14 F tests: the two E-environment checks load a tree copy whose selector names E (they read the committed selector, which names F since 48d44d5) | observability-placement-runtime-otel-ablation (ancestor), observability-placement-runtime-otel-fseed (ancestor), observability-placement-runtime-otel-protocol (HEAD) | 250 |
| `otel-ablation-4ab4433/` | `4ab4433352e17818d19851434b8ffe73a1b26700` | 2026-10-15 Activate OTel F ablation (otel-offpath-f-nolag-v1) in this worktree: selector, tombstone, ledger, activation tests (mirrors 48d44d5) | observability-placement-runtime-otel-ablation (HEAD) | 253 |
| `otel-seed2-f08ba1d/` | `f08ba1d5313bef128ec88d73e1b4cdd1fe2cafe5` | 2026-10-15 R2 tests: F's descriptor and plan-1 pins re-pinned to seed 20261016; the replicate planted defect made seed-independent | observability-placement-runtime-otel-fseed (HEAD) | 250 |
| `teastore-c-3b4a513/` | `3b4a513ff3c4b00b65131dbc82ba1b472d1c0548` | 2026-10-11 Activate teastore-traffic-sweep-c-v1 (study-epoch selector) for campaign C, protocol decision 82 | observability-placement-runtime-teastore-protocol (ancestor) | 220 |
| `teastore-offpath-f74b29b/` | `f74b29b92de283878ca50ea4ab2a5e1beb74eef7` | 2026-10-14 Activate teastore-offpath-v1 (study-epoch selector) for the off-path pause, BUDGET_TEASTORE_OFFPATH.md | observability-placement-runtime-teastore-protocol (ancestor) | 223 |
| `teastore-offpath-placement-04254228/` | `04254228aba90566dfeca603dfcc7b05b7d8d2e3` | 2026-10-15 tests/test_teastore_barrier_ack.py: the barrier acknowledgement drains, is bounded, records its probes, and the terminal still refuses | observability-placement-runtime-teastore-protocol (HEAD) | 224 |
| `hotel-offpath-9ad0b98/` | `9ad0b98194f715b921aba187df5ed511082f1f7b` | 2026-10-15 Hotel off-path epoch: the consul row of images.json is its own image, not the application image (review blocker) | observability-placement-runtime-hotel-protocol (HEAD) | 182 |

## Launch and fetch scripts (`scratchpad/gate-drivers/`)

Copied from the working tree of the build machine (the only files not taken from a commit).

| File | SHA-256 as copied (before redaction) | Relation to the source commit |
|---|---|---|
| `scratchpad/gate-drivers/launch_teastore.sh` | `af4040549dd09e7b10818c576481509adc7f8f5a2d2e9828550f2256937855b1` | tracked at the commit, identical |
| `scratchpad/gate-drivers/launch_hotel.sh` | `6ede09d0feaf502ae5f4ed62656783b70cc336f76b53b30f9dffeaab128e2a06` | tracked at the commit, identical |
| `scratchpad/gate-drivers/launch_otel_offpath.sh` | `2b6499074b43dfa96e8c6a3c15c9f64aeb878f38480594b6fb33939e6bd33a5d` | tracked at the commit, identical |
| `scratchpad/gate-drivers/fetch_overnight.sh` | `427ffe392c6d1be7df373fad17cfb97ad08db9f0911c6883b33ac4961a2ae6a9` | tracked at the commit, identical |
| `scratchpad/gate-drivers/fetch_r1relaunch.sh` | `d2e3a497b7c9caded0873e8a8b9af36da3819e75daec4b9d787010eaf09a164d` | tracked at the commit, identical |
