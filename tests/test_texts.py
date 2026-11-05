"""
Tests of the checks of texts against the glossaries, the notations and the audiences bound to them.

One consumer binds its notes through the index of their folder, resolved by Anagraphe, and one
note writes every construct that a check reports, one or two per line. Each planted defect of a
record or a binding expects exactly the issue of its check.
"""

from pathlib import Path

import pytest
import yaml

from onomasia.configuration import load_configuration
from onomasia.errors import ConfigurationError
from onomasia.service import check_records

ANAGRAPHE = {
    "schema_version": 2,
    "bindings": {
        "index": "_index.md",
        "roles": {
            "onomasia.glossary": {"key": "glossary"},
            "onomasia.notation": {"key": "notation"},
            "onomasia.audiences": {"key": "audiences"},
        },
    },
}

CONFIGURATION = {
    "schema_version": 1,
    "records": {
        "glossaries": ["records/*.glossary.yml"],
        "notations": ["records/*.notation.yml"],
    },
    "texts": {"anagraphe": "anagraphe.yml", "paths": ["notes/**/*.md"]},
    "checks": {"undeclared-entry": "off"},
}


def _rule(forms: list[str], **fields: object) -> dict:
    """Write a lexical rule forbidding forms, with an instruction as its replacement."""
    return {"forms": forms, "replace_with": [{"instruction": "rephrase"}], "reason": "r", **fields}


GLOSSARY = {
    "_schema": "onomasia:glossary@1",
    "id": "base",
    "terms": {
        "gain": {"label": "gain", "gloss": "g", "frames": ["~ of {input|stimulus} [in {}]"]},
        "input": {"label": "input", "gloss": "g"},
        "stimulus": {"label": "stimulus", "gloss": "g"},
        "old-word": {
            "label": "oldword",
            "gloss": "g",
            "status": "deprecated",
            "replaced_by": "gain",
        },
        "draft-word": {"label": "draftword", "gloss": "g", "status": "candidate"},
    },
    "rules": {
        "no-regime": _rule(["regime"], exceptions=["learning regime"]),
        "ml-only": _rule(["neural code"], audiences=["ml"]),
        "physics-only": _rule(["field"], audiences=["physics"]),
        "soft": _rule(["population"], severity="warning"),
        "draft-rule": _rule(["proposedban"], status="candidate"),
        "retired-rule": _rule(["retired"], status="deprecated"),
    },
}

NOTATION = {
    "_schema": "onomasia:notation@1",
    "id": "base",
    "classes": {"matrix": {"template": "\\boldsymbol{{{base}}}"}},
    "entries": {
        "w": {"gloss": "g", "base": "W", "class": "matrix", "name": "Wm"},
        "old-x": {
            "gloss": "g",
            "body": "x_{\\mathrm{old}}",
            "status": "deprecated",
            "replaced_by": "w",
        },
    },
}

NOTE = """---
title: a
---
The gain of the input in V1 is stable.
The gain drifts.
A learning regime differs from a regime.
The neural code of the gain of a stimulus.
A field and a population.
An oldword, a draftword, a proposedban, a retired form.
A `regime` in code and $regime$ in mathematics.
Math: $\\onooldX + \\Wm + \\onomissing + \\boldsymbol{W}$.
"""

FILES: dict[str, object] = {
    "anagraphe.yml": ANAGRAPHE,
    "onomasia.yml": CONFIGURATION,
    "records/base.glossary.yml": GLOSSARY,
    "records/base.notation.yml": NOTATION,
    "notes/_index.md": "---\nglossary: base\nnotation: base\naudiences: [ml]\n---\n# Notes\n",
    "notes/a.md": NOTE,
}

TEXT_CHECKS = {
    "forbidden-form",
    "frame-mismatch",
    "term-status",
    "entry-status",
    "unknown-macro",
    "raw-printed-form",
}
"""Checks reported by the clean consumer itself, so that its test shows them firing."""


