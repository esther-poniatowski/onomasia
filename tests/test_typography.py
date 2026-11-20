"""
Tests of the macro table, its serializations and the contract documents written by the build.

One consumer exercises every feature: a class template, an entry argument, an operator with a
binder, an operator taking a list, an overlay, and the six products. Each planted defect expects exactly
the issue of its check, and a build reporting an error writes nothing.
"""

from collections.abc import Sequence
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from onomasia.configuration import load_configuration
from onomasia.contracts import CONTRACT_SCHEMAS, MACRO_LOOKUP, MACRO_TABLE, TERM_TABLE
from onomasia.provenance import Source
from onomasia.records.validation import SchemaValidator
from onomasia.service import build_outputs, check_records

SOURCE = Source("https://example.org/vault.git", "0123456789abcdef0123456789abcdef01234567", False)


class FixedProvenance:
    """Provenance of a test consumer, read from no repository."""

    def sources(self, root: Path, files: Sequence[Path]) -> tuple[Source, ...]:
        """Return the fixed source."""
        del root, files
        return (SOURCE,)


MANIFEST = "_schema: anagraphe:repository@1\nrepository:\n  id: vault\n"
"""Manifest of the consumer, whose identifier normalizes the targets of its notation."""


def _unit(unit: str) -> dict[str, str]:
    """Write the target of a unit of the model record of the consumer, without its repository."""
    return {"id": "mixture-model", "unit": unit}


def _normalized(unit: str) -> dict[str, str]:
    """Write the normalized target of a unit of the model record of the consumer."""
    return {"repository": "vault", **_unit(unit)}


NOTATION = {
    "_schema": "onomasia:notation@2",
    "id": "mixture",
    "classes": {"matrix": {"template": "\\boldsymbol{{{base}}}"}},
    "entries": {
        "w-ff": {"denotes": _unit("weights"), "base": "W", "class": "matrix"},
        "w-entry": {"denotes": _unit("weight-entry"), "body": "W_{#1}", "entry": True},
        "sum-op": {"denotes": _unit("sum"), "body": "\\sum_{#1} #2"},
        "set-of": {"denotes": _unit("set"), "body": "\\{#1\\}", "separator": ","},
        "lam": {"gloss": "a free parameter", "body": "\\lambda", "name": "lam"},
    },
}

OVERLAY = {
    "_schema": "onomasia:overlay@1",
    "id": "poster",
    "overlays": "mixture",
    "classes": {"matrix": {"template": "\\mathbf{{{base}}}"}},
    "entries": {"w-ff": {"base": "V"}},
}

GLOSSARY = {
    "_schema": "onomasia:glossary@1",
    "id": "base",
    "terms": {
        "gain": {"label": "gain", "gloss": "a factor scaling a response", "forms": ["gains"]}
    },
}

TARGETS = {
    "_schema": "onomasia:denotes-targets@3",
    "sources": [],
    "targets": [
        {"target": _normalized("sum"), "arguments": 2, "bound": 1},
        {"target": _normalized("set"), "arguments": 1, "list": 1},
    ],
}

OUTPUTS = [
    {
        "product": "macro-table",
        "notations": ["mixture"],
        "overlays": ["poster"],
        "path": "out/table.yml",
    },
    {"product": "macro-lookup", "notations": ["mixture"], "path": "out/lookup.yml"},
    {"product": "term-table", "glossary": "base", "path": "out/terms.yml"},
    {"product": "latex-package", "notations": ["mixture"], "path": "out/mixture.sty"},
    {"product": "mathjax-preamble", "notations": ["mixture"], "path": "out/preamble.sty"},
    {
        "product": "python-expander",
        "notations": ["mixture"],
        "overlays": ["poster"],
        "path": "out/poster_notation.py",
    },
]


