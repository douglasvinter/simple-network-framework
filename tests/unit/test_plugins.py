from __future__ import annotations

import logging

import snf.plugins as plugin_module


class EntryPoint:
    def __init__(
        self,
        name: str,
        value: str,
        loaded: object = None,
        error: Exception | None = None,
    ):
        self.name = name
        self.value = value
        self._loaded = loaded
        self._error = error

    def load(self) -> object:
        if self._error is not None:
            raise self._error
        return self._loaded


class ValidPlugin:
    async def start(self) -> None:
        pass

    async def discover(self):
        if False:
            yield

    async def stop(self) -> None:
        pass


def test_load_plugins_logs_import_failure_and_continues(monkeypatch, caplog):
    broken = EntryPoint("broken", "broken_plugin:Plugin", error=ImportError("missing dependency"))
    valid = EntryPoint("valid", "valid_plugin:Plugin", loaded=ValidPlugin)
    monkeypatch.setattr(plugin_module, "entry_points", lambda **kwargs: [broken, valid])

    with caplog.at_level(logging.ERROR, logger="snf.plugins"):
        loaded = plugin_module.load_plugins()

    assert loaded == {"valid": ValidPlugin}
    assert "Failed to load SNF protocol plugin 'broken'" in caplog.text
    assert "missing dependency" in caplog.text


def test_load_plugins_logs_invalid_plugin_and_continues(monkeypatch, caplog):
    invalid = EntryPoint("invalid", "invalid_plugin:Plugin", loaded=object)
    valid = EntryPoint("valid", "valid_plugin:Plugin", loaded=ValidPlugin)
    monkeypatch.setattr(plugin_module, "entry_points", lambda **kwargs: [invalid, valid])

    with caplog.at_level(logging.ERROR, logger="snf.plugins"):
        loaded = plugin_module.load_plugins()

    assert loaded == {"valid": ValidPlugin}
    assert "missing start()" in caplog.text


def test_load_plugins_logs_and_skips_duplicate_entry_points(monkeypatch, caplog):
    first = EntryPoint("same", "first:Plugin", loaded=ValidPlugin)
    duplicate = EntryPoint("same", "second:Plugin", loaded=ValidPlugin)
    monkeypatch.setattr(plugin_module, "entry_points", lambda **kwargs: [first, duplicate])

    with caplog.at_level(logging.ERROR, logger="snf.plugins"):
        loaded = plugin_module.load_plugins()

    assert loaded == {"same": ValidPlugin}
    assert "duplicate SNF protocol plugin" in caplog.text


class BrokenConstructorPlugin(ValidPlugin):
    def __init__(self):
        raise RuntimeError("cannot initialize")


def test_create_plugins_skips_broken_constructor_by_default(monkeypatch, caplog):
    monkeypatch.setattr(
        plugin_module,
        "load_plugins",
        lambda: {"broken": BrokenConstructorPlugin, "valid": ValidPlugin},
    )
    with caplog.at_level(logging.ERROR, logger="snf.plugins"):
        instances = plugin_module.create_plugins()

    assert len(instances) == 1
    assert isinstance(instances[0], ValidPlugin)
    assert "Failed to initialize SNF protocol plugin 'broken'" in caplog.text


def test_create_plugins_strict_raises_constructor_error(monkeypatch):
    monkeypatch.setattr(
        plugin_module,
        "load_plugins",
        lambda: {"broken": BrokenConstructorPlugin, "valid": ValidPlugin},
    )
    import pytest

    with pytest.raises(RuntimeError, match="cannot initialize"):
        plugin_module.create_plugins(strict=True)
