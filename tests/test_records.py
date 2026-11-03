"""
Tests of the loading, the composition and the checks of records.

A clean consumer exercises every feature and reports nothing. Each other test plants one defect
and expects exactly the issue of its check, so that a missed issue and a false positive both fail.
"""

from pathlib import Path

import pytest
import yaml

from onomasia.configuration import load_configuration
from onomasia.errors import ConfigurationError
from onomasia.issues import Severity, default_severities
from onomasia.service import check_records

CONFIGURATION = {
    "schema_version": 1,
    "records": {
        "glossaries": ["**/glossary*.yml"],
        "notations": ["**/notation*.yml"],
        "overlays": ["**/overlay*.yml"],
        "exclude": ["archive"],
    },
    "vocabulary": {
        "statuses": {
            "in-use": {"requires_replacement": False},
            "deprecated": {"requires_replacement": True},
        },
        "default_status": "in-use",
        "contexts": {"register": ["formal", "informal"]},
        "relations": ["narrows"],
    },
}

BASE_GLOSSARY = {
    "_schema": "onomasia:glossary@1",
    "id": "base",
    "terms": {
        "curve": {"label": "curve", "gloss": "a one-dimensional set"},
        "tuning-curve": {
            "label": "tuning curve",
            "gloss": "the response of a neuron to one feature",
            "forms": ["tuning curves", {"regex": "tuning[- ]curves?"}],
            "alternatives": [{"label": "response curve", "when": {"register": ["informal"]}}],
            "relations": {"narrows": ["curve"]},
        },
    },
    "rules": {
        "neural-code": {
            "forms": ["neural code"],
            "replace_with": [{"term": "tuning-curve"}, {"instruction": "name the code"}],
            "reason": "too vague for this audience",
            "audiences": ["ml"],
        }
    },
}

PROJECT_GLOSSARY = {
    "_schema": "onomasia:glossary@1",
    "id": "project",
    "imports": [{"from": "base", "except": ["curve"]}, {"from": "base", "as": "b"}],
    "terms": {
        "old-name": {
            "label": "old name",
            "gloss": "a former name",
            "status": "deprecated",
            "replaced_by": "tuning-curve",
        },
        "manifold": {
            "label": "manifold",
            "gloss": "a smooth set",
            "relations": {"narrows": ["b.curve"]},
        },
    },
}

NOTATION = {
    "_schema": "onomasia:notation@1",
    "id": "mixture",
    "classes": {"matrix": {"template": "\\boldsymbol{{{base}}}", "gloss": "a matrix in bold"}},
    "entries": {
        "w-ff": {"denotes": "mixture:model.weights", "base": "W", "class": "matrix", "entry": True},
        "lam": {"gloss": "a free parameter", "body": "\\lambda"},
    },
}

OVERLAY = {
    "_schema": "onomasia:overlay@1",
    "id": "poster",
    "overlays": "mixture",
    "entries": {"w-ff": {"base": "V"}},
}


