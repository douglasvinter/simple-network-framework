from __future__ import annotations

import asyncio

import pytest

from snf import DiscoveryEngine, DiscoveryState, InMemoryStorage
from snf.adapters.slp import SLPPlugin


class FakeProcess:
    returncode = 0

    def __init__(self, output: bytes):
        self.output = output

    async def communicate(self):
        return self.output, b""

    def kill(self):
        pass


@pytest.mark.asyncio
async def test_real_slp_adapter_and_engine_with_mocked_subprocess(monkeypatch):
    calls = []

    async def fake_create_subprocess_exec(*command, **kwargs):
        calls.append(command)
        if command[-1] == "findsrvtypes":
            return FakeProcess(b"service:printer\n")
        if command[-2:] == ("findsrvs", "service:printer"):
            return FakeProcess(
                b"service:printer://printer.local:9100/queue,600\n"
            )
        raise AssertionError(f"Unexpected slptool command: {command!r}")

    monkeypatch.setattr("snf.adapters.slp.shutil.which", lambda command: "/mock/slptool")
    monkeypatch.setattr(
        "snf.adapters.slp.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    plugin = SLPPlugin(interval=60, command_timeout=1)

    async with DiscoveryEngine([plugin], storage=InMemoryStorage()) as engine:
        stream = engine.discover()
        event = await asyncio.wait_for(anext(stream), timeout=1)
        await stream.aclose()

        assert event.state is DiscoveryState.ADDED
        assert event.observation.protocol == "slp"
        assert event.observation.services[0].service_type == "printer"
        assert event.observation.endpoints[0].address == "printer.local"
        assert event.observation.endpoints[0].port == 9100
        assert event.observation.metadata["lifetime"] == "600"
        assert engine.get_observation("slp", event.observation.identifier) == event.observation

    assert len(calls) == 2
