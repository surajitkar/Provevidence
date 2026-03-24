"""Tests for app.hello."""

from app.hello import hello_universe


def test_hello_universe_prints(capsys):
    hello_universe()
    out, _ = capsys.readouterr()
    assert out.strip() == "Hello, universe!"
