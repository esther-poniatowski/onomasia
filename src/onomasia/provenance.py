"""
Provenance of generated documents: the repository, the commit and the state of their records.

A build records the commit of the files that it read, so a document generated from records names
its sources. A source is dirty when its commit does not hold one of those files: the file differs
from its committed state, is untracked or ignored, or lies outside the repository. A change to any
other file, the generated document included, leaves the source clean. The provider of that
information is a port, so that the core reads no repository itself; the Git adapter runs `git` on
the root of the consumer. A document also lists, as its inputs, each record of another repository
imported into its records, with the digest of its bytes.

Classes
-------
Source
    Repository, commit and state of the records behind a document.
Input
    Record of another repository imported into the records behind a document.
ProvenanceProvider
    Protocol of a provider of the sources of a root.
GitProvenance
    Provider reading the repository holding the root.

Functions
---------
public_location(url) -> str
    The location of a repository without the user information of its URL.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
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
        Whether the commit does not hold one of the files read to generate the document.
    """

    repository: str
    commit: str
    dirty: bool

    def describe(self) -> str:
        """State the source in one phrase."""
        state = " with files read outside the commit" if self.dirty else ""
        return f"{self.repository} at {self.commit}{state}"

    def to_data(self) -> dict[str, object]:
        """Return the plain-data form of the common field `sources` of a contract."""
        return {"repository": self.repository, "commit": self.commit, "dirty": self.dirty}


@dataclass(frozen=True, order=True)
class Input:
    """
    Record of another repository imported into the records behind a document, at its commit.

    The order of the fields is the order of the receipt `inputs` of a generated document.

    Attributes
    ----------
    repository : str
        Identifier of the repository, as its manifest `repository.yml` declares it.
    commit : str
        Full identifier of the commit selected by the resolution context of the consumer.
    identifier : str
        Identifier of the record.
    sha256 : str
        Hexadecimal sha256 digest of the bytes of the record at that commit.
    path : str
        Path of the record within its repository, which the receipt does not list and which
        neither the order nor the equality of inputs compares.
    """

    repository: str
    commit: str
    identifier: str
    sha256: str
    path: str = field(default="", compare=False)

    def to_data(self) -> dict[str, object]:
        """Return the plain-data form of one item of the block `inputs` of a contract."""
        return {
            "repository": self.repository,
            "commit": self.commit,
            "id": self.identifier,
            "sha256": self.sha256,
        }


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

    def sources(self, root: Path, files: Sequence[Path]) -> tuple[Source, ...]:
        """Return the sources of the files read under a root, empty when none is known."""


def _git(root: Path, *arguments: str) -> str | None:
    """Run one command of Git on `root`, returning its output or None on failure."""
    try:
        completed = subprocess.run(
            ["git", "--literal-pathspecs", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def _outside_commit(top: Path, files: Sequence[Path]) -> bool:
    """Whether the commit checked out under `top` does not hold one of `files`."""
    resolved = [path.resolve() for path in files]
    if any(not path.is_relative_to(top) for path in resolved):
        return True
    if not resolved:
        return False
    relative = [path.relative_to(top).as_posix() for path in resolved]
    status = _git(
        top, "status", "--porcelain", "--ignored", "--untracked-files=all", "--", *relative
    )
    return status is None or bool(status)


class GitProvenance:
    """Provider reading the repository holding the root, through the command `git`."""

    def sources(self, root: Path, files: Sequence[Path]) -> tuple[Source, ...]:
        """Return the repository holding the root, or nothing when the root lies in none.

        The source is dirty when the commit checked out does not hold one of `files`."""
        commit = _git(root, "rev-parse", "HEAD")
        top = _git(root, "rev-parse", "--show-toplevel")
        if commit is None or top is None:
            return ()
        remote = _git(root, "config", "--get", "remote.origin.url")
        repository = public_location(remote) if remote else str(root)
        return (Source(repository, commit, _outside_commit(Path(top).resolve(), files)),)
