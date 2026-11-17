"""
Imports across repositories: the limits of an import closure, the port reading the source of an
import, and its adapter over the record resolver of Anagraphe.

An import of `onomasia:glossary@2` or `onomasia:notation@2` may name its source by a logical target
into another repository. The composer reads such a source through a `SourceReader`, so that the
composition depends on no resolver. The adapter `AnagrapheSources` builds the resolution context of
the consumer, which selects the state of every repository reached, then resolves and reads each
target through the record resolver of Anagraphe and its state provider. The provider is injected,
so that a test serves its states from memory and the command line reads them from Git.

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
    Reader resolving each target through the record resolver of Anagraphe.

Functions
---------
consumer_repository(root) -> str | None
    Identifier declared by the manifest of the consumer, None without one.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Protocol

from anagraphe.configuration import RepositoryConfig, load_config, locate_config
from anagraphe.core.configuration import CONFIG_LOCATIONS
from anagraphe.core.configuration import ConfigurationError as AnagrapheConfigurationError
from anagraphe.core.schemas import SchemaReader
from anagraphe.resolution import (
    Finding,
    Outcome,
    RecordRead,
    RecordResolver,
    Resolution,
    StateProvider,
    build_context,
)
from anagraphe.resolution.configuration import ResolutionConfig
from anagraphe.targets.declarations import Declarations
from anagraphe.targets.kinds import RENAMED_REPOSITORY, RENAMED_TARGET, UNVERIFIED_TARGET
from anagraphe.targets.manifest import read_manifest
from anagraphe.targets.model import Target

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


def consumer_repository(root: Path) -> str | None:
    """Return the identifier declared by the manifest `repository.yml` of the consumer, None when
    the consumer holds no valid manifest."""
    manifest = read_manifest(root).manifest
    return manifest.id if manifest is not None else None


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
    Reader resolving each target through the record resolver of Anagraphe.

    The resolution context and the resolver are built at the first target, so that a consumer
    importing from no other repository reads neither its submodules nor its states. Each record is
    read once per run, keyed by its repository, its commit and its path.

    Parameters
    ----------
    root : Path
        Root of the consumer, whose submodules and section `resolution` select the states.
    provider : StateProvider
        Reader of the selected states, such as the Git provider of Anagraphe.
    validator : SchemaValidator
        Validator of the formats, applied to each record read.
    sink : IssueSink
        Collector of the issues of the records read, each reported at the location of its record.
    anagraphe : Path | None
        Configuration of Anagraphe, None for the file found below the root, or for none.
    """

    def __init__(
        self,
        root: Path,
        provider: StateProvider,
        validator: SchemaValidator,
        sink: IssueSink,
        anagraphe: Path | None = None,
    ) -> None:
        self._root = root
        self._provider = provider
        self._validator = validator
        self._sink = sink
        self._anagraphe = anagraphe
        self._resolver: RecordResolver | None = None
        self._reads: dict[tuple[str, str, str, RecordKind], SourceRead] = {}

    def read(self, target: Target, kind: RecordKind) -> SourceRead:
        """Resolve a target, then read, validate and parse its record."""
        resolver = self._resolver_of_root()
        resolution = resolver.resolve(target)
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
            self._reads[key] = self._record(resolver, resolution, kind)
        read = self._reads[key]
        warnings = _findings(resolution.findings, True)
        return SourceRead(read.record, warnings + read.findings, read.local)

    def _record(
        self, resolver: RecordResolver, resolution: Resolution, kind: RecordKind
    ) -> SourceRead:
        """Read the record of a resolved target, verified by the resolver, then by its schema."""
        read: RecordRead = resolver.read(resolution, ((kind.contract,),))
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

    def _resolver_of_root(self) -> RecordResolver:
        """Return the resolver of the root, built at the first call.

        Raises
        ------
        ConfigurationError
            If the configuration of Anagraphe is invalid, or the resolution context selects two
            states of one repository.
        """
        if self._resolver is not None:
            return self._resolver
        try:
            manifest = read_manifest(self._root).manifest
            config = self._configuration()
            resolution = config.resolution if config is not None else ResolutionConfig()
            context = build_context(self._root, manifest, resolution, self._provider)
            records = config.targets.records if config is not None and config.targets else None
            declarations = (
                Declarations(SchemaReader(self._root, records.registry))
                if records is not None
                else None
            )
        except (AnagrapheConfigurationError, OSError) as error:
            raise ConfigurationError(f"the resolution of imports: {error}") from error
        self._resolver = RecordResolver(
            context,
            self._provider,
            declarations,
            records.binding if records is not None else "_schema",
        )
        return self._resolver

    def _configuration(self) -> RepositoryConfig | None:
        """Return the configuration of Anagraphe of the root, None when the root holds none."""
        if self._anagraphe is not None:
            return load_config(self._root, self._anagraphe)
        if not any((self._root / location).is_file() for location in CONFIG_LOCATIONS):
            return None
        return load_config(self._root, locate_config(self._root))
