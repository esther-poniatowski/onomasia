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
"""

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Protocol


@dataclass(frozen=True)
class Source:
    """
    Repository, commit and state of the records behind a document.

    Attributes
    ----------
    repository : str
        Address of the repository, or its path when it has no remote.
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
        repository = git("config", "--get", "remote.origin.url") or str(root)
        status = git("status", "--porcelain")
        return (Source(repository, commit, bool(status)),)
