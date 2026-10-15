import pytest

from obsplacement.gate_driver.errors import ContractViolation, ModuleLoadError
from obsplacement.gate_driver.module_loader import load_binding_keys, load_module, load_sut_module


def test_load_module_executes_the_file_and_returns_its_namespace(tmp_path):
    module_path = tmp_path / "greeter.py"
    module_path.write_text("VALUE = 41 + 1\n")
    module = load_module("greeter_under_test", module_path)
    assert module.VALUE == 42


def test_load_module_raises_for_a_missing_file(tmp_path):
    with pytest.raises(ModuleLoadError):
        load_module("missing_under_test", tmp_path / "does-not-exist.py")


def test_load_sut_module_resolves_relative_to_root(tmp_path):
    (tmp_path / "modules" / "fake").mkdir(parents=True)
    (tmp_path / "modules" / "fake" / "installer.py").write_text("RELEASE_BINDING_KEYS = ('a', 'b')\n")
    module = load_sut_module(tmp_path, "modules/fake/installer.py", "installer_under_test")
    assert module.RELEASE_BINDING_KEYS == ("a", "b")


def test_load_binding_keys_sources_from_the_loaded_module_every_call(tmp_path):
    """Non-negotiable property #2: binding keys come from the installed
    framework, never a hardcoded copy. Changing the file must change what
    the next call returns -- there is no caching of a stale value."""
    installer_path = tmp_path / "installer.py"
    installer_path.write_text("RELEASE_BINDING_KEYS = ('releaseRoot', 'imageBuildReceiptSha256')\n")
    first = load_binding_keys(tmp_path, "installer.py", module_name="installer_v1")
    assert first == ("releaseRoot", "imageBuildReceiptSha256")

    # The seventh-transcription incident this guards against: the installed
    # framework adds a key, and the driver must pick it up without anyone
    # editing a second, hand-copied list anywhere.
    installer_path.write_text(
        "RELEASE_BINDING_KEYS = ('releaseRoot', 'imageBuildReceiptSha256', 'activationCompile')\n"
    )
    second = load_binding_keys(tmp_path, "installer.py", module_name="installer_v2")
    assert second == ("releaseRoot", "imageBuildReceiptSha256", "activationCompile")


def test_load_binding_keys_fails_closed_when_the_attribute_is_missing(tmp_path):
    installer_path = tmp_path / "installer_no_keys.py"
    installer_path.write_text("SOMETHING_ELSE = 1\n")
    with pytest.raises(ContractViolation) as excinfo:
        load_binding_keys(tmp_path, "installer_no_keys.py", module_name="installer_broken")
    assert "RELEASE_BINDING_KEYS" in excinfo.value.missing


def test_load_binding_keys_has_no_hardcoded_fallback_list():
    """A direct check on the seam itself: the function's keyword defaults
    (`module_name`, `attr`) are strings naming *where to look*, never a
    literal key list standing in for the real one."""
    defaults = dict(load_binding_keys.__kwdefaults__ or {})
    assert set(defaults) == {"module_name", "attr"}
    for value in defaults.values():
        assert isinstance(value, str)



def test_load_sut_module_rejects_an_absolute_relative_path(tmp_path):
    """`Path(root) / "/etc/passwd"` is `Path("/etc/passwd")`: an absolute
    `relative` silently discards `root`, so a SUT module path could name any
    file on the machine while still reading as "inside the pinned worktree"."""
    escapee = tmp_path / "outside_the_root.py"
    escapee.write_text("RELEASE_BINDING_KEYS = ('escaped',)\n")
    root = tmp_path / "pinned-runtime-root"
    root.mkdir()
    with pytest.raises(ContractViolation) as excinfo:
        load_sut_module(root, str(escapee), "escaped_module")
    assert "relative" in excinfo.value.missing[0]


def test_load_sut_module_still_loads_an_ordinary_relative_path(tmp_path):
    module_dir = tmp_path / "modules/sut/execution"
    module_dir.mkdir(parents=True)
    (module_dir / "adapter.py").write_text("MARKER = 'loaded'\n")
    module = load_sut_module(tmp_path, "modules/sut/execution/adapter.py", "relative_ok")
    assert module.MARKER == "loaded"