def _consumer(root: Path, files: dict[str, object] | None = None) -> Path:
    """Write the consumer, with some files replaced."""
    for relative, content in {**FILES, **(files or {})}.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            text = content if isinstance(content, str) else yaml.safe_dump(content)
            path.write_text(text, encoding="utf-8")
    return root


def _issues(root: Path) -> list[tuple[str, int | None, str, str, str]]:
    """Return each issue as (resource, line, check, severity, pointer)."""
    configuration = load_configuration(root, root / "onomasia.yml")
    return [
        (issue.resource, issue.line, issue.check, issue.severity.value, issue.pointer)
        for issue in check_records(configuration)
    ]


def test_note_reports_each_construct_at_its_line(tmp_path: Path) -> None:
    issues = [issue[1:4] for issue in _issues(_consumer(tmp_path)) if issue[0] == "notes/a.md"]
    assert sorted(issues) == [
        (5, "frame-mismatch", "warning"),
        (6, "forbidden-form", "error"),
        (7, "forbidden-form", "error"),
        (8, "forbidden-form", "warning"),
        (9, "forbidden-form", "warning"),
        (9, "term-status", "error"),
        (9, "term-status", "warning"),
        (11, "entry-status", "error"),
        (11, "raw-printed-form", "warning"),
        (11, "unknown-macro", "error"),
    ]


def test_note_without_binding_is_not_checked(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"notes/_index.md": "# Notes\n"})
    assert [issue for issue in _issues(root) if issue[0] == "notes/a.md"] == []


def test_scope_table_extends_the_audiences_of_a_text(tmp_path: Path) -> None:
    table = {
        "contract": "onomasia:scope-table@1",
        "sources": [],
        "audiences": {"ml": {"ancestors": ["physics"], "descendants": []}},
    }
    configuration = {
        **CONFIGURATION,
        "texts": {**CONFIGURATION["texts"], "scope_table": "scope.yml"},
    }
    root = _consumer(tmp_path, {"scope.yml": table, "onomasia.yml": configuration})
    lines = [issue[1] for issue in _issues(root) if issue[2] == "forbidden-form"]
    assert lines.count(8) == 2


@pytest.mark.parametrize(
    ("frame", "text", "admitted"),
    [
        ("[the] ~", "The gain rises.", True),
        ("~ of {}", "The gain of noise.", True),
        ("~ of {input}", "The gain of the noisy input.", False),
        ("~ of {input}", "The gain of\nthe input.", True),
        ("~ of {input}", "The gain of\n\nthe input.", False),
    ],
)
def test_frame_admits_its_constructions(
    tmp_path: Path, frame: str, text: str, admitted: bool
) -> None:
    glossary = yaml.safe_load(yaml.safe_dump(GLOSSARY))
    glossary["terms"]["gain"]["frames"] = [frame]
    root = _consumer(tmp_path, {"records/base.glossary.yml": glossary, "notes/a.md": text})
    mismatches = [issue for issue in _issues(root) if issue[2] == "frame-mismatch"]
    assert (mismatches == []) is admitted


def _glossary(**terms: object) -> dict:
    """Copy the glossary, replacing or adding terms."""
    copy = yaml.safe_load(yaml.safe_dump(GLOSSARY))
    copy["terms"].update(terms)
    return copy


PLANTED = {
    "invalid-frame": (
        {
            "records/base.glossary.yml": _glossary(
                twice={"label": "twice", "gloss": "g", "frames": ["~ ~"]}
            )
        },
        ("records/base.glossary.yml", None, "invalid-frame", "error", "/terms/twice/frames/0"),
    ),
    "invalid-form": (
        {
            "records/base.glossary.yml": _glossary(
                flag={"label": "flag", "gloss": "g", "forms": [{"regex": "(?P<t>flag)"}]}
            )
        },
        ("records/base.glossary.yml", None, "invalid-form", "error", "/terms/flag/forms/0/regex"),
    ),
    "unresolved-text-binding": (
        {"notes/_index.md": "---\nglossary: absent\n---\n# Notes\n"},
        ("notes/_index.md", None, "unresolved-text-binding", "error", "/glossary"),
    ),
    "unreadable-text": (
        {"notes/b.md": b"\xff\xfe not utf-8"},
        ("notes/b.md", None, "unreadable-text", "error", ""),
    ),
}


