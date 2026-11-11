"""
Sources of records, and their loading into typed records.

A source yields the raw documents of a consumer, each with the format expected from its location.
The loader parses each document, checks its format and its schema, and reports every defect as an
issue, so that one broken record never stops the reading of the others.

Classes
-------
RawDocument
    Text of one record, with the format expected from its location.
RecordSource
    Protocol of a provider of raw documents.
FileRecordSource
    Source reading the files matched by the globs of a configuration.

Functions
---------
load_records(source, validator, sink) -> list[Record]
    Read, validate and parse every document of a source.
"""

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Protocol

import yaml

from .configuration import FORMAT_KEY, RecordLocations
from .issues import IssueSink
from .records.model import Record, RecordKind
from .records.parsing import parse_record
from .records.validation import SchemaValidator


@dataclass(frozen=True)
class RawDocument:
    """
    Text of one record, with the format expected from its location.

    Attributes
    ----------
    resource : str
        Path of the record, relative to the root of the consumer.
    text : str
        Content of the record.
    expected : RecordKind
        Format whose globs matched the record.
    """

    resource: str
    text: str
    expected: RecordKind


class RecordSource(Protocol):
    """Protocol of a provider of raw documents."""

    def documents(self) -> Iterable[RawDocument]:
        """Yield the raw documents of the consumer."""


class FileRecordSource:
    """
    Source reading the files matched by the globs of a configuration.

    Parameters
    ----------
    root : Path
        Root of the consumer, against which the globs resolve.
    locations : RecordLocations
        Globs of each format, and the paths excluded from them.
    """

    def __init__(self, root: Path, locations: RecordLocations) -> None:
        self._root = root
        self._locations = locations

    def documents(self) -> Iterator[RawDocument]:
        """Yield each matched file once, in path order, under the first format matching it."""
        seen: set[Path] = set()
        for kind in RecordKind:
            for pattern in self._locations.globs[kind]:
                for path in sorted(self._root.glob(pattern)):
                    relative = path.relative_to(self._root).as_posix()
                    if path in seen or not path.is_file() or self._excluded(relative):
                        continue
                    seen.add(path)
                    yield RawDocument(relative, path.read_text(encoding="utf-8"), kind)

    def _excluded(self, relative: str) -> bool:
        """Whether a path matches an exclusion glob, or lies under an excluded folder."""
        return excluded(relative, self._locations.exclude)


def excluded(relative: str, patterns: Iterable[str]) -> bool:
    """
    Whether a relative path matches an exclusion glob, or lies under an excluded folder.

    Examples
    --------
    >>> excluded("archive/a.md", ["archive"]), excluded("notes/a.md", ["archive", "*.tmp"])
    (True, False)
    """
    return any(
        fnmatch(relative, pattern) or relative.startswith(pattern.rstrip("/") + "/")
        for pattern in patterns
    )


def matched_files(root: Path, patterns: Iterable[str], exclude: Iterable[str]) -> list[str]:
    """Return the files matched by globs under a root, relative to it and sorted, excluded ones
    left out."""
    exclusions = tuple(exclude)
    found = {
        path.relative_to(root).as_posix()
        for pattern in patterns
        for path in root.glob(pattern)
        if path.is_file()
    }
    return sorted(relative for relative in found if not excluded(relative, exclusions))


class _UniqueKeyLoader(yaml.SafeLoader):  # pylint: disable=too-many-ancestors
    """Safe loader rejecting a mapping that repeats a key, whose earlier value would be lost."""


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[object, object]:
    """Build a mapping, raising on the first repeated key with its line."""
    keys: set[object] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node)
        if key in keys:
            raise yaml.constructor.ConstructorError(
                None, None, f"repeated key {key!r}", key_node.start_mark
            )
        keys.add(key)
    return loader.construct_mapping(node)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _parse(document: RawDocument, sink: IssueSink) -> object | None:
    """Parse the YAML of a document, reporting an invalid one or a repeated key."""
    try:
        # The loader derives from the safe loader, so it builds plain data only.
        data: object = yaml.load(document.text, Loader=_UniqueKeyLoader)
        return data
    except yaml.constructor.ConstructorError as error:
        sink.report("duplicate-key", document.resource, "", str(error.problem_mark or error))
    except yaml.YAMLError as error:
        sink.report("invalid-yaml", document.resource, "", str(error))
    return None


def load_records(source: RecordSource, validator: SchemaValidator, sink: IssueSink) -> list[Record]:
    """
    Read, validate and parse every document of a source.

    Parameters
    ----------
    source : RecordSource
        Provider of the raw documents.
    validator : SchemaValidator
        Validator of the formats.
    sink : IssueSink
        Collector of the issues.

    Returns
    -------
    list[Record]
        Records that parse and validate; each other document is reported and left out.
    """
    records: list[Record] = []
    for document in source.documents():
        data = _parse(document, sink)
        if data is None:
            continue
        kind = RecordKind.from_schema(data.get(FORMAT_KEY) if isinstance(data, Mapping) else None)
        if kind is None or not isinstance(data, Mapping):
            sink.report(
                "unknown-format",
                document.resource,
                f"/{FORMAT_KEY}",
                "no format of Onomasia is named",
            )
            continue
        if kind is not document.expected:
            sink.report(
                "wrong-format",
                document.resource,
                f"/{FORMAT_KEY}",
                f"declares {kind.schema}, while its path matches the {document.expected.plural}",
            )
            continue
        violations = list(validator.errors(kind, data))
        for pointer, message in violations:
            sink.report("schema-violation", document.resource, pointer, message)
        if not violations:
            records.append(parse_record(kind, data, document.resource))
    return records
