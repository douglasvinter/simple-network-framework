from __future__ import annotations

import asyncio
import logging

import pytest

from snf import Device, DiscoveryEngine, DiscoveryEvent, DiscoveryState, InMemoryStorage


class QueuePlugin:
    def __init__(self, name: str, events=()):
        self.name = name
        self.events = events
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def discover(self):
        for event in self.events:
            yield event

    async def stop(self):
        self.stopped = True


def event(name: str, state: DiscoveryState = DiscoveryState.ADDED):
    return DiscoveryEvent(state, Device("test", name, name))


@pytest.mark.asyncio
async def test_failing_plugin_does_not_interrupt_healthy_plugin(caplog):
    class FailingPlugin(QueuePlugin):
        async def discover(self):
            yield event("before-error")
            raise RuntimeError("simulated protocol failure")

    healthy = QueuePlugin("healthy", [event("healthy-device")])
    failing = FailingPlugin("failing")

    with caplog.at_level(logging.ERROR, logger="snf.engine"):
        async with DiscoveryEngine([failing, healthy], storage=InMemoryStorage()) as engine:
            received = [item async for item in engine.discover()]

    assert {item.device.identifier for item in received} == {
        "before-error",
        "healthy-device",
    }
    assert healthy.stopped and failing.stopped
    assert "Discovery plugin failing failed" in caplog.text


@pytest.mark.asyncio
async def test_closing_consumer_cancels_plugin_streams_and_runs_generator_cleanup():
    cleaned_up = asyncio.Event()

    class ContinuousPlugin(QueuePlugin):
        async def discover(self):
            try:
                yield event("first")
                await asyncio.Event().wait()
            finally:
                cleaned_up.set()

    plugin = ContinuousPlugin("continuous")
    async with DiscoveryEngine([plugin], storage=InMemoryStorage()) as engine:
        stream = engine.discover()
        first = await asyncio.wait_for(anext(stream), timeout=1)
        assert first.device.identifier == "first"
        await stream.aclose()
        await asyncio.wait_for(cleaned_up.wait(), timeout=1)

    assert plugin.stopped


@pytest.mark.asyncio
async def test_removed_device_is_removed_from_inventory_and_can_reappear():
    device = Device("test", "device-1", "Device")
    plugin = QueuePlugin(
        "test",
        [
            DiscoveryEvent(DiscoveryState.ADDED, device),
            DiscoveryEvent(DiscoveryState.REMOVED, device),
            DiscoveryEvent(DiscoveryState.ADDED, device),
        ],
    )

    async with DiscoveryEngine([plugin], storage=InMemoryStorage()) as engine:
        received = [item async for item in engine.discover()]
        assert engine.get_device("test", "device-1") == device

    assert [item.state for item in received] == [
        DiscoveryState.ADDED,
        DiscoveryState.REMOVED,
        DiscoveryState.ADDED,
    ]


@pytest.mark.asyncio
async def test_plugin_shutdown_failure_does_not_prevent_other_shutdown(caplog):
    class StopFailurePlugin(QueuePlugin):
        async def stop(self):
            self.stopped = True
            raise RuntimeError("stop failed")

    failing = StopFailurePlugin("failing")
    healthy = QueuePlugin("healthy")

    with caplog.at_level(logging.WARNING, logger="snf.engine"):
        async with DiscoveryEngine([failing, healthy], storage=InMemoryStorage()):
            pass

    assert failing.stopped and healthy.stopped
    assert "Failed to stop failing cleanly" in caplog.text
