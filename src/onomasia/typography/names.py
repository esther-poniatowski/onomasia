"""
Macro names: the name of an entry is declared by the entry, or derived from its identifier.

A derived name joins the reserved prefix and the identifier, each hyphen removed and the letter
after it capitalized, each digit replaced by its word, since a control word of TeX holds letters
only. The prefix keeps every derived name apart from the commands of TeX, so an identifier such as
`nu` never overwrites `\\nu`.

Functions
---------
derived_name(identifier, prefix, digit_names) -> str
    Derive the macro name of an entry from its identifier.
"""

from typing import Sequence

HYPHEN = "-"
"""Separator of the words of an identifier."""


def derived_name(identifier: str, prefix: str, digit_names: Sequence[str]) -> str:
    """
    Derive the macro name of an entry from its identifier.

    Parameters
    ----------
    identifier : str
        Identifier of the entry: lowercase letters, digits and hyphens.
    prefix : str
        Reserved prefix of derived names.
    digit_names : Sequence[str]
        Word replacing each digit, from 0 to 9.

    Examples
    --------
    >>> digits = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
    >>> derived_name("w-out", "ono", digits), derived_name("sigma2", "ono", digits)
    ('onowOut', 'onosigmaTwo')
    """
    parts: list[str] = [prefix]
    capitalize = False
    for character in identifier:
        if character == HYPHEN:
            capitalize = True
        elif character.isdigit():
            parts.append(digit_names[int(character)])
            capitalize = False
        else:
            parts.append(character.upper() if capitalize else character)
            capitalize = False
    return "".join(parts)
