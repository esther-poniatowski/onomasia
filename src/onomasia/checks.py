"""
Checks of composed records against the vocabularies and the typography of the consumer.

Each check is a function reading one `CheckContext` and reporting to its sink; the tuple
`RECORD_CHECKS` registers them, so a new check joins the run without changing the runner. A check
reports an entry only in the record that declares it, so that a glossary imported by ten others is
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
    LexicalRule,
    Replacement,
    Term,
    TypographicClass,
)


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


def check_form_collisions(context: CheckContext) -> None:
    """Check that terms share no form, and that no rule forbids a form of a term."""
    for composition in context.glossaries:
        owners: dict[str, tuple[str, Visible]] = {}
        for identifier, visible in composition.sections.get("terms", {}).items():
            assert isinstance(visible.entry, Term)
            for form in _literal_forms(visible.entry):
                first = owners.setdefault(form, (identifier, visible))
                local = (
                    visible.record is composition.record or first[1].record is composition.record
                )
                if first[0] != identifier and local:
                    message = f"{identifier} and {first[0]} share the form {form!r}"
                    context.sink.report(
                        "form-collision",
                        composition.record.resource,
                        f"/terms/{identifier}",
                        message,
                    )
        for identifier, visible in composition.sections.get("rules", {}).items():
            assert isinstance(visible.entry, LexicalRule)
            for form in _literal_forms(visible.entry):
                owner = owners.get(form)
                if owner is not None and (
                    visible.record is composition.record or owner[1].record is composition.record
                ):
                    message = f"the rule forbids {form!r}, a form of the term {owner[0]}"
                    context.sink.report(
                        "rule-shadows-term",
                        composition.record.resource,
                        f"/rules/{identifier}",
                        message,
                    )


def printed_body(entry: Entry, composition: Composition, placeholder: str) -> str | None:
    """
    Return the TeX printed for an entry: its body, or the template of its class applied to its base.

    Returns None when the entry gives no body and its class prints no template.
    """
    if entry.body is not None:
        return entry.body
    if entry.base is None or entry.typographic_class is None:
        return None
    visible = composition.lookup("classes", entry.typographic_class)
    if (
        visible is None
        or not isinstance(visible.entry, TypographicClass)
        or visible.entry.template is None
    ):
        return None
    return visible.entry.template.replace(placeholder, entry.base)


def check_entries(context: CheckContext) -> None:
    """Check the printed form and the meaning of each entry, and the collisions of printed forms."""
    placeholder = context.typography.base_placeholder
    for composition in context.notations:
        printed: dict[str, str] = {}
        for identifier, visible in composition.sections.get("entries", {}).items():
            entry = visible.entry
            if not isinstance(entry, Entry):
                continue
            local = visible.record is composition.record
            pointer = f"/entries/{identifier}"
            if local:
                _check_meaning(context, visible, entry, pointer)
                if entry.body is not None and entry.base is not None:
                    _report(
                        context,
                        "ambiguous-body",
                        visible,
                        pointer,
                        "the entry gives both a body and a base",
                    )
            body = printed_body(entry, composition, placeholder)
            if body is None:
                if local:
                    _report(
                        context,
                        "missing-body",
                        visible,
                        pointer,
                        "neither a body nor a base under a class with a template",
                    )
                continue
            first = printed.setdefault(body, identifier)
            if first != identifier and local:
                message = f"{identifier} and {first} both print {body!r}"
                context.sink.report("body-collision", composition.record.resource, pointer, message)


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


RECORD_CHECKS: tuple[Callable[[CheckContext], None], ...] = (
    check_statuses,
    check_term_references,
    check_classes,
    check_contexts,
    check_form_collisions,
    check_entries,
)
"""Checks run on the composed records, in order."""


def run_record_checks(context: CheckContext) -> None:
    """Run every registered check."""
    for check in RECORD_CHECKS:
        check(context)
