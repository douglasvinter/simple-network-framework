"""Background consumer, fan-out and lifecycle contracts."""

import asyncio

import pytest

from snf import DiscoveryEvent, DiscoveryObservation, DiscoveryState
from snf.runtime import NetworkRuntime


class FakePlugin:
    name = "fake"

    def __init__(self):
        self.queue = asyncio.Queue()
        self.stopped = False

    async def start(self):
        pass

    async def discover(self):
        while True:
            yield await self.queue.get()

    async def stop(self):
        self.stopped = True


def event(identifier):
    return DiscoveryEvent(DiscoveryState.ADDED, DiscoveryObservation("fake", identifier, "Device"))


@pytest.mark.asyncio
async def test_one_consumer_multiple_subscribers_and_snapshot():
    plugin = FakePlugin()
    async with NetworkRuntime([plugin]) as runtime:
        first = runtime.subscribe()
        second = runtime.subscribe(protocol="fake")
        first_events = aiter(first)
        second_events = aiter(second)
        await plugin.queue.put(event("one"))
        assert (await asyncio.wait_for(anext(first_events), 1)).observation.identifier == "one"
        assert (await asyncio.wait_for(anext(second_events), 1)).observation.identifier == "one"
        assert runtime.snapshot() == (event("one").observation,)
        assert runtime.observation_map() == {"fake": {"one": event("one").observation}}
        first.close()
        second.close()
    assert plugin.stopped


@pytest.mark.asyncio
async def test_slow_subscriber_is_disconnected_without_blocking_discovery():
    plugin = FakePlugin()
    async with NetworkRuntime([plugin], subscriber_buffer_size=1) as runtime:
        subscriber = runtime.subscribe()
        await plugin.queue.put(event("one"))
        await plugin.queue.put(event("two"))
        for _ in range(100):
            if len(runtime.snapshot()) == 2:
                break
            await asyncio.sleep(0.01)
        assert len(runtime.snapshot()) == 2
        assert subscriber._closed
        assert len(runtime._subscribers) == 0


@pytest.mark.asyncio
async def test_validation_and_shutdown_closes_subscribers():
    plugin = FakePlugin()
    runtime = NetworkRuntime([plugin])
    async with runtime:
        with pytest.raises(ValueError):
            runtime.subscribe(protocol="other")
        subscriber = runtime.subscribe()
    assert subscriber._closed
    assert not runtime.running
    assert plugin.stopped


@pytest.mark.asyncio
async def test_no_plugins_and_reentry():
    runtime = NetworkRuntime([])
    async with runtime:
        with pytest.raises(RuntimeError):
            await runtime.__aenter__()
        assert not runtime.running or runtime.protocols == ()
    with pytest.raises(RuntimeError):
        runtime.snapshot()
