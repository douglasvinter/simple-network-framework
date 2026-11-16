"""Simple Network Framework public API."""

import logging

from snf.engine import DiscoveryEngine
from snf.models import (
    Device,
    DiscoveryEvent,
    DiscoveryState,
    Endpoint,
    Service,
)
from snf.plugins import DiscoveryPlugin, create_plugins, load_plugins
from snf.registry import DeviceRegistry

# Library logging is configured by the consuming application.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "Device",
    "DeviceRegistry",
    "DiscoveryEngine",
    "DiscoveryEvent",
    "DiscoveryPlugin",
    "DiscoveryState",
    "Endpoint",
    "Service",
    "create_plugins",
    "load_plugins",
]

__version__ = "1.0.0"