def _consumer(
    tmp_path: Path, records: dict[str, object], configuration: dict | None = None
) -> Path:
    """Write a configuration and records under a root, returning the root."""
    (tmp_path / "onomasia.yml").write_text(
        yaml.safe_dump(configuration or CONFIGURATION), encoding="utf-8"
    )
    for relative, data in records.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        text = data if isinstance(data, str) else yaml.safe_dump(data, allow_unicode=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def _issues(root: Path) -> list[tuple[str, str, str]]:
    """Run the check of the records, returning each issue as (check, resource, pointer)."""
    configuration = load_configuration(root, root / "onomasia.yml")
    return [(issue.check, issue.resource, issue.pointer) for issue in check_records(configuration)]


CLEAN = {
    "lexicon/glossary-base.yml": BASE_GLOSSARY,
    "projects/p/glossary.yml": PROJECT_GLOSSARY,
    "projects/p/notation.yml": NOTATION,
    "projects/p/overlay-poster.yml": OVERLAY,
}


def test_clean_consumer_reports_nothing_but_its_undeclared_entry(tmp_path: Path) -> None:
    assert _issues(_consumer(tmp_path, CLEAN)) == [
        ("undeclared-entry", "projects/p/notation.yml", "/entries/lam")
    ]


def test_excluded_folder_is_not_read(tmp_path: Path) -> None:
    records = dict(CLEAN, **{"archive/glossary.yml": "not: [valid"})
    assert ("invalid-yaml", "archive/glossary.yml", "") not in _issues(_consumer(tmp_path, records))


def _with(data: dict, path: list[str], value: object) -> dict:
    """Copy nested data, setting the value at a path of keys."""
    copy = yaml.safe_load(yaml.safe_dump(data))
    target = copy
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return copy


PLANTED = {
    "invalid-yaml": (
        {"projects/p/glossary.yml": "terms: [unclosed"},
        "projects/p/glossary.yml",
        "",
    ),
    "duplicate-key": (
        {"projects/p/glossary.yml": "_schema: x\n_schema: y\n"},
        "projects/p/glossary.yml",
        "",
    ),
    "unknown-format": (
        {"projects/p/glossary.yml": {"_schema": "other@1", "id": "x"}},
        "projects/p/glossary.yml",
        "/_schema",
    ),
    "wrong-format": ({"projects/p/glossary.yml": NOTATION}, "projects/p/glossary.yml", "/_schema"),
    "schema-violation": (
        {"projects/p/glossary.yml": _with(PROJECT_GLOSSARY, ["terms", "manifold", "gloss"], 3)},
        "projects/p/glossary.yml",
        "/terms/manifold/gloss",
    ),
    "duplicate-record": (
        {"projects/q/glossary.yml": _with(PROJECT_GLOSSARY, ["terms"], {})},
        "projects/q/glossary.yml",
        "/id",
    ),
    "unresolved-import": (
        {"projects/p/glossary.yml": _with(PROJECT_GLOSSARY, ["imports"], [{"from": "absent"}])},
        "projects/p/glossary.yml",
        "/imports/0/from",
    ),
    # The cycle closes at the import of base by project, where it is reported.
    "import-cycle": (
        {"lexicon/glossary-base.yml": _with(BASE_GLOSSARY, ["imports"], [{"from": "project"}])},
        "projects/p/glossary.yml",
        "/imports/0/from",
    ),
    "import-conflict": (
        {
            "lexicon/glossary-other.yml": {
                "_schema": "onomasia:glossary@1",
                "id": "other",
                "terms": {"curve": {"label": "bend", "gloss": "another curve"}},
            },
            "projects/p/glossary.yml": _with(
                PROJECT_GLOSSARY, ["imports"], [{"from": "base"}, {"from": "other"}]
            ),
        },
        "projects/p/glossary.yml",
        "/imports/1",
    ),
    "unresolved-import-entry": (
        {"projects/p/glossary.yml": _with(PROJECT_GLOSSARY, ["imports", 0, "except"], ["absent"])},
        "projects/p/glossary.yml",
        "/imports/0/except",
    ),
    "duplicate-alias": (
        {
            "projects/p/glossary.yml": _with(
                PROJECT_GLOSSARY,
                ["imports"],
                [{"from": "base", "as": "b"}, {"from": "base", "as": "b"}],
            )
        },
        "projects/p/glossary.yml",
        "/imports/1/as",
    ),
    "duplicate-entry": (
        {
            "projects/p/glossary.yml": _with(
                PROJECT_GLOSSARY, ["rules"], {"manifold": BASE_GLOSSARY["rules"]["neural-code"]}
            )
        },
        "projects/p/glossary.yml",
        "/rules/manifold",
    ),
    "unresolved-reference": (
        {
            "projects/p/glossary.yml": _with(
                PROJECT_GLOSSARY, ["terms", "manifold", "relations", "narrows"], ["b.absent"]
            )
        },
        "projects/p/glossary.yml",
        "/terms/manifold/relations/narrows",
    ),
    "unknown-status": (
        {
            "projects/p/glossary.yml": _with(
                PROJECT_GLOSSARY, ["terms", "manifold", "status"], "draft"
            )
        },
        "projects/p/glossary.yml",
        "/terms/manifold/status",
    ),
    "missing-replacement": (
        {
            "projects/p/glossary.yml": _with(
                PROJECT_GLOSSARY, ["terms", "manifold", "status"], "deprecated"
            )
        },
        "projects/p/glossary.yml",
        "/terms/manifold",
    ),
    "unknown-context": (
        {
            "lexicon/glossary-base.yml": _with(
                BASE_GLOSSARY,
                ["terms", "tuning-curve", "alternatives", 0, "when"],
                {"register": ["casual"]},
            )
        },
        "lexicon/glossary-base.yml",
        "/terms/tuning-curve/alternatives/0/when/register",
    ),
    "unknown-relation": (
        {
            "projects/p/glossary.yml": _with(
                PROJECT_GLOSSARY, ["terms", "manifold", "relations"], {"broadens": ["b.curve"]}
            )
        },
        "projects/p/glossary.yml",
        "/terms/manifold/relations/broadens",
    ),
    "form-collision": (
        {
            "projects/p/glossary.yml": _with(
                PROJECT_GLOSSARY, ["terms", "manifold", "forms"], ["Tuning Curves"]
            )
        },
        "projects/p/glossary.yml",
        "/terms/manifold",
    ),
    "rule-shadows-term": (
        {
            "projects/p/glossary.yml": _with(
                PROJECT_GLOSSARY,
                ["rules"],
                {
                    "no-manifold": {
                        "forms": ["manifold"],
                        "replace_with": [{"instruction": "x"}],
                        "reason": "r",
                    }
                },
            )
        },
        "projects/p/glossary.yml",
        "/rules/no-manifold",
    ),
    "missing-body": (
        {"projects/p/notation.yml": _with(NOTATION, ["entries", "lam", "body"], None)},
        "projects/p/notation.yml",
        "/entries/lam",
    ),
    "ambiguous-body": (
        {"projects/p/notation.yml": _with(NOTATION, ["entries", "lam", "base"], "l")},
        "projects/p/notation.yml",
        "/entries/lam",
    ),
    "body-collision": (
        {"projects/p/notation.yml": _with(NOTATION, ["entries", "lam", "body"], "\\boldsymbol{W}")},
        "projects/p/notation.yml",
        "/entries/w-ff",
    ),
    "missing-gloss": (
        {"projects/p/notation.yml": _with(NOTATION, ["entries", "lam", "gloss"], None)},
        "projects/p/notation.yml",
        "/entries/lam",
    ),
    "gloss-with-target": (
        {"projects/p/notation.yml": _with(NOTATION, ["entries", "w-ff", "gloss"], "the weights")},
        "projects/p/notation.yml",
        "/entries/w-ff/gloss",
    ),
    "unresolved-overlay": (
        {"projects/p/overlay-poster.yml": _with(OVERLAY, ["overlays"], "absent")},
        "projects/p/overlay-poster.yml",
        "/overlays",
    ),
    "unknown-override": (
        {"projects/p/overlay-poster.yml": _with(OVERLAY, ["entries"], {"absent": {"body": "x"}})},
        "projects/p/overlay-poster.yml",
        "/entries/absent",
    ),
    "template-without-placeholder": (
        {
            "projects/p/notation.yml": _with(
                NOTATION, ["classes", "matrix", "template"], "\\mathbf{W}"
            )
        },
        "projects/p/notation.yml",
        "/classes/matrix/template",
    ),
}


def _without_none(data: object) -> object:
    """Drop the keys whose value is None, so that a planted None removes a field."""
    if isinstance(data, dict):
        return {key: _without_none(value) for key, value in data.items() if value is not None}
    if isinstance(data, list):
        return [_without_none(item) for item in data]
    return data


@pytest.mark.parametrize("check", sorted(PLANTED))
def test_planted_defect_is_reported(tmp_path: Path, check: str) -> None:
    records, resource, pointer = PLANTED[check]
    planted = dict(CLEAN, **{path: _without_none(data) for path, data in records.items()})
    assert (check, resource, pointer) in _issues(_consumer(tmp_path, planted))


def _glossary(identifier: str, terms: dict, imports: list | None = None) -> dict:
    """Write a glossary holding terms, each a label, and imports."""
    return {
        "_schema": "onomasia:glossary@1",
        "id": identifier,
        "imports": [{"from": source} for source in imports or []],
        "terms": {term: {"label": label, "gloss": "g"} for term, label in terms.items()},
    }


def test_collision_of_two_imports_is_reported_once_at_the_record_joining_them(
    tmp_path: Path,
) -> None:
    records = {
        "glossary-a.yml": _glossary("a", {"gain": "gain"}),
        "glossary-b.yml": _glossary("b", {"amplification": "gain"}),
        "glossary-c.yml": _glossary("c", {}, ["a", "b"]),
        "glossary-d.yml": _glossary("d", {}, ["c"]),
    }
    assert _issues(_consumer(tmp_path, records)) == [
        ("form-collision", "glossary-c.yml", "/imports/1")
    ]


def test_collision_with_an_imported_term_is_reported_at_the_local_term(tmp_path: Path) -> None:
    records = {
        "glossary-a.yml": _glossary("a", {"gain": "gain"}),
        "glossary-c.yml": _glossary("c", {"amplification": "gain"}, ["a"]),
    }
    assert _issues(_consumer(tmp_path, records)) == [
        ("form-collision", "glossary-c.yml", "/terms/amplification")
    ]


def test_template_of_an_overlay_causing_a_collision_is_reported_at_the_overlay(
    tmp_path: Path,
) -> None:
    notation = _with(NOTATION, ["entries", "lam", "body"], "\\mathbf{W}")
    overlay = {
        "_schema": "onomasia:overlay@1",
        "id": "slides",
        "overlays": "mixture",
        "classes": {"matrix": {"template": "\\mathbf{{{base}}}"}},
    }
    records = dict(CLEAN, **{"projects/p/notation.yml": notation, "overlay.yml": overlay})
    collisions = [
        issue for issue in _issues(_consumer(tmp_path, records)) if issue[0] != "undeclared-entry"
    ]
    assert collisions == [("body-collision", "overlay.yml", "/overlays")]


def test_consumer_turns_a_check_off(tmp_path: Path) -> None:
    configuration = dict(CONFIGURATION, checks={"undeclared-entry": "off"})
    assert _issues(_consumer(tmp_path, CLEAN, configuration)) == []


def test_bare_off_turns_a_check_off(tmp_path: Path) -> None:
    root = _consumer(tmp_path, CLEAN)
    text = (root / "onomasia.yml").read_text(encoding="utf-8")
    (root / "onomasia.yml").write_text(
        text + "checks:\n  undeclared-entry: off\n", encoding="utf-8"
    )
    assert _issues(root) == []


def test_overlay_changes_only_bodies_and_classes(tmp_path: Path) -> None:
    overlay = _with(OVERLAY, ["entries", "w-ff"], {"name": "V"})
    issues = _issues(_consumer(tmp_path, dict(CLEAN, **{"projects/p/overlay-poster.yml": overlay})))
    assert ("schema-violation", "projects/p/overlay-poster.yml", "/entries/w-ff") in issues


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema_version": 2}, "schema_version"),
        ({"checks": {"absent-check": "off"}}, "absent-check: unknown key"),
        ({"checks": {"form-collision": "loud"}}, "expected error, warning or off"),
        ({"records": {"lexicons": ["*.yml"]}}, "records.lexicons: unknown key"),
    ],
)
def test_invalid_configuration_is_rejected(tmp_path: Path, change: dict, message: str) -> None:
    root = _consumer(tmp_path, {}, dict(CONFIGURATION, **change))
    with pytest.raises(ConfigurationError, match=message):
        load_configuration(root, root / "onomasia.yml")


