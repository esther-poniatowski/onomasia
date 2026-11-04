"""
Checks of composed records against the vocabularies and the typography of the consumer.

Each check is a function reading one `CheckContext` and reporting to its sink; the tuple
`RECORD_CHECKS` registers them, so a new check joins the run without changing the runner. A check
of one entry reports it in the record that declares it, and a check of a collision reports it in
the record that first brings its two entries together, so that a glossary imported by ten others is
reported once.

Classes
-------
CheckContext
    Compositions, vocabularies and sink shared by the checks of one run.

Functions
---------
run_record_checks(context) -> None
    Run every registered check.
"""

from dataclasses import dataclass
from typing import Callable, Iterable, Iterator

from .composition import Composition, Visible
from .configuration import Typography, Vocabulary
from .issues import IssueSink
from .records.model import (
    Alternative,
    Contexts,
    Entry,
    Form,
    LexicalRule,
    RecordKind,
    Replacement,
    Term,
    TypographicClass,
)
from .typography.bodies import printed_body
from .grammar.frames import FrameError, slot_refs
from .grammar.frames import parse as parse_frame
from .grammar.patterns import regex_problem


@dataclass(frozen=True)
class CheckContext:
    """
    Compositions, vocabularies and sink shared by the checks of one run.

    Attributes
    ----------
    glossaries : tuple[Composition, ...]
        Composition of each glossary.
    notations : tuple[Composition, ...]
        Composition of each notation, and of each notation under each of its overlays.
    vocabulary : Vocabulary
        Value sets of the consumer.
    typography : Typography
        Conventions of the printed forms.
    sink : IssueSink
        Collector of the issues.
    """

    glossaries: tuple[Composition, ...]
    notations: tuple[Composition, ...]
    vocabulary: Vocabulary
    typography: Typography
    sink: IssueSink


SECTION_NOUNS = {"terms": "term", "rules": "rule", "entries": "entry", "classes": "class"}
"""Noun naming one entry of each section, in messages."""


def _report(
    context: CheckContext, check: str, visible: Visible, pointer: str, message: str
) -> None:
    """Report an issue on the record declaring an entry."""
    context.sink.report(check, visible.record.resource, pointer, message)


# --- statuses and references --------------------------------------------------------------------


def _status_entries(
    composition: Composition,
) -> Iterator[tuple[str, str, Visible, str | None, str | None]]:
    """Yield the section, identifier, entry, status and replacement of each local entry."""
    for section in ("terms", "rules", "entries"):
        for identifier, visible in composition.local(section):
            entry = visible.entry
            if isinstance(entry, (Term, Entry)):
                yield section, identifier, visible, entry.status, entry.replaced_by
            elif isinstance(entry, LexicalRule):
                yield section, identifier, visible, entry.status, None


def check_statuses(context: CheckContext) -> None:
    """Check each status against the vocabulary, and the replacement that a status requires."""
    vocabulary = context.vocabulary
    for composition in context.glossaries + context.notations:
        for section, identifier, visible, status, replaced_by in _status_entries(composition):
            pointer = f"/{section}/{identifier}"
            role = vocabulary.statuses.get(status or vocabulary.default_status)
            if role is None:
                _report(
                    context,
                    "unknown-status",
                    visible,
                    f"{pointer}/status",
                    f"status {status} is not declared",
                )
            elif role.requires_replacement and replaced_by is None and section != "rules":
                _report(
                    context,
                    "missing-replacement",
                    visible,
                    pointer,
                    f"status {status} requires replaced_by",
                )
            if replaced_by is not None and composition.lookup(section, replaced_by) is None:
                _report(
                    context,
                    "unresolved-reference",
                    visible,
                    f"{pointer}/replaced_by",
                    f"no {SECTION_NOUNS[section]} {replaced_by}",
                )


def check_term_references(context: CheckContext) -> None:
    """Check the relations of terms and the replacements of rules."""
    relations = context.vocabulary.relations
    for composition in context.glossaries:
        for identifier, visible in composition.local("terms"):
            assert isinstance(visible.entry, Term)
            for relation, targets in visible.entry.relations.items():
                pointer = f"/terms/{identifier}/relations/{relation}"
                if relation not in relations:
                    _report(
                        context,
                        "unknown-relation",
                        visible,
                        pointer,
                        f"relation {relation} is not declared",
                    )
                for target in targets:
                    if composition.lookup("terms", target) is None:
                        _report(
                            context, "unresolved-reference", visible, pointer, f"no term {target}"
                        )
        for identifier, visible in composition.local("rules"):
            assert isinstance(visible.entry, LexicalRule)
            for index, replacement in enumerate(visible.entry.replacements):
                if (
                    replacement.term is not None
                    and composition.lookup("terms", replacement.term) is None
                ):
                    pointer = f"/rules/{identifier}/replace_with/{index}/term"
                    _report(
                        context,
                        "unresolved-reference",
                        visible,
                        pointer,
                        f"no term {replacement.term}",
                    )


