"""
Tests of the imports across repositories, and of the targets of the notations.

A consumer, `thesis`, imports glossaries and notations of two other repositories, `lexicon` and
`atlas`, whose states an in-memory provider of Anagraphe serves. The consumer declares both
repositories under `resolution.repositories`, and a schema registry holding the packaged schemas of
Onomasia, so that the resolver verifies the identifier and the contract of each record. The
composition of the glossary `project` is read from the term table that the build writes. Each
planted defect expects the issue of its check at the key `from` of the import that it concerns.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
import hashlib
from importlib import resources
from pathlib import Path
import shutil
import subprocess

from anagraphe_read import (
    Blob,
    MemoryProvider,
    Mode,
    Reading,
    State,
    StateProvider,
    git_provider,
    open_repository,
)
import pytest
import yaml

from onomasia.composition import Composer
from onomasia.configuration import ImportLimits, load_configuration
from onomasia.contracts import CONTRACT_SCHEMAS, MACRO_LOOKUP, MACRO_TABLE, TERM_TABLE
from onomasia.errors import ConfigurationError
from onomasia.imports import FOLLOWED, AnagrapheSources
from onomasia.issues import IssueSink
from onomasia.records.model import RecordKind
from onomasia.repository import FileRecordSource, load_records
from onomasia.issues import Severity
from onomasia.provenance import Source
from onomasia.records.validation import SCHEMA_FILES, SchemaValidator
from onomasia.service import BuildResult, build_outputs

CONSUMER = "thesis"
LEXICON = "lexicon"
ATLAS = "atlas"
COMMITS = {LEXICON: "1" * 40, ATLAS: "2" * 40}
"""Commit selected for each repository by the resolution context of the consumer."""

SOURCE = Source("https://example.org/thesis.git", "3" * 40, False)

REGISTRY = "schemas/registry.yml"
"""Schema registry of the consumer, holding the packaged schemas of Onomasia."""

TERMS = {"product": "term-table", "glossary": "project", "path": "out/terms.yml"}
"""Output reading the composition of the glossary `project`."""


class FixedProvenance:  # pylint: disable=too-few-public-methods
    """Provenance of a test consumer, read from no repository."""

    def sources(self, root: Path, files: Sequence[Path]) -> tuple[Source, ...]:
        """Return the fixed source."""
        del root, files
        return (SOURCE,)


@dataclass
class CountingProvider:
    """In-memory provider counting the reads of each path of each state."""

    inner: MemoryProvider
    reads: Counter[tuple[str, str]] = field(default_factory=Counter)

    def read(self, state: State, path: str) -> Reading:
        """Count the read, then serve it from memory."""
        self.reads[(state.commit, path)] += 1
        return self.inner.read(state, path)


def _yaml(data: object) -> bytes:
    """Write data as the bytes of a YAML file, a string being written as it is."""
    return (data if isinstance(data, str) else yaml.safe_dump(data, sort_keys=False)).encode()


def _glossary(
    identifier: str,
    terms: dict[str, str],
    imports: list[object] | None = None,
    version: int = 2,
) -> dict:
    """Write a glossary whose terms map identifiers to labels, with its imports; an import given
    as a mapping without `from` is the value of `from`."""
    data: dict[str, object] = {"_schema": f"onomasia:glossary@{version}", "id": identifier}
    if imports:
        data["imports"] = [
            item if isinstance(item, dict) and "from" in item else {"from": item}
            for item in imports
        ]
    data["terms"] = {key: {"label": label, "gloss": f"the {label}"} for key, label in terms.items()}
    return data


def _state(
    repository: str,
    records: dict[str, object],
    *,
    retired: dict[str, dict] | None = None,
    registered: dict[str, str] | None = None,
    configuration: object | None = None,
    identity: object | None = None,
) -> dict[str, Blob]:
    """Write the state of a repository: its configuration of Anagraphe, whose section `repository`
    holds `identity` or else the identifier of the repository, its record registry and its records,
    keyed by path. Each record of data is registered under its identifier, and `registered` adds
    identifiers registered at given paths."""
    paths = {str(data["id"]): path for path, data in records.items() if isinstance(data, dict)} | (
        registered or {}
    )
    files: dict[str, Blob] = {
        "anagraphe.yml": Blob(
            _yaml(
                configuration
                if configuration is not None
                else {
                    "_schema": "anagraphe:configuration@3",
                    "repository": identity if identity is not None else {"id": repository},
                    "targets": {},
                    "records": {},
                }
            )
        ),
        "record-registry.yml": Blob(
            _yaml(
                {
                    "_schema": "anagraphe:record-registry@1",
                    "repository": repository,
                    "records": {
                        identifier: {"path": path, "format": "yaml"}
                        for identifier, path in sorted(paths.items())
                    },
                    "retired": retired or {},
                }
            )
        ),
    }
    for path, data in records.items():
        files[path] = data if isinstance(data, Blob) else Blob(_yaml(data))
    return files


BASE = _glossary("base", {"curve": "curve", "gain": "gain"})
CORE = _glossary("core", {"rate": "rate"})
SHAPES = _glossary("shapes", {"torus": "torus"})
PROJECT = _glossary("project", {"manifold": "manifold"}, [{"repository": LEXICON, "id": "base"}])


def _states(
    lexicon: dict[str, object] | None = None,
    atlas: dict[str, object] | None = None,
    **options: object,
) -> dict[str, dict[str, Blob]]:
    """Write the states of both repositories, each holding the records given, by path; the
    options apply to the state of `lexicon`."""
    return {
        COMMITS[LEXICON]: _state(
            LEXICON,
            lexicon if lexicon is not None else {"base.yml": BASE},
            **options,  # type: ignore[arg-type]
        ),
        COMMITS[ATLAS]: _state(ATLAS, atlas if atlas is not None else {"shapes.yml": SHAPES}),
    }


def _consumer(
    root: Path,
    records: dict[str, object],
    *,
    imports: dict[str, int] | None = None,
    outputs: list[dict] | None = None,
) -> Path:
    """Write the consumer: its configuration of Anagraphe naming its identifier, both repositories
    and its schema registry, its configuration of Onomasia, and its records."""
    shutil.copytree(Path(str(resources.files("onomasia") / "data" / "schemas")), root / "schemas")
    files: dict[str, object] = {
        "anagraphe.yml": {
            "_schema": "anagraphe:configuration@3",
            "repository": {"id": CONSUMER},
            "targets": {"records": {"registry": REGISTRY}},
            "resolution": {
                "repositories": {
                    name: {"commit": commit, "remote": f"https://example.org/{name}.git"}
                    for name, commit in COMMITS.items()
                }
            },
        },
        REGISTRY: {
            "_schema": "kleisis:schema-registry@2",
            "schemas": {contract: f"schemas/{name}" for contract, name in SCHEMA_FILES.items()},
            "exports": sorted(SCHEMA_FILES),
            "resources": {},
        },
        "onomasia.yml": {
            "_schema": "onomasia:configuration@1",
            "records": {
                "glossaries": ["glossary-*.yml"],
                "notations": ["notation-*.yml"],
                "overlays": ["overlay-*.yml"],
            },
            **({"imports": imports} if imports is not None else {}),
            "build": {
                "denotes_targets": ["targets.yml"] if "targets.yml" in records else [],
                "outputs": outputs if outputs is not None else [TERMS],
            },
        },
        **records,
    }
    for relative, data in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_yaml(data))
    return root


def _build(root: Path, provider: StateProvider) -> BuildResult:
    """Build the outputs of a consumer over a provider of states, under the fixed provenance."""
    configuration = load_configuration(root, root / "onomasia.yml")
    return build_outputs(configuration, provenance=FixedProvenance(), provider=provider)


def _issues(root: Path, provider: StateProvider) -> list[tuple[str, str, str]]:
    """Build a consumer, returning each issue as (check, resource, pointer)."""
    return [(issue.check, issue.resource, issue.pointer) for issue in _build(root, provider).issues]


def _document(root: Path, name: str) -> dict:
    """Read a document written by the build."""
    return yaml.safe_load((root / "out" / name).read_text(encoding="utf-8"))


def _terms(root: Path) -> dict[str, tuple[str | None, str]]:
    """Read the term table of the glossary `project`: the repository, None for the consumer, and
    the path within it of the record declaring each term."""
    return {
        term["id"]: (term["gloss"].get("repository"), term["gloss"]["resource"])
        for term in _document(root, "terms.yml")["terms"]
    }


# --- composition across repositories ------------------------------------------------------------


def test_glossary_imports_a_glossary_of_another_repository(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"glossary-project.yml": PROJECT})
    result = _build(root, MemoryProvider(_states()))
    assert result.issues == []
    assert _terms(root) == {
        "curve": (LEXICON, "base.yml"),
        "gain": (LEXICON, "base.yml"),
        "manifold": (None, "glossary-project.yml"),
    }


def test_identifier_in_a_source_names_a_record_of_its_repository(tmp_path: Path) -> None:
    """The consumer holds a glossary `core` too, which a bare identifier read in the consumer would
    adopt; a target without repository, `{id: extra}`, also names a record of the source."""
    base = _glossary(
        "base", {"curve": "curve"}, ["core", {"id": "extra"}, {"repository": ATLAS, "id": "shapes"}]
    )
    lexicon = {"base.yml": base, "core.yml": CORE, "extra.yml": _glossary("extra", {"slope": "s"})}
    local_core = _glossary("core", {"local-rate": "local rate"})
    root = _consumer(tmp_path, {"glossary-project.yml": PROJECT, "glossary-core.yml": local_core})
    assert _build(root, MemoryProvider(_states(lexicon))).issues == []
    assert _terms(root) == {
        "curve": (LEXICON, "base.yml"),
        "manifold": (None, "glossary-project.yml"),
        "rate": (LEXICON, "core.yml"),
        "slope": (LEXICON, "extra.yml"),
        "torus": (ATLAS, "shapes.yml"),
    }


def test_target_in_a_source_names_a_repository_of_the_consumer_context(tmp_path: Path) -> None:
    """A source of `lexicon` imports `{repository: thesis, id: local}`: the consumer itself, whose
    working tree holds the record, since its context selects no state of it."""
    base = _glossary("base", {"curve": "curve"}, [{"repository": CONSUMER, "id": "local"}])
    local = _glossary("local", {"own": "own"})
    root = _consumer(tmp_path, {"glossary-project.yml": PROJECT, "glossary-local.yml": local})
    assert _build(root, MemoryProvider(_states({"base.yml": base}))).issues == []
    assert _terms(root)["own"] == (None, "glossary-local.yml")


def test_repeated_source_is_read_once(tmp_path: Path) -> None:
    """`base` is reached three times: merged, under an alias, and through `shapes`."""
    shapes = _glossary("shapes", {"torus": "torus"}, [{"repository": LEXICON, "id": "base"}])
    project = _glossary(
        "project",
        {"manifold": "manifold"},
        [
            {"repository": LEXICON, "id": "base"},
            {"from": {"repository": LEXICON, "id": "base"}, "as": "b"},
            {"repository": ATLAS, "id": "shapes"},
        ],
    )
    provider = CountingProvider(MemoryProvider(_states(atlas={"shapes.yml": shapes})))
    root = _consumer(tmp_path, {"glossary-project.yml": project})
    assert _build(root, provider).issues == []
    assert provider.reads[(COMMITS[LEXICON], "base.yml")] == 1
    assert _terms(root)["torus"] == (ATLAS, "shapes.yml")


@pytest.mark.parametrize(
    ("closing", "resource"),
    [
        ({"repository": LEXICON, "id": "base"}, "atlas:shapes.yml"),
        ({"repository": CONSUMER, "id": "project"}, "atlas:shapes.yml"),
    ],
)
def test_cycle_across_repositories_is_reported_where_it_closes(
    tmp_path: Path, closing: dict, resource: str
) -> None:
    base = _glossary("base", {"curve": "curve"}, [{"repository": ATLAS, "id": "shapes"}])
    shapes = _glossary("shapes", {"torus": "torus"}, [closing])
    root = _consumer(tmp_path, {"glossary-project.yml": PROJECT})
    issues = _issues(root, MemoryProvider(_states({"base.yml": base}, {"shapes.yml": shapes})))
    assert ("import-cycle", resource, "/imports/0/from") in issues


def test_conflicting_entries_of_two_sources_are_reported(tmp_path: Path) -> None:
    shapes = _glossary("shapes", {"curve": "bend"})
    project = _glossary(
        "project",
        {"manifold": "manifold"},
        [{"repository": LEXICON, "id": "base"}, {"repository": ATLAS, "id": "shapes"}],
    )
    root = _consumer(tmp_path, {"glossary-project.yml": project})
    issues = _issues(root, MemoryProvider(_states(atlas={"shapes.yml": shapes})))
    assert issues == [("import-conflict", "glossary-project.yml", "/imports/1")]


def test_one_entry_reached_through_two_paths_is_no_conflict(tmp_path: Path) -> None:
    shapes = _glossary("shapes", {"torus": "torus"}, [{"repository": LEXICON, "id": "base"}])
    project = _glossary(
        "project",
        {"manifold": "manifold"},
        [{"repository": LEXICON, "id": "base"}, {"repository": ATLAS, "id": "shapes"}],
    )
    root = _consumer(tmp_path, {"glossary-project.yml": project})
    assert _issues(root, MemoryProvider(_states(atlas={"shapes.yml": shapes}))) == []


def test_source_breaking_its_schema_is_reported_in_it_and_left_unread(tmp_path: Path) -> None:
    broken = dict(BASE, terms={"curve": {"label": "curve"}})
    root = _consumer(tmp_path, {"glossary-project.yml": PROJECT})
    issues = _issues(root, MemoryProvider(_states({"base.yml": broken})))
    assert issues == [
        ("unresolved-import", "glossary-project.yml", "/imports/0/from"),
        ("schema-violation", "lexicon:base.yml", "/terms/curve"),
    ]


# --- the findings of the resolver ---------------------------------------------------------------


def test_unread_source_is_an_error_at_the_key_from(tmp_path: Path) -> None:
    """Anagraphe reports an absent state as a warning; for an import, it is an error."""
    root = _consumer(tmp_path, {"glossary-project.yml": PROJECT})
    issues = _build(root, MemoryProvider({})).issues
    assert [(issue.check, issue.severity, issue.resource, issue.pointer) for issue in issues] == [
        ("unreadable-target-state", Severity.ERROR, "glossary-project.yml", "/imports/0/from")
    ]
    assert not (root / "out").exists()


def test_source_read_without_the_schemas_of_its_contract(tmp_path: Path) -> None:
    """Without a schema registry, the resolver verifies the record by the identifier and the
    contract that it writes, and Onomasia reads the record."""
    root = _consumer(tmp_path, {"glossary-project.yml": PROJECT})
    configuration = yaml.safe_load((root / "anagraphe.yml").read_text())
    del configuration["targets"]["records"]
    (root / "anagraphe.yml").write_bytes(_yaml(configuration))
    assert _build(root, MemoryProvider(_states())).issues == []
    assert _terms(root)["curve"] == (LEXICON, "base.yml")


def _target(identifier: str, repository: str = LEXICON) -> dict[str, str]:
    """Write the target of a record."""
    return {"repository": repository, "id": identifier}


PROJECT_AT = ("glossary-project.yml", "/imports/0/from")
"""Location of the import of `project`, where each finding of the resolver is reported."""

NOTATION = {"_schema": "onomasia:notation@2", "id": "base", "entries": {}}
LINKED = Blob(b"", Mode.LINK)

PLANTED: dict[str, tuple[object, object, tuple[str, str]]] = {
    # Each case: the source imported by `project`, the states, and the location of the issue.
    "unknown-repository": (_target("base", "nowhere"), _states(), PROJECT_AT),
    "renamed-repository": (
        _target("base", "old-lexicon"),
        _states(identity={"id": LEXICON, "retired": ["old-lexicon"]}),
        PROJECT_AT,
    ),
    "unreadable-target-state": (_target("base"), {}, PROJECT_AT),
    "invalid-target-state": (_target("base"), "invalid", PROJECT_AT),
    "invalid-target-repository": (
        _target("base"),
        _states(identity={"id": "elsewhere"}),
        PROJECT_AT,
    ),
    "invalid-record-registry": (
        _target("base"),
        _states(retired={"gone": {"date": "yesterday"}}),
        PROJECT_AT,
    ),
    "unverified-target": (
        _target("base"),
        _states(
            configuration={
                "_schema": "anagraphe:configuration@3",
                "repository": {"id": LEXICON},
                "targets": {},
            }
        ),
        PROJECT_AT,
    ),
    "unknown-record": (_target("absent"), _states(), PROJECT_AT),
    "renamed-target": (
        _target("old-base"),
        _states(retired={"old-base": {"date": "2026-11-17", "replaced_by": "base"}}),
        PROJECT_AT,
    ),
    "retired-target": (
        _target("gone"),
        _states(retired={"gone": {"date": "2026-11-17"}}),
        PROJECT_AT,
    ),
    "escaping-target-path": (
        _target("base"),
        _states({"base.yml": BASE, "linked": LINKED}, registered={"base": "linked/base.yml"}),
        PROJECT_AT,
    ),
    "linked-target-path": (
        _target("base"),
        _states({"base.yml": LINKED}, registered={"base": "base.yml"}),
        PROJECT_AT,
    ),
    "stale-target-registry": (
        _target("base"),
        _states({}, registered={"base": "absent.yml"}),
        PROJECT_AT,
    ),
    "unreadable-record": (
        _target("base"),
        _states({"base.yml": Blob(b"terms: [unclosed")}, registered={"base": "base.yml"}),
        PROJECT_AT,
    ),
    "target-contract-mismatch": (_target("base"), _states({"base.yml": NOTATION}), PROJECT_AT),
    "unbound-target": (
        _target("base"),
        _states({"base.yml": Blob(b"metadata: {id: base}\n")}, registered={"base": "base.yml"}),
        PROJECT_AT,
    ),
    "import-limit": (
        _target("base"),
        _states({"base.yml": _glossary("base", {"curve": "curve"}, ["core"]), "core.yml": CORE}),
        ("lexicon:base.yml", "/imports/0/from"),
    ),
}
"""Checks of the imports across repositories, each planted by its source and its states."""

PLANTED_LIMITS = {"import-limit": {"depth": 1}}
"""Limits of the consumer under which a case of `PLANTED` is checked."""


def _provider(states: object) -> MemoryProvider:
    """Serve the states of a planted case; `invalid` marks the state of `lexicon` as invalid."""
    if states == "invalid":
        return MemoryProvider(_states(), invalid=frozenset({COMMITS[LEXICON]}))
    assert isinstance(states, dict)
    return MemoryProvider(states)


@pytest.mark.parametrize("check", sorted(PLANTED))
def test_planted_defect_of_an_import_is_reported(tmp_path: Path, check: str) -> None:
    """Each finding leaving the source unread is an error; a followed rename is a warning."""
    source, states, location = PLANTED[check]
    project = _glossary("project", {"manifold": "manifold"}, [source])
    root = _consumer(tmp_path, {"glossary-project.yml": project}, imports=PLANTED_LIMITS.get(check))
    issues = _build(root, _provider(states)).issues
    expected = Severity.WARNING if check in FOLLOWED else Severity.ERROR
    assert (check, expected, *location) in {
        (issue.check, issue.severity, issue.resource, issue.pointer) for issue in issues
    }


@pytest.mark.parametrize("check", ["renamed-repository", "renamed-target"])
def test_followed_rename_is_a_warning_and_reads_the_source(tmp_path: Path, check: str) -> None:
    source, states, _ = PLANTED[check]
    project = _glossary("project", {"manifold": "manifold"}, [source])
    root = _consumer(tmp_path, {"glossary-project.yml": project})
    result = _build(root, _provider(states))
    assert [(issue.check, issue.severity) for issue in result.issues] == [(check, Severity.WARNING)]
    assert _terms(root)["curve"] == (LEXICON, "base.yml")


# --- the limits of a closure --------------------------------------------------------------------


def test_limit_of_depth_reads_no_further_import_of_the_branch(tmp_path: Path) -> None:
    base = _glossary("base", {"curve": "curve"}, ["core"])
    provider = CountingProvider(MemoryProvider(_states({"base.yml": base, "core.yml": CORE})))
    root = _consumer(tmp_path, {"glossary-project.yml": PROJECT}, imports={"depth": 1})
    issues = _issues(root, provider)
    assert issues == [("import-limit", "lexicon:base.yml", "/imports/0/from")]
    assert provider.reads[(COMMITS[LEXICON], "core.yml")] == 0
    root = _consumer(tmp_path / "deeper", {"glossary-project.yml": PROJECT}, imports={"depth": 2})
    assert _issues(root, provider) == []


def test_limit_of_records_counts_the_closure(tmp_path: Path) -> None:
    """The closure of `project` holds itself, `base` and `core`: three records."""
    base = _glossary("base", {"curve": "curve"}, ["core"])
    states = _states({"base.yml": base, "core.yml": CORE})
    root = _consumer(tmp_path, {"glossary-project.yml": PROJECT}, imports={"records": 2})
    assert _issues(root, MemoryProvider(states)) == [
        ("import-limit", "glossary-project.yml", "/imports/0/from")
    ]
    root = _consumer(tmp_path / "more", {"glossary-project.yml": PROJECT}, imports={"records": 3})
    assert _issues(root, MemoryProvider(states)) == []


def test_limit_of_bytes_counts_the_documents_of_the_closure(tmp_path: Path) -> None:
    states = _states()
    size = len(states[COMMITS[LEXICON]]["base.yml"].data) + len(_yaml(PROJECT))
    root = _consumer(tmp_path, {"glossary-project.yml": PROJECT}, imports={"bytes": size - 1})
    assert _issues(root, MemoryProvider(states)) == [
        ("import-limit", "glossary-project.yml", "/imports/0/from")
    ]
    root = _consumer(tmp_path / "more", {"glossary-project.yml": PROJECT}, imports={"bytes": size})
    assert _issues(root, MemoryProvider(states)) == []


def test_limits_default_to_the_packaged_values(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {}, imports={"records": 10})
    assert load_configuration(root, root / "onomasia.yml").imports == ImportLimits(8, 10, 4194304)


@pytest.mark.parametrize("value", [0, "8", None])
def test_invalid_limit_is_rejected(tmp_path: Path, value: object) -> None:
    root = _consumer(tmp_path, {}, imports={"depth": value})  # type: ignore[dict-item]
    with pytest.raises(ConfigurationError, match="imports.depth"):
        load_configuration(root, root / "onomasia.yml")


# --- the receipt --------------------------------------------------------------------------------


def test_receipt_lists_each_input_ordered_by_repository_commit_and_identifier(
    tmp_path: Path,
) -> None:
    base = _glossary("base", {"curve": "curve"}, ["core"])
    project = _glossary(
        "project",
        {"manifold": "manifold"},
        [{"repository": LEXICON, "id": "base"}, {"repository": ATLAS, "id": "shapes"}],
    )
    states = _states({"base.yml": base, "core.yml": CORE})
    root = _consumer(tmp_path, {"glossary-project.yml": project})
    assert _build(root, MemoryProvider(states)).issues == []

    def digest(repository: str, path: str) -> str:
        return hashlib.sha256(states[COMMITS[repository]][path].data).hexdigest()

    assert _document(root, "terms.yml")["inputs"] == [
        {
            "repository": ATLAS,
            "commit": COMMITS[ATLAS],
            "id": "shapes",
            "sha256": digest(ATLAS, "shapes.yml"),
        },
        {
            "repository": LEXICON,
            "commit": COMMITS[LEXICON],
            "id": "base",
            "sha256": digest(LEXICON, "base.yml"),
        },
        {
            "repository": LEXICON,
            "commit": COMMITS[LEXICON],
            "id": "core",
            "sha256": digest(LEXICON, "core.yml"),
        },
    ]


def test_document_without_imported_records_holds_no_receipt(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"glossary-project.yml": _glossary("project", {"m": "m"})})
    assert _build(root, MemoryProvider({})).issues == []
    data = _document(root, "terms.yml")
    assert "inputs" not in data
    assert list(SchemaValidator().contract_errors(CONTRACT_SCHEMAS[TERM_TABLE], data)) == []


# --- the versions of the records ----------------------------------------------------------------


def test_records_of_version_1_are_still_read(tmp_path: Path) -> None:
    """A glossary of version 2 imports a glossary of version 1 of another repository, which
    imports by identifier; a notation of version 1 names its unit by a text, which declares the
    entry and carries no target."""
    base = _glossary("base", {"curve": "curve"}, ["core"], version=1)
    core = _glossary("core", {"rate": "rate"}, version=1)
    notation = {
        "_schema": "onomasia:notation@1",
        "id": "old",
        "entries": {"w": {"denotes": "model:weights", "body": "W"}},
    }
    outputs = [TERMS, {"product": "macro-table", "notations": ["old"], "path": "out/table.yml"}]
    root = _consumer(
        tmp_path,
        {"glossary-project.yml": PROJECT, "notation-old.yml": notation},
        outputs=outputs,
    )
    assert _build(root, MemoryProvider(_states({"base.yml": base, "core.yml": core}))).issues == []
    assert _terms(root)["rate"] == (LEXICON, "core.yml")
    [entry] = _document(root, "table.yml")["entries"]
    assert (entry["target"], entry["arity"]) == (None, 0)


def test_target_is_rejected_by_the_import_of_version_1(tmp_path: Path) -> None:
    project = _glossary("project", {"m": "m"}, [{"repository": LEXICON, "id": "base"}], version=1)
    root = _consumer(tmp_path, {"glossary-project.yml": project})
    assert ("schema-violation", "glossary-project.yml", "/imports/0/from") in _issues(
        root, MemoryProvider(_states())
    )


# --- the targets of the notations ---------------------------------------------------------------


def test_denotes_is_normalized_by_the_repository_holding_the_notation(tmp_path: Path) -> None:
    """The notation of `lexicon` writes `{id: model, unit: sum}`, which names a unit of `lexicon`;
    the notation of the consumer writes `{id: model, unit: set}`, which names a unit of `thesis`.
    Each matches the unit of the denotes targets bearing its normalized target."""
    source = {
        "_schema": "onomasia:notation@2",
        "id": "base",
        "entries": {"sum-op": {"denotes": {"id": "model", "unit": "sum"}, "body": "\\sum_{#1} #2"}},
    }
    local = {
        "_schema": "onomasia:notation@2",
        "id": "local",
        "imports": [{"from": {"repository": LEXICON, "id": "base"}}],
        "entries": {
            "set-of": {
                "denotes": {"id": "model", "unit": "set"},
                "body": "\\{#1\\}",
                "separator": ",",
            }
        },
    }
    targets = {
        "_schema": "onomasia:denotes-targets@3",
        "sources": [],
        "targets": [
            {
                "target": {"repository": LEXICON, "id": "model", "unit": "sum"},
                "arguments": 2,
                "bound": 1,
            },
            {
                "target": {"repository": CONSUMER, "id": "model", "unit": "set"},
                "arguments": 1,
                "list": 1,
            },
            {"target": {"repository": CONSUMER, "id": "model", "unit": "sum"}, "arguments": 5},
        ],
    }
    outputs = [
        {"product": "macro-table", "notations": ["local"], "path": "out/table.yml"},
        {"product": "macro-lookup", "notations": ["local"], "path": "out/lookup.yml"},
    ]
    root = _consumer(
        tmp_path,
        {"notation-local.yml": local, "targets.yml": targets},
        outputs=outputs,
    )
    assert _build(root, MemoryProvider(_states({"base.yml": source}))).issues == []
    table = _document(root, "table.yml")
    entries = {entry["id"]: entry for entry in table["entries"]}
    assert entries["sum-op"]["target"] == {"repository": LEXICON, "id": "model", "unit": "sum"}
    assert (entries["sum-op"]["arity"], entries["sum-op"]["binder"]) == (2, 1)
    assert entries["set-of"]["target"] == {"repository": CONSUMER, "id": "model", "unit": "set"}
    assert entries["set-of"]["arity"] == 1
    assert [item["id"] for item in table["inputs"]] == ["base"]
    lookup = _document(root, "lookup.yml")
    assert lookup["targets"] == [
        {"target": {"repository": LEXICON, "id": "model", "unit": "sum"}, "name": "onosumOp"},
        {"target": {"repository": CONSUMER, "id": "model", "unit": "set"}, "name": "onosetOf"},
    ]
    for name, contract in (("table.yml", MACRO_TABLE), ("lookup.yml", MACRO_LOOKUP)):
        data = _document(root, name)
        assert list(SchemaValidator().contract_errors(CONTRACT_SCHEMAS[contract], data)) == []


# --- the overlays of a notation of another repository -----------------------------------------


MIXTURE = {
    "_schema": "onomasia:notation@2",
    "id": "mixture",
    "classes": {"matrix": {"template": "\\boldsymbol{{{base}}}"}},
    "entries": {
        "w-ff": {"denotes": {"id": "model", "unit": "weights"}, "base": "W", "class": "matrix"}
    },
}

POSTER = {
    "_schema": "onomasia:overlay@2",
    "id": "poster",
    "overlays": {"repository": LEXICON, "id": "mixture"},
    "entries": {"w-ff": {"base": "V"}},
}


def _compose_overlay(root: Path, provider: StateProvider) -> tuple[object, IssueSink]:
    """Apply the overlay `poster` of a consumer through the composer, returning the composition
    and the issues."""
    configuration = load_configuration(root, root / "onomasia.yml")
    sink = IssueSink(configuration.severities)
    validator = SchemaValidator()
    opened = open_repository(root, provider=provider)
    repository = opened.identity.id
    composer = Composer(
        load_records(FileRecordSource(root, configuration.records), validator, sink, repository),
        sink,
        repository=repository,
        sources=AnagrapheSources(opened, validator, sink),
        limits=configuration.imports,
    )
    [overlay] = composer.records(RecordKind.OVERLAY)
    return composer.apply_overlay(overlay), sink


def test_overlay_changes_a_notation_of_another_repository(tmp_path: Path) -> None:
    states = _states({"mixture.yml": MIXTURE})
    root = _consumer(tmp_path, {"overlay-poster.yml": POSTER}, outputs=[])
    composition, sink = _compose_overlay(root, MemoryProvider(states))
    assert sink.issues == []
    assert composition is not None
    entry = composition.sections["entries"]["w-ff"]  # type: ignore[attr-defined]
    assert entry.entry.base == "V" and entry.record.identifier == "poster"
    assert [(item.repository, item.identifier) for item in composition.inputs()] == [
        (LEXICON, "mixture")
    ]  # type: ignore[attr-defined]
    assert _issues(root, MemoryProvider(states)) == []


def test_overlay_overriding_an_entry_absent_from_the_remote_notation_is_reported(
    tmp_path: Path,
) -> None:
    poster = dict(POSTER, entries={"absent": {"body": "x"}})
    root = _consumer(tmp_path, {"overlay-poster.yml": poster}, outputs=[])
    issues = _issues(root, MemoryProvider(_states({"mixture.yml": MIXTURE})))
    assert issues == [("unknown-override", "overlay-poster.yml", "/entries/absent")]


def test_unread_notation_of_an_overlay_is_an_error_at_its_key(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"overlay-poster.yml": POSTER}, outputs=[])
    issues = _build(root, MemoryProvider({})).issues
    assert [(issue.check, issue.severity, issue.resource, issue.pointer) for issue in issues] == [
        ("unreadable-target-state", Severity.ERROR, "overlay-poster.yml", "/overlays")
    ]


def test_overlay_is_held_within_the_limits_of_its_closure(tmp_path: Path) -> None:
    """The closure of the overlay holds itself and the notation: two records."""
    states = _states({"mixture.yml": MIXTURE})
    root = _consumer(tmp_path, {"overlay-poster.yml": POSTER}, imports={"records": 1}, outputs=[])
    assert _issues(root, MemoryProvider(states)) == [
        ("import-limit", "overlay-poster.yml", "/overlays")
    ]


def test_overlay_naming_an_absent_notation_of_the_consumer_is_unresolved(tmp_path: Path) -> None:
    poster = dict(POSTER, overlays={"id": "absent"})
    root = _consumer(tmp_path, {"overlay-poster.yml": poster}, outputs=[])
    assert _issues(root, MemoryProvider({})) == [
        ("unresolved-overlay", "overlay-poster.yml", "/overlays")
    ]


@pytest.mark.parametrize("version", [1, 2])
def test_overlay_of_a_notation_of_the_consumer_applies_in_the_build(
    tmp_path: Path, version: int
) -> None:
    """An overlay of version 1 names the notation by its identifier, as one of version 2 may."""
    poster = dict(POSTER, _schema=f"onomasia:overlay@{version}", overlays="mixture")
    outputs = [
        {
            "product": "macro-table",
            "notations": ["mixture"],
            "overlays": ["poster"],
            "path": "out/table.yml",
        }
    ]
    root = _consumer(
        tmp_path,
        {"notation-mixture.yml": MIXTURE, "overlay-poster.yml": poster},
        outputs=outputs,
    )
    assert _build(root, MemoryProvider({})).issues == []
    [entry] = _document(root, "table.yml")["entries"]
    assert entry["body"] == "\\boldsymbol{V}"


def test_overlay_of_version_1_rejects_a_target(tmp_path: Path) -> None:
    poster = dict(POSTER, _schema="onomasia:overlay@1")
    root = _consumer(tmp_path, {"overlay-poster.yml": poster}, outputs=[])
    assert ("schema-violation", "overlay-poster.yml", "/overlays") in _issues(
        root, MemoryProvider({})
    )


# --- the inputs of the serializations -----------------------------------------------------------


SERIALIZATIONS = [
    {"product": "latex-package", "notations": ["local"], "path": "out/local.sty"},
    {"product": "mathjax-preamble", "notations": ["local"], "path": "out/preamble.sty"},
    {"product": "python-expander", "notations": ["local"], "path": "out/local_notation.py"},
]


def _local_notation(imports: list[dict]) -> dict:
    """Write the notation `local` of the consumer, with one entry and its imports."""
    return {
        "_schema": "onomasia:notation@2",
        "id": "local",
        "imports": imports,
        "entries": {
            "lam": {"denotes": {"id": "model", "unit": "lam"}, "body": "\\lambda", "name": "lam"}
        },
    }


def _serialized(root: Path, provider: StateProvider) -> tuple[list[str], list[str], list[dict]]:
    """Build the three serializations, returning the lines of the package and of the preamble,
    and the inputs of the expander."""
    assert _build(root, provider).issues == []
    package = (root / "out" / "local.sty").read_text(encoding="utf-8").splitlines()
    preamble = (root / "out" / "preamble.sty").read_text(encoding="utf-8").splitlines()
    namespace: dict[str, object] = {}
    exec(  # pylint: disable=exec-used
        (root / "out" / "local_notation.py").read_text(encoding="utf-8"), namespace
    )
    return package, preamble, namespace["INPUTS"]  # type: ignore[return-value]


def test_serializations_state_each_input_in_order(tmp_path: Path) -> None:
    lexicon = {
        "zeta.yml": {"_schema": "onomasia:notation@2", "id": "zeta", "entries": {}},
        "alpha.yml": {"_schema": "onomasia:notation@2", "id": "alpha", "entries": {}},
    }
    shapes = {"_schema": "onomasia:notation@2", "id": "shapes", "entries": {}}
    notation = _local_notation(
        [
            {"from": {"repository": LEXICON, "id": "zeta"}},
            {"from": {"repository": ATLAS, "id": "shapes"}},
            {"from": {"repository": LEXICON, "id": "alpha"}},
        ]
    )
    states = _states(lexicon, {"shapes.yml": shapes})
    root = _consumer(tmp_path, {"notation-local.yml": notation}, outputs=SERIALIZATIONS)
    package, preamble, inputs = _serialized(root, MemoryProvider(states))

    def item(repository: str, identifier: str, path: str) -> dict[str, str]:
        data = states[COMMITS[repository]][path].data
        digest = hashlib.sha256(data).hexdigest()
        return {
            "repository": repository,
            "commit": COMMITS[repository],
            "id": identifier,
            "sha256": digest,
        }

    expected = [item(ATLAS, "shapes", "shapes.yml"), item(LEXICON, "alpha", "alpha.yml")]
    expected.append(item(LEXICON, "zeta", "zeta.yml"))
    lines = [f"% {i['repository']} {i['commit']} {i['id']} {i['sha256']}" for i in expected]
    assert package[1:4] == lines and package[4] == "\\NeedsTeXFormat{LaTeX2e}"
    assert preamble[1:4] == lines and preamble[4] == "\\newcommand{\\lam}{\\lambda}"
    assert inputs == expected


def test_serializations_without_imported_records_state_no_input(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"notation-local.yml": _local_notation([])}, outputs=SERIALIZATIONS)
    package, preamble, inputs = _serialized(root, MemoryProvider({}))
    assert package[1] == "\\NeedsTeXFormat{LaTeX2e}"
    assert preamble[1:] == ["\\newcommand{\\lam}{\\lambda}"]
    assert inputs == []


# --- the location of a gloss --------------------------------------------------------------------


def test_gloss_of_a_remote_term_names_its_repository_its_commit_and_its_path(
    tmp_path: Path,
) -> None:
    root = _consumer(tmp_path, {"glossary-project.yml": PROJECT})
    assert _build(root, MemoryProvider(_states({"lexicons/base.yml": BASE}))).issues == []
    data = _document(root, "terms.yml")
    glosses = {term["id"]: term["gloss"] for term in data["terms"]}
    assert glosses["curve"] == {
        "text": "the curve",
        "resource": "lexicons/base.yml",
        "pointer": "/terms/curve/gloss",
        "repository": LEXICON,
        "commit": COMMITS[LEXICON],
    }
    assert glosses["manifold"] == {
        "text": "the manifold",
        "resource": "glossary-project.yml",
        "pointer": "/terms/manifold/gloss",
    }
    assert not list(SchemaValidator().contract_errors(CONTRACT_SCHEMAS[TERM_TABLE], data))


# --- the schemas --------------------------------------------------------------------------------


def _schemas() -> dict[str, dict]:
    """Read every packaged schema, by its identifier."""
    folder = resources.files("onomasia") / "data" / "schemas"
    return {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in folder.iterdir()
        if path.name.endswith(".schema.yml")
    }


EXAMPLED = [name for name, schema in sorted(_schemas().items()) if "examples" in schema]
"""Schemas carrying examples: those of the versions published with the targets."""


def test_the_schemas_published_with_the_targets_carry_examples() -> None:
    assert EXAMPLED == [
        "denotes-targets.schema.yml",
        "glossary.schema.yml",
        "macro-lookup.schema.yml",
        "macro-table.schema.yml",
        "notation.schema.yml",
        "overlay.schema.yml",
        "term-table.schema.yml",
    ]


@pytest.mark.parametrize("name", EXAMPLED)
def test_schema_validates_its_examples(name: str) -> None:
    validator = SchemaValidator()
    for example in _schemas()[name]["examples"]:
        assert list(validator.contract_errors(name, example)) == []


@pytest.mark.parametrize(
    ("name", "invalid", "pointer"),
    [
        (
            "glossary.schema.yml",
            {"from": {"repository": LEXICON, "id": "base", "unit": "x"}},
            "/imports/0/from",
        ),
        ("glossary.schema.yml", {"from": {"repository": LEXICON}}, "/imports/0/from"),
        (
            "notation.schema.yml",
            {"from": {"repository": LEXICON, "id": "x"}, "as": "BAD"},
            "/imports/0/as",
        ),
    ],
)
def test_schema_rejects_an_import_naming_no_record(name: str, invalid: dict, pointer: str) -> None:
    example = dict(_schemas()[name]["examples"][0], imports=[invalid])
    assert pointer in {item for item, _ in SchemaValidator().contract_errors(name, example)}


def test_notation_of_version_2_requires_a_unit_under_denotes() -> None:
    example = yaml.safe_load(yaml.safe_dump(_schemas()["notation.schema.yml"]["examples"][0]))
    example["entries"]["w-ff"]["denotes"] = {"id": "mixture-model"}
    errors = SchemaValidator().contract_errors("notation.schema.yml", example)
    assert "/entries/w-ff/denotes" in {pointer for pointer, _ in errors}


def test_the_registered_schemas_declare_their_target_fields() -> None:
    """The schemas of version 2 declare the identifier read by Anagraphe under `x-identifier`, and
    each field holding a logical target under `x-target-contract`, with the contract of the record
    that the target names; `denotes` names a unit of any contract."""
    schemas = _schemas()

    def at(name: str, *path: str) -> dict:
        node = schemas[name]
        for key in path:
            node = node[key]
        return node

    for name in ("glossary.schema.yml", "notation.schema.yml", "overlay.schema.yml"):
        assert schemas[name]["x-identifier"] == "id"
    for name, contract in (
        ("glossary.schema.yml", "onomasia:glossary"),
        ("notation.schema.yml", "onomasia:notation"),
    ):
        assert at(name, "properties", "imports", "items", "properties", "from")[
            "x-target-contract"
        ] == [contract]
    assert at("overlay.schema.yml", "properties", "overlays")["x-target-contract"] == [
        "onomasia:notation"
    ]
    denotes = at("notation.schema.yml", "$defs", "entry", "properties", "denotes")
    assert denotes["$ref"].endswith("#/$defs/target") and "x-target-contract" not in denotes


# --- the Git provider ---------------------------------------------------------------------------


def _git(folder: Path, *arguments: str) -> str:
    """Run one command of Git in a folder, returning its output."""
    identity = ["-c", "user.name=Test", "-c", "user.email=test@example.org"]
    completed = subprocess.run(
        ["git", "-C", str(folder), *identity, "-c", "commit.gpgsign=false", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="the command git is absent")
def test_git_provider_reads_the_source_from_a_local_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone = tmp_path / "lexicon"
    clone.mkdir()
    for path, blob in _state(LEXICON, {"base.yml": BASE}).items():
        (clone / path).write_bytes(blob.data)
    _git(clone, "init", "--quiet")
    _git(clone, "add", ".")
    _git(clone, "commit", "--quiet", "-m", "records")
    machine = tmp_path / "machine.yml"
    machine.write_text(yaml.safe_dump({LEXICON: str(clone)}), encoding="utf-8")
    monkeypatch.setenv("ANAGRAPHE_REPOSITORIES", str(machine))
    monkeypatch.setitem(COMMITS, LEXICON, _git(clone, "rev-parse", "HEAD"))
    root = _consumer(tmp_path / "thesis", {"glossary-project.yml": PROJECT})
    result = _build(root, git_provider())
    assert result.issues == []
    assert _document(root, "terms.yml")["inputs"] == [
        {
            "repository": LEXICON,
            "commit": COMMITS[LEXICON],
            "id": "base",
            "sha256": hashlib.sha256((clone / "base.yml").read_bytes()).hexdigest(),
        }
    ]
