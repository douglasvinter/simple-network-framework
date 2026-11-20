"""Cross-platform SLP subprocess contract tests (Windows and Linux).

These tests intentionally mock the OS process boundary; live OpenSLP validation
requires an installed slptool and a controlled responder on each platform.
"""

import asyncio
from types import SimpleNamespace

import pytest

from snf.adapters.slp import SLPPlugin


@pytest.mark.asyncio
async def test_slp_invokes_system_binary_with_scope_and_parses_services(monkeypatch):
    calls = []

    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            returncode=0,
            communicate=lambda: asyncio.sleep(
                0, result=(b"service:printer://printer.local:9100,600\n", b"")
            ),
        )

    monkeypatch.setattr("snf.adapters.slp.shutil.which", lambda cmd: "C:/tools/slptool.exe")
    monkeypatch.setattr("snf.adapters.slp.asyncio.create_subprocess_exec", fake_exec)
    plugin = SLPPlugin(service_types=["service:printer"], scope="DEFAULT", interval=0.01)
    assert plugin.command == "C:/tools/slptool.exe"
    assert await plugin._run("findsrvs", "service:printer") == [
        "service:printer://printer.local:9100,600"
    ]
    assert calls[0][0] == (
        "C:/tools/slptool.exe", "-s", "DEFAULT", "findsrvs", "service:printer"
    )


@pytest.mark.asyncio
async def test_slp_command_failure_surfaces_stderr(monkeypatch):
    async def fake_exec(*args, **kwargs):
        return SimpleNamespace(
            returncode=1,
            communicate=lambda: asyncio.sleep(0, result=(b"", b"service unavailable")),
        )

    monkeypatch.setattr("snf.adapters.slp.shutil.which", lambda cmd: "/usr/bin/slptool")
    monkeypatch.setattr("snf.adapters.slp.asyncio.create_subprocess_exec", fake_exec)
    plugin = SLPPlugin(service_types=["service:printer"], interval=0.01)
    with pytest.raises(RuntimeError, match="service unavailable"):
        await plugin._run("findsrvs", "service:printer")


@pytest.mark.asyncio
async def test_slp_subprocess_timeout_terminates_process(monkeypatch):
    process = SimpleNamespace(returncode=None, killed=False)

    async def communicate():
        if not process.killed:
            await asyncio.Event().wait()
        return b"", b""

    def kill():
        process.killed = True

    process.communicate = communicate
    process.kill = kill

    async def fake_exec(*args, **kwargs):
        return process

    monkeypatch.setattr("snf.adapters.slp.shutil.which", lambda cmd: "/usr/bin/slptool")
    monkeypatch.setattr("snf.adapters.slp.asyncio.create_subprocess_exec", fake_exec)
    plugin = SLPPlugin(service_types=["service:printer"], command_timeout=0.01)
    with pytest.raises(TimeoutError, match="SLP command timed out"):
        await plugin._run("findsrvs", "service:printer")
    assert process.killed


def test_slp_requires_installed_system_binary(monkeypatch):
    monkeypatch.setattr("snf.adapters.slp.shutil.which", lambda cmd: None)
    with pytest.raises(RuntimeError, match="slptool"):
        SLPPlugin()