def check_classes(context: CheckContext) -> None:
    """Check that each entry names a visible class, and that each template holds the placeholder."""
    placeholder = context.typography.base_placeholder
    for composition in context.notations:
        for identifier, visible in composition.local("classes"):
            assert isinstance(visible.entry, TypographicClass)
            template = visible.entry.template
            if template is not None and placeholder not in template:
                pointer = f"/classes/{identifier}/template"
                _report(
                    context,
                    "template-without-placeholder",
                    visible,
                    pointer,
                    f"the template holds no {placeholder}",
                )
        for identifier, visible in composition.local("entries"):
            entry = visible.entry
            if isinstance(entry, Entry) and entry.typographic_class is not None:
                if composition.lookup("classes", entry.typographic_class) is None:
                    pointer = f"/entries/{identifier}/class"
                    _report(
                        context,
                        "unresolved-reference",
                        visible,
                        pointer,
                        f"no class {entry.typographic_class}",
                    )


# --- contexts -----------------------------------------------------------------------------------


def _contexts_of(entry: object) -> Iterator[tuple[str, Contexts]]:
    """Yield the pointer suffix and the contexts of each alternative or replacement of an entry."""
    items: Iterable[Alternative | Replacement] = ()
    key = "alternatives"
    if isinstance(entry, (Term, Entry)):
        items = entry.alternatives
    elif isinstance(entry, LexicalRule):
        items, key = entry.replacements, "replace_with"
    for index, item in enumerate(items):
        yield f"{key}/{index}/when", item.contexts


def _check_context_values(
    context: CheckContext, visible: Visible, pointer: str, contexts: Contexts
) -> None:
    """Check the dimensions and the values of one set of contexts."""
    for dimension, values in contexts.items():
        admitted = context.vocabulary.contexts.get(dimension)
        if admitted is None:
            _report(
                context,
                "unknown-context",
                visible,
                pointer,
                f"dimension {dimension} is not declared",
            )
            continue
        for value in values:
            if value not in admitted:
                _report(
                    context,
                    "unknown-context",
                    visible,
                    f"{pointer}/{dimension}",
                    f"value {value} is not declared",
                )


def check_contexts(context: CheckContext) -> None:
    """Check each context dimension and value against the vocabulary of contexts."""
    for composition in context.glossaries + context.notations:
        for section in ("terms", "rules", "entries"):
            for identifier, visible in composition.local(section):
                for suffix, contexts in _contexts_of(visible.entry):
                    _check_context_values(
                        context, visible, f"/{section}/{identifier}/{suffix}", contexts
                    )


# --- collisions ---------------------------------------------------------------------------------


def _literal_forms(entry: Term | LexicalRule) -> Iterator[str]:
    """Yield the literal forms of a term, its label included, or of a rule, case folded if asked."""
    texts = [entry.label] if isinstance(entry, Term) else []
    texts.extend(form.text for form in entry.forms if not form.regex)
    for text in texts:
        yield text if entry.case_sensitive else text.casefold()


@dataclass(frozen=True)
class Collision:
    """
    Two visible entries sharing a key, such as a written form or a printed body.

    Attributes
    ----------
    key : str
        Value that the two entries share.
    first, second : tuple[str, str, Visible]
        Section, identifier and entry of each member, the first one met first.
    """

    key: str
    first: tuple[str, str, Visible]
    second: tuple[str, str, Visible]

    def signature(self) -> tuple[str, frozenset[tuple[str, str, str]]]:
        """Identify the collision by its key and the declarations of its members, in any order."""
        members = (self.first, self.second)
        return self.key, frozenset((s, i, v.record.resource) for s, i, v in members)

    def pointer(self, composition: Composition) -> str:
        """Locate the collision at a member declared by the composition, or at the import of one."""
        section, identifier, visible = self.second
        if visible.record is not composition.record and self.first[2].record is composition.record:
            section, identifier, _ = self.first
        return composition.pointer(section, identifier)


