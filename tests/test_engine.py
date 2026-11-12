import pytest

from snf.engine import DiscoveryEngine
from snf.models import Service


class FakePlugin:
    name = "fake"

    def __init__(self):
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def discover(self):
        yield Service(protocol=self.name, name="test", address="127.0.0.1")

    async def stop(self):
        self.stopped = True


@pytest.mark.asyncio
async def test_engine_lifecycle_and_discovery():
    plugin = FakePlugin()
    async with DiscoveryEngine([plugin]) as engine:
        assert plugin.started
        results = [service async for service in engine.discover()]
        assert len(results) == 1
        assert results[0].address == "127.0.0.1"
    assert plugin.stopped


@pytest.mark.asyncio
async def test_engine_requires_context_manager():
    engine = DiscoveryEngine([])
    with pytest.raises(RuntimeError):
        _ = [service async for service in engine.discover()]
