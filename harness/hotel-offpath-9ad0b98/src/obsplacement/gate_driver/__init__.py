"""candidate_common: the shared gate-driver library (plan node B1).

Factors the governance flow implemented four times over in
`scratchpad/gate-drivers/{gate_setup,gate_run,campaign_setup,
campaign_status}.py` (TeaStore's canonical, campaign-proven drivers) into one
reusable library, so Hotel Reservation, OTel Demo, and Online Boutique each
get a driver set from a small `contract.SutConfig` plus loaded adapter/
transport modules, instead of four divergent reimplementations of the same
GATE-PLAN -> GATE-SETUP -> readiness -> preflight -> GATE-RUN chain.

See each submodule's docstring for what it generalizes and which exact lines
of the canonical scripts it replaces. `contract.py` is the place to start:
it defines `SutConfig` (the "thin per-SUT configuration") and the
`AdapterProtocol` / `TransportProtocol` a SUT module must satisfy.
"""
