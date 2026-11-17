"""
Parsing of validated record data into typed records.

The parser assumes data valid against the schema of its format, so that every structural defect
has already been reported by the validator. It reads every version of a format that the validator
admits. It normalizes each logical target by the repository holding the record: a target without
repository, and the identifier of an import, name a record of that repository.

Functions
---------
parse_record(kind, data, resource, *, repository, origin, size) -> Record
    Build the typed record of validated data.
"""

from typing import Callable, Mapping, Sequence, cast

from anagraphe.targets.model import Target

from ..provenance import Input
from .model import (
    Alternative,
    Contexts,
    Entry,
    Form,
    Import,
    LexicalRule,
    Override,
    Record,
    RecordKind,
    Replacement,
    SectionEntry,
    Term,
    TypographicClass,
)

Data = Mapping[str, object]
"""Validated mapping of a record or of one of its entries."""


def _text(data: Data, key: str) -> str | None:
    """Read an optional string of validated data."""
    value = data.get(key)
    return None if value is None else str(value)


def _list(data: Data, key: str) -> Sequence[object]:
    """Read an optional list of validated data, empty when absent."""
    value = data.get(key)
    return cast(Sequence[object], value) if value is not None else ()


def _contexts(value: object) -> Contexts:
    """Read the contexts of an alternative or a replacement."""
    mapping = cast(Mapping[str, Sequence[str]], value or {})
    return {dimension: tuple(values) for dimension, values in mapping.items()}


def _form(value: object) -> Form:
    """Read a form, literal or regular expression, written alone or with its description."""
    if not isinstance(value, Mapping):
        return Form(str(value))
    data = cast(Data, value)
    regex = "regex" in data
    return Form(str(data["regex" if regex else "literal"]), regex, _text(data, "description"))


def _metadata(data: Data) -> Mapping[str, object]:
    """Read the fields of the consumer, empty when absent."""
    return cast(Mapping[str, object], data.get("metadata") or {})


def _term(data: Data) -> Term:
    """Read a term."""
    relations = cast(Mapping[str, Sequence[str]], data.get("relations") or {})
    return Term(
        label=str(data["label"]),
        gloss=str(data["gloss"]),
        forms=tuple(_form(form) for form in _list(data, "forms")),
        source=_text(data, "source"),
        status=_text(data, "status"),
        superseded_by=_text(data, "superseded_by"),
        case_sensitive=bool(data.get("case_sensitive", False)),
        frames=tuple(str(frame) for frame in _list(data, "frames")),
        alternatives=tuple(
            Alternative(str(item["label"]), _contexts(item.get("when")))
            for item in cast(Sequence[Data], _list(data, "alternatives"))
        ),
        relations={name: tuple(targets) for name, targets in relations.items()},
        metadata=_metadata(data),
    )


def _rule(data: Data) -> LexicalRule:
    """Read a lexical rule."""
    audiences = data.get("audiences")
    return LexicalRule(
        forms=tuple(_form(form) for form in _list(data, "forms")),
        replacements=tuple(
            Replacement(
                _text(item, "term"),
                _text(item, "instruction"),
                _contexts(item.get("when")),
                _text(item, "condition"),
            )
            for item in cast(Sequence[Data], _list(data, "replace_with"))
        ),
        reason=str(data["reason"]),
        severity=_text(data, "severity"),
        status=_text(data, "status"),
        audiences=frozenset(cast(Sequence[str], audiences)) if audiences is not None else None,
        exceptions=tuple(_form(form) for form in _list(data, "exceptions")),
        case_sensitive=bool(data.get("case_sensitive", False)),
        metadata=_metadata(data),
    )


def _class(data: Data) -> TypographicClass:
    """Read a typographic class."""
    return TypographicClass(template=_text(data, "template"), gloss=_text(data, "gloss"))


def _target(value: object, repository: str | None) -> Target:
    """Read a logical target of validated data, normalized by the repository holding the record."""
    return Target.parse(dict(cast(Data, value))).normalized(repository)