@pytest.mark.parametrize("check", sorted(PLANTED))
def test_planted_defect_is_reported(tmp_path: Path, check: str) -> None:
    files, expected = PLANTED[check]
    assert expected in _issues(_consumer(tmp_path, files))


def test_frame_naming_an_absent_term_is_reported(tmp_path: Path) -> None:
    glossary = _glossary(gap={"label": "gap", "gloss": "g", "frames": ["~ of {absent}"]})
    root = _consumer(tmp_path, {"records/base.glossary.yml": glossary})
    assert (
        "records/base.glossary.yml",
        None,
        "invalid-frame",
        "error",
        "/terms/gap/frames/0",
    ) in _issues(root)


def _messages(root: Path) -> list[str]:
    """Return the message of each issue of the texts, in order."""
    configuration = load_configuration(root, root / "onomasia.yml")
    return [issue.message for issue in check_records(configuration) if issue.line is not None]


def test_messages_name_the_replacements(tmp_path: Path) -> None:
    messages = _messages(_consumer(tmp_path))
    assert any("'oldword' is the term old-word" in m and m.endswith("write gain") for m in messages)
    assert any(
        m.startswith("\\onooldX prints the entry old-x") and m.endswith("write \\Wm")
        for m in messages
    )
    assert any(
        "'regime' is forbidden by no-regime" in m and "write rephrase" in m for m in messages
    )


def test_described_forms_match_and_conditions_reach_the_advice(tmp_path: Path) -> None:
    glossary = yaml.safe_load(yaml.safe_dump(GLOSSARY))
    glossary["rules"] = {
        "no-curve": {
            "forms": [{"literal": "tuning curve", "description": "the compound"}],
            "replace_with": [
                {"term": "gain", "condition": "in the sense of a scaling"},
                {"instruction": "write response profile", "condition": "for a profile"},
            ],
            "reason": "r",
            "exceptions": [
                {"literal": "tuning curve shape", "description": "the shape of a figure"},
                {"regex": "tuning curves? of V1", "description": "a recorded curve"},
            ],
        }
    }
    text = "A tuning curve.\nA tuning curve shape.\nA tuning curve of V1.\n"
    root = _consumer(tmp_path, {"records/base.glossary.yml": glossary, "notes/a.md": text})
    found = [m for m in _messages(root) if "forbidden by no-curve" in m]
    assert len(found) == 1
    assert "write gain (in the sense of a scaling) or write response profile (for a profile)" in (
        found[0]
    )


def _text(tmp_path: Path, text: str, **glossary_terms: object) -> list[tuple[int | None, str]]:
    """Check one note against the glossary, terms replaced or added, returning (line, check)."""
    files: dict[str, object] = {"notes/a.md": text}
    if glossary_terms:
        files["records/base.glossary.yml"] = _glossary(**glossary_terms)
    return [
        (issue[1], issue[2])
        for issue in _issues(_consumer(tmp_path, files))
        if issue[0] == "notes/a.md"
    ]


@pytest.mark.parametrize(
    ("text", "reported"),
    [
        ("A tuning curve.", True),
        ("A tuning\ncurve.", True),
        ("> [!NOTE] Title\n> a tuning\n> curve\n", True),
        ("A tuning $x$ curve.", False),
        ("A tuning `x` curve.", False),
        ("A tuning-curve shape.", False),
        ("A tuning\u00a0curve.", True),
        ("See [[tuning curve]].", True),
        ("See [[notes|tuning curve]] and [x](tuning curve).", True),
        ("See [x](<tuning curve>).", False),
    ],
)
def test_form_matches_in_prose_only(tmp_path: Path, text: str, reported: bool) -> None:
    glossary = yaml.safe_load(yaml.safe_dump(GLOSSARY))
    glossary["rules"] = {"no-curve": _rule(["tuning curve"])}
    root = _consumer(tmp_path, {"records/base.glossary.yml": glossary, "notes/a.md": text})
    found = [issue for issue in _issues(root) if issue[2] == "forbidden-form"]
    assert bool(found) is reported


