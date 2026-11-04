"""
The prose and the mathematics of a text, read from the regions of Merismos.

The prose is the text with every region of a masked kind filled by a character that is neither a
space nor a word character, so that no form and no frame spans a masked region, while a form beside
it still meets its boundary. Two exceptions keep the reading of Obsidian:

- the destination of a wikilink without an alias is the text that the link displays, so it stays
  prose;
- the container prefixes of a quotation, such as `>`, and the marker `[!type]` of a callout are
  blanked with spaces, so that a form running over two lines of a callout still matches.

The fill keeps every offset and every line break, so a match locates its line in the source. The
mathematics is the content of each formula, read without its container prefixes.

Classes
-------
Prose
    Prose and mathematics of one text.

Functions
---------
read_prose(source, masked, math, syntax) -> Prose
    Segment a text and read its prose and its mathematics.
kinds_problem(kinds, syntax) -> str | None
    Why kinds of Merismos cannot be read from a text, None when they can.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

from merismos import (
    ContentView,
    MerismosError,
    Region,
    Segmentation,
    content_view,
    mask,
    segment,
)

SOURCE_TYPE = "markdown"
"""Source type of Merismos under which a text is read."""

FILL = "\x00"
"""Character filling a masked region: no space and no word character."""

QUOTATION, LINK, DESTINATION, LINK_TEXT = ("quotation", "link", "link-destination", "link-text")
"""Kinds of Merismos read for the structure of a text, apart from the masked kinds."""


@dataclass(frozen=True)
class Prose:
    """
    Prose and mathematics of one text.

    Attributes
    ----------
    source : str
        Text itself.
    prose : str
        Text with every masked region filled, and every container prefix blanked.
    math : tuple[ContentView, ...]
        Content of each formula, with the offsets of its characters in the source.
    starts : tuple[int, ...]
        Offset of the start of each line of the source.
    """

    source: str
    prose: str
    math: tuple[ContentView, ...]
    starts: tuple[int, ...]

    def line(self, offset: int) -> int:
        """Return the line of an offset of the source, counted from 1."""
        return bisect.bisect_right(self.starts, offset)

    def paragraph(self, offset: int) -> int:
        """Return the offset opening the paragraph that holds an offset of the prose."""
        found = max(self.prose.rfind("\n\n", 0, offset), self.prose.rfind("\n\r\n", 0, offset))
        return found + 1 if found >= 0 else 0


def _kept_destinations(segmentation: Segmentation) -> Iterator[Region]:
    """Yield the destinations of the wikilinks without an alias, which display their destination."""
    regions = segmentation.select([LINK, DESTINATION, LINK_TEXT])
    for index, region in enumerate(regions):
        if region.kind != LINK or region.attributes.get("syntax") != "wiki":
            continue
        children = [
            child
            for child in regions[index + 1 :]
            if region.range.start <= child.range.start < region.range.end
        ]
        if not any(child.kind == LINK_TEXT for child in children):
            yield from (child for child in children if child.kind == DESTINATION)


def _prefixes(segmentation: Segmentation, source: str) -> Iterator[tuple[int, int]]:
    """Yield the spans of the container prefixes of the quotations, and of their callout markers."""
    for quotation in segmentation.select([QUOTATION]):
        yield from ((gap.start, gap.end) for gap in quotation.gaps)
        if quotation.content is None:
            continue
        yield quotation.range.start, quotation.content.start
        if quotation.attributes.get("callout") is not None:
            closing = source.find("]", quotation.content.start, quotation.content.end)
            if closing >= 0:
                fold = quotation.attributes.get("fold")
                yield quotation.content.start, closing + 1 + (1 if fold else 0)


def read_prose(
    source: str, masked: Sequence[str], math: Sequence[str], syntax: Path | None = None
) -> Prose:
    """
    Segment a text and read its prose and its mathematics.

    Examples
    --------
    >>> source = "A `gain` and $g$ and [[note]].\\n> [!NOTE] a tuning\\n> curve\\n"
    >>> kinds = ["inline-code", "inline-math", "link-destination"]
    >>> prose = read_prose(source, kinds, ["inline-math"])
    >>> prose.prose.replace("\\x00", "").split(), [view.text for view in prose.math]
    (['A', 'and', 'and', '[[note]].', 'a', 'tuning', 'curve'], ['g'])
    """
    segmentation = segment(source, SOURCE_TYPE, syntax)
    kept = {(region.range.start, region.range.end) for region in _kept_destinations(segmentation)}
    hidden = [
        region
        for region in segmentation.select(masked)
        if region.kind != DESTINATION or (region.range.start, region.range.end) not in kept
    ]
    characters = list(mask(source, hidden, FILL))
    for start, end in _prefixes(segmentation, source):
        for offset in range(start, end):
            if characters[offset] not in "\r\n":
                characters[offset] = " "
    views = tuple(
        content_view(source, region)
        for region in segmentation.select(math)
        if region.content is not None
    )
    starts = (0, *(index + 1 for index, character in enumerate(source) if character == "\n"))
    return Prose(source, "".join(characters), views, starts)


def kinds_problem(kinds: Sequence[str], syntax: Path | None = None) -> str | None:
    """Return why kinds of Merismos cannot be read from a text, None when they can."""
    try:
        segment("", SOURCE_TYPE, syntax).select(kinds)
    except (ValueError, MerismosError) as error:
        return str(error)
    return None
