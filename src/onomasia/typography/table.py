"""
Macro table: one macro per entry of a composition of notations, with its name, body and arguments.

The arguments of a macro come from the unit that its entry denotes, as the denotes targets state
them: its arity, its binder slot, and whether it takes a list of items. An entry may also take the
optional entry argument, which comes first. The table is checked as it is built: a declared name
under the reserved prefix, two entries of one name, two entries of one unit, too many parameters,
a variadic macro without separator, and bodies calling one another in a cycle.

Classes
-------
TargetSignature
    Arguments of a unit, as its producer states them.
Macro
    One macro of the table.
MacroTable
    Macros of a composition of notations.

Functions
---------
build_macro_table(compositions, signatures, typography, sink) -> MacroTable
    Build and check the macro table of a composition of notations.
"""

from dataclasses import dataclass
import re
from typing import Mapping, Sequence

from ..composition import Composition, Visible
from ..configuration import Typography
from ..issues import IssueSink
from ..records.model import Entry
from .bodies import printed_body
from .names import derived_name

CONTROL_WORD = re.compile(r"\\([A-Za-z]+)")
"""Control word of TeX, a backslash followed by letters."""


@dataclass(frozen=True)
class TargetSignature:
    """
    Arguments of a unit, as its producer states them.

    Attributes
    ----------
    arity : int
        Number of arguments, 1 for a variadic operator.
    binder : int | None
        Position, from 1, of the argument binding a variable.
    variadic : bool
        Whether the argument holds a list of items.
    """

    arity: int = 0
    binder: int | None = None
    variadic: bool = False


@dataclass(frozen=True)
class Macro:  # pylint: disable=too-many-instance-attributes
    """
    One macro of the table.

    Attributes
    ----------
    identifier : str
        Identifier of the entry.
    notation : str
        Identifier of the notation, or of the overlay, declaring the entry.
    target : str | None
        Unit denoted by the entry.
    name : str
        Macro name.
    body : str
        TeX body, with parameters `#1` to `#n`.
    arity : int
        Number of mandatory arguments.
    entry_argument : bool
        Whether the optional entry argument comes first, as `#1`.
    binder : int | None
        Position of the mandatory argument binding a variable.
    separator : str | None
        Separator of the items of a variadic macro.
    typographic_class : str | None
        Class of the entry.
    """

    identifier: str
    notation: str
    target: str | None
    name: str
    body: str
    arity: int
    entry_argument: bool
    binder: int | None
    separator: str | None
    typographic_class: str | None

    @property
    def parameters(self) -> int:
        """Number of parameters of the macro, the optional entry argument included."""
        return self.arity + (1 if self.entry_argument else 0)


@dataclass(frozen=True)
class MacroTable:
    """
    Macros of a composition of notations.

    Attributes
    ----------
    notations : tuple[str, ...]
        Base notations composed, in order.
    overlays : tuple[str, ...]
        Overlays applied, in order.
    macros : tuple[Macro, ...]
        Macros, sorted by name.
    """

    notations: tuple[str, ...]
    overlays: tuple[str, ...]
    macros: tuple[Macro, ...]


def _macro(
    identifier: str,
    visible: Visible,
    composition: Composition,
    signatures: Mapping[str, TargetSignature],
    typography: Typography,
) -> Macro | None:
    """Build the macro of one entry, or None when the entry prints no body."""
    entry = visible.entry
    if not isinstance(entry, Entry):
        return None
    body = printed_body(entry, composition, typography.base_placeholder)
    if body is None:
        return None
    signature = signatures.get(entry.denotes or "", TargetSignature())
    name = entry.name or derived_name(identifier, typography.macro_prefix, typography.digit_names)
    return Macro(
        identifier=identifier,
        notation=visible.record.identifier,
        target=entry.denotes,
        name=name,
        body=body,
        arity=signature.arity,
        entry_argument=entry.entry_argument,
        binder=signature.binder,
        separator=entry.separator,
        typographic_class=entry.typographic_class,
    )


