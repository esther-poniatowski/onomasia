"""Test that every check of the catalog is shown to fire by a planted case."""

from onomasia.issues import default_severities

import test_records
import test_typography

SHOWN_WITHOUT_PLANTING = {"undeclared-entry"}
"""Checks reported by the clean consumers themselves, so that their tests show them firing."""


def test_every_check_of_the_catalog_is_planted() -> None:
    """A check of the catalog without a planted case is a check that nothing shows to work."""
    planted = (
        set(test_records.PLANTED)
        | set(test_typography.PLANTED)
        | {test_typography.UNRESOLVED_OUTPUT}
    )
    assert set(default_severities()) == planted | SHOWN_WITHOUT_PLANTING