def test_callout_marker_is_no_prose(tmp_path: Path) -> None:
    glossary = yaml.safe_load(yaml.safe_dump(GLOSSARY))
    glossary["rules"] = {"no-note": _rule(["note"])}
    text = "> [!note]- Title\n> body\n\nA note.\n"
    root = _consumer(tmp_path, {"records/base.glossary.yml": glossary, "notes/a.md": text})
    assert [issue[1] for issue in _issues(root) if issue[2] == "forbidden-form"] == [4]


def test_scoped_rule_binds_no_text_without_audiences(tmp_path: Path) -> None:
    index = "---\nglossary: base\nnotation: base\n---\n"
    root = _consumer(tmp_path, {"notes/_index.md": index, "notes/a.md": "The neural code.\n"})
    assert [issue for issue in _issues(root) if issue[2] == "forbidden-form"] == []


@pytest.mark.parametrize(
    ("rule", "text", "count"),
    [
        (_rule(["Gain"], case_sensitive=True), "gain and Gain.", 1),
        (_rule([{"regex": "gains?"}]), "Gain and gains.", 2),
        (
            _rule(["population"], exceptions=[{"regex": "(?i)population code"}]),
            "A Population code.",
            0,
        ),
    ],
)
def test_rule_matches_its_case_and_its_expressions(
    tmp_path: Path, rule: dict, text: str, count: int
) -> None:
    glossary = yaml.safe_load(yaml.safe_dump(GLOSSARY))
    glossary["rules"] = {"probe": rule}
    root = _consumer(tmp_path, {"records/base.glossary.yml": glossary, "notes/a.md": text})
    assert len([issue for issue in _issues(root) if issue[2] == "forbidden-form"]) == count


def test_expression_matching_the_empty_string_is_rejected_and_not_matched(tmp_path: Path) -> None:
    glossary = yaml.safe_load(yaml.safe_dump(GLOSSARY))
    glossary["rules"] = {"probe": _rule([{"regex": "x*"}])}
    root = _consumer(tmp_path, {"records/base.glossary.yml": glossary, "notes/a.md": "Text.\n"})
    checks = [issue[2] for issue in _issues(root)]
    assert "invalid-form" in checks and "forbidden-form" not in checks


@pytest.mark.parametrize(
    ("frames", "forms", "text", "mismatches"),
    [
        (["neural ~"], [], "Neural gain rises.", 0),
        (["[the] ~ of {}"], [], "the gain of the gain of noise.", 0),
        (["{} ~"], [], "input gain gain.", 0),
        (["~ of {}"], ["gain field"], "The gain field of noise.", 0),
        (["~ of {}"], [], "The gain of the.", 1),
        (["~ ~"], [], "The gain rises.", 0),
        (["~ of {input} [[in] {}]"], [], "The gain of the input in V1.", 0),
    ],
)
def test_frames_admit_their_constructions(
    tmp_path: Path, frames: list[str], forms: list[str], text: str, mismatches: int
) -> None:
    term = {"label": "gain", "gloss": "g", "frames": frames, "forms": forms}
    found = _text(tmp_path, text, gain=term)
    assert len([check for _, check in found if check == "frame-mismatch"]) == mismatches


def test_slot_term_keeps_its_own_case(tmp_path: Path) -> None:
    gain = {"label": "gain", "gloss": "g", "frames": ["~ of {input}"]}
    term = {"label": "Input", "gloss": "g", "case_sensitive": True}
    found = _text(tmp_path, "The GAIN of the input. The gain of Input.", gain=gain, input=term)
    assert [check for _, check in found if check == "frame-mismatch"] == ["frame-mismatch"]


