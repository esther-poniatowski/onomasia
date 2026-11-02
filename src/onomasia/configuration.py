"""
Configuration of a consumer, `onomasia.yml`: where its records live, its vocabularies, and the
severity of each check.

The file declares its `schema_version`, then three sections, each optional:

- `records`, the globs of the records of each format, relative to the root, and the paths
  excluded from every glob;
- `vocabulary`, the statuses, the context dimensions and the relations of the consumer, each
  replacing the packaged default as a whole;
- `typography`, the placeholder of the base in the templates of typographic classes;
- `checks`, the severity of each check that the consumer changes: `error`, `warning` or `off`.

Classes
-------
StatusRole
    Behaviour of one status of the vocabulary.
Vocabulary
    Value sets of the consumer, against which the checks read the records.
RecordLocations
    Globs of the records of each format, and the paths excluded from them.
Typography
    Conventions of the printed forms of notation entries.
Configuration
    Resolved configuration of one consumer.

Functions
---------
load_configuration(root, path) -> Configuration
    Read and resolve the configuration of a consumer.
default_configuration(root) -> Configuration
    Configuration of a consumer that declares none.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml

from .errors import ConfigurationError
from .issues import Severity, default_severities, packaged_defaults
from .reading import Fields
from .records.model import RecordKind

SCHEMA_VERSION = 1
"""Version of the layout of `onomasia.yml` read by this release."""


@dataclass(frozen=True)
class StatusRole:
    """
    Behaviour of one status of the vocabulary.

    Attributes
    ----------
    requires_replacement : bool
        Whether an entry of this status must name the entry replacing it.
    """

    requires_replacement: bool


@dataclass(frozen=True)
class Vocabulary:
    """
    Value sets of the consumer, against which the checks read the records.

    Attributes
    ----------
    statuses : Mapping[str, StatusRole]
        Admitted statuses, with their behaviour.
    default_status : str
        Status of an entry that declares none.
    contexts : Mapping[str, frozenset[str]]
        Admitted values of each context dimension.
    relations : frozenset[str]
        Relations that a term may hold to other terms.
    """

    statuses: Mapping[str, StatusRole]
    default_status: str
    contexts: Mapping[str, frozenset[str]]
    relations: frozenset[str]


@dataclass(frozen=True)
class RecordLocations:
    """
    Globs of the records of each format, and the paths excluded from them.

    Attributes
    ----------
    globs : Mapping[RecordKind, tuple[str, ...]]
        Globs of the records of each format, relative to the root.
    exclude : tuple[str, ...]
        Globs of the paths that no format reads.
    """

    globs: Mapping[RecordKind, tuple[str, ...]]
    exclude: tuple[str, ...]


@dataclass(frozen=True)
class Typography:
    """
    Conventions of the printed forms of notation entries.

    Attributes
    ----------
    base_placeholder : str
        Placeholder standing for the base of an entry in the template of its class.
    """

    base_placeholder: str


@dataclass(frozen=True)
class Configuration:
    """
    Resolved configuration of one consumer.

    Attributes
    ----------
    root : Path
        Root of the consumer, against which every glob resolves.
    records : RecordLocations
        Locations of the records.
    vocabulary : Vocabulary
        Value sets of the consumer.
    typography : Typography
        Conventions of the printed forms.
    severities : Mapping[str, Severity]
        Severity of each check of the catalog.
    """

    root: Path
    records: RecordLocations
    vocabulary: Vocabulary
    typography: Typography
    severities: Mapping[str, Severity]


def _vocabulary(fields: Fields) -> Vocabulary:
    """Read a vocabulary section, rejecting a default status absent from the statuses."""
    statuses_data = fields.mapping("statuses") or {}
    statuses: dict[str, StatusRole] = {}
    for name, data in statuses_data.items():
        if not isinstance(data, Mapping):
            raise fields.error(f"statuses.{name}", "expected a mapping")
        role = Fields(data, f"statuses.{name}", "vocabulary")
        statuses[name] = StatusRole(requires_replacement=role.boolean("requires_replacement"))
        role.finish()
    default_status = fields.string("default_status")
    if default_status not in statuses:
        raise fields.error("default_status", f"status {default_status!r} is absent from statuses")
    contexts_data = fields.mapping("contexts") or {}
    contexts: dict[str, frozenset[str]] = {}
    for dimension, values in contexts_data.items():
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise fields.error(f"contexts.{dimension}", "expected a list of values")
        contexts[dimension] = frozenset(values)
    vocabulary = Vocabulary(
        statuses, default_status, contexts, frozenset(fields.strings("relations"))
    )
    fields.finish()
    return vocabulary


def _records(fields: Fields | None) -> RecordLocations:
    """Read the records section, each format reading no record when it lists no glob."""
    globs: dict[RecordKind, tuple[str, ...]] = {kind: () for kind in RecordKind}
    if fields is None:
        return RecordLocations(globs, ())
    for kind in RecordKind:
        globs[kind] = fields.strings(kind.plural, default=())
    exclude = fields.strings("exclude", default=())
    fields.finish()
    return RecordLocations(globs, exclude)


def _severities(fields: Fields | None) -> dict[str, Severity]:
    """Merge the severities of the consumer over the defaults of the catalog."""
    severities = default_severities()
    if fields is None:
        return severities
    for check in list(severities):
        if fields.present(check):
            value = fields.string(check)
            try:
                severities[check] = Severity(value)
            except ValueError as error:
                raise fields.error(check, "expected error, warning or off") from error
    fields.finish()
    return severities


def _packaged_section(key: str) -> Fields:
    """Read a section of the packaged defaults, standing for a section absent from the consumer."""
    defaults = packaged_defaults().get(key)
    if not isinstance(defaults, Mapping):
        raise ConfigurationError(f"the packaged defaults hold no section {key}")
    return Fields(defaults, key, "packaged defaults")


def _typography(fields: Fields) -> Typography:
    """Read the typography section."""
    typography = Typography(base_placeholder=fields.string("base_placeholder"))
    fields.finish()
    return typography


def _resolve(root: Path, data: Mapping[str, object], origin: str) -> Configuration:
    """Resolve a configuration mapping, the packaged vocabulary standing for an absent section."""
    fields = Fields(data, "", origin)
    version = fields.integer("schema_version")
    if version != SCHEMA_VERSION:
        raise fields.error("schema_version", f"version {version}, expected {SCHEMA_VERSION}")
    configuration = Configuration(
        root=root,
        records=_records(fields.section("records")),
        vocabulary=_vocabulary(fields.section("vocabulary") or _packaged_section("vocabulary")),
        typography=_typography(fields.section("typography") or _packaged_section("typography")),
        severities=_severities(fields.section("checks")),
    )
    fields.finish()
    return configuration


def load_configuration(root: Path, path: Path) -> Configuration:
    """
    Read and resolve the configuration of a consumer.

    Parameters
    ----------
    root : Path
        Root of the consumer.
    path : Path
        Configuration file, inside the root.

    Raises
    ------
    ConfigurationError
        If the file cannot be read, lies outside the root, or holds an invalid value.
    """
    root = root.resolve()
    try:
        path.resolve().relative_to(root)
    except ValueError as error:
        raise ConfigurationError(
            f"{path}: the configuration lies outside the root {root}"
        ) from error
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError(f"{path}: cannot read the configuration: {error}") from error
    if not isinstance(data, Mapping):
        raise ConfigurationError(f"{path}: the configuration is a mapping")
    return _resolve(root, data, str(path))


def default_configuration(root: Path) -> Configuration:
    """Configuration of a consumer that declares none: no record, packaged vocabularies."""
    return _resolve(root.resolve(), {"schema_version": SCHEMA_VERSION}, "default configuration")
