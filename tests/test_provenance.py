"""Tests of the provenance of a build: the location of a repository written under `sources`."""

import pytest

from onomasia.provenance import public_location


@pytest.mark.parametrize(
    ("url", "public"),
    [
        ("https://user:token@github.com/org/repo.git", "https://github.com/org/repo.git"),
        ("https://token@example.org:8443/repo", "https://example.org:8443/repo"),
        ("ssh://git@host.org/org/repo.git", "ssh://host.org/org/repo.git"),
        ("git@github.com:org/repo.git", "github.com:org/repo.git"),
        ("https://github.com/org/repo.git", "https://github.com/org/repo.git"),
        ("/path/to/repo", "/path/to/repo"),
    ],
)
def test_public_location_strips_the_user_information(url: str, public: str) -> None:
    """The location of a remote loses its user and its token, and a path stays as it is."""
    assert public_location(url) == public
