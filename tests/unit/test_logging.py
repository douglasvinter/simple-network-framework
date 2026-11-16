"""Verify SNF leaves logging destinations under application control."""

from __future__ import annotations

import importlib
import logging

import snf


def test_snf_uses_only_null_handler_by_default():
    logger = logging.getLogger("snf")
    assert any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)


def test_reimport_does_not_modify_root_handlers():
    root = logging.getLogger()
    before = tuple(root.handlers)
    importlib.reload(snf)
    assert tuple(root.handlers) == before


def test_snf_logs_propagate_to_application_handler():
    logger = logging.getLogger("snf.engine")
    parent = logging.getLogger("snf")
    root = logging.getLogger()
    records: list[logging.LogRecord] = []

    class CollectingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = CollectingHandler()
    original_level = logger.level
    original_parent_level = parent.level
    original_propagate = parent.propagate
    try:
        parent.setLevel(logging.DEBUG)
        parent.propagate = True
        logger.setLevel(logging.DEBUG)
        root.addHandler(handler)
        logger.info("SNF test message")
        assert len(records) == 1
        assert records[0].name == "snf.engine"
        assert records[0].getMessage() == "SNF test message"
    finally:
        root.removeHandler(handler)
        handler.close()
        logger.setLevel(original_level)
        parent.setLevel(original_parent_level)
        parent.propagate = original_propagate
