# Logging

SNF uses Python's `logging` namespace `snf` and installs a `NullHandler`. It never calls `basicConfig()` or writes log files. The host application controls levels, handlers, and destinations.

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("snf").setLevel(logging.DEBUG)
```

For targeted diagnostics, set `snf.adapters.mdns`, `snf.adapters.ble`, `snf.engine`, or `snf.runtime` to DEBUG independently.

A pump-start message means SNF is consuming a plugin stream, not that a device was found. Plugin pump failures are logged; the background runtime logs unexpected consumer failures and disconnects slow subscribers when their buffers fill. A running consumer does not imply all plugins are healthy.

Use standard Python handlers/filters for separate files, JSON logs, or external observability; SNF requires no custom logging integration.
