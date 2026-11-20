"""Characterize subscription shutdown semantics before type-safe iteration cleanup."""

import asyncio

import pytest

from snf.models import DiscoveryEvent, DiscoveryObservation, DiscoveryState
from snf.runtime import DiscoverySubscription


class _RuntimeStub:
    def __init__(self):
        self._subscribers = set()


@pytest.mark.asyncio
async def test_close_wakes_blocked_reader_and_terminates_iteration():
    runtime = _RuntimeStub()
    subscription = DiscoverySubscription(runtime, None, 1)
    runtime._subscribers.add(subscription)
    iterator = aiter(subscription)
    pending = asyncio.create_task(anext(iterator))
    await asyncio.sleep(0)
    subscription.close()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(pending, 1)
    assert subscription not in runtime._subscribers


@pytest.mark.asyncio
async def test_close_discards_full_queue_and_preserves_idempotency():
    runtime = _RuntimeStub()
    subscription = DiscoverySubscription(runtime, None, 1)
    runtime._subscribers.add(subscription)
    observation = DiscoveryObservation("mdns", "one", "One")
    subscription._queue.put_nowait(DiscoveryEvent(DiscoveryState.ADDED, observation))
    subscription.close()
    subscription.close()
    with pytest.raises(StopAsyncIteration):
        await anext(aiter(subscription))
