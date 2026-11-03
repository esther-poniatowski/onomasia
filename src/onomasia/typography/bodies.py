"""
Printed body of a notation entry: its own body, or the template of its class applied to its base.

Functions
---------
printed_body(entry, composition, placeholder) -> str | None
    Return the TeX printed for an entry.
"""

from ..composition import Composition
from ..records.model import Entry, TypographicClass


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
