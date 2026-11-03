"""
Tests of the macro table, its serializations and the contract documents written by the build.

One consumer exercises every feature: a class template, an entry argument, an operator with a
binder, a variadic operator, an overlay, and the six products. Each planted defect expects exactly
the issue of its check, and a build reporting an error writes nothing.
"""

import importlib.util
from pathlib import Path

import pytest
import yaml

from onomasia.configuration import load_configuration
from onomasia.contracts import CONTRACT_SCHEMAS, MACRO_LOOKUP, MACRO_TABLE, TERM_TABLE
from onomasia.provenance import Source
from onomasia.records.validation import SchemaValidator
from onomasia.service import build_outputs

SOURCE = Source("https://example.org/vault.git", "0123456789abcdef0123456789abcdef01234567", False)


class FixedProvenance:
    """Provenance of a test consumer, read from no repository."""

    def sources(self, root: Path) -> tuple[Source, ...]:
        """Return the fixed source."""
        del root
        return (SOURCE,)


NOTATION = {
    "_schema": "onomasia:notation@1",
    "id": "mixture",
    "classes": {"matrix": {"template": "\\boldsymbol{{{base}}}"}},
    "entries": {
        "w-ff": {"denotes": "mixture:weights", "base": "W", "class": "matrix"},
        "w-entry": {"denotes": "mixture:weight-entry", "body": "W_{#1}", "entry": True},
        "sum-op": {"denotes": "mixture:sum", "body": "\\sum_{#1} #2"},
        "set-of": {"denotes": "mixture:set", "body": "\\{#1\\}", "separator": ","},
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
    "contract": "onomasia:denotes-targets@1",
    "sources": [],
    "targets": [
        {"target": "mixture:sum", "arity": 2, "binder": 1},
        {"target": "mixture:set", "arity": 1, "variadic": True},
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
        "schema_version": 1,
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
    assert data["contract"] == contract and data["sources"] == [SOURCE.to_data()]


def test_macro_table_takes_arguments_from_the_targets(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {})
    _build(root)
    entries = {
        entry["id"]: entry
        for entry in yaml.safe_load((root / "out" / "table.yml").read_text())["entries"]
    }
    assert (entries["sum-op"]["arity"], entries["sum-op"]["binder"]) == (2, 1)
    assert (entries["set-of"]["arity"], entries["set-of"]["separator"]) == (1, ",")
    assert (entries["w-entry"]["arity"], entries["w-entry"]["entry"]) == (0, True)
    assert entries["w-ff"]["body"] == "\\mathbf{V}" and entries["w-ff"]["name"] == "onowFf"


def test_lookup_names_each_declared_unit(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {})
    _build(root)
    targets = yaml.safe_load((root / "out" / "lookup.yml").read_text())["targets"]
    assert targets == {
        "mixture:weights": "onowFf",
        "mixture:weight-entry": "onowEntry",
        "mixture:sum": "onosumOp",
        "mixture:set": "onosetOf",
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
        {"notation.yml": _notation(v={"denotes": "mixture:weights", "body": "v"})},
        "/entries/w-ff",
    ),
    "too-many-parameters": (
        {"targets.yml": dict(TARGETS, targets=[{"target": "mixture:weight-entry", "arity": 9}])},
        "/entries/w-entry",
    ),
    "missing-separator": (
        {"notation.yml": _notation(**{"set-of": {"denotes": "mixture:set", "body": "\\{#1\\}"}})},
        "/entries/set-of",
    ),
    "macro-cycle": (
        {
            "notation.yml": _notation(
                a={"gloss": "g", "body": "\\onob", "name": "onoa"},
                b={"gloss": "g", "body": "\\onoa"},
            )
        },
        "/entries/b",
    ),
    "invalid-contract": (
        {"targets.yml": dict(TARGETS, targets=[{"target": "x", "arity": "two"}])},
        "/targets/0/arity",
    ),
}


@pytest.mark.parametrize("check", sorted(PLANTED))
def test_planted_defect_is_reported_and_nothing_is_written(tmp_path: Path, check: str) -> None:
    records, pointer = PLANTED[check]
    result = _build(_consumer(tmp_path, records))
    assert check in {issue.check for issue in result.issues if issue.pointer == pointer}
    assert result.written == ()
    assert not (tmp_path / "out").exists()


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
