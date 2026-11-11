"""
Provenance of generated documents: the repository, the commit and the state of their records.

A build records the commit of the notation that it used, so a document generated from records
names its sources. The provider of that information is a port, so that the core reads no
repository itself; the Git adapter runs `git` on the root of the consumer.

Classes
-------
Source
    Repository, commit and state of the records behind a document.
ProvenanceProvider
    Protocol of a provider of the sources of a root.
GitProvenance
    Provider reading the repository holding the root.

Functions
---------
public_location(url) -> str
    The location of a repository without the user information of its URL.
"""

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

SCP_USER = re.compile(r"\A[^@/:]+@(?=[^/:]+:)")
"""User of a remote written in the form of `scp`, `user@host:path`, which has no scheme."""


@dataclass(frozen=True)
class Source:
    """
    Repository, commit and state of the records behind a document.

    Attributes
    ----------
    repository : str
        Address of the repository without its user information, or its path when it has no
        remote.
    commit : str
        Full identifier of the commit checked out.
    dirty : bool
        Whether the working tree held uncommitted changes.
    """

    repository: str
    commit: str
    dirty: bool

    def describe(self) -> str:
        """State the source in one phrase."""
        state = " with uncommitted changes" if self.dirty else ""
        return f"{self.repository} at {self.commit}{state}"

    def to_data(self) -> dict[str, object]:
        """Return the plain-data form of the common field `sources` of a contract."""
        return {"repository": self.repository, "commit": self.commit, "dirty": self.dirty}


def public_location(url: str) -> str:
    """
    Return the location `url` of a repository without its user information.

    A remote may carry a user and a token, as `https://user:token@host/path`, which a generated
    document must not publish. A URL with a scheme keeps its host after the last `@`, and a remote
    in the form of `scp` drops its user.

    Examples
    --------
    >>> public_location("https://user:token@github.com/org/repo.git")
    'https://github.com/org/repo.git'
    >>> public_location("git@github.com:org/repo.git")
    'github.com:org/repo.git'
    >>> public_location("/path/to/repo")
    '/path/to/repo'
    """
    parts = urlsplit(url)
    if parts.scheme and parts.netloc:
        host = parts.netloc.rpartition("@")[2]
        return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    return SCP_USER.sub("", url)


class ProvenanceProvider(Protocol):
    """Protocol of a provider of the sources of a root."""

    def sources(self, root: Path) -> tuple[Source, ...]:
        """Return the sources of the records under a root, empty when none is known."""


class GitProvenance:
    """Provider reading the repository holding the root, through the command `git`."""

    def sources(self, root: Path) -> tuple[Source, ...]:
        """Return the repository holding the root, or nothing when the root lies in none."""

        def git(*arguments: str) -> str | None:
            """Run one command of Git on the root, returning its output or None on failure."""
            try:
                completed = subprocess.run(
                    ["git", "-C", str(root), *arguments], capture_output=True, text=True, check=True
                )
            except (OSError, subprocess.CalledProcessError):
                return None
            return completed.stdout.strip()

        commit = git("rev-parse", "HEAD")
        if commit is None:
            return ()
        remote = git("config", "--get", "remote.origin.url")
        repository = public_location(remote) if remote else str(root)
        status = git("status", "--porcelain")
        return (Source(repository, commit, bool(status)),)