def test_default_severities_cover_every_check() -> None:
    assert all(isinstance(severity, Severity) for severity in default_severities().values())


def test_a_consumer_supplies_records_through_its_own_source(tmp_path: Path) -> None:
    """The port admits a source other than files, such as records held in memory."""
    from onomasia import RawDocument, RecordKind, default_configuration

    class InMemory:
        def documents(self):  # type: ignore[no-untyped-def]
            text = yaml.safe_dump(_without_none(_with(NOTATION, ["entries", "lam", "gloss"], None)))
            yield RawDocument("memory/notation.yml", text, RecordKind.NOTATION)

    issues = check_records(default_configuration(tmp_path), InMemory())
    assert [(issue.check, issue.pointer) for issue in issues] == [("missing-gloss", "/entries/lam")]


def test_cli_exits_with_the_status_of_the_issues(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from onomasia.cli import app

    root = _consumer(tmp_path, CLEAN)
    assert CliRunner().invoke(app, ["check", "--root", str(root)]).exit_code == 0
    planted = dict(CLEAN, **{"projects/p/glossary.yml": "terms: [unclosed"})
    result = CliRunner().invoke(app, ["check", "--root", str(_consumer(tmp_path, planted))])
    assert result.exit_code == 1 and "invalid-yaml" in result.output
    missing = CliRunner().invoke(app, ["check", "--root", str(tmp_path / "absent")])
    assert missing.exit_code == 2
