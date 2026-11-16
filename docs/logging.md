# Logging integration

SNF is a Python library, not an application logging configurator. It uses
`logging.getLogger(__name__)` under the `snf` namespace, with a
`logging.NullHandler` on the `snf` package logger. The consuming application
controls levels, handlers, formatting, rotation, and destinations.

SNF never calls `logging.basicConfig()` in library code and never writes
log files itself. The standalone example may configure logging because it is
an application entry point.

## Share application handlers

The simplest configuration routes SNF and application records through the
root logger. Propagation is enabled by default; `NullHandler` does not block
records from reaching parent handlers.

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logging.getLogger("snf").setLevel(logging.DEBUG)
```

## Separate SNF logs from application logs

Configure distinct handlers in the consuming application:

```python
import logging.config

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        }
    },
    "handlers": {
        "application": {
            "class": "logging.FileHandler",
            "filename": "application.log",
            "formatter": "standard",
        },
        "snf_file": {
            "class": "logging.FileHandler",
            "filename": "snf.log",
            "formatter": "standard",
        },
    },
    "loggers": {
        "my_home_automation": {
            "level": "INFO",
            "handlers": ["application"],
            "propagate": False,
        },
        "snf": {
            "level": "DEBUG",
            "handlers": ["snf_file"],
            "propagate": False,
        },
    },
})
```

`propagate=False` prevents duplicate records when the root logger has
additional handlers. Use `propagate=True` (the default) when you want SNF
records to flow into the application's parent/root handlers.

## Per-protocol levels

All module loggers inherit the `snf` namespace. You can selectively
change verbosity:

```python
import logging

logging.getLogger("snf").setLevel(logging.INFO)
logging.getLogger("snf.adapters.ble").setLevel(logging.DEBUG)
logging.getLogger("snf.adapters.mdns").setLevel(logging.WARNING)
```

Standard Python logging filters, queue handlers, JSON formatters, and
observability integrations can be configured by the consuming application.
SNF does not require a logger constructor parameter.
