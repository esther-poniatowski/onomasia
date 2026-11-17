"""
Typed model of the records of Onomasia: glossaries, notations and overlays.

A record holds an identifier, its imports, and sections of entries keyed by identifier: the terms
and the lexical rules of a glossary, the classes and the entries of a notation, the classes and
the entries that an overlay overrides. The composition engine treats every section alike, so the
sections of each format are declared once, in `RecordKind`.

Classes
-------
RecordKind
    Format of a record, with its contract, its schema identifiers and its sections.
Form
    Written form of a term or a rule: a literal, or a regular expression.
Alternative
    Other name of a term, or other body of an entry, with the contexts that it suits.
Term
    Admitted term of a glossary.
Replacement
    Term or instruction replacing a form forbidden by a rule.
LexicalRule
    Forbidden form, its replacements, and the audiences that the rule binds.
TypographicClass
    Class of notation entries, whose template prints the base of each entry.
Entry
    Symbol of a notation.
Override
    Change that an overlay applies to one entry of the notation it overlays.
Import
    Source of entries of a record, merged or bound to an alias.
Record
    Glossary, notation or overlay, read from one file.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Union

from anagraphe.targets.model import Target

from ..provenance import Input

Contexts = Mapping[str, tuple[str, ...]]
"""Values of each context dimension that an alternative or a replacement suits."""


class RecordKind(Enum):
    """
    Format of a record, with its contract, its schema identifiers and its sections.

    Each member holds the contract of the format, the versions of that contract read by this
    release, its name, the key of its globs in the configuration, and the names of its sections of
    entries. A record names one of the versions under `_schema`.
    """

    GLOSSARY = ("onomasia:glossary", (1, 2), "glossary", "glossaries", ("terms", "rules"))
    NOTATION = ("onomasia:notation", (1, 2), "notation", "notations", ("classes", "entries"))
    OVERLAY = ("onomasia:overlay", (1,), "overlay", "overlays", ("classes", "entries"))

    def __init__(
        self,
        contract: str,
        versions: tuple[int, ...],
        singular: str,
        plural: str,
        sections: tuple[str, ...],
    ) -> None:
        self.contract = contract
        self.schemas = tuple(f"{contract}@{version}" for version in versions)
        self.singular = singular
        self.plural = plural
        self.sections = sections

    @classmethod
    def from_schema(cls, schema: object) -> "RecordKind | None":
        """
        Return the format of a schema identifier, any version read by this release, or None for
        an unknown one.

        Examples
        --------
        >>> RecordKind.from_schema("onomasia:glossary@2") is RecordKind.GLOSSARY
        True
        >>> RecordKind.from_schema("onomasia:glossary@3") is None
        True
        """
        return next((kind for kind in cls if schema in kind.schemas), None)


@dataclass(frozen=True)
class Form:
    """
    Written form of a term or a rule: a literal matched at word boundaries, or a regular expression.

    Attributes
    ----------
    text : str
        Literal, or pattern when `regex` is true.
    regex : bool
        Whether `text` is a regular expression of the Python module `re`.
    description : str | None
        What the form stands for, stated by the consumer and read by no check.
    """

    text: str
    regex: bool = False
    description: str | None = None


@dataclass(frozen=True)
class Alternative:
    """
    Other name of a term, or other body of an entry, with the contexts that it suits.

    Attributes
    ----------
    text : str
        Label of the other name, or TeX of the other body.
    contexts : Contexts
        Values of each context dimension that the alternative suits.
    """

    text: str
    contexts: Contexts


@dataclass(frozen=True)
class Term:  # pylint: disable=too-many-instance-attributes
    """
    Admitted term of a glossary.

    Attributes
    ----------
    label : str
        Preferred form of the term.
    gloss : str
        Meaning of the term, in one sentence.
    forms : tuple[Form, ...]
        Admitted forms besides the label, such as a plural or an abbreviation.
    source : str | None
        Logical target of the note holding the canonical definition.
    status : str | None
        Status of the term, None for the default status of the vocabulary.
    superseded_by : str | None
        Term replacing this one, for a status requiring a replacement.
    case_sensitive : bool
        Whether the forms match with their case.
    frames : tuple[str, ...]
        Constructions admitted for the term, `~` standing for its label or a form.
    alternatives : tuple[Alternative, ...]
        Other names of the concept, each with the contexts that it suits.
    relations : Mapping[str, tuple[str, ...]]
        Terms related to this one, by relation of the vocabulary.
    metadata : Mapping[str, object]
        Fields of the consumer, which Onomasia does not read.
    """

    label: str
    gloss: str
    forms: tuple[Form, ...] = ()
    source: str | None = None
    status: str | None = None
    superseded_by: str | None = None
    case_sensitive: bool = False
    frames: tuple[str, ...] = ()
    alternatives: tuple[Alternative, ...] = ()
    relations: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Replacement:
    """
    Term or instruction replacing a form forbidden by a rule.

    Attributes
    ----------
    term : str | None
        Term replacing the form, or None when an instruction stands instead.
    instruction : str | None
        Rewriting instruction, for a form that no declared term replaces.
    contexts : Contexts
        Contexts in which this replacement holds, when several replacements compete.
    condition : str | None
        Sense of the forbidden form that this replacement serves, printed with it in the advice.
    """

    term: str | None
    instruction: str | None
    contexts: Contexts = field(default_factory=dict)
    condition: str | None = None


@dataclass(frozen=True)
class LexicalRule:  # pylint: disable=too-many-instance-attributes
    """
    Forbidden form, its replacements, and the audiences that the rule binds.

    Attributes
    ----------
    forms : tuple[Form, ...]
        Forms forbidden by the rule.
    replacements : tuple[Replacement, ...]
        Terms or instructions replacing the forms.
    reason : str
        Reason for the rule.
    severity : str | None
        Severity of a match, None for the severity of its check.
    status : str | None
        Status of the rule, None for the default status of the vocabulary.
    audiences : frozenset[str] | None
        Audiences whose texts the rule binds, None for every text.
    exceptions : tuple[Form, ...]
        Forms inside which a match of the rule is admitted.
    case_sensitive : bool
        Whether the forms match with their case.
    metadata : Mapping[str, object]
        Fields of the consumer, which Onomasia does not read.
    """

    forms: tuple[Form, ...]
    replacements: tuple[Replacement, ...]
    reason: str
    severity: str | None = None
    status: str | None = None
    audiences: frozenset[str] | None = None
    exceptions: tuple[Form, ...] = ()
    case_sensitive: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TypographicClass:
    """
    Class of notation entries, whose template prints the base of each entry.

    Attributes
    ----------
    template : str | None
        TeX in which the base placeholder stands for the base of an entry, or None for a class
        whose entries write their bodies.
    gloss : str | None
        Convention that the class states, such as a matrix in bold italic.
    """

    template: str | None
    gloss: str | None = None


@dataclass(frozen=True)
class Entry:  # pylint: disable=too-many-instance-attributes
    """
    Symbol of a notation.

    Attributes
    ----------
    denotes : Target | None
        Logical target of the unit that the entry designates, normalized by the repository holding
        the notation; None for an entry naming no unit by a target.
    denotes_text : str | None
        Text naming the unit in an entry of `onomasia:notation@1`, which carries no logical
        target, so that no output and no document of denotes targets matches it.
    gloss : str | None
        Meaning of an undeclared entry, which a declared entry takes from its unit.
    body : str | None
        TeX of the printed form, or None when the class template prints the base.
    base : str | None
        Base printed by the template of the class, or None when the body is written.
    typographic_class : str | None
        Class of the entry.
    name : str | None
        Macro name, or None for a name derived from the identifier.
    entry_argument : bool
        Whether the macro takes the optional entry argument.
    separator : str | None
        Separator of the items of a variadic macro.
    status : str | None
        Status of the entry, None for the default status of the vocabulary.
    superseded_by : str | None
        Entry replacing this one, for a status requiring a replacement.
    alternatives : tuple[Alternative, ...]
        Other bodies of the symbol, each with the contexts that it suits.
    overloads : tuple[str, ...]
        Entries of the composed notation printing the same body on purpose.
    metadata : Mapping[str, object]
        Fields of the consumer, which Onomasia does not read.
    """

    denotes: Target | None = None
    denotes_text: str | None = None
    gloss: str | None = None
    body: str | None = None
    base: str | None = None
    typographic_class: str | None = None
    name: str | None = None
    entry_argument: bool = False
    separator: str | None = None
    status: str | None = None
    superseded_by: str | None = None
    alternatives: tuple[Alternative, ...] = ()
    overloads: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def declared(self) -> bool:
        """Whether the entry names a unit, by a logical target or by the text of version 1."""
        return self.denotes is not None or self.denotes_text is not None


@dataclass(frozen=True)
class Override:
    """
    Change that an overlay applies to one entry of the notation it overlays.

    Only the printed form and the class may change, so that every macro name, argument and
    target of the notation holds under every overlay.

    Attributes
    ----------
    body, base, typographic_class : str | None
        New body, base or class of the entry, None to keep the value of the notation.
    """

    body: str | None = None
    base: str | None = None
    typographic_class: str | None = None


SectionEntry = Union[Term, LexicalRule, TypographicClass, Entry, Override]
"""Type of an entry of any section of any format."""


@dataclass(frozen=True)
class Import:
    """
    Source of entries of a record, merged or bound to an alias.

    Attributes
    ----------
    source : Target
        Source record, of the format of the importing record, normalized by the repository
        holding the importing record: an identifier names a record of that repository, as a target
        without repository does. The target keeps no repository when that repository declares no
        identifier.
    alias : str | None
        Alias through which the entries are referenced, None for a merged import.
    only : frozenset[str] | None
        Identifiers of the entries imported, None for all of them.
    excluded : frozenset[str]
        Identifiers of the entries left out.
    pointer : str
        JSON Pointer of the import in its record.
    """

    source: Target
    alias: str | None
    only: frozenset[str] | None
    excluded: frozenset[str]
    pointer: str


@dataclass(frozen=True)
class Record:  # pylint: disable=too-many-instance-attributes
    """
    Glossary, notation or overlay, read from one file.

    Attributes
    ----------
    kind : RecordKind
        Format of the record.
    identifier : str
        Identifier of the record, unique among the records of its format.
    resource : str
        Path of the file, relative to the root of the consumer.
    imports : tuple[Import, ...]
        Sources of entries, in order.
    sections : Mapping[str, Mapping[str, SectionEntry]]
        Entries of each section, keyed by identifier.
    overlays : str | None
        Identifier of the notation that an overlay overlays.
    origin : Input | None
        Repository, commit, identifier and digest of a record read from another repository, None
        for a record of the consumer.
    size : int
        Number of bytes of the document of the record, counted by the limits of an import closure.
    """

    kind: RecordKind
    identifier: str
    resource: str
    imports: tuple[Import, ...]
    sections: Mapping[str, Mapping[str, SectionEntry]]
    overlays: str | None = None
    origin: Input | None = None
    size: int = 0
