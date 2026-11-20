"""
Composition of records: the entries visible from a record through its imports, and the overlays
applied to notations.

A merged import adopts the entries of its source, the source first composed through its own
imports, and selected by `only` or `except`. A namespaced import binds an alias, through which the
entries of its source are referenced as `alias.id` without being adopted. An entry declared by the
record shadows a merged entry of the same identifier. The engine treats every section of every
format alike, so it holds no rule of a particular format.

The source of an import, and the notation changed by an overlay, is a record of the consumer, or a
record of another repository read through a `SourceReader`. The engine keys each record by its
format, its repository, its commit and its identifier, the commit of a record of the consumer
standing empty, and composes each key once. The closure of a
record holds the record and every record that its imports reach. The limits of the consumer bound
the levels, the records and the bytes of each closure: an import exceeding one is reported, and is
not followed.

Classes
-------
Visible
    Entry visible from a composition, with the record that declares it.
Composition
    Entries visible from one record, and the compositions bound to its aliases.
Composer
    Engine composing the records of one consumer.
"""

from dataclasses import dataclass, field, replace
from typing import Iterable, Mapping

from anagraphe_read import Target

from .configuration import ImportLimits
from .imports import UNRESOLVED_IMPORT, SourceReader
from .issues import IssueSink, Severity
from .provenance import Input
from .records.model import (
    Entry,
    Import,
    Override,
    Record,
    RecordKind,
    SectionEntry,
    TypographicClass,
)

ALIAS_SEPARATOR = "."
"""Character between an alias and an identifier in a reference to a namespaced entry."""

RecordKey = tuple[RecordKind, str | None, str | None, str]
"""Format, repository, commit and identifier of a record; a record of the consumer has no commit,
and no repository when the consumer declares none."""


@dataclass(frozen=True)
class _Reference:
    """
    Key of a record naming another record: the key `from` of an import, or the key `overlays` of
    an overlay.

    Attributes
    ----------
    target : Target
        Normalized target of the record named.
    pointer : str
        JSON Pointer of the key in the referring record, at which each finding is reported.
    kind : RecordKind
        Format of the record named.
    missing : str
        Check reporting a record that no repository provides.
    """

    target: Target
    pointer: str
    kind: RecordKind
    missing: str = UNRESOLVED_IMPORT


@dataclass(frozen=True)
class Visible:
    """
    Entry visible from a composition, with the record that declares it.

    Attributes
    ----------
    entry : SectionEntry
        Entry itself.
    record : Record
        Record declaring the entry.
    """

    entry: SectionEntry
    record: Record


@dataclass(frozen=True)
class Composition:
    """
    Entries visible from one record, and the compositions bound to its aliases.

    Attributes
    ----------
    record : Record
        Composed record.
    sections : Mapping[str, Mapping[str, Visible]]
        Visible entries of each section, by identifier.
    namespaces : Mapping[str, Composition]
        Composition of the source of each alias.
    merged : tuple[tuple[str, Composition], ...]
        Composition of each merged source, with the pointer of the import merging it; for an
        overlay, the notation that it changes, with the pointer of its key `overlays`.
    closure : Mapping[RecordKey, Record]
        Records of the closure of the composed record, itself included, by key.
    height : int
        Levels of imports below the composed record, 0 for a record importing nothing.
    """

    record: Record
    sections: Mapping[str, Mapping[str, Visible]]
    namespaces: Mapping[str, "Composition"] = field(default_factory=dict)
    merged: tuple[tuple[str, "Composition"], ...] = ()
    closure: Mapping[RecordKey, Record] = field(default_factory=dict)
    height: int = 0

    def inputs(self) -> tuple[Input, ...]:
        """
        Return the records of other repositories in the closure, ordered by repository, then
        commit, then identifier.

        Examples
        --------
        >>> from onomasia.records.model import Record, RecordKind
        >>> record = Record(RecordKind.GLOSSARY, "g", "g.yml", (), {"terms": {}, "rules": {}})
        >>> Composition(record, {"terms": {}, "rules": {}}).inputs()
        ()
        """
        return tuple(sorted({item.origin for item in self.closure.values() if item.origin}))

    def lookup(self, section: str, reference: str) -> Visible | None:
        """
        Find the entry named by a reference, `id` or `alias.id`, in a section.

        Examples
        --------
        >>> from onomasia.records.model import Record, RecordKind
        >>> record = Record(RecordKind.GLOSSARY, "g", "g.yml", (), {"terms": {}, "rules": {}})
        >>> Composition(record, {"terms": {}, "rules": {}}).lookup("terms", "x") is None
        True
        """
        alias, separator, identifier = reference.partition(ALIAS_SEPARATOR)
        if separator:
            namespace = self.namespaces.get(alias)
            return namespace.lookup(section, identifier) if namespace is not None else None
        return self.sections.get(section, {}).get(reference)

    def local(self, section: str) -> Iterable[tuple[str, Visible]]:
        """Yield the entries of a section declared by the composed record itself."""
        for identifier, visible in self.sections.get(section, {}).items():
            if visible.record is self.record:
                yield identifier, visible

    def pointer(self, section: str, identifier: str) -> str:
        """
        Locate a visible entry in the composed record: its declaration, or the import adopting it.

        Examples
        --------
        >>> from onomasia.records.model import Record, RecordKind
        >>> record = Record(RecordKind.GLOSSARY, "g", "g.yml", (), {"terms": {}, "rules": {}})
        >>> Composition(record, {"terms": {}, "rules": {}}).pointer("terms", "x")
        '/terms/x'
        """
        visible = self.sections.get(section, {}).get(identifier)
        if visible is not None and visible.record is not self.record:
            for pointer, source in self.merged:
                if source.sections.get(section, {}).get(identifier) is visible:
                    return pointer
        return f"/{section}/{identifier}"