def _new_collisions(
    composition: Composition, collisions: Callable[[Composition], list[Collision]]
) -> Iterator[Collision]:
    """
    Yield the collisions first brought together by a composition.

    A collision already held by a merged source is reported in the composition of that source, so
    each collision is reported once, at the record that joins its two members.
    """
    inherited = {
        collision.signature()
        for _, source in composition.merged
        for collision in collisions(source)
    }
    for collision in collisions(composition):
        if collision.signature() not in inherited:
            yield collision


def _form_collisions(composition: Composition) -> list[Collision]:
    """List the pairs of terms sharing a written form, each with the first term met."""
    owners: dict[str, tuple[str, str, Visible]] = {}
    collisions: list[Collision] = []
    for identifier, visible in composition.sections.get("terms", {}).items():
        assert isinstance(visible.entry, Term)
        for form in _literal_forms(visible.entry):
            first = owners.setdefault(form, ("terms", identifier, visible))
            if first[1] != identifier:
                collisions.append(Collision(form, first, ("terms", identifier, visible)))
    return collisions


def _shadowed_terms(composition: Composition) -> list[Collision]:
    """List the pairs of a term and a rule forbidding one of its written forms."""
    owners: dict[str, tuple[str, str, Visible]] = {}
    for identifier, visible in composition.sections.get("terms", {}).items():
        assert isinstance(visible.entry, Term)
        for form in _literal_forms(visible.entry):
            owners.setdefault(form, ("terms", identifier, visible))
    collisions: list[Collision] = []
    for identifier, visible in composition.sections.get("rules", {}).items():
        assert isinstance(visible.entry, LexicalRule)
        for form in _literal_forms(visible.entry):
            if form in owners:
                collisions.append(Collision(form, owners[form], ("rules", identifier, visible)))
    return collisions


def check_form_collisions(context: CheckContext) -> None:
    """Check that terms share no form, and that no rule forbids a form of a term."""
    for composition in context.glossaries:
        for collision in _new_collisions(composition, _form_collisions):
            message = (
                f"{collision.second[1]} and {collision.first[1]} share the form {collision.key!r}"
            )
            context.sink.report(
                "form-collision",
                composition.record.resource,
                collision.pointer(composition),
                message,
            )
        for collision in _new_collisions(composition, _shadowed_terms):
            rule, term = collision.second[1], collision.first[1]
            message = f"the rule {rule} forbids {collision.key!r}, a form of the term {term}"
            context.sink.report(
                "rule-shadows-term",
                composition.record.resource,
                collision.pointer(composition),
                message,
            )


def _overloaded(first: tuple[str, str, Visible], second: tuple[str, str, Visible]) -> bool:
    """Whether either of two entries declares the other under `overloads`."""
    first_entry, second_entry = first[2].entry, second[2].entry
    assert isinstance(first_entry, Entry) and isinstance(second_entry, Entry)
    return first[1] in second_entry.overloads or second[1] in first_entry.overloads


def _body_collisions(placeholder: str) -> Callable[[Composition], list[Collision]]:
    """
    Return the lister of the pairs of entries printing the same body under a placeholder.

    Each entry is paired with the first earlier entry printing its body without a declared
    overload, so an entry overloading one entry still collides with a third one.
    """

    def collisions(composition: Composition) -> list[Collision]:
        printed: dict[str, list[tuple[str, str, Visible]]] = {}
        found: list[Collision] = []
        for identifier, visible in composition.sections.get("entries", {}).items():
            if not isinstance(visible.entry, Entry):
                continue
            body = printed_body(visible.entry, composition, placeholder)
            if body is None:
                continue
            member = ("entries", identifier, visible)
            earlier = printed.setdefault(body, [])
            clash = next((other for other in earlier if not _overloaded(other, member)), None)
            if clash is not None:
                found.append(Collision(body, clash, member))
            earlier.append(member)
        return found

    return collisions


def _check_overloads(
    context: CheckContext, composition: Composition, identifier: str, visible: Visible
) -> None:
    """Check that each overload of an entry names another entry printing the same body."""
    entry = visible.entry
    assert isinstance(entry, Entry)
    placeholder = context.typography.base_placeholder
    body = printed_body(entry, composition, placeholder)
    for index, other in enumerate(entry.overloads):
        pointer = f"/entries/{identifier}/overloads/{index}"
        target = composition.sections.get("entries", {}).get(other)
        if target is None:
            _report(context, "unresolved-reference", visible, pointer, f"no entry {other}")
        elif other == identifier:
            _report(context, "unneeded-overload", visible, pointer, "the entry names itself")
        elif not isinstance(target.entry, Entry) or (
            printed_body(target.entry, composition, placeholder) != body
        ):
            _report(context, "unneeded-overload", visible, pointer, f"{other} prints another body")


