"""Real handler against exact cached-helper/caller generations; no import fallback."""
import hashlib
import importlib
import importlib.util
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from . import test_attachment_tool_correlation as cases

H0_SHA = "37663e1735e57850c5de56bd333b34f4ebee6719bf8d3f6903dd2354dd9b5764"
H1_SHA = "d9784ee70d9c9fbd85ed1a801b0086e4997dc218f576ac0d3949760c14e26e4e"
C1_SHA = "0ae2e6fcc72ce31dd3295251972c4a6c0f3f82339ca84a52e342f1eaccfc02b1"


@pytest.fixture(scope="module", params=["h0_current", "h1_c1", "h1_current"])
def generation(request, tmp_path_factory):
    source = Path(__file__).resolve().parents[1]
    fixtures = source / "tests/fixtures/module_skew"
    assert hashlib.sha256((fixtures / "media_diagnostics_h0.py").read_bytes()).hexdigest() == H0_SHA
    assert hashlib.sha256((fixtures / "attachment_tool_c1.py").read_bytes()).hexdigest() == C1_SHA
    assert hashlib.sha256((fixtures / "media_diagnostics_h1.py").read_bytes()).hexdigest() == H1_SHA
    tree = tmp_path_factory.mktemp(request.param)
    for path in list(source.glob("*.py")) + list((source / "mixins").rglob("*.py")):
        dst = tree / path.relative_to(source)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
    helper = "media_diagnostics_h0.py" if request.param.startswith("h0_") else "media_diagnostics_h1.py"
    shutil.copy2(fixtures / helper, tree / "mixins/media_diagnostics.py")
    if request.param.endswith("_c1"):
        shutil.copy2(fixtures / "attachment_tool_c1.py", tree / "attachment_tool.py")
    name = "max_skew_" + request.param
    spec = importlib.util.spec_from_file_location(name, tree / "__init__.py", submodule_search_locations=[str(tree)])
    assert spec is not None and spec.loader is not None
    package = importlib.util.module_from_spec(spec)
    sys.modules[name] = package
    spec.loader.exec_module(package)
    # Load/cache the selected helper FIRST, exactly the risky deployment condition.
    diagnostic = importlib.import_module(name + ".mixins.media_diagnostics")
    assert hasattr(diagnostic, "media_group") is not request.param.startswith("h0_")
    yield SimpleNamespace(name=name, diagnostic=diagnostic, variant=request.param)
    for key in list(sys.modules):
        if key == name or key.startswith(name + "."):
            del sys.modules[key]


@pytest.mark.asyncio
@pytest.mark.parametrize("kinds", [("image",), ("video",), ("audio",), ("file",), ("image", "image")])
@pytest.mark.parametrize("case", ["success", "reject", "not_ready", "cancel", "upload_error", "upload_cancel", "prepare_error", "prepare_cancel", "transport_error", "invalid_json", "unknown_mid", "postprocess_error"])
async def test_cached_generation_real_registered_handler(generation, kinds, case, monkeypatch, tmp_path, caplog):
    tool = None
    try:
        tool = importlib.import_module(generation.name + ".attachment_tool")
    except ImportError as error:
        pytest.fail(f"cached-helper/new-caller must import without media_group: {error}", pytrace=False)
    assert tool is not None
    modules = {
        "attachment_tool": tool,
        "tools": importlib.import_module(generation.name + ".tools"),
        "media_diagnostics": generation.diagnostic,
        "media_readiness": importlib.import_module(generation.name + ".mixins.media_readiness"),
        "media_upload": importlib.import_module(generation.name + ".mixins.media_upload"),
    }
    for key, value in modules.items():
        monkeypatch.setattr(cases, key, value)
    finished = []
    finish = generation.diagnostic.MediaOperation.finish
    def counted_finish(self, *args, **kw):
        finished.append(self)
        return finish(self, *args, **kw)
    monkeypatch.setattr(generation.diagnostic.MediaOperation, "finish", counted_finish)
    await cases.test_registered_tool_owns_final_delivery(kinds, case, monkeypatch, tmp_path, caplog)
    assert len(finished) == len(kinds), "no extra silent-send accumulator completion"


@pytest.mark.parametrize("generation", ["h0_current", "h1_current"], indirect=True)
def test_fixed_network_transfer_no_history_or_extra_completion(generation, monkeypatch, caplog):
    import asyncio
    import gc
    import logging
    import threading
    import tracemalloc

    diagnostic = generation.diagnostic
    tool = importlib.import_module(generation.name + ".attachment_tool")
    caplog.set_level(logging.INFO)
    owners = [diagnostic.MediaOperation("adapter", kind) for kind in ("image", "video")]
    shared = diagnostic.MediaOperation("adapter", "file")
    for index, owner in enumerate(owners):
        owner.source_id, owner.file_fingerprint = str(index) * 64, "b" * 64
        owner.size, owner.attachment_index = 17 + index, index
        owner.durations["admission"] = 123
        owner.attempts["cdn"] = 1
    shared.active = shared.error_stage = "readiness"
    shared.error, shared.status, shared.mid = "error", 599, "c" * 64
    shared.wait_ms = diagnostic.MAX_MS
    for stage in ("readiness", "send"):
        shared.attempts[stage] = diagnostic.MAX_COUNT
        shared.durations[stage] = diagnostic.MAX_MS
    def forbidden(*args, **kw):
        raise AssertionError("transfer may not create I/O/tasks/threads")
    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(asyncio, "create_task", forbidden)
    monkeypatch.setattr(asyncio, "to_thread", forbidden)
    monkeypatch.setattr(threading.Thread, "start", forbidden)
    tracemalloc.start()
    try:
        for _ in range(100):
            tool._copy_send_diagnostics(shared, owners)
        gc.collect()
        before = tracemalloc.get_traced_memory()[0]
        for _ in range(20000):
            tool._copy_send_diagnostics(shared, owners)
        gc.collect()
        growth = tracemalloc.get_traced_memory()[0] - before
        assert growth < 65536
    finally:
        tracemalloc.stop()
    assert not cases.rows(caplog) and not shared.finished
    for index, owner in enumerate(owners):
        assert not hasattr(owner, "__dict__")
        assert set(owner.durations) == set(owner.attempts) == set(diagnostic.STAGES)
        assert owner.media_type == ("image", "video")[index]
        assert owner.source_id == str(index) * 64 and owner.file_fingerprint == "b" * 64
        assert owner.size == 17 + index and owner.durations["admission"] == 123
        assert owner.attempts["cdn"] == 1
        assert owner.wait_ms == diagnostic.MAX_MS and owner.status == 599
        assert owner.error_stage == "readiness" and owner.error == "error" and owner.mid == "c" * 64
        for stage in ("readiness", "send"):
            assert owner.attempts[stage] == diagnostic.MAX_COUNT
            assert owner.durations[stage] == diagnostic.MAX_MS
        owner.finish("error")
    assert len(cases.rows(caplog)) == 2
    assert diagnostic._current.get() is None
    print(f"transfer_generation={generation.variant} retained_growth_bytes={growth} owners=2 temporary_summaries=0 no_io_tasks_threads=true")