def _entry(data: Data, repository: str | None) -> Entry:
    """Read a notation entry, whose `denotes` is a target in version 2 and a text in version 1."""
    denotes = data.get("denotes")
    return Entry(
        denotes=_target(denotes, repository) if isinstance(denotes, Mapping) else None,
        denotes_text=str(denotes) if isinstance(denotes, str) else None,
        gloss=_text(data, "gloss"),
        body=_text(data, "body"),
        base=_text(data, "base"),
        typographic_class=_text(data, "class"),
        name=_text(data, "name"),
        entry_argument=bool(data.get("entry", False)),
        separator=_text(data, "separator"),
        status=_text(data, "status"),
        superseded_by=_text(data, "superseded_by"),
        alternatives=tuple(
            Alternative(str(item["body"]), _contexts(item.get("when")))
            for item in cast(Sequence[Data], _list(data, "alternatives"))
        ),
        overloads=tuple(str(item) for item in _list(data, "overloads")),
        metadata=_metadata(data),
    )


def _override(data: Data) -> Override:
    """Read the change that an overlay applies to one entry."""
    return Override(
        body=_text(data, "body"), base=_text(data, "base"), typographic_class=_text(data, "class")
    )


SECTION_PARSERS: dict[RecordKind, dict[str, Callable[[Data, str | None], SectionEntry]]] = {
    RecordKind.GLOSSARY: {
        "terms": lambda data, _: _term(data),
        "rules": lambda data, _: _rule(data),
    },
    RecordKind.NOTATION: {"classes": lambda data, _: _class(data), "entries": _entry},
    RecordKind.OVERLAY: {
        "classes": lambda data, _: _class(data),
        "entries": lambda data, _: _override(data),
    },
}
"""Parser of the entries of each section of each format, given the repository holding the record."""


def _imports(data: Data, repository: str | None) -> tuple[Import, ...]:
    """Read the imports of a record, each with its pointer, and its source normalized."""
    imports: list[Import] = []
    for index, item in enumerate(cast(Sequence[Data], _list(data, "imports"))):
        only = item.get("only")
        source = item["from"]
        imports.append(
            Import(
                source=(
                    _target(source, repository)
                    if isinstance(source, Mapping)
                    else Target(repository, str(source))
                ),
                alias=_text(item, "as"),
                only=frozenset(cast(Sequence[str], only)) if only is not None else None,
                excluded=frozenset(cast(Sequence[str], item.get("except") or ())),
                pointer=f"/imports/{index}",
            )
        )
    return tuple(imports)


def parse_record(  # pylint: disable=too-many-arguments
    kind: RecordKind,
    data: Data,
    resource: str,
    *,
    repository: str | None = None,
    origin: Input | None = None,
    size: int = 0,
) -> Record:
    """
    Build the typed record of validated data.

    Parameters
    ----------
    kind : RecordKind
        Format of the record.
    data : Mapping[str, object]
        Content of the record, valid against the schema of one version of its format.
    resource : str
        Path of the record, relative to the root of the consumer, or the location of a record of
        another repository.
    repository : str | None
        Identifier of the repository holding the record, which normalizes its targets; None when
        that repository declares no identifier.
    origin : Input | None
        Commit and digest of a record read from another repository, None for a record of the
        consumer.
    size : int
        Number of bytes of the document of the record.
    """
    parsers = SECTION_PARSERS[kind]
    sections = {
        name: {
            str(identifier): parsers[name](cast(Data, value), repository)
            for identifier, value in cast(Data, data.get(name) or {}).items()
        }
        for name in kind.sections
    }
    return Record(
        kind=kind,
        identifier=str(data["id"]),
        resource=resource,
        imports=_imports(data, repository),
        sections=sections,
        overlays=_text(data, "overlays"),
        origin=origin,
        size=size,
    )
