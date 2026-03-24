"""Tests for app.hello."""

import random

from app.hello import hello_universe, hello_welcome_planet


def test_hello_universe_prints(capsys):
    hello_universe()
    out, _ = capsys.readouterr()
    assert out.strip() == "Hello, universe!"


def test_hello_welcome_planet_uses_random_planet(capsys, monkeypatch):
    monkeypatch.setattr(random, "choice", lambda _seq: "Mars")
    hello_welcome_planet()
    out, _ = capsys.readouterr()
    assert out.strip() == "hello welcome to Mars"
