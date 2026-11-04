"""
The bindings of a text to its glossaries, its notations and its audiences.

Onomasia reads three roles, which Anagraphe resolves along the directory chain: the glossaries,
the notations and the audiences of a text. The consumer names the key of each role in the section
`bindings` of its Anagraphe configuration; a role that it does not name binds no text. Each role
merges by `override`, the nearest declaration binding the text.

Classes
-------
TextBinding
    Values bound to one text, with the declarations naming them.
BindingSource
    Protocol of a provider of the bindings of texts.
AnagrapheBindings
    Source resolving the bindings through Anagraphe.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from anagraphe.bindings import BindingResolver, Role
from anagraphe.configuration import load_config
from anagraphe.core.configuration import ConfigurationError as AnagrapheConfigurationError

from ..errors import ConfigurationError

GLOSSARY_ROLE = "onomasia.glossary"
"""Role naming the glossaries of a text."""

NOTATION_ROLE = "onomasia.notation"
"""Role naming the notations of a text."""

AUDIENCES_ROLE = "onomasia.audiences"
"""Role naming the audiences for which a text is written."""


@dataclass(frozen=True)
class Bound:
    """
    One value bound to a text, with the file and the key declaring it.

    Attributes
    ----------
    value : str
        Identifier of a glossary, a notation or an audience.
    resource : str
        Path of the declaring file, relative to the root.
    pointer : str
        JSON Pointer of the declaring key in that file.
    """

    value: str
    resource: str
    pointer: str


@dataclass(frozen=True)
class TextBinding:
    """
    Values bound to one text.

    Attributes
    ----------
    glossaries, notations, audiences : tuple[Bound, ...]
        Glossaries, notations and audiences of the text, in the order of their declaration.
    """

    glossaries: tuple[Bound, ...] = ()
    notations: tuple[Bound, ...] = ()
    audiences: tuple[Bound, ...] = ()


class BindingSource(Protocol):
    """Protocol of a provider of the bindings of texts."""

    def binding(self, resource: str) -> TextBinding:
        """Return the bindings of a text, given by its path relative to the root."""


class AnagrapheBindings:
    """
    Source resolving the bindings of texts through Anagraphe.

    Parameters
    ----------
    root : Path
        Root of the consumer, which is also the root of its Anagraphe configuration.
    configuration : Path
        Anagraphe configuration, whose section `bindings` names the key of each role.

    Raises
    ------
    ConfigurationError
        If the Anagraphe configuration is invalid or declares no section `bindings`.
    """

    def __init__(self, root: Path, configuration: Path) -> None:
        try:
            bindings = load_config(root, configuration).bindings
        except (AnagrapheConfigurationError, OSError) as error:
            raise ConfigurationError(f"{configuration}: {error}") from error
        if bindings is None:
            raise ConfigurationError(f"{configuration}: declares no section bindings")
        self._resolver = BindingResolver(root, bindings)
        self._roles = frozenset(bindings.roles)

    def binding(self, resource: str) -> TextBinding:
        """Return the bindings of a text, each role merged by `override`."""
        return TextBinding(
            self._values(resource, GLOSSARY_ROLE),
            self._values(resource, NOTATION_ROLE),
            self._values(resource, AUDIENCES_ROLE),
        )

    def _values(self, resource: str, role: str) -> tuple[Bound, ...]:
        """Return the values bound to a text for one role, none when the role is not declared."""
        if role not in self._roles:
            return ()
        binding = self._resolver.resolve(resource, Role(role))
        return tuple(
            Bound(value, declaration.rel, declaration.pointer)
            for declaration in binding.declarations
            for value in declaration.values
        )