class _TableChecks:
    """Checks of a macro table, reporting each defect on the record declaring the entry."""

    def __init__(self, sink: IssueSink, typography: Typography) -> None:
        self._sink = sink
        self._typography = typography

    def _report(self, check: str, visible: Visible, identifier: str, message: str) -> None:
        """Report a defect of one entry on its record."""
        self._sink.report(check, visible.record.resource, f"/entries/{identifier}", message)

    def entry(self, macro: Macro, visible: Visible, signature: TargetSignature) -> None:
        """Check the name, the parameters and the separator of one macro."""
        entry = visible.entry
        assert isinstance(entry, Entry)
        if entry.name is not None and entry.name.startswith(self._typography.macro_prefix):
            self._report(
                "reserved-prefix",
                visible,
                macro.identifier,
                f"{entry.name} starts with the reserved prefix",
            )
        if macro.parameters > self._typography.maximum_parameters:
            self._report(
                "too-many-parameters", visible, macro.identifier, f"{macro.parameters} parameters"
            )
        if signature.variadic and entry.separator is None:
            self._report(
                "missing-separator",
                visible,
                macro.identifier,
                f"{macro.target} takes a list of items",
            )

    def unique(self, macros: Sequence[tuple[Macro, Visible]]) -> None:
        """Check that no two macros share a name, and no two entries denote one unit."""
        names: dict[str, str] = {}
        targets: dict[str, str] = {}
        for macro, visible in macros:
            first = names.setdefault(macro.name, macro.identifier)
            if first != macro.identifier:
                self._report(
                    "macro-name-collision",
                    visible,
                    macro.identifier,
                    f"{first} also bears {macro.name}",
                )
            if macro.target is not None:
                owner = targets.setdefault(macro.target, macro.identifier)
                if owner != macro.identifier:
                    self._report(
                        "ambiguous-target",
                        visible,
                        macro.identifier,
                        f"{owner} also denotes {macro.target}",
                    )

    def acyclic(self, macros: Sequence[tuple[Macro, Visible]]) -> None:
        """Check that the bodies of the macros call one another without a cycle."""
        names = {macro.name for macro, _ in macros}
        calls = {macro.name: set(CONTROL_WORD.findall(macro.body)) & names for macro, _ in macros}
        for macro, visible in macros:
            if _reaches(calls, macro.name):
                self._report(
                    "macro-cycle", visible, macro.identifier, f"{macro.name} expands into itself"
                )


def _reaches(calls: Mapping[str, set[str]], name: str) -> bool:
    """Whether the expansion of a macro reaches the macro again, through the bodies it calls."""
    pending = list(calls.get(name, ()))
    seen: set[str] = set()
    while pending:
        called = pending.pop()
        if called == name:
            return True
        if called not in seen:
            seen.add(called)
            pending.extend(calls.get(called, ()))
    return False


def build_macro_table(
    compositions: Sequence[Composition],
    overlays: Sequence[str],
    signatures: Mapping[str, TargetSignature],
    typography: Typography,
    sink: IssueSink,
) -> MacroTable:
    """
    Build and check the macro table of a composition of notations.

    Parameters
    ----------
    compositions : Sequence[Composition]
        Composition of each notation of the table, its overlays already applied.
    overlays : Sequence[str]
        Identifiers of the overlays applied, recorded in the table.
    signatures : Mapping[str, TargetSignature]
        Arguments of each unit, by target; a unit absent from the mapping takes no argument.
    typography : Typography
        Prefix, digit names, placeholder and parameter limit.
    sink : IssueSink
        Collector of the issues of the table.
    """
    checks = _TableChecks(sink, typography)
    built: list[tuple[Macro, Visible]] = []
    for composition in compositions:
        for identifier, visible in composition.sections.get("entries", {}).items():
            macro = _macro(identifier, visible, composition, signatures, typography)
            if macro is None:
                continue
            checks.entry(macro, visible, signatures.get(macro.target or "", TargetSignature()))
            built.append((macro, visible))
    checks.unique(built)
    checks.acyclic(built)
    notations = tuple(
        composition.record.overlays or composition.record.identifier for composition in compositions
    )
    macros = tuple(sorted((macro for macro, _ in built), key=lambda macro: macro.name))
    return MacroTable(notations, tuple(overlays), macros)
