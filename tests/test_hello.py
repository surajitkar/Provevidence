"""Tests for app.hello."""

from app.hello import ask_age, hello_universe


def test_hello_universe_prints(capsys):
    hello_universe()
    out, _ = capsys.readouterr()
    assert out.strip() == "Hello, universe!"


def test_ask_age_returns_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "42")
    assert ask_age() == "42"
