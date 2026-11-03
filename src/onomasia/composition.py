"""
Composition of records: the entries visible from a record through its imports, and the overlays
applied to notations.

A merged import adopts the entries of its source, the source first composed through its own
imports, and selected by `only` or `except`. A namespaced import binds an alias, through which the
entries of its source are referenced as `alias.id` without being adopted. An entry declared by the
record shadows a merged entry of the same identifier. The engine treats every section of every
format alike, so it holds no rule of a particular format.

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

from .issues import IssueSink
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
    """

    record: Record
    sections: Mapping[str, Mapping[str, Visible]]
    namespaces: Mapping[str, "Composition"] = field(default_factory=dict)

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


class Composer:
    """
    Engine composing the records of one consumer.

    Parameters
    ----------
    records : Iterable[Record]
        Records of the consumer, of every format.
    sink : IssueSink
        Collector of the issues of composition.
    """

    def __init__(self, records: Iterable[Record], sink: IssueSink) -> None:
        self._sink = sink
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
        self._done: dict[tuple[RecordKind, str], Composition | None] = {}

    def records(self, kind: RecordKind) -> list[Record]:
        """Return the records of a format, sorted by identifier."""
        return [
            record
            for (record_kind, _), record in sorted(
                self._records.items(), key=lambda item: item[0][1]
            )
            if record_kind is kind
        ]

    def compose(self, kind: RecordKind, identifier: str) -> Composition | None:
        """Compose a record, or None when it is unknown or lies on an import cycle."""
        record = self._records.get((kind, identifier))
        return None if record is None else self._compose(record, ())

    def _compose(self, record: Record, stack: tuple[str, ...]) -> Composition | None:
        """Compose a record, `stack` holding the identifiers of the records importing it."""
        key = (record.kind, record.identifier)
        if key in self._done:
            return self._done[key]
        sections: dict[str, dict[str, Visible]] = {name: {} for name in record.kind.sections}
        namespaces: dict[str, Composition] = {}
        for item in record.imports:
            source = self._records.get((record.kind, item.source))
            if source is None:
                self._sink.report(
                    "unresolved-import",
                    record.resource,
                    f"{item.pointer}/from",
                    f"no {record.kind.singular} {item.source}",
                )
                continue
            if source.identifier in stack + (record.identifier,):
                path = " → ".join(stack + (record.identifier, source.identifier))
                self._sink.report(
                    "import-cycle", record.resource, f"{item.pointer}/from", f"cycle {path}"
                )
                continue
            composed = self._compose(source, stack + (record.identifier,))
            if composed is None:
                continue
            self._check_selection(record, item, composed)
            if item.alias is not None:
                if item.alias in namespaces:
                    self._sink.report(
                        "duplicate-alias",
                        record.resource,
                        f"{item.pointer}/as",
                        f"alias {item.alias} is bound twice",
                    )
                else:
                    namespaces[item.alias] = composed
                continue
            self._merge(record, item, composed, sections)
        self._declare(record, sections)
        composition = Composition(record, sections, namespaces)
        self._done[key] = composition
        return composition

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
                    origins = f"{present.record.identifier} and {visible.record.identifier}"
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
            overlay, or None when the notation is unknown.
        """
        notation = (
            base if base is not None else self.compose(RecordKind.NOTATION, overlay.overlays or "")
        )
        if notation is None:
            self._sink.report(
                "unresolved-overlay",
                overlay.resource,
                "/overlays",
                f"no notation {overlay.overlays}",
            )
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
        return Composition(overlay, sections, notation.namespaces)


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