def _consumer(
    tmp_path: Path, records: dict[str, object], outputs: list[dict] | None = None
) -> Path:
    """Write a consumer with its records, its denotes targets and its outputs."""
    configuration = {
        "_schema": "onomasia:configuration@1",
        "records": {
            "glossaries": ["glossary.yml"],
            "notations": ["notation.yml"],
            "overlays": ["overlay.yml"],
        },
        "build": {
            "denotes_targets": ["targets.yml"],
            "outputs": outputs if outputs is not None else OUTPUTS,
        },
    }
    (tmp_path / "onomasia.yml").write_text(yaml.safe_dump(configuration), encoding="utf-8")
    files = {
        "repository.yml": MANIFEST,
        "glossary.yml": GLOSSARY,
        "notation.yml": NOTATION,
        "overlay.yml": OVERLAY,
        "targets.yml": TARGETS,
    }
    files.update(records)
    for name, data in files.items():
        (tmp_path / name).write_text(
            data if isinstance(data, str) else yaml.safe_dump(data), encoding="utf-8"
        )
    return tmp_path


def _build(root: Path):  # type: ignore[no-untyped-def]
    """Build the outputs of a consumer under the fixed provenance."""
    return build_outputs(
        load_configuration(root, root / "onomasia.yml"), provenance=FixedProvenance()
    )


