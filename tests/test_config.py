import pytest

from spendcube import config


def test_require_returns_value(monkeypatch):
    monkeypatch.setenv("EXAMPLE_SETTING", "abc")
    assert config.require("EXAMPLE_SETTING") == "abc"


def test_require_fails_clearly_when_missing(monkeypatch):
    monkeypatch.delenv("EXAMPLE_SETTING", raising=False)
    with pytest.raises(RuntimeError, match="EXAMPLE_SETTING"):
        config.require("EXAMPLE_SETTING")


def test_get_uses_default(monkeypatch):
    monkeypatch.delenv("EXAMPLE_SETTING", raising=False)
    assert config.get("EXAMPLE_SETTING", "fallback") == "fallback"
