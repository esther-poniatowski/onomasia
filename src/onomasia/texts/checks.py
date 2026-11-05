"""
Checks of a text against the glossaries, the notations and the audiences bound to it.

The prose of the text is checked against the glossaries:

- a form forbidden by a lexical rule binding the text is reported, unless it lies inside a match of
  one of the exceptions of the rule; a rule scoped by audiences binds a text when one of them is
  related, through the scope table, to an audience of the text;
- a term whose status reports its use in texts is reported, with its replacement;
- a term written outside every frame declared for it is reported, a term whose frames are all
  malformed being left to the check of its record.

The mathematics of the text is checked against the macro table of its notations, composed in the
order of the binding:

- a macro of an entry whose status reports its use, or its printed body taking no parameter, is
  reported, with the macro of its replacement and the body that it prints;
- a macro under the reserved prefix that the notations do not define is reported;
- the printed body of an entry whose use is admitted, written instead of its macro, is reported
  once with every macro printing it, when the body takes no parameter and holds a control
  sequence;
- among the bodies sought, the longest wins where one body opens another, and a body opening on a
  letter is matched only where no letter or backslash precedes it.

The status of an entry or a rule lowers the severity of its issue, through the vocabulary of the
consumer. Each issue is reported at the line of the text holding it.

Classes
-------
TextChecker
    Checker of the texts of one consumer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from ..composition import Composer, Composition, Visible
from ..configuration import StatusRole, Texts, Typography, Vocabulary
from ..contracts import ScopeTable
from ..grammar.frames import CompiledFrame, FrameError, UnresolvedSlot, compile_frame, parse
from ..grammar.patterns import alternation, form_pattern, term_pattern, valid
from ..issues import IssueSink, Severity
from ..records.model import Entry, LexicalRule, RecordKind, Replacement, Term
from ..typography.table import Macro, MacroTable, TargetSignature, build_macro_table
from .bindings import BindingSource, Bound, TextBinding
from .prose import Prose, read_prose

CONTROL_WORD = re.compile(r"\\([A-Za-z]+)")
"""Control word of TeX, capturing its name."""

EXCERPT = 60
"""Most characters of a text quoted in a message."""


def excerpt(text: str) -> str:
    """
    Return a text as quoted in a message: on one line, its masked characters left out.

    Examples
    --------
    >>> excerpt("tuning\\n  curve"), excerpt("a\\x00\\x00b")
    ('tuning curve', 'a b')
    """
    quoted = " ".join(text.replace("\x00", " ").split())
    return quoted if len(quoted) <= EXCERPT else quoted[: EXCERPT - 1] + "…"


def _spans(patterns: Iterable[re.Pattern[str]], text: str) -> list[tuple[int, int]]:
    """Return the span of every match of the patterns in a text."""
    return [match.span() for pattern in patterns for match in pattern.finditer(text)]


@dataclass(frozen=True)
class _Notation:
    """Macro table of the notations bound to a text, with its compiled search of bodies."""

    table: MacroTable
    entries: Mapping[str, Visible]
    macros: Mapping[str, Macro]
    bodies: re.Pattern[str] | None
    printing: Mapping[str, tuple[str, ...]]
    reported: Mapping[str, tuple[Macro, ...]]


@dataclass(frozen=True)
class _Context:
    """Glossary and notation entries visible from the bindings of one text."""

    terms: tuple[tuple[str, Visible], ...]
    rules: tuple[tuple[str, Visible], ...]
    notation: _Notation | None
    audiences: frozenset[str]


@dataclass(frozen=True)
class _Matching:
    """Compiled patterns of one term or one rule."""

    forms: re.Pattern[str] | None
    exceptions: tuple[re.Pattern[str], ...] = ()
    frames: tuple[CompiledFrame, ...] | None = None


class TextChecker:  # pylint: disable=too-many-instance-attributes
    """
    Checker of the texts of one consumer.

    Parameters
    ----------
    texts : Texts
        Reading of the texts.
    vocabulary : Vocabulary
        Value sets of the consumer, whose statuses state their effect on texts.
    typography : Typography
        Conventions of the printed forms, whose prefix reserves the derived macro names.
    composer : Composer
        Composer of the records of the consumer.
    bindings : BindingSource
        Provider of the bindings of the texts.
    signatures : Mapping[str, TargetSignature]
        Arguments of each unit, read from the denotes targets.
    scope : ScopeTable | None
        Scope table relating the audiences, None when each audience relates to itself only.
    sink : IssueSink
        Collector of the issues.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        texts: Texts,
        vocabulary: Vocabulary,
        typography: Typography,
        composer: Composer,
        bindings: BindingSource,
        signatures: Mapping[str, TargetSignature],
        scope: ScopeTable | None,
        sink: IssueSink,
    ) -> None:
        self._texts = texts
        self._vocabulary = vocabulary
        self._typography = typography
        self._composer = composer
        self._bindings = bindings
        self._signatures = signatures
        self._scope = scope
        self._sink = sink
        self._bound: dict[str, TextBinding] = {}
        self._notations: dict[tuple[str, ...], _Notation] = {}
        self._matchings: dict[tuple[str, str, str], _Matching] = {}
        self._unresolved: set[tuple[str, str, str]] = set()

    # --- one text -----------------------------------------------------------------------------

    def binds(self, resource: str) -> bool:
        """Whether a text is bound to a glossary or a notation, and is therefore checked."""
        if resource not in self._bound:
            self._bound[resource] = self._bindings.binding(resource)
        binding = self._bound[resource]
        return bool(binding.glossaries or binding.notations)

    def check(self, resource: str, source: str) -> None:
        """Check one text, given by its path relative to the root and its content."""
        if not self.binds(resource):
            return
        context = self._context(self._bound[resource])
        prose = read_prose(source, self._texts.masked, self._texts.math, self._texts.syntax)
        for identifier, visible in context.terms:
            self._check_term(resource, prose, identifier, visible)
        for identifier, visible in context.rules:
            self._check_rule(resource, prose, identifier, visible, context.audiences)
        if context.notation is not None:
            self._check_math(resource, prose, context.notation)

    def _context(self, binding: TextBinding) -> _Context:
        """Gather the entries visible from the glossaries and the notations bound to a text."""
        terms: dict[tuple[str, str], tuple[str, Visible]] = {}
        rules: dict[tuple[str, str], tuple[str, Visible]] = {}
        for bound in binding.glossaries:
            composition = self._resolved(RecordKind.GLOSSARY, bound)
            if composition is None:
                continue
            for target, section in ((terms, "terms"), (rules, "rules")):
                for identifier, visible in composition.sections.get(section, {}).items():
                    target.setdefault((visible.record.resource, identifier), (identifier, visible))
        compositions = [
            composition
            for composition in (
                self._resolved(RecordKind.NOTATION, bound) for bound in binding.notations
            )
            if composition is not None
        ]
        related: set[str] = set()
        for bound in binding.audiences:
            related |= (
                self._scope.related(bound.value) if self._scope is not None else {bound.value}
            )
        return _Context(
            tuple(terms.values()),
            tuple(rules.values()),
            self._notation(compositions) if compositions else None,
            frozenset(related),
        )

    def _resolved(self, kind: RecordKind, bound: Bound) -> Composition | None:
        """Compose a bound record, reporting at its declaration a binding naming no record."""
        composition = self._composer.compose(kind, bound.value)
        if composition is None:
            key = (bound.resource, bound.pointer, bound.value)
            if key not in self._unresolved:
                self._unresolved.add(key)
                self._sink.report(
                    "unresolved-text-binding",
                    bound.resource,
                    bound.pointer,
                    f"no {kind.singular} {bound.value}",
                )
        return composition

    def _notation(self, compositions: Sequence[Composition]) -> _Notation:
        """Return the macro table of the bound notations, built and checked once per combination.

        A combination named by no output of the build is checked here only, so the defects of its
        table are reported; a defect shared with a table of the build is reported once, since the
        service keeps one of identical issues.
        """
        key = tuple(composition.record.identifier for composition in compositions)
        if key not in self._notations:
            table = build_macro_table(
                compositions, (), self._signatures, self._typography, self._sink
            )
            entries: dict[str, Visible] = {}
            for composition in compositions:
                entries.update(composition.sections.get("entries", {}))
            printing: dict[str, list[str]] = {}
            reported: dict[str, list[Macro]] = {}
            for macro in table.macros:
                if macro.parameters or macro.body == f"\\{macro.name}":
                    continue
                if self._reported(entries.get(macro.identifier)):
                    reported.setdefault(macro.body, []).append(macro)
                elif "\\" in macro.body:
                    printing.setdefault(macro.body, []).append(macro.name)
            ordered = sorted({*printing, *reported}, key=lambda body: -len(body))
            self._notations[key] = _Notation(
                table,
                entries,
                {macro.name: macro for macro in table.macros},
                (
                    re.compile(alternation(_body_pattern(body) for body in ordered))
                    if ordered
                    else None
                ),
                {body: tuple(names) for body, names in printing.items()},
                {body: tuple(macros) for body, macros in reported.items()},
            )
        return self._notations[key]

    def _reported(self, visible: Visible | None) -> bool:
        """Whether the status of an entry reports its use in texts."""
        entry = visible.entry if visible is not None else None
        role = self._role(entry.status) if isinstance(entry, Entry) else None
        return role is not None and role.term_in_texts is not Severity.OFF

    def _role(self, status: str | None) -> StatusRole | None:
        """Return the behaviour of a status, the default status standing for an absent one."""
        return self._vocabulary.statuses.get(status or self._vocabulary.default_status)

    def _status(self, status: str | None) -> str:
        """Return the name of a status, the default status standing for an absent one."""
        return status or self._vocabulary.default_status

    # --- terms --------------------------------------------------------------------------------

    def _term_matching(self, identifier: str, visible: Visible) -> _Matching:
        """Return the compiled patterns of a term, its valid frames included."""
        key = (visible.record.resource, "terms", identifier)
        if key not in self._matchings:
            term = visible.entry
            assert isinstance(term, Term)
            frames: list[CompiledFrame] = []
            if term.frames:
                composition = self._composer.compose(RecordKind.GLOSSARY, visible.record.identifier)
                for frame in term.frames:
                    try:
                        frames.append(
                            compile_frame(
                                parse(frame),
                                lambda refs: _slot(composition, refs),
                                self._texts.determiners,
                                term.case_sensitive,
                            )
                        )
                    except (FrameError, UnresolvedSlot):
                        # A malformed frame is reported by the check of its record.
                        continue
            self._matchings[key] = _Matching(
                re.compile(term_pattern(term)), frames=tuple(frames) if frames else None
            )
        return self._matchings[key]

    def _check_term(self, resource: str, prose: Prose, identifier: str, visible: Visible) -> None:
        """Report the uses of a term reported by its status, and its uses outside its frames."""
        term = visible.entry
        assert isinstance(term, Term)
        matching = self._term_matching(identifier, visible)
        assert matching.forms is not None
        occurrences = [
            match for match in matching.forms.finditer(prose.prose) if match.end() > match.start()
        ]
        if not occurrences:
            return
        role = self._role(term.status)
        if role is not None and role.term_in_texts is not Severity.OFF:
            advice = self._term_label(visible, term.replaced_by)
            for match in occurrences:
                self._sink.report(
                    "term-status",
                    resource,
                    "",
                    f"'{excerpt(match.group(0))}' is the term {identifier} of status "
                    f"{self._status(term.status)} ({visible.record.resource})"
                    + (f"; write {advice}" if advice else ""),
                    prose.line(match.start()),
                    role.term_in_texts,
                )
        if matching.frames is None:
            return
        for match in occurrences:
            start, end = match.span()
            opening = prose.paragraph(start)
            if not any(frame.admits(prose.prose, start, end, opening) for frame in matching.frames):
                self._sink.report(
                    "frame-mismatch",
                    resource,
                    "",
                    f"'{excerpt(match.group(0))}' matches none of the frames of {identifier}: "
                    + ", ".join(term.frames),
                    prose.line(start),
                )

    def _term_label(self, visible: Visible, reference: str | None) -> str | None:
        """Return the label of a term named from the record of another, None when unresolved."""
        if reference is None:
            return None
        composition = self._composer.compose(RecordKind.GLOSSARY, visible.record.identifier)
        found = composition.lookup("terms", reference) if composition is not None else None
        return found.entry.label if found is not None and isinstance(found.entry, Term) else None

    # --- rules --------------------------------------------------------------------------------

    def _rule_matching(self, identifier: str, visible: Visible) -> _Matching:
        """Return the compiled patterns of a rule: its valid forms and its valid exceptions."""
        key = (visible.record.resource, "rules", identifier)
        if key not in self._matchings:
            rule = visible.entry
            assert isinstance(rule, LexicalRule)
            forms = valid(rule.forms)
            pattern = alternation(form_pattern(form, rule.case_sensitive) for form in forms)
            self._matchings[key] = _Matching(
                re.compile(pattern) if forms else None,
                tuple(
                    re.compile(form_pattern(form, rule.case_sensitive))
                    for form in valid(rule.exceptions)
                ),
            )
        return self._matchings[key]

    def _check_rule(
        self,
        resource: str,
        prose: Prose,
        identifier: str,
        visible: Visible,
        audiences: frozenset[str],
    ) -> None:
        """Report the forbidden forms of a rule binding the text, outside its exceptions."""
        rule = visible.entry
        assert isinstance(rule, LexicalRule)
        if rule.audiences is not None and not rule.audiences & audiences:
            return
        cap = self._rule_cap(rule)
        matching = self._rule_matching(identifier, visible)
        if cap is Severity.OFF or matching.forms is None:
            return
        found = [
            match for match in matching.forms.finditer(prose.prose) if match.end() > match.start()
        ]
        if not found:
            return
        # The exceptions are searched only in a text holding a forbidden form, since most texts
        # hold none and an exception may cost far more than the forms.
        excepted = _spans(matching.exceptions, prose.prose)
        advice = " or ".join(self._replacement(visible, item) for item in rule.replacements)
        for match in found:
            start, end = match.span()
            if any(first <= start and end <= last for first, last in excepted):
                continue
            self._sink.report(
                "forbidden-form",
                resource,
                "",
                f"'{excerpt(match.group(0))}' is forbidden by {identifier} "
                f"({visible.record.resource}); write {advice}; {rule.reason}",
                prose.line(start),
                cap,
            )

    def _rule_cap(self, rule: LexicalRule) -> Severity:
        """Return the severity of a match of a rule: its own, capped by the effect of its status."""
        role = self._role(rule.status)
        cap = Severity(rule.severity) if rule.severity else Severity.ERROR
        return cap.capped(role.rule_in_texts if role is not None else None)

    def _replacement(self, visible: Visible, replacement: Replacement) -> str:
        """Return the text of a replacement, its term or its instruction, and its condition."""
        if replacement.term is not None:
            text = self._term_label(visible, replacement.term) or replacement.term
        else:
            text = replacement.instruction or ""
        return f"{text} ({replacement.condition})" if replacement.condition else text

    # --- mathematics --------------------------------------------------------------------------

    def _check_math(self, resource: str, prose: Prose, notation: _Notation) -> None:
        """Report the macros of the mathematics against the macro table of the notations."""
        prefix = self._typography.macro_prefix
        for view in prose.math:
            for match in CONTROL_WORD.finditer(view.text):
                line = prose.line(view.to_source(match.start()))
                macro = notation.macros.get(match.group(1))
                if macro is not None:
                    self._check_entry(resource, line, macro, notation)
                elif match.group(1).startswith(prefix):
                    self._sink.report(
                        "unknown-macro",
                        resource,
                        "",
                        f"\\{match.group(1)} is defined by none of the bound notations",
                        line,
                    )
            if notation.bodies is None:
                continue
            for match in notation.bodies.finditer(view.text):
                body, line = match.group(0), prose.line(view.to_source(match.start()))
                if body not in notation.printing:
                    for macro in notation.reported[body]:
                        self._check_entry(resource, line, macro, notation, written=body)
                    continue
                names = " or ".join(f"\\{name}" for name in notation.printing[body])
                self._sink.report(
                    "raw-printed-form",
                    resource,
                    "",
                    f"'{body}' is the printed form of the macro {names}; call it",
                    line,
                )

    def _check_entry(
        self, resource: str, line: int, macro: Macro, notation: _Notation, written: str = ""
    ) -> None:
        """Report the macro of an entry whose status reports its use in texts, or its printed body
        when `written` gives it."""
        visible = notation.entries.get(macro.identifier)
        if visible is None or not isinstance(visible.entry, Entry):
            return
        entry = visible.entry
        role = self._role(entry.status)
        if role is None or role.term_in_texts is Severity.OFF:
            return
        replacement = next(
            (item for item in notation.table.macros if item.identifier == entry.replaced_by),
            None,
        )
        advice = ""
        if replacement is not None:
            advice = f"; write \\{replacement.name}"
            if written:
                advice += f", printing '{replacement.body}'"
        subject = f"'{written}'" if written else f"\\{macro.name}"
        self._sink.report(
            "entry-status",
            resource,
            "",
            f"{subject} prints the entry {macro.identifier} of status "
            f"{self._status(entry.status)}{advice}",
            line,
            role.term_in_texts,
        )


def _slot(composition: Composition | None, refs: tuple[str, ...]) -> str:
    """Return the pattern of the terms named by a slot, each under its own case.

    Raises
    ------
    UnresolvedSlot
        If a slot names a term that the glossary does not hold.
    """
    patterns: list[str] = []
    for ref in refs:
        found = composition.lookup("terms", ref) if composition is not None else None
        if found is None or not isinstance(found.entry, Term):
            raise UnresolvedSlot(ref)
        patterns.append(term_pattern(found.entry))
    return alternation(patterns)


def _body_pattern(body: str) -> str:
    """Return the pattern of a printed body, opened by a boundary when it starts with a letter, and
    closed by a boundary when it ends on a control word.

    Examples
    --------
    >>> pattern = re.compile(_body_pattern("s_k"))
    >>> bool(pattern.search("\\\\cos_k")), bool(pattern.search("a + s_k"))
    (False, True)
    """
    opening = r"(?<![A-Za-z\\])" if body[:1].isalpha() else ""
    closing = r"(?![A-Za-z])" if re.search(r"\\[A-Za-z]+$", body) else ""
    return opening + re.escape(body) + closing
