"""
Frames: the constructions admitted for a term in the prose of a text.

A frame is a sequence of tokens separated by spaces, words of the text being written as they are:

- `~` stands for the term itself, written in any of its forms, exactly once and outside every
  optional part;
- a word is matched as a literal form, under the case of the term;
- `[ ... ]` holds an optional part, which may nest;
- `{a|b}` is a slot holding one of the terms named, each in any of its forms and under its own
  case, possibly after one determiner of the configuration;
- `{}` is a slot holding any one word other than a determiner, possibly after one determiner.

For example, `~ of {input|stimulus} [in {}]` admits "gain of the input in V1" and "gain of a
stimulus". A frame is compiled into two halves, the text before the term and the text after it,
so that an occurrence of the term is admitted when the text before it ends with a match of the
first half and the text after it begins with a match of the second. Two admitted occurrences may
therefore share words, as in "the gain of the gain of noise".

Functions
---------
parse(frame) -> tuple[Node, ...]
    Parse a frame, raising `FrameError` when it is malformed.
compile_frame(nodes, slot, determiners, case_sensitive) -> CompiledFrame
    The two halves of a parsed frame.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Sequence

from .patterns import JOINER, LEFT, RIGHT, alternation, literal

TOKEN = re.compile(r"\[|\]|\{[^{}]*\}|[{}]|~|[^\s\[\]{}~]+")
"""Tokens of a frame: brackets, slots, a lone brace, the mark of the term, and words."""

WORD = r"[^\s.,;:!?()\[\]\x00]+"
"""Any one word of a slot `{}`."""


class FrameError(ValueError):
    """Raised for a malformed frame."""


class UnresolvedSlot(LookupError):
    """Raised when a slot names a term that the glossary does not hold."""


@dataclass(frozen=True)
class Node:
    """
    Element of a parsed frame.

    Attributes
    ----------
    kind : str
        `term`, `word`, `slot` or `optional`.
    text : str
        Word of a node `word`.
    refs : tuple[str, ...]
        Terms named by a slot, empty for a slot of any word.
    children : tuple[Node, ...]
        Elements of an optional part.
    """

    kind: str
    text: str = ""
    refs: tuple[str, ...] = ()
    children: tuple["Node", ...] = ()


@dataclass(frozen=True)
class CompiledFrame:
    """
    The two halves of a frame around its term.

    Attributes
    ----------
    before : re.Pattern[str] | None
        Pattern that the text before the term must end with, None when the frame opens on it.
    after : re.Pattern[str] | None
        Pattern that the text after the term must begin with, None when the frame closes on it.
    """

    before: re.Pattern[str] | None
    after: re.Pattern[str] | None

    def admits(self, text: str, start: int, end: int, opening: int = 0) -> bool:
        """
        Whether the frame admits the occurrence of its term spanning `start` to `end` in a text,
        the text before the term being read from `opening` on.
        """
        if self.before is not None and self.before.search(text, opening, start) is None:
            return False
        return self.after is None or self.after.match(text, end) is not None


def parse(frame: str) -> tuple[Node, ...]:
    """
    Parse a frame into its elements.

    Raises
    ------
    FrameError
        If a bracket or a brace is unbalanced, a slot names an empty term, or the frame holds no or
        several marks `~`, or a mark inside an optional part.

    Examples
    --------
    >>> [node.kind for node in parse("[the] ~ of {input|stimulus}")]
    ['optional', 'term', 'word', 'slot']
    >>> parse("~ ] of {}")
    Traceback (most recent call last):
    ...
    onomasia.grammar.frames.FrameError: a closing bracket opens no optional part
    """
    stack: list[list[Node]] = [[]]
    for token in TOKEN.findall(frame):
        if token == "[":
            stack.append([])
        elif token == "]":
            if len(stack) == 1:
                raise FrameError("a closing bracket opens no optional part")
            children = tuple(stack.pop())
            stack[-1].append(Node("optional", children=children))
        elif token in ("{", "}"):
            raise FrameError(f"a brace {token} opens or closes no slot")
        elif token == "~":
            if len(stack) > 1:
                raise FrameError("the mark ~ of the term lies inside an optional part")
            stack[-1].append(Node("term"))
        elif token.startswith("{"):
            inner = token[1:-1].strip()
            refs = tuple(ref.strip() for ref in inner.split("|")) if inner else ()
            if any(not ref for ref in refs):
                raise FrameError(f"the slot {token} names an empty term")
            stack[-1].append(Node("slot", refs=refs))
        else:
            stack[-1].append(Node("word", text=token))
    if len(stack) > 1:
        raise FrameError("an optional part is never closed")
    marks = sum(node.kind == "term" for node in stack[0])
    if marks != 1:
        raise FrameError(f"a frame holds the mark ~ once, not {marks} times")
    return tuple(stack[0])


def slot_refs(nodes: Sequence[Node]) -> tuple[str, ...]:
    """Return every term named by the slots of a parsed frame, optional parts included."""
    refs: list[str] = []
    for node in nodes:
        refs.extend(node.refs)
        refs.extend(slot_refs(node.children))
    return tuple(refs)


def compile_frame(
    nodes: Sequence[Node],
    slot: Callable[[tuple[str, ...]], str],
    determiners: Sequence[str],
    case_sensitive: bool,
) -> CompiledFrame:
    """
    Compile a parsed frame into the two halves around its term.

    Parameters
    ----------
    nodes : Sequence[Node]
        Parsed frame.
    slot : Callable[[tuple[str, ...]], str]
        Pattern of the forms of the terms named by a slot; it raises `UnresolvedSlot` for a term
        that the glossary does not hold.
    determiners : Sequence[str]
        Words admitted, one at most, before a slot.
    case_sensitive : bool
        Whether the words of the frame keep their case, as the forms of the framed term do.

    Examples
    --------
    >>> frame = compile_frame(parse("[the] ~ of {}"), lambda refs: "", ["the"], False)
    >>> text = "the gain of the gain of noise"
    >>> frame.admits(text, 4, 8), frame.admits(text, 16, 20), frame.admits("gain of the.", 0, 4)
    (True, True, False)
    """
    determiner = alternation(literal(word, False) for word in determiners) if determiners else ""
    optional_determiner = f"(?:{determiner}{JOINER})?" if determiner else ""
    any_word = LEFT + (f"(?!{determiner}{RIGHT})" if determiner else "") + WORD + RIGHT

    def element(node: Node) -> str:
        if node.kind == "word":
            return literal(node.text, case_sensitive)
        if node.kind == "slot":
            return optional_determiner + (slot(node.refs) if node.refs else any_word)
        return sequence(node.children, required=False)

    def sequence(elements: Sequence[Node], required: bool) -> str:
        pattern = ""
        for node in elements:
            inner = element(node)
            if node.kind == "optional":
                pattern += f"(?:{JOINER}{inner})?" if required else f"(?:{inner}{JOINER})?"
            else:
                pattern += (JOINER if required else "") + inner
                required = True
        return pattern

    position = next(index for index, node in enumerate(nodes) if node.kind == "term")
    before, after = nodes[:position], nodes[position + 1 :]
    before_pattern = None
    if before:
        joined = sequence(before, required=False)
        if any(node.kind != "optional" for node in before):
            joined += JOINER
        before_pattern = re.compile(f"(?:{joined})\\Z")
    after_pattern = re.compile(sequence(after, required=True)) if after else None
    return CompiledFrame(before_pattern, after_pattern)