class Composer:
    """
    Engine composing the records of one consumer.

    Parameters
    ----------
    records : Iterable[Record]
        Records of the consumer, of every format.
    sink : IssueSink
        Collector of the issues of composition.
    repository : str | None
        Identifier of the repository of the consumer, None when it declares none.
    sources : SourceReader | None
        Reader of the records of other repositories, None when the consumer reads none.
    limits : ImportLimits
        Limits of the closure of each record.
    """

    def __init__(
        self,
        records: Iterable[Record],
        sink: IssueSink,
        *,
        repository: str | None = None,
        sources: SourceReader | None = None,
        limits: ImportLimits = ImportLimits(),
    ) -> None:
        self._sink = sink
        self._repository = repository
        self._sources = sources
        self._limits = limits
        self._records: dict[tuple[RecordKind, str], Record] = {}
        for record in records:
            key = (record.kind, record.identifier)
            if key in self._records:
                first = self._records[key].resource
                sink.report(
                    "duplicate-record",
                    record.resource,
                    "/id",
                    f"{record.identifier} is also declared by {first}",
                )
                continue
            self._records[key] = record
        self._done: dict[RecordKey, Composition] = {}

    def records(self, kind: RecordKind) -> list[Record]:
        """Return the records of a format of the consumer, sorted by identifier."""
        return [
            record
            for (record_kind, _), record in sorted(
                self._records.items(), key=lambda item: item[0][1]
            )
            if record_kind is kind
        ]

    def compose(self, kind: RecordKind, identifier: str) -> Composition | None:
        """Compose a record of the consumer, or None when the consumer holds no such record."""
        record = self._records.get((kind, identifier))
        return None if record is None else self._compose(record, ())[0]

    def _key(self, record: Record) -> RecordKey:
        """Return the format, the repository, the commit and the identifier of a record."""
        if record.origin is not None:
            origin = record.origin
            return (record.kind, origin.repository, origin.commit, record.identifier)
        return (record.kind, self._repository, None, record.identifier)

    def local(self, target: Target) -> str | None:
        """Return the identifier of the record of the consumer named by a normalized target, None
        for a target into another repository."""
        if target.repository is None or target.repository == self._repository:
            return target.id
        return None

    def _label(self, record: Record) -> str:
        """Name a record in a message: its identifier, with its repository when it lies in
        another repository."""
        return _named(self._key(record))

    def _limit(self, record: Record, pointer: str, message: str) -> None:
        """Report a key that the composer does not follow, since it exceeds a limit."""
        self._sink.report("import-limit", record.resource, pointer, message)

    def _source(self, record: Record, reference: _Reference) -> Record | None:
        """Return the record named by the key of a reference, of the consumer or of another
        repository, reporting at that key the findings of its reading."""
        target, pointer, kind = reference.target, reference.pointer, reference.kind
        local = self.local(target)
        if local is None and self._sources is None:
            self._sink.report(
                reference.missing,
                record.resource,
                pointer,
                f"{target}: no reader of the records of other repositories is configured",
            )
            return None
        if local is None:
            assert self._sources is not None
            read = self._sources.read(target, kind)
            for finding in read.findings:
                known = (
                    finding.check != UNRESOLVED_IMPORT and finding.check in self._sink.severities
                )
                self._sink.report(
                    finding.check if known else reference.missing,
                    record.resource,
                    pointer,
                    (
                        finding.message
                        if known or finding.check == UNRESOLVED_IMPORT
                        else f"{finding.check}: {finding.message}"
                    ),
                    cap=None if finding.blocking else Severity.WARNING,
                )
            if read.local is None:
                return read.record
            local = read.local
        source = self._records.get((kind, local or ""))
        if source is None:
            self._sink.report(
                reference.missing, record.resource, pointer, f"no {kind.singular} {local}"
            )
        return source

    def _compose(
        self, record: Record, stack: tuple[RecordKey, ...]
    ) -> tuple[Composition | None, bool]:
        """
        Compose a record, `stack` holding the keys of the records importing it.

        Returns
        -------
        tuple[Composition | None, bool]
            Composition of the record, or None when it is unknown; and whether a limit of depth,
            which depends on the place of the record below the record composed first, cut its
            closure. Such a composition is not kept, so that the record composed alone is
            composed again.
        """
        key = self._key(record)
        if key in self._done:
            return self._done[key], False
        sections: dict[str, dict[str, Visible]] = {name: {} for name in record.kind.sections}
        namespaces: dict[str, Composition] = {}
        merged: list[tuple[str, Composition]] = []
        closure: dict[RecordKey, Record] = {key: record}
        height = 0
        cut = False
        for item in record.imports:
            composed, partial = self._follow(
                record, _Reference(item.source, f"{item.pointer}/from", record.kind), stack + (key,)
            )
            cut = cut or partial
            if composed is None:
                continue
            union = {**closure, **composed.closure}
            if not self._within(record, f"{item.pointer}/from", union):
                continue
            closure = union
            height = max(height, composed.height + 1)
            self._check_selection(record, item, composed)
            if item.alias is None:
                self._merge(record, item, composed, sections)
                merged.append((item.pointer, composed))
            elif item.alias in namespaces:
                self._sink.report(
                    "duplicate-alias",
                    record.resource,
                    f"{item.pointer}/as",
                    f"alias {item.alias} is bound twice",
                )
            else:
                namespaces[item.alias] = composed
        self._declare(record, sections)
        composition = Composition(record, sections, namespaces, tuple(merged), closure, height)
        if not cut:
            self._done[key] = composition
        return composition, cut

    def _follow(
        self, record: Record, reference: _Reference, path: tuple[RecordKey, ...]
    ) -> tuple[Composition | None, bool]:
        """
        Compose the record named by a reference, `path` holding the keys from the record composed
        first to the referring record.

        Returns
        -------
        tuple[Composition | None, bool]
            Composition of the named record, or None when the reference is not followed: a record
            left unread, a cycle, or a limit of depth; and whether a limit of depth cut the
            closure.
        """
        level = len(path)
        depth = self._limits.depth
        if level > depth:
            self._limit(record, reference.pointer, f"the key opens level {level}, beyond {depth}")
            return None, True
        source = self._source(record, reference)
        if source is None:
            return None, False
        if self._key(source) in path:
            labels = " → ".join(_named(member) for member in (*path, self._key(source)))
            self._sink.report("import-cycle", record.resource, reference.pointer, f"cycle {labels}")
            return None, False
        composed, cut = self._compose(source, path)
        if composed is not None and level + composed.height > depth:
            self._limit(
                record,
                reference.pointer,
                f"the closure of {self._label(source)} opens level {level + composed.height}, "
                f"beyond {depth}",
            )
            return None, True
        return composed, cut

    def _within(self, record: Record, pointer: str, union: Mapping[RecordKey, Record]) -> bool:
        """Whether a closure stays within the limits of records and bytes, reporting at a key the
        reference that would exceed one."""
        size = sum(member.size for member in union.values())
        if len(union) > self._limits.records:
            message = f"the closure would hold {len(union)} records, beyond {self._limits.records}"
        elif size > self._limits.size:
            message = f"the closure would hold {size} bytes, beyond {self._limits.size}"
        else:
            return True
        self._limit(record, pointer, message)
        return False

    def _check_selection(self, record: Record, item: Import, source: Composition) -> None:
        """Report each identifier selected or excluded by an import but absent from its source."""
        available = {identifier for entries in source.sections.values() for identifier in entries}
        for key, names in (("only", item.only or frozenset()), ("except", item.excluded)):
            for name in sorted(names - available):
                message = f"{source.record.identifier} declares no {name}"
                self._sink.report(
                    "unresolved-import-entry", record.resource, f"{item.pointer}/{key}", message
                )

    def _merge(
        self,
        record: Record,
        item: Import,
        source: Composition,
        sections: dict[str, dict[str, Visible]],
    ) -> None:
        """Adopt the entries selected by a merged import, reporting conflicting duplicates."""
        for name, entries in source.sections.items():
            for identifier, visible in entries.items():
                if (
                    item.only is not None and identifier not in item.only
                ) or identifier in item.excluded:
                    continue
                present = sections[name].get(identifier)
                shadowed = identifier in record.sections.get(name, {})
                if present is not None and not shadowed and not _same(present, visible):
                    origins = f"{self._label(present.record)} and {self._label(visible.record)}"
                    self._sink.report(
                        "import-conflict",
                        record.resource,
                        item.pointer,
                        f"{identifier} comes from {origins}",
                    )
                    continue
                sections[name][identifier] = visible

    def _declare(self, record: Record, sections: dict[str, dict[str, Visible]]) -> None:
        """Add the entries of the record itself, which shadow merged entries of the same name."""
        seen: dict[str, str] = {}
        for name, entries in record.sections.items():
            for identifier, entry in entries.items():
                if identifier in seen:
                    self._sink.report(
                        "duplicate-entry",
                        record.resource,
                        f"/{name}/{identifier}",
                        f"{identifier} is also declared under {seen[identifier]}",
                    )
                seen.setdefault(identifier, name)
                sections[name][identifier] = Visible(entry, record)

    def apply_overlay(self, overlay: Record, base: Composition | None = None) -> Composition | None:
        """
        Apply an overlay to the composition of the notation that it overlays.

        Parameters
        ----------
        overlay : Record
            Overlay to apply.
        base : Composition | None
            Composition to change, such as the notation under an earlier overlay, or None for the
            composition of the notation itself.

        Returns
        -------
        Composition | None
            Composition of the notation under the overlay, the overridden entries declared by the
            overlay, or None when the notation is left unread or exceeds a limit.

        The notation named by the overlay is read as the source of an import is: from the consumer,
        or from another repository through the reader, with the same keys, findings and limits.
        """
        notation = base if base is not None else self._overlaid(overlay)
        if notation is None:
            return None
        sections = {name: dict(entries) for name, entries in notation.sections.items()}
        for identifier, entry in overlay.sections.get("classes", {}).items():
            if identifier not in sections["classes"]:
                self._sink.report(
                    "unknown-override",
                    overlay.resource,
                    f"/classes/{identifier}",
                    f"{notation.record.identifier} has no class {identifier}",
                )
                continue
            assert isinstance(entry, TypographicClass)
            sections["classes"][identifier] = Visible(entry, overlay)
        for identifier, change in overlay.sections.get("entries", {}).items():
            present = sections["entries"].get(identifier)
            if present is None:
                self._sink.report(
                    "unknown-override",
                    overlay.resource,
                    f"/entries/{identifier}",
                    f"{notation.record.identifier} has no entry {identifier}",
                )
                continue
            assert isinstance(change, Override) and isinstance(present.entry, Entry)
            sections["entries"][identifier] = Visible(_overridden(present.entry, change), overlay)
        closure = {self._key(overlay): overlay, **notation.closure}
        return Composition(
            overlay,
            sections,
            notation.namespaces,
            (("/overlays", notation),),
            closure,
            notation.height + 1,
        )

    def _overlaid(self, overlay: Record) -> Composition | None:
        """Compose the notation named by an overlay, reporting at its key `overlays` why it is not
        read, and keeping the overlay within the limits."""
        if overlay.overlays is None:
            return None
        reference = _Reference(
            overlay.overlays, "/overlays", RecordKind.NOTATION, "unresolved-overlay"
        )
        notation, _ = self._follow(overlay, reference, (self._key(overlay),))
        if notation is None:
            return None
        if not self._within(
            overlay, "/overlays", {self._key(overlay): overlay, **notation.closure}
        ):
            return None
        return notation


def _named(key: RecordKey) -> str:
    """
    Name the record of a key in a message: its identifier for a record of the consumer, its
    target for a record of another repository.

    Examples
    --------
    >>> from onomasia.records.model import RecordKind
    >>> kind = RecordKind.GLOSSARY
    >>> _named((kind, "thesis", None, "project")), _named((kind, "lexicon", "0" * 40, "base"))
    ('project', '{repository: lexicon, id: base}')
    """
    _, repository, commit, identifier = key
    return identifier if commit is None else str(Target(repository, identifier))


def _same(first: Visible, second: Visible) -> bool:
    """Whether two visible entries are one entry of one record, reached by two import paths."""
    return first.entry is second.entry and first.record is second.record


def _overridden(entry: Entry, change: Override) -> Entry:
    """Apply an override to an entry, a new body or base replacing both of the former."""
    if change.body is not None:
        entry = replace(entry, body=change.body, base=None)
    if change.base is not None:
        entry = replace(entry, base=change.base, body=None)
    if change.typographic_class is not None:
        entry = replace(entry, typographic_class=change.typographic_class)
    return entry
