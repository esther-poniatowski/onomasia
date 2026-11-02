"""
Issues: the defects found in records, each attached to one check of the catalog.

The catalog of checks lives in the packaged file `data/defaults.yml`, with the default severity
of each check. A consumer overrides a severity in its configuration, or turns a check off, but
cannot name a check absent from the catalog.

Classes
-------
Severity
    Severity of an issue, or `off` for a check left unreported.
Issue
    Defect found in a record.
IssueSink
    Collector of the issues of one run, applying the severity of each check.

Functions
---------
default_severities() -> dict[str, Severity]
    Read the catalog of checks and their default severities.
"""

from dataclasses import dataclass, field
from enum import Enum
from importlib import resources
from typing import Mapping

import yaml

from .errors import OnomasiaError

DEFAULTS_FILE = "data/defaults.yml"
"""Packaged file holding the catalog of checks and the default configuration."""


class Severity(Enum):
    """Severity of an issue, or `off` for a check left unreported."""

    ERROR = "error"
    WARNING = "warning"
    OFF = "off"


@dataclass(frozen=True)
class Issue:
    """
    Defect found in a record.

    Attributes
    ----------
    check : str
        Identifier of the check, in the catalog.
    severity : Severity
        Severity of the issue, `error` or `warning`.
    resource : str
        Path of the record, relative to the root of the consumer.
    pointer : str
        JSON Pointer of the offending value in the record, empty for the whole record.
    message : str
        Statement of the defect.
    """

    check: str
    severity: Severity
    resource: str
    pointer: str
    message: str


@dataclass
class IssueSink:
    """
    Collector of the issues of one run, applying the severity of each check.

    Parameters
    ----------
    severities : Mapping[str, Severity]
        Severity of each check of the catalog.
    """

    severities: Mapping[str, Severity]
    issues: list[Issue] = field(default_factory=list)

    def report(self, check: str, resource: str, pointer: str, message: str) -> None:
        """
        Record an issue under the severity of its check, unless the check is off.

        Raises
        ------
        OnomasiaError
            If the check is absent from the catalog, which is a defect of Onomasia.
        """
        try:
            severity = self.severities[check]
        except KeyError as error:
            raise OnomasiaError(f"check {check!r} is absent from the catalog") from error
        if severity is not Severity.OFF:
            self.issues.append(Issue(check, severity, resource, pointer, message))

    def has_errors(self) -> bool:
        """Whether an issue of severity `error` was reported."""
        return any(issue.severity is Severity.ERROR for issue in self.issues)


def packaged_defaults() -> Mapping[str, object]:
    """
    Read the packaged defaults file: the catalog of checks and the default configuration.

    Raises
    ------
    OnomasiaError
        If the packaged file is not a mapping.
    """
    resource = resources.files(__package__).joinpath(DEFAULTS_FILE)
    data = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise OnomasiaError(f"{DEFAULTS_FILE}: expected a mapping")
    return data


def default_severities() -> dict[str, Severity]:
    """
    Read the catalog of checks and their default severities.

    Raises
    ------
    OnomasiaError
        If the catalog is missing or names an unknown severity.
    """
    catalog = packaged_defaults().get("checks")
    if not isinstance(catalog, Mapping):
        raise OnomasiaError(f"{DEFAULTS_FILE}: expected a mapping under checks")
    try:
        return {
            str(check): Severity(str(entry.get("severity"))) for check, entry in catalog.items()
        }
    except (AttributeError, ValueError) as error:
        raise OnomasiaError(f"{DEFAULTS_FILE}: every check declares a severity") from error
