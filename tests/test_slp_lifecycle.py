"""SLP snapshot reconciliation and lifecycle contracts."""

import asyncio

import pytest

from snf.adapters.slp import SLPPlugin
from snf.models import DiscoveryState


@pytest.mark.asyncio
async def test_slp_emits_removal_then_rediscovery(monkeypatch):
    monkeypatch.setattr("snf.adapters.slp.shutil.which", lambda command: "/mock/slptool")
    plugin = SLPPlugin(service_types=["service:printer"], interval=0.001)
    responses = iter([
        ["service:printer://printer.local:9100,600"],
        [],
        ["service:printer://printer.local:9100,600"],
    ])

    async def fake_run(*args):
        return next(responses)

    plugin._run = fake_run
    await plugin.start()
    stream = plugin.discover()
    try:
        events = [await asyncio.wait_for(anext(stream), 0.5) for _ in range(3)]
    finally:
        await stream.aclose()
        await plugin.stop()
    assert [event.state for event in events] == [
        DiscoveryState.ADDED, DiscoveryState.REMOVED, DiscoveryState.ADDED
    ]


@pytest.mark.asyncio
async def test_slp_same_service_url_is_not_reannounced(monkeypatch):
    monkeypatch.setattr("snf.adapters.slp.shutil.which", lambda command: "/mock/slptool")
    plugin = SLPPlugin(service_types=["service:printer"], interval=0.001)
    responses = iter([
        ["service:printer://printer.local:9100,600"],
        ["service:printer://printer.local:9100,600"],
        ["service:printer://printer.local:9100,600", "service:printer://tv.local:9100,600"],
    ])

    async def fake_run(*args):
        return next(responses)

    plugin._run = fake_run
    await plugin.start()
    stream = plugin.discover()
    try:
        first = await asyncio.wait_for(anext(stream), 0.5)
        second = await asyncio.wait_for(anext(stream), 0.5)
    finally:
        await stream.aclose()
        await plugin.stop()
    assert first.state is second.state is DiscoveryState.ADDED
    assert first.observation.identifier != second.observation.identifier


@pytest.mark.asyncio
async def test_slp_restart_resets_previous_discovery_state(monkeypatch):
    monkeypatch.setattr("snf.adapters.slp.shutil.which", lambda command: "/mock/slptool")
    plugin = SLPPlugin(service_types=["service:printer"], interval=0.001)

    async def fake_run(*args):
        return ["service:printer://printer.local:9100,600"]

    plugin._run = fake_run
    for _ in range(2):
        await plugin.start()
        stream = plugin.discover()
        try:
            event = await asyncio.wait_for(anext(stream), 0.5)
            assert event.state is DiscoveryState.ADDED
        finally:
            await stream.aclose()
            await plugin.stop()
