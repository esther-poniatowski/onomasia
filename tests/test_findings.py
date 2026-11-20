"""Tests of the findings log: each issue written as a result that the profile of Elenchos admits."""

from elenchos import profile

from onomasia.findings import sarif_log
from onomasia.issues import Issue, Severity, default_severities


def _log(issues: list[Issue]) -> dict:
    """Write the log of `issues`, after checking it against the profile."""
    log = sarif_log(issues)
    assert profile.violations(log) == []
    return log


def test_every_check_of_the_catalog_is_a_rule_of_the_log() -> None:
    rules = _log([])["runs"][0]["tool"]["driver"]["rules"]
    assert [rule["id"] for rule in rules] == list(default_severities())


def test_a_record_issue_is_located_by_its_pointer() -> None:
    issue = Issue("missing-gloss", Severity.WARNING, "notation.yml", "/entries/lam", "no gloss")
    log = _log([issue])
    (result,) = log["runs"][0]["results"]
    assert (
        result["level"] == "warning" and "region" not in result["locations"][0]["physicalLocation"]
    )
    assert profile.identities(log) == ["onomasia|missing-gloss|path:notation.yml|/entries/lam"]


def test_a_text_issue_is_located_by_its_typed_locus_and_line() -> None:
    issues = [
        Issue("forbidden-form", Severity.ERROR, "note.md", "", "m", 3, "term:base", "neuron"),
        Issue("entry-status", Severity.ERROR, "note.md", "", "m", 4, "symbol:mix", "\\onoW"),
    ]
    log = _log(issues)
    regions = [
        result["locations"][0]["physicalLocation"]["region"] for result in log["runs"][0]["results"]
    ]
    assert regions == [{"startLine": 3}, {"startLine": 4}]
    assert profile.identities(log) == [
        "onomasia|forbidden-form|path:note.md|term:base|neuron",
        "onomasia|entry-status|path:note.md|symbol:mix|\\onoW",
    ]


def test_a_record_of_another_repository_keeps_its_resource() -> None:
    issue = Issue("schema-violation", Severity.ERROR, "mixture:notation.yml", "/id", "bad")
    log = _log([issue])
    assert profile.identities(log) == ["onomasia|schema-violation|path:mixture:notation.yml|/id"]