def _expander(path: Path):  # type: ignore[no-untyped-def]
    """Import a generated expander from its file."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_writes_every_output(tmp_path: Path) -> None:
    result = _build(_consumer(tmp_path, {}))
    assert [(issue.check, issue.pointer) for issue in result.issues] == [
        ("undeclared-entry", "/entries/lam")
    ]
    assert sorted(path.name for path in result.written) == sorted(
        Path(output["path"]).name for output in OUTPUTS
    )


@pytest.mark.parametrize(
    ("path", "contract"),
    [("table.yml", MACRO_TABLE), ("lookup.yml", MACRO_LOOKUP), ("terms.yml", TERM_TABLE)],
)
def test_documents_follow_their_contracts(tmp_path: Path, path: str, contract: str) -> None:
    root = _consumer(tmp_path, {})
    _build(root)
    data = yaml.safe_load((root / "out" / path).read_text(encoding="utf-8"))
    assert list(SchemaValidator().contract_errors(CONTRACT_SCHEMAS[contract], data)) == []
    assert data["_schema"] == contract and data["sources"] == [SOURCE.to_data()]


@pytest.mark.skipif(shutil.which("git") is None, reason="the command git is absent")
def test_sources_of_a_build_publish_no_user_information(tmp_path: Path) -> None:
    """A build reading its Git repository writes the remote without its user and its token."""
    root = _consumer(tmp_path, {})
    identity = ["-c", "user.name=Test", "-c", "user.email=test@example.org"]
    for arguments in (
        ["init", "--quiet"],
        ["remote", "add", "origin", "https://user:secret-token@example.org/vault.git"],
        ["add", "."],
        [*identity, "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "records"],
    ):
        subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)
    result = build_outputs(load_configuration(root, root / "onomasia.yml"))
    assert result.written
    data = yaml.safe_load((root / "out" / "table.yml").read_text(encoding="utf-8"))
    [source] = data["sources"]
    assert source["repository"] == "https://example.org/vault.git"
    leaked = [path.name for path in result.written if "secret-token" in path.read_text()]
    assert leaked == []


def test_term_table_writes_described_forms_without_their_descriptions(tmp_path: Path) -> None:
    glossary = yaml.safe_load(yaml.safe_dump(GLOSSARY))
    glossary["terms"]["gain"]["forms"] = [
        "gains",
        {"literal": "gain factor", "description": "a compound"},
        {"regex": "gains? of", "description": "a construction"},
    ]
    root = _consumer(tmp_path, {"glossary.yml": glossary})
    _build(root)
    data = yaml.safe_load((root / "out" / "terms.yml").read_text(encoding="utf-8"))
    assert list(SchemaValidator().contract_errors(CONTRACT_SCHEMAS[TERM_TABLE], data)) == []
    assert data["terms"][0]["forms"] == ["gain", "gains", "gain factor", {"regex": "gains? of"}]


def test_macro_table_takes_arguments_from_the_targets(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {})
    _build(root)
    entries = {
        entry["id"]: entry
        for entry in yaml.safe_load((root / "out" / "table.yml").read_text())["entries"]
    }
    assert (entries["sum-op"]["arity"], entries["sum-op"]["binder"]) == (2, 1)
    assert (entries["set-of"]["arity"], entries["set-of"]["separator"]) == (1, ",")
    assert (entries["set-of"]["list"], entries["sum-op"]["list"]) == (1, None)
    assert (entries["w-entry"]["arity"], entries["w-entry"]["entry"]) == (0, True)
    assert entries["w-ff"]["body"] == "\\mathbf{V}" and entries["w-ff"]["name"] == "onowFf"


def test_lookup_names_each_declared_unit(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {})
    _build(root)
    targets = yaml.safe_load((root / "out" / "lookup.yml").read_text())["targets"]
    assert targets == [
        {"target": _normalized("set"), "name": "onosetOf"},
        {"target": _normalized("sum"), "name": "onosumOp"},
        {"target": _normalized("weight-entry"), "name": "onowEntry"},
        {"target": _normalized("weights"), "name": "onowFf"},
    ]


def test_macro_table_writes_the_normalized_target_or_null(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {})
    _build(root)
    entries = {
        entry["id"]: entry["target"]
        for entry in yaml.safe_load((root / "out" / "table.yml").read_text())["entries"]
    }
    assert entries["w-ff"] == _normalized("weights") and entries["lam"] is None


def test_denotes_target_without_repository_names_a_unit_of_the_consumer(tmp_path: Path) -> None:
    """A denotes target without repository is normalized by the repository of the consumer, so it
    matches the unit of an entry."""
    targets = dict(TARGETS, targets=[{"target": _unit("sum"), "arguments": 2, "bound": 1}])
    root = _consumer(tmp_path, {"targets.yml": targets})
    _build(root)
    entries = {
        entry["id"]: entry
        for entry in yaml.safe_load((root / "out" / "table.yml").read_text())["entries"]
    }
    assert (entries["sum-op"]["arity"], entries["sum-op"]["binder"]) == (2, 1)


def test_target_with_its_repository_written_matches_the_same_unit(tmp_path: Path) -> None:
    """A target written with the repository of the consumer and one written without it are one
    normalized target, so both match one unit of the denotes targets, and they collide."""
    notation = _notation(**{"sum-op": {"denotes": _normalized("sum"), "body": "\\sum_{#1} #2"}})
    root = _consumer(tmp_path, {"notation.yml": notation})
    _build(root)
    entries = {
        entry["id"]: entry
        for entry in yaml.safe_load((root / "out" / "table.yml").read_text())["entries"]
    }
    assert (entries["sum-op"]["arity"], entries["sum-op"]["binder"]) == (2, 1)
    clash = _notation(other={"denotes": _normalized("weights"), "body": "o"})
    issues = _build(_consumer(tmp_path, {"notation.yml": clash})).issues
    assert ("ambiguous-target", "/entries/w-ff") in {
        (issue.check, issue.pointer) for issue in issues
    }


def test_latex_package_defines_each_macro_once(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {})
    _build(root)
    lines = (root / "out" / "mixture.sty").read_text(encoding="utf-8").splitlines()
    assert lines[1:3] == ["\\NeedsTeXFormat{LaTeX2e}", "\\ProvidesPackage{mixture}"]
    assert lines[3:] == [
        "\\newcommand{\\lam}{\\lambda}",
        "\\newcommand{\\onosetOf}[1]{\\{#1\\}}",
        "\\newcommand{\\onosumOp}[2]{\\sum_{#1} #2}",
        "\\newcommand{\\onowEntry}[1][]{W_{#1}}",
        "\\newcommand{\\onowFf}{\\boldsymbol{W}}",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\\onowFf", "\\mathbf{V}"),
        ("\\onowEntry[ij] + \\lam", "W_{ij} + \\lambda"),
        ("\\onowEntry + 1", "W_{} + 1"),
        ("\\onosumOp{i}{x_i}", "\\sum_{i} x_i"),
        ("\\onosumOp i x", "\\sum_{i} x"),
        ("\\onosetOf{a, b}", "\\{a, b\\}"),
        ("\\alpha\\lam", "\\alpha\\lambda"),
    ],
)
def test_generated_expander_expands_the_macros(tmp_path: Path, text: str, expected: str) -> None:
    root = _consumer(tmp_path, {})
    _build(root)
    assert _expander(root / "out" / "poster_notation.py").expand(text) == expected


def _notation(**entries: object) -> dict:
    """Copy the notation, replacing or adding entries."""
    copy = yaml.safe_load(yaml.safe_dump(NOTATION))
    copy["entries"].update(entries)
    return copy


PLANTED = {
    "reserved-prefix": (
        {"notation.yml": _notation(lam={"gloss": "g", "body": "\\lambda", "name": "onoLam"})},
        "/entries/lam",
    ),
    "macro-name-collision": (
        {"notation.yml": _notation(mu={"gloss": "g", "body": "\\mu", "name": "lam"})},
        "/entries/mu",
    ),
    "ambiguous-target": (
        {"notation.yml": _notation(v={"denotes": _unit("weights"), "body": "v"})},
        "/entries/w-ff",
    ),
    "too-many-parameters": (
        {
            "targets.yml": dict(
                TARGETS, targets=[{"target": _normalized("weight-entry"), "arguments": 9}]
            )
        },
        "/entries/w-entry",
    ),
    "missing-separator": (
        {"notation.yml": _notation(**{"set-of": {"denotes": _unit("set"), "body": "\\{#1\\}"}})},
        "/entries/set-of",
    ),
    "unnormalized-target": ({"repository.yml": "no: manifest\n"}, "/entries/w-ff/denotes"),
    "macro-cycle": (
        {
            "notation.yml": _notation(
                a={"gloss": "g", "body": "\\onob", "name": "onoa"},
                b={"gloss": "g", "body": "\\onoa"},
            )
        },
        "/entries/b",
    ),
    "invalid-contract": ({"targets.yml": dict(TARGETS, sources="none")}, "/sources"),
    "invalid-item": (
        {"targets.yml": dict(TARGETS, targets=[{"target": _normalized("x"), "arguments": "two"}])},
        "/targets/0/arguments",
    ),
}


@pytest.mark.parametrize("check", sorted(PLANTED))
def test_planted_defect_is_reported_and_nothing_is_written(tmp_path: Path, check: str) -> None:
    records, pointer = PLANTED[check]
    result = _build(_consumer(tmp_path, records))
    assert check in {issue.check for issue in result.issues if issue.pointer == pointer}
    assert result.written == ()
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("check", sorted(PLANTED))
def test_check_reports_the_defects_of_a_build_and_writes_nothing(
    tmp_path: Path, check: str
) -> None:
    records, pointer = PLANTED[check]
    root = _consumer(tmp_path, records)
    issues = check_records(load_configuration(root, root / "onomasia.yml"))
    assert check in {issue.check for issue in issues if issue.pointer == pointer}
    assert issues == _build(root).issues
    assert not (root / "out").exists()


def test_output_naming_an_absent_notation_is_reported(tmp_path: Path) -> None:
    outputs = [{"product": "latex-package", "notations": ["absent"], "path": "out/x.sty"}]
    result = _build(_consumer(tmp_path, {}, outputs))
    assert [
        (issue.check, issue.pointer)
        for issue in result.issues
        if issue.check == "unresolved-output"
    ] == [("unresolved-output", "/build/outputs/0/notations")]
    assert result.written == ()


UNRESOLVED_OUTPUT = "unresolved-output"
"""Check planted by `test_output_naming_an_absent_notation_is_reported`."""


def test_unresolved_output_is_reported_at_the_configuration_read(tmp_path: Path) -> None:
    outputs = [{"product": "latex-package", "notations": ["absent"], "path": "out/x.sty"}]
    root = _consumer(tmp_path, {}, outputs)
    (root / "config").mkdir()
    (root / "onomasia.yml").rename(root / "config" / "onomasia-ci.yml")
    configuration = load_configuration(root, root / "config" / "onomasia-ci.yml")
    result = build_outputs(configuration, provenance=FixedProvenance())
    assert [
        (issue.resource, issue.pointer)
        for issue in result.issues
        if issue.check == UNRESOLVED_OUTPUT
    ] == [("config/onomasia-ci.yml", "/build/outputs/0/notations")]


def _macros(root: Path) -> dict[str, dict[str, object]]:
    """The entries of the macro table written by a build, by identifier."""
    return {
        entry["id"]: entry
        for entry in yaml.safe_load((root / "out" / "table.yml").read_text())["entries"]
    }


def test_a_unit_binding_a_variable_over_a_list_takes_both_arguments(tmp_path: Path) -> None:
    """The arguments of a unit are its domain facts: a unit binding a variable over a list takes
    two arguments, one for the variable and one for the list, whose items the separator joins."""
    targets = dict(
        TARGETS,
        targets=[
            {"target": _normalized("sum"), "arguments": 2, "bound": 1},
            {"target": _normalized("set"), "arguments": 2, "bound": 1, "list": 2},
        ],
    )
    notation = _notation(
        **{"set-of": {"denotes": _unit("set"), "body": "\\{#1 : #2\\}", "separator": ","}}
    )
    root = _consumer(tmp_path, {"targets.yml": targets, "notation.yml": notation})
    _build(root)
    entry = _macros(root)["set-of"]
    assert (entry["arity"], entry["binder"], entry["list"]) == (2, 1, 2)


def test_an_invalid_item_is_skipped_and_the_others_stay(tmp_path: Path) -> None:
    """An invalid item of the denotes targets is reported alone; the valid items still give their
    arguments, so one defect does not discard the whole document."""
    targets = dict(
        TARGETS,
        targets=[
            {"target": _normalized("sum"), "arguments": 2, "bound": 1},
            {"target": _normalized("set"), "arguments": 1, "list": 3},
        ],
    )
    result = _build(_consumer(tmp_path, {"targets.yml": targets}))
    assert [
        (issue.check, issue.pointer) for issue in result.issues if issue.check == "invalid-item"
    ] == [("invalid-item", "/targets/1/list")]
    root = _consumer(tmp_path, {"targets.yml": dict(TARGETS, targets=[targets["targets"][0]])})
    _build(root)
    assert _macros(root)["sum-op"]["arity"] == 2


def test_a_slot_shared_by_the_variable_and_the_list_is_invalid(tmp_path: Path) -> None:
    targets = dict(
        TARGETS, targets=[{"target": _normalized("set"), "arguments": 1, "bound": 1, "list": 1}]
    )
    result = _build(_consumer(tmp_path, {"targets.yml": targets}))
    assert ("invalid-item", "/targets/0/list") in {
        (issue.check, issue.pointer) for issue in result.issues
    }


def test_a_document_binding_its_contract_under_contract_is_skipped(tmp_path: Path) -> None:
    """A document binds its contract under `_schema`; the former key `contract` breaks the header."""
    targets = {"contract" if key == "_schema" else key: value for key, value in TARGETS.items()}
    result = _build(_consumer(tmp_path, {"targets.yml": targets}))
    assert {""} == {issue.pointer for issue in result.issues if issue.check == "invalid-contract"}


def test_the_source_is_dirty_only_when_a_file_read_leaves_the_commit(tmp_path: Path) -> None:
    """A build in a repository marks its source dirty when a record that it read changed, and
    leaves it clean when another file changed, its own outputs included."""
    root = _consumer(tmp_path, {})
    identity = ["-c", "user.name=Test", "-c", "user.email=test@example.org"]
    for arguments in (
        ["init", "-q"],
        ["add", "--all"],
        [*identity, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "records"],
    ):
        subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)
    configuration = load_configuration(root, root / "onomasia.yml")

    def dirty() -> bool:
        build_outputs(configuration)
        table = yaml.safe_load((root / "out" / "table.yml").read_text(encoding="utf-8"))
        return bool(table["sources"][0]["dirty"])

    assert not dirty()
    (root / "notes.md").write_text("draft\n", encoding="utf-8")
    assert not dirty()
    with (root / "notation.yml").open("a", encoding="utf-8") as handle:
        handle.write("# changed\n")
    assert dirty()
