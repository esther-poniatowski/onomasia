"""Pytest configuration and shared fixtures for onomasia tests."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_states(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the cache of the states of Anagraphe to a folder of the test, and name no machine file
    of local clones, so that no test reads or fills the cache of the user."""
    cache = tmp_path_factory.mktemp("anagraphe-cache")
    monkeypatch.setenv("ANAGRAPHE_CACHE", str(cache))
    monkeypatch.delenv("ANAGRAPHE_REPOSITORIES", raising=False)
    return cache
