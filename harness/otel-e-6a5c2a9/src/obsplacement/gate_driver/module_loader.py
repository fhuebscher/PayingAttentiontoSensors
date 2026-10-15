"""Loading SUT modules by file path, and sourcing binding keys the safe way.

Every canonical driver defines the same `load(name, relative)` helper
(gate_setup.py:29-34, gate_run.py:34-39, campaign_setup.py:48-53) that loads
a module directly from a file path in the pinned runtime worktree, rather
than importing it as an installed package -- the module under test/drive is
whatever the framework commit at `ROOT` currently contains, not whatever
happens to be on `sys.path`.

`load_binding_keys` exists because of a specific, named incident. From
campaign_setup.py's own comment (campaign_setup.py:42-46):

    Deliberately NOT a copy of the key list. This was a seventh
    transcription of it, and adding activationCompile to the six in-repo
    declarations left this one behind, so the binding digest the driver
    computed no longer matched the one the target computed and readiness
    refused every install.

and gate_setup.py's cmd_readiness (gate_setup.py:216-224):

    The release binding must be hashed over EXACTLY the framework's
    authoritative key set; a hardcoded copy here silently drifts ... so
    source the keys from the installed installer module instead.

Non-negotiable property #2 is: exactly one function in this whole library may
read `RELEASE_BINDING_KEYS`, and it always reads it from the loaded SUT
module, never from a literal tuple/list checked in anywhere else.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .errors import ContractViolation, ModuleLoadError

__all__ = ["load_module", "load_sut_module", "load_binding_keys"]


def load_module(name: str, path: Path):
    """Load a module from an exact file path (not via `sys.path` import)."""
    path = Path(path)
    if not path.is_file():
        raise ModuleLoadError(f"cannot load module '{name}': {path} does not exist")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ModuleLoadError(f"cannot load module '{name}' from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_sut_module(root: Path, relative: str, name: str):
    """Load a SUT-owned module at `root / relative` under a stable module name.

    `root` is the pinned runtime worktree for the campaign in question (each
    SUT's `SutConfig.root`), never the development checkout this library
    itself lives in -- see contract.SutConfig's docstring.

    `relative` must be relative. `Path("/a") / "/b" == Path("/b")`: an
    absolute `relative` silently discards `root` entirely, so a SUT module
    path could name any file on the machine while still looking like it was
    resolved inside the pinned worktree. Refused here rather than defended
    against at each of the seven call sites.
    """
    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise ContractViolation(
            name, (f"module path must be relative to root, got {relative!r}",),
        )
    return load_module(name, Path(root) / relative_path)


def load_binding_keys(root: Path, installer_relative: str, *,
                       module_name: str = "candidate_release_installer",
                       attr: str = "RELEASE_BINDING_KEYS") -> tuple:
    """Return the installed framework's own `RELEASE_BINDING_KEYS`, sourced
    fresh from the loaded installer module every time this is called.

    There is no fallback list and no caching of a previously-seen value: if
    the attribute is missing, this raises `ContractViolation` rather than
    silently proceeding with an empty or stale key set (fail closed, per
    non-negotiable property #2 -- a wrong-but-present key set is exactly the
    bug that made readiness refuse every install).
    """
    installer = load_sut_module(root, installer_relative, module_name)
    try:
        keys = getattr(installer, attr)
    except AttributeError as exc:
        raise ContractViolation(installer_relative, (attr,)) from exc
    return tuple(keys)