def test_unbalanced_brace_of_a_frame_is_reported(tmp_path: Path) -> None:
    glossary = _glossary(gain={"label": "gain", "gloss": "g", "frames": ["~ of {input"]})
    root = _consumer(tmp_path, {"records/base.glossary.yml": glossary})
    assert (
        "records/base.glossary.yml",
        None,
        "invalid-frame",
        "error",
        "/terms/gain/frames/0",
    ) in _issues(root)


def _notation(**entries: object) -> dict:
    """Copy the notation, replacing or adding entries."""
    copy = yaml.safe_load(yaml.safe_dump(NOTATION))
    copy["entries"].update(entries)
    return copy


def test_raw_bodies_report_the_longest_body_and_every_overload(tmp_path: Path) -> None:
    notation = _notation(
        wt={"gloss": "g", "body": "\\boldsymbol{W}_t", "name": "Wt"},
        mean={"gloss": "g", "body": "\\mu", "name": "mean", "overloads": ["measure"]},
        measure={"gloss": "g", "body": "\\mu", "name": "measure"},
        old={
            "gloss": "g",
            "body": "\\theta",
            "name": "oldtheta",
            "status": "deprecated",
            "replaced_by": "w",
        },
    )
    text = "Math: $\\boldsymbol{W}_t + \\mu + \\theta$.\n"
    root = _consumer(tmp_path, {"records/base.notation.yml": notation, "notes/a.md": text})
    messages = [m for m in _messages(root) if "printed form" in m]
    assert messages == [
        "'\\boldsymbol{W}_t' is the printed form of the macro \\Wt; call it",
        "'\\mu' is the printed form of the macro \\mean or \\measure; call it",
    ]


@pytest.mark.parametrize(
    ("texts", "message"),
    [
        ({"masked": ["code"]}, "unknown kinds"),
        ({"paths": ["../elsewhere/*.md"]}, "leaves the root"),
        ({"scope_table": "absent.yml"}, "names no file"),
    ],
)
def test_invalid_texts_section_is_rejected(tmp_path: Path, texts: dict, message: str) -> None:
    configuration = {**CONFIGURATION, "texts": {**CONFIGURATION["texts"], **texts}}
    root = _consumer(tmp_path, {"onomasia.yml": configuration})
    with pytest.raises(ConfigurationError, match=message):
        load_configuration(root, root / "onomasia.yml")


def test_status_declares_its_effect_on_texts(tmp_path: Path) -> None:
    vocabulary = {
        "statuses": {
            "in-use": {"requires_replacement": False},
            "deprecated": {
                "requires_replacement": True,
                "in_texts": {"term": "warning", "rule": "off"},
            },
            "candidate": {
                "requires_replacement": False,
                "in_texts": {"term": "off", "rule": "error"},
            },
        },
        "default_status": "in-use",
        "contexts": {},
        "relations": [],
    }
    root = _consumer(tmp_path, {"onomasia.yml": {**CONFIGURATION, "vocabulary": vocabulary}})
    found = sorted(
        (issue[1], issue[2], issue[3])
        for issue in _issues(root)
        if issue[0] == "notes/a.md" and issue[1] == 9
    )
    assert found == [(9, "forbidden-form", "error"), (9, "term-status", "warning")]


def test_invalid_severity_in_texts_is_rejected(tmp_path: Path) -> None:
    vocabulary = {
        "statuses": {"in-use": {"requires_replacement": False, "in_texts": {"term": "loud"}}},
        "default_status": "in-use",
        "contexts": {},
        "relations": [],
    }
    root = _consumer(tmp_path, {"onomasia.yml": {**CONFIGURATION, "vocabulary": vocabulary}})
    with pytest.raises(ConfigurationError, match="expected error, warning or off"):
        load_configuration(root, root / "onomasia.yml")
