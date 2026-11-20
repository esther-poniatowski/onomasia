"""
Imports across repositories: the limits of an import closure, the port reading the source of an
import, and its adapter over the repository opened by the read package of Anagraphe.

An import of `onomasia:glossary@2` or `onomasia:notation@2` may name its source by a logical target
into another repository. The composer reads such a source through a `SourceReader`, so that the
composition depends on no resolver. The adapter `AnagrapheSources` resolves and reads each target
through the repository of the consumer, opened by `anagraphe_read.open_repository`, whose
resolution context selects the state of every repository reached. The state provider of that
repository is injected, so that a test serves its states from memory and the command line reads
them from Git.

Every finding of the resolver keeps its kind. A finding that leaves the source unread is blocking:
the composer reports it at the severity of its check, an error by default. Three findings let the
source be read: a renamed repository, a renamed identifier, and a record whose contract the
consumer cannot verify; the composer reports them as warnings at most.

Classes
-------
ImportFinding
    One finding on the source of an import, with whether it leaves the source unread.
SourceRead
    Outcome of reading the source of an import from another repository.
SourceReader
    Protocol of a reader of the sources of imports from other repositories.
AnagrapheSources
    Reader resolving each target through the repository of the consumer.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Protocol

from anagraphe_read import (
    RENAMED_REPOSITORY,
    RENAMED_TARGET,
    UNVERIFIED_TARGET,
    Finding,
    Outcome,
    RecordRead,
    Repository,
    Resolution,
    Target,
)
from anagraphe_read import ConfigurationError as AnagrapheConfigurationError

from .errors import ConfigurationError
from .issues import IssueSink
from .provenance import Input
from .records.model import Record, RecordKind
from .records.validation import SchemaValidator
from .repository import RawDocument, load_document

UNRESOLVED_IMPORT = "unresolved-import"
"""Check reporting an import whose source no record holds, and a kind of finding of the resolver
that the catalog of checks does not list."""

FOLLOWED = frozenset({RENAMED_REPOSITORY, RENAMED_TARGET})
"""Findings of the resolver on a target that it follows to its current names, reading the source."""


@dataclass(frozen=True)
class ImportFinding:
    """
    One finding on the source of an import, with whether it leaves the source unread.

    Attributes
    ----------
    check : str
        Check of the catalog reporting the finding: the kind of the finding of the resolver.
    message : str
        Statement of the finding, opening on the written target.
    blocking : bool
        Whether the finding leaves the source unread, which makes it an error by default.
    """

    check: str
    message: str
    blocking: bool


@dataclass(frozen=True)
class SourceRead:
    """
    Outcome of reading the source of an import from another repository.

    Attributes
    ----------
    record : Record | None
        Record read and parsed, None when a finding leaves it unread or names a record of the
        consumer.
    findings : tuple[ImportFinding, ...]
        Findings of the resolver, and of the reading of the record, in order.
    local : str | None
        Identifier of a record of the consumer, for a target naming a former identifier of the
        consumer repository.
    """

    record: Record | None
    findings: tuple[ImportFinding, ...] = ()
    local: str | None = None


class SourceReader(Protocol):
    """Protocol of a reader of the sources of imports from other repositories."""

    def read(self, target: Target, kind: RecordKind) -> SourceRead:
        """Read the record of a normalized target into another repository, of a format."""


def _findings(findings: tuple[Finding, ...], read: bool) -> tuple[ImportFinding, ...]:
    """Classify the findings of the resolver. A rename never blocks, and a contract left
    unverified blocks only when the record itself is left unread; every other finding blocks."""
    return tuple(
        ImportFinding(
            finding.kind,
            finding.detail,
            not (finding.kind in FOLLOWED or (read and finding.kind == UNVERIFIED_TARGET)),
        )
        for finding in findings
    )


class AnagrapheSources:
    """
    Reader resolving each target through the repository of the consumer.

    The repository builds its resolution context and its resolver at the first target, so that a
    consumer importing from no other repository reads neither its submodules nor its states. Each
    record is read once per run, keyed by its repository, its commit and its path.

    Parameters
    ----------
    repository : Repository
        Repository of the consumer, opened by the read package of Anagraphe with its provider.
    validator : SchemaValidator
        Validator of the formats, applied to each record read.
    sink : IssueSink
        Collector of the issues of the records read, each reported at the location of its record.
    """

    def __init__(self, repository: Repository, validator: SchemaValidator, sink: IssueSink) -> None:
        self._repository = repository
        self._validator = validator
        self._sink = sink
        self._reads: dict[tuple[str, str, str, RecordKind], SourceRead] = {}

    def read(self, target: Target, kind: RecordKind) -> SourceRead:
        """Resolve a target, then read, validate and parse its record.

        Raises
        ------
        ConfigurationError
            If the resolution context of the consumer selects two states of one repository.
        """
        try:
            resolution = self._repository.resolve(target)
        except AnagrapheConfigurationError as error:
            raise ConfigurationError(f"the resolution of imports: {error}") from error
        if resolution.outcome is Outcome.LOCAL:
            return SourceRead(None, _findings(resolution.findings, True), resolution.target.id)
        provenance = resolution.provenance
        if resolution.outcome is not Outcome.RECORD or provenance is None:
            findings = _findings(resolution.findings, False)
            if not any(finding.blocking for finding in findings):
                message = f"{target}: the target names a repository, and no record of it"
                findings += (ImportFinding(UNRESOLVED_IMPORT, message, True),)
            return SourceRead(None, findings)
        assert provenance.path is not None
        key = (provenance.repository, provenance.commit, provenance.path, kind)
        if key not in self._reads:
            self._reads[key] = self._record(resolution, kind)
        read = self._reads[key]
        warnings = _findings(resolution.findings, True)
        return SourceRead(read.record, warnings + read.findings, read.local)

    def _record(self, resolution: Resolution, kind: RecordKind) -> SourceRead:
        """Read the record of a resolved target, verified by the resolver, then by its schema."""
        read: RecordRead = self._repository.read(resolution, ((kind.contract,),))
        findings = _findings(read.findings, read.data is not None)
        if read.data is None or any(finding.blocking for finding in findings):
            return SourceRead(None, findings)
        provenance = read.provenance
        assert provenance.path is not None and resolution.target.id is not None
        origin = Input(
            provenance.repository,
            provenance.commit,
            resolution.target.id,
            hashlib.sha256(read.data).hexdigest(),
            provenance.path,
        )
        document = RawDocument(
            f"{provenance.repository}:{provenance.path}", read.data.decode("utf-8"), kind
        )
        record = load_document(
            document, self._validator, self._sink, repository=provenance.repository, origin=origin
        )
        if record is None:
            message = (
                f"{resolution.target}: {document.resource} at {provenance.commit} holds no valid "
                f"{kind.singular}"
            )
            return SourceRead(None, findings + (ImportFinding(UNRESOLVED_IMPORT, message, True),))
        return SourceRead(record, findings)
