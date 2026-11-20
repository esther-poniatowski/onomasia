"""
Findings log: the issues of a run written in the findings profile of the gate Elenchos.

Each issue becomes one result. The rule is the check of the catalog, and the level is the severity
of the issue, after the configuration of the consumer. The resource is the path of the record or
of the text, relative to the root of the consumer. The locus is the JSON Pointer of the offending
value in a record, or the typed locus of a defect in a text, `term:<glossary>` or
`symbol:<notation>`. The discriminator is the offending content, such as the form matched in a
text. A record read from another repository keeps its resource `<repository>:<path>`, since the
profile names no form for a file read at a commit of another repository.

Functions
---------
sarif_log(issues, stopped) -> dict
    Write the findings log of a run.
"""

from typing import Any, Sequence
from urllib.parse import quote

from . import __version__
from .issues import Issue, packaged_defaults

TOOL = "onomasia"
"""Driver name of the log, the first component of each identity."""

SARIF_SCHEMA = (
    "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"
)
"""Schema URI of SARIF 2.1.0, errata 01."""


def _rules() -> list[dict[str, Any]]:
    """Return one descriptor per check of the catalog, with its gloss and default severity."""
    checks = packaged_defaults()["checks"]
    assert isinstance(checks, dict)
    return [
        {
            "id": check,
            "shortDescription": {"text": entry["gloss"]},
            "defaultConfiguration": {"level": entry["severity"]},
        }
        for check, entry in checks.items()
    ]


def _result(issue: Issue) -> dict[str, Any]:
    """Write one issue as a result of the profile."""
    locus = issue.pointer or issue.locus
    resource = "path:" + issue.resource.replace("%", "%25").replace("#", "%23")
    location: dict[str, Any] = {
        "logicalLocations": [{"name": f"{resource}#{locus}" if locus else resource}]
    }
    physical: dict[str, Any] = {
        "artifactLocation": {"uri": quote(issue.resource), "uriBaseId": "SRCROOT"}
    }
    if issue.line is not None:
        physical["region"] = {"startLine": issue.line}
    location["physicalLocation"] = physical
    result: dict[str, Any] = {
        "ruleId": issue.check,
        "level": issue.severity.value,
        "message": {"text": issue.message},
        "locations": [location],
    }
    if issue.discriminator:
        result["partialFingerprints"] = {"discriminator/v1": issue.discriminator}
    return result


def sarif_log(issues: Sequence[Issue], stopped: str | None = None) -> dict[str, Any]:
    """
    Write the findings log of a run of `onomasia check` or `onomasia build`.

    Parameters
    ----------
    issues : Sequence[Issue]
        Issues of the run, each with a resource relative to the root of the consumer.
    stopped : str, optional
        Why the run could not start; the log then holds a failed run without results.

    Returns
    -------
    dict
        The log, ready to serialize as JSON.
    """
    run: dict[str, Any] = {
        "tool": {
            "driver": {
                "name": TOOL,
                "version": __version__,
                "isComprehensive": True,
                "rules": _rules(),
            }
        },
        "columnKind": "unicodeCodePoints",
    }
    if stopped is not None:
        run["invocations"] = [
            {
                "executionSuccessful": False,
                "toolExecutionNotifications": [{"level": "error", "message": {"text": stopped}}],
            }
        ]
    else:
        run["results"] = [_result(issue) for issue in issues]
    return {"version": "2.1.0", "$schema": SARIF_SCHEMA, "runs": [run]}