def check_entries(context: CheckContext) -> None:
    """Check the printed form and the meaning of each entry, and the collisions of printed forms."""
    placeholder = context.typography.base_placeholder
    for composition in context.notations:
        for identifier, visible in composition.local("entries"):
            entry = visible.entry
            if not isinstance(entry, Entry):
                continue
            pointer = f"/entries/{identifier}"
            _check_meaning(context, visible, entry, pointer)
            if entry.body is not None and entry.base is not None:
                _report(
                    context,
                    "ambiguous-body",
                    visible,
                    pointer,
                    "the entry gives both a body and a base",
                )
            if composition.record.kind is RecordKind.NOTATION:
                _check_overloads(context, composition, identifier, visible)
            if printed_body(entry, composition, placeholder) is None:
                _report(
                    context,
                    "missing-body",
                    visible,
                    pointer,
                    "neither a body nor a base under a class with a template",
                )
        for collision in _new_collisions(composition, _body_collisions(placeholder)):
            message = f"{collision.second[1]} and {collision.first[1]} both print {collision.key!r}"
            context.sink.report(
                "body-collision",
                composition.record.resource,
                collision.pointer(composition),
                message,
            )


def _check_meaning(context: CheckContext, visible: Visible, entry: Entry, pointer: str) -> None:
    """Check that an entry takes its meaning either from its target or from its gloss."""
    if entry.denotes is None and entry.gloss is None:
        _report(
            context,
            "missing-gloss",
            visible,
            pointer,
            "an undeclared entry states its meaning in a gloss",
        )
    elif entry.denotes is None:
        _report(context, "undeclared-entry", visible, pointer, "the entry denotes no unit")
    elif entry.gloss is not None:
        _report(
            context,
            "gloss-with-target",
            visible,
            f"{pointer}/gloss",
            "the unit states the meaning of the entry",
        )


def check_forms_and_frames(context: CheckContext) -> None:
    """Check the regular expressions of the forms, and the frames of the terms."""
    for composition in context.glossaries:
        for identifier, visible in composition.local("terms"):
            assert isinstance(visible.entry, Term)
            pointer = f"/terms/{identifier}"
            _check_regexes(context, visible, f"{pointer}/forms", visible.entry.forms)
            for number, frame in enumerate(visible.entry.frames):
                problem = _frame_problem(composition, frame)
                if problem is not None:
                    _report(
                        context, "invalid-frame", visible, f"{pointer}/frames/{number}", problem
                    )
        for identifier, visible in composition.local("rules"):
            assert isinstance(visible.entry, LexicalRule)
            pointer = f"/rules/{identifier}"
            _check_regexes(context, visible, f"{pointer}/forms", visible.entry.forms)
            _check_regexes(context, visible, f"{pointer}/exceptions", visible.entry.exceptions)


def _check_regexes(
    context: CheckContext, visible: Visible, pointer: str, forms: Iterable[Form]
) -> None:
    """Report each form given as a regular expression that cannot serve as a form."""
    for number, form in enumerate(forms):
        problem = regex_problem(form.text) if form.regex else None
        if problem is not None:
            _report(context, "invalid-form", visible, f"{pointer}/{number}/regex", problem)


def _frame_problem(composition: Composition, frame: str) -> str | None:
    """Return why a frame is malformed, or names a slot term absent from the glossary."""
    try:
        nodes = parse_frame(frame)
    except FrameError as error:
        return str(error)
    for ref in slot_refs(nodes):
        found = composition.lookup("terms", ref)
        if found is None or not isinstance(found.entry, Term):
            return f"the slot names no term {ref}"
    return None


RECORD_CHECKS: tuple[Callable[[CheckContext], None], ...] = (
    check_statuses,
    check_term_references,
    check_classes,
    check_contexts,
    check_form_collisions,
    check_entries,
    check_forms_and_frames,
)
"""Checks run on the composed records, in order."""


def run_record_checks(context: CheckContext) -> None:
    """Run every registered check."""
    for check in RECORD_CHECKS:
        check(context)
