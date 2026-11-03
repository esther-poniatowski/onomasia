"""
Configuration of a consumer, `onomasia.yml`: where its records live, its vocabularies, and the
severity of each check.

The file declares its `schema_version`, then three sections, each optional:

- `records`, the globs of the records of each format, relative to the root, and the paths
  excluded from every glob;
- `vocabulary`, the statuses, the context dimensions and the relations of the consumer, each
  replacing the packaged default as a whole;
- `typography`, the placeholder of the base in the templates of typographic classes, and the
  derivation of macro names;
- `build`, the input documents read by the build, and the outputs that it writes;
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
from enum import Enum
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
    macro_prefix : str
        Prefix of a derived macro name, which no declared name may start with.
    digit_names : tuple[str, ...]
        Words replacing the digits 0 to 9 in a derived name.
    maximum_parameters : int
        Parameters of one macro, as TeX admits them.
    """

    base_placeholder: str
    macro_prefix: str
    digit_names: tuple[str, ...]
    maximum_parameters: int


class Product(Enum):
    """Product written by the build: a contract document or a serialization of a macro table."""

    MACRO_TABLE = "macro-table"
    MACRO_LOOKUP = "macro-lookup"
    TERM_TABLE = "term-table"
    LATEX_PACKAGE = "latex-package"
    MATHJAX_PREAMBLE = "mathjax-preamble"
    PYTHON_EXPANDER = "python-expander"


@dataclass(frozen=True)
class Output:
    """
    One output of the build.

    Attributes
    ----------
    product : Product
        Product written.
    path : Path
        File written, resolved against the root.
    notations : tuple[str, ...]
        Notations composed into a macro product, in order.
    overlays : tuple[str, ...]
        Overlays applied to those notations, in order.
    glossary : str | None
        Glossary of a term table.
    """

    product: Product
    path: Path
    notations: tuple[str, ...] = ()
    overlays: tuple[str, ...] = ()
    glossary: str | None = None


@dataclass(frozen=True)
class Build:
    """
    Inputs and outputs of the build.

    Attributes
    ----------
    denotes_targets : tuple[Path, ...]
        Documents of the denotes targets, resolved against the root.
    outputs : tuple[Output, ...]
        Outputs to write.
    """

    denotes_targets: tuple[Path, ...]
    outputs: tuple[Output, ...]


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
    build : Build
        Inputs and outputs of the build.
    severities : Mapping[str, Severity]
        Severity of each check of the catalog.
    """

    root: Path
    records: RecordLocations
    vocabulary: Vocabulary
    typography: Typography
    build: Build
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
            value = fields.value(check)
            if value is False:  # YAML 1.1 reads a bare `off` as false.
                value = Severity.OFF.value
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
    """Read the typography section, checking that it names one word per digit."""
    digits = fields.strings("digit_names")
    if len(digits) != 10 or not all(name.isalpha() for name in digits):
        raise fields.error("digit_names", "expected ten words of letters, for the digits 0 to 9")
    typography = Typography(
        base_placeholder=fields.string("base_placeholder"),
        macro_prefix=fields.string("macro_prefix"),
        digit_names=digits,
        maximum_parameters=fields.integer("maximum_parameters"),
    )
    fields.finish()
    return typography


def _output(root: Path, data: object, index: int) -> Output:
    """Read one output of the build, the keys it requires depending on its product."""
    if not isinstance(data, Mapping):
        raise ConfigurationError(f"build.outputs.{index}: expected a mapping")
    fields = Fields(data, f"build.outputs.{index}", "configuration")
    try:
        product = Product(fields.string("product"))
    except ValueError as error:
        choices = ", ".join(member.value for member in Product)
        raise fields.error("product", f"expected one of {choices}") from error
    path = root / fields.string("path")
    if product is Product.TERM_TABLE:
        output = Output(product, path, glossary=fields.string("glossary"))
    else:
        output = Output(
            product, path, fields.strings("notations"), fields.strings("overlays", default=())
        )
    fields.finish()
    return output


def _build(root: Path, fields: Fields | None) -> Build:
    """Read the build section, which declares no output when it is absent."""
    if fields is None:
        return Build((), ())
    targets = tuple(root / path for path in fields.strings("denotes_targets", default=()))
    raw = fields.items("outputs")
    build = Build(targets, tuple(_output(root, item, index) for index, item in enumerate(raw)))
    fields.finish()
    return build


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
        build=_build(root, fields.section("build")),
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
