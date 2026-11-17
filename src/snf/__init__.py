"""Simple Network Framework public API."""

import logging

from snf.engine import DiscoveryEngine
from snf.entities import EntityResolver, NetworkEntity
from snf.models import (
    DiscoveryEvent,
    DiscoveryObservation,
    DiscoveryState,
    Endpoint,
    Service,
)
from snf.plugins import DiscoveryPlugin, create_plugins, load_plugins
from snf.registry import ObservationRegistry
from snf.runtime import DiscoverySubscription, NetworkRuntime
from snf.storage import InMemoryStorage, ObservationStorage

# Library logging is configured by the consuming application.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "DiscoveryObservation",
    "EntityResolver",
    "NetworkEntity",
    "ObservationRegistry",
    "NetworkRuntime",
    "DiscoverySubscription",
    "DiscoveryEngine",
    "DiscoveryEvent",
    "DiscoveryPlugin",
    "DiscoveryState",
    "Endpoint",
    "InMemoryStorage",
    "ObservationStorage",
    "Service",
    "create_plugins",
    "load_plugins",
]

__version__ = "1.0.0"
