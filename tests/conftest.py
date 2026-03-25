"""Shared pytest configuration."""

import os

# autoresearch.py requires GITHUB_TOKEN at import time
os.environ.setdefault("GITHUB_TOKEN", "test-token-for-tests")
