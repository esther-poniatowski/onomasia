"""
Regular expressions matching the written forms of terms and rules in the prose of a text.

A literal form matches as whole words: no letter, digit, underscore or hyphen touches it on either
side, so `regime` matches neither `regimes` nor `learning-regime`. Its words are separated in the
text by spaces, non-breaking spaces included, holding one line break at most, so a form never spans
two paragraphs; a masked region of the text holds no space, so a form never spans one either. A form
given as a regular expression is used as written, a leading global flag such as `(?i)` being read
as a flag of the form alone. The case of a form is ignored unless its term or its rule sets
`case_sensitive`, and each pattern carries its own flag, so patterns of different cases combine.
Among the forms of one term, the longer literal forms are tried first, so that `gain field` wins
over `gain`.

Functions
---------
literal(text, case_sensitive) -> str
    Pattern of a literal form.
form_pattern(form, case_sensitive) -> str
    Pattern of one written form.
term_pattern(term) -> str
    Pattern of every valid written form of a term, the longest first.
regex_problem(text) -> str | None
    Why a regular expression cannot serve as a form, None when it can.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..records.model import Form, Term

SPACE = r"[ \t\u00a0]"
"""One space between two words, a non-breaking space included."""

JOINER = rf"(?:{SPACE}+(?:\r?\n{SPACE}*)?|\r?\n{SPACE}*)"
"""Separation of two words in a text: spaces holding one line break at most."""

LEFT = r"(?<![\w-])"
"""Left boundary of a word: neither a word character nor a hyphen precedes it."""

RIGHT = r"(?![\w-])"
"""Right boundary of a word: neither a word character nor a hyphen follows it."""

GLOBAL_FLAGS = re.compile(r"^\(\?([aiLmsux]+)\)")
"""Leading global flags of a regular expression, such as `(?i)`."""

BACKREFERENCE = re.compile(r"\\[1-9]|\(\?P=")
"""Backreference of a regular expression, numbered or named."""


def flagged(pattern: str, case_sensitive: bool) -> str:
    """Return a pattern under its own case flag, which combines with patterns of another case."""
    return pattern if case_sensitive else f"(?i:{pattern})"


def literal(text: str, case_sensitive: bool = True) -> str:
    """
    Return the pattern of a literal form, matched as whole words.

    Examples
    --------
    >>> pattern = re.compile(literal("tuning curve"))
    >>> texts = ("a tuning\\ncurve", "a tuning-curve", "tuning\\n\\ncurve", "tuning\\0curve")
    >>> [bool(pattern.search(text)) for text in texts]
    [True, False, False, False]
    """
    pattern = LEFT + JOINER.join(re.escape(word) for word in text.split()) + RIGHT
    return flagged(pattern, case_sensitive)


def scoped(text: str) -> str:
    """
    Return a regular expression with its leading global flags scoped to it alone.

    Examples
    --------
    >>> scoped("(?i)gain"), scoped("gain")
    ('(?i:gain)', 'gain')
    """
    flags = GLOBAL_FLAGS.match(text)
    return f"(?{flags.group(1)}:{text[flags.end():]})" if flags else text


def form_pattern(form: Form, case_sensitive: bool) -> str:
    """Return the pattern of one written form under its case flag."""
    if form.regex:
        return flagged(f"(?:{scoped(form.text)})", case_sensitive)
    return literal(form.text, case_sensitive)


def alternation(patterns: Iterable[str]) -> str:
    """Return the alternation of patterns, the earlier ones tried first."""
    return "(?:" + "|".join(patterns) + ")"


def regex_problem(text: str) -> str | None:
    """
    Return why a regular expression cannot serve as a form, None when it can.

    A form is matched inside a larger expression, so it may name no group and hold no
    backreference, and it must not match the empty string.

    Examples
    --------
    >>> regex_problem("tuning[- ]curves?") is None, regex_problem("(?i)gain") is None
    (True, True)
    >>> regex_problem("x*"), regex_problem("(?P<term>gain)")
    ('the expression matches the empty string', 'the expression names a group')
    """
    try:
        compiled = re.compile(scoped(text))
        re.compile(f"(?i:(?:{scoped(text)}))")
    except re.error as error:
        return str(error)
    if compiled.groupindex:
        return "the expression names a group"
    if BACKREFERENCE.search(text):
        return "the expression holds a backreference"
    if compiled.fullmatch(""):
        return "the expression matches the empty string"
    return None


def valid(forms: Iterable[Form]) -> tuple[Form, ...]:
    """Return the forms that can be matched, a malformed regular expression being left out; the
    check of its record reports it."""
    return tuple(form for form in forms if not form.regex or regex_problem(form.text) is None)


def term_pattern(term: Term) -> str:
    """Return the pattern of every valid written form of a term, the longest literal first, then
    the regular expressions in their order."""
    forms = (Form(term.label), *valid(term.forms))
    literals = sorted((form for form in forms if not form.regex), key=lambda form: -len(form.text))
    expressions = [form for form in forms if form.regex]
    return alternation(
        form_pattern(form, term.case_sensitive) for form in (*literals, *expressions)
    )
