"""
Configuration of a consumer, `onomasia.yml`: where its records live, its vocabularies, and the
severity of each check.

The file lies at `config/tools/onomasia.yml` or at `onomasia.yml` below the root, and both places
holding a file is an error, unless another file is named. The root of a command is the folder given
by `--root`, else by the variable `ONOMASIA_ROOT`, else the nearest folder, from the current one
upwards, that holds the file at one of its places, else the current folder. The file names its
format under `_schema`, then declares six sections, each optional:

- `records`, the globs of the records of each format, relative to the root, and the paths
  excluded from every glob;
- `vocabulary`, the statuses, the context dimensions and the relations of the consumer, each
  replacing the packaged default as a whole;
- `typography`, the placeholder of the base in the templates of typographic classes, and the
  derivation of macro names;
- `build`, the input documents read by the build, and the outputs that it writes;
- `checks`, the severity of each check that the consumer changes: `error`, `warning` or `off`;
- `texts`, the texts checked against their glossaries and notations, and how they are read.

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
find_root(start) -> Path
    Nearest folder, from `start` upwards, holding a configuration, else `start`.
locate_configuration(root, path) -> Path
    Configuration file named, or the one found in its default places below the root.
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
from .texts.prose import kinds_problem
from .records.model import RecordKind

FORMAT_KEY = "_schema"
"""Key holding the format identifier of a file of Onomasia, the configuration or a record."""

CONFIGURATION_FORMAT = "onomasia:configuration@1"
"""Format identifier of `onomasia.yml` read by this release."""

RETIRED_FORMAT_KEY = "schema_version"
"""Key that named the version of the layout before `_schema`, rejected with its replacement."""

CONFIGURATION_FILE = "onomasia.yml"
"""Name of the configuration file."""

CONFIGURATION_LOCATIONS = (Path("config/tools") / CONFIGURATION_FILE, Path(CONFIGURATION_FILE))
"""Places of the configuration file below the root."""

ROOT_VARIABLE = "ONOMASIA_ROOT"
"""Environment variable naming the root, read when the command line names none."""


@dataclass(frozen=True)
class StatusRole:
    """
    Behaviour of one status of the vocabulary.

    Attributes
    ----------
    requires_replacement : bool
        Whether an entry of this status must name the entry replacing it.
    term_in_texts : Severity
        Severity of a use, in a text, of a term or a notation entry of this status; `off` when
        such a use is admitted.
    rule_in_texts : Severity
        Highest severity of a lexical rule of this status, `off` for a rule that binds no text.
    """

    requires_replacement: bool
    term_in_texts: Severity = Severity.OFF
    rule_in_texts: Severity = Severity.ERROR


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
class Texts:  # pylint: disable=too-many-instance-attributes
    """
    Texts of a consumer checked against the glossaries and the notations bound to them.

    Attributes
    ----------
    anagraphe : Path
        Configuration of Anagraphe, whose section `bindings` names the key of each role read by
        Onomasia.
    paths : tuple[str, ...]
        Globs of the texts, relative to the root.
    exclude : tuple[str, ...]
        Globs or folders left out of the texts.
    scope_table : Path | None
        Scope table relating the audiences, None when each audience relates to itself only.
    masked : tuple[str, ...]
        Kinds of Merismos masked before prose is matched, such as code and mathematics.
    math : tuple[str, ...]
        Kinds of Merismos holding the mathematics checked against the notations.
    determiners : tuple[str, ...]
        Words admitted before the slot of a frame.
    syntax : Path | None
        Syntax file of Merismos for the Markdown dialect, None for the packaged Obsidian syntax.
    """

    anagraphe: Path
    paths: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    scope_table: Path | None = None
    masked: tuple[str, ...] = ()
    math: tuple[str, ...] = ()
    determiners: tuple[str, ...] = ()
    syntax: Path | None = None


@dataclass(frozen=True)
class Configuration:
    """
    Resolved configuration of one consumer.

    Attributes
    ----------
    root : Path
        Root of the consumer, against which every glob resolves.
    resource : str
        Path of the configuration file relative to the root, at which an issue of the
        configuration is reported.
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
    texts : Texts | None
        Texts to check, None when the consumer checks none.
    """

    root: Path
    resource: str
    records: RecordLocations
    vocabulary: Vocabulary
    typography: Typography
    build: Build
    severities: Mapping[str, Severity]
    texts: "Texts | None" = None


def _severity(fields: Fields | None, key: str, default: Severity) -> Severity:
    """Read an optional severity, `error`, `warning` or `off`, or the default when absent."""
    if fields is None or not fields.present(key):
        return default
    value = fields.value(key)
    if value is False:  # YAML 1.1 reads a bare `off` as false.
        value = Severity.OFF.value
    try:
        return Severity(value)
    except ValueError as error:
        raise fields.error(key, "expected error, warning or off") from error


def _vocabulary(fields: Fields) -> Vocabulary:
    """Read a vocabulary section, rejecting a default status absent from the statuses."""
    statuses_data = fields.mapping("statuses") or {}
    statuses: dict[str, StatusRole] = {}
    for name, data in statuses_data.items():
        if not isinstance(data, Mapping):
            raise fields.error(f"statuses.{name}", "expected a mapping")
        role = Fields(data, f"statuses.{name}", "vocabulary")
        in_texts = role.section("in_texts")
        statuses[name] = StatusRole(
            requires_replacement=role.boolean("requires_replacement"),
            term_in_texts=_severity(in_texts, "term", Severity.OFF),
            rule_in_texts=_severity(in_texts, "rule", Severity.ERROR),
        )
        if in_texts is not None:
            in_texts.finish()
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


def _path(root: Path, fields: Fields, key: str) -> Path:
    """Read a path relative to the root, which must name a file."""
    path = root / fields.string(key)
    if not path.is_file():
        raise fields.error(key, f"names no file: {path}")
    return path


def _texts(root: Path, fields: Fields | None) -> Texts | None:
    """Read the texts section, its unset reading keys taken from the packaged defaults."""
    if fields is None:
        return None
    packaged = _packaged_section("texts")
    texts = Texts(
        anagraphe=_path(root, fields, "anagraphe"),
        paths=fields.strings("paths"),
        exclude=fields.strings("exclude", default=()),
        scope_table=_path(root, fields, "scope_table") if fields.present("scope_table") else None,
        masked=fields.strings("masked", default=packaged.strings("masked")),
        math=fields.strings("math", default=packaged.strings("math")),
        determiners=fields.strings("determiners", default=packaged.strings("determiners")),
        syntax=_path(root, fields, "syntax") if fields.present("syntax") else None,
    )
    fields.finish()
    for key, globs in (("paths", texts.paths), ("exclude", texts.exclude)):
        for glob in globs:
            if glob.startswith("/") or ".." in glob.split("/"):
                raise fields.error(key, f"the glob {glob} leaves the root")
    problem = kinds_problem((*texts.masked, *texts.math), texts.syntax)
    if problem is not None:
        raise fields.error("masked", problem)
    return texts


def _require_format(fields: Fields) -> None:
    """Require the format of the configuration, or raise an error naming the value to write."""
    instruction = f"write {FORMAT_KEY}: {CONFIGURATION_FORMAT} as the first key"
    if fields.present(RETIRED_FORMAT_KEY):
        raise fields.error(RETIRED_FORMAT_KEY, f"retired; {instruction}")
    if not fields.present(FORMAT_KEY):
        raise fields.error(FORMAT_KEY, f"absent; {instruction}")
    declared = fields.value(FORMAT_KEY)
    if declared != CONFIGURATION_FORMAT:
        raise fields.error(FORMAT_KEY, f"{declared}, expected {CONFIGURATION_FORMAT}")


def _resolve(root: Path, resource: str, data: Mapping[str, object], origin: str) -> Configuration:
    """Resolve a configuration mapping, the packaged vocabulary standing for an absent section."""
    fields = Fields(data, "", origin)
    _require_format(fields)
    configuration = Configuration(
        root=root,
        resource=resource,
        records=_records(fields.section("records")),
        vocabulary=_vocabulary(fields.section("vocabulary") or _packaged_section("vocabulary")),
        typography=_typography(fields.section("typography") or _packaged_section("typography")),
        build=_build(root, fields.section("build")),
        severities=_severities(fields.section("checks")),
        texts=_texts(root, fields.section("texts")),
    )
    fields.finish()
    return configuration


def find_root(start: Path) -> Path:
    """
    Nearest folder, from `start` upwards, holding a configuration, else `start`.

    Parameters
    ----------
    start : Path
        Folder where the search begins, the current folder of a command.

    Returns
    -------
    Path
        First folder, from `start` up to the top of the file system, holding a file at one of
        `CONFIGURATION_LOCATIONS`; `start` itself, resolved, when no folder holds one.
    """
    start = start.resolve()
    for folder in (start, *start.parents):
        if any((folder / location).is_file() for location in CONFIGURATION_LOCATIONS):
            return folder
    return start


def locate_configuration(root: Path, path: Path | None = None) -> Path:
    """
    Configuration file named, or the one found in its default places below the root.

    Parameters
    ----------
    root : Path
        Root of the consumer.
    path : Path | None
        Configuration file named on the command line, read from the current folder.

    Returns
    -------
    Path
        `path` when named, made absolute; otherwise the one of `config/tools/onomasia.yml` and
        `onomasia.yml` that exists below the root.

    Raises
    ------
    ConfigurationError
        If the named file does not exist, if both default places hold a file, or if no file is
        named and no default place holds one.
    """
    if path is not None:
        named = path.absolute()
        if not named.is_file():
            raise ConfigurationError(f"{path}: no configuration file")
        return named
    found = [root / location for location in CONFIGURATION_LOCATIONS if (root / location).is_file()]
    if len(found) > 1:
        raise ConfigurationError(
            "two configuration files: " + " and ".join(str(item) for item in found) + "; keep one"
        )
    if found:
        return found[0]
    places = " or ".join(location.as_posix() for location in CONFIGURATION_LOCATIONS)
    raise ConfigurationError(f"{root}: no configuration at {places}")


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
    return _resolve(root, path.resolve().relative_to(root).as_posix(), data, str(path))


def default_configuration(root: Path) -> Configuration:
    """Configuration of a consumer that declares none: no record, packaged vocabularies."""
    return _resolve(
        root.resolve(),
        CONFIGURATION_FILE,
        {FORMAT_KEY: CONFIGURATION_FORMAT},
        "default configuration",
    )
