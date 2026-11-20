"""Run the published cases of the field `sources` against the schemas and the Git provenance."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

import pytest
import yaml

from onomasia.contracts import SCOPE_TABLE
from onomasia.provenance import GitProvenance
from onomasia.records.validation import SchemaValidator

CASES: list[dict[str, Any]] = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "specs" / "cases" / "sources.yml").read_text(
        encoding="utf-8"
    )
)["cases"]


def _of_kind(kind: str) -> list[dict[str, Any]]:
    """Return the cases of one kind."""
    return [case for case in CASES if kind in case]


def _git(root: Path, *arguments: str) -> None:
    """Run one command of Git in a test repository."""
    subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)


def _repository(root: Path, files: list[str]) -> None:
    """Create a repository at `root` whose one commit holds `files`."""
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.org")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")
    for name in files:
        (root / name).write_text(f"{name}\n", encoding="utf-8")
    _git(root, "add", "--", *files)
    _git(root, "commit", "-q", "-m", "records")


def test_every_case_has_one_kind() -> None:
    """Each case is a value, a remote or a state case, so that no case is skipped."""
    for case in CASES:
        assert len({"value", "remote", "state"} & case.keys()) == 1, case["name"]


@pytest.mark.parametrize("case", _of_kind("value"), ids=lambda case: case["name"])
def test_value_case(case: dict[str, Any]) -> None:
    """The schema of the contracts admits a value of `sources` exactly when the case says so."""
    document = {"_schema": SCOPE_TABLE, "sources": case["value"], "audiences": {}}
    errors = list(SchemaValidator().contract_errors("scope-table.schema.yml", document))
    assert (not errors) is case["expect"]["valid"], errors


@pytest.mark.parametrize("case", _of_kind("remote"), ids=lambda case: case["name"])
def test_remote_case(case: dict[str, Any], tmp_path: Path) -> None:
    """The provenance writes the location of the remote without its user information."""
    root = tmp_path / "repository"
    _repository(root, ["onomasia.yml"])
    if case["remote"] is not None:
        _git(root, "remote", "add", "origin", case["remote"])
    (source,) = GitProvenance().sources(root, [root / "onomasia.yml"])
    assert source.repository == case["expect"]["repository"].replace("{root}", str(root))


@pytest.mark.parametrize("case", _of_kind("state"), ids=lambda case: case["name"])
def test_state_case(case: dict[str, Any], tmp_path: Path) -> None:
    """A source is dirty exactly when its commit does not hold one of the files read."""
    state = case["state"]
    root = tmp_path / "repository"
    _repository(root, state["committed"])
    for name in state.get("modified", []) + state.get("staged", []):
        (root / name).write_text(f"{name} changed\n", encoding="utf-8")
    if state.get("staged"):
        _git(root, "add", "--", *state["staged"])
    if state.get("ignored"):
        (root / ".git" / "info" / "exclude").write_text(
            "\n".join(state["ignored"]) + "\n", encoding="utf-8"
        )
    for name in state.get("untracked", []) + state.get("ignored", []):
        (root / name).write_text(f"{name}\n", encoding="utf-8")
    for name in state.get("outside", []):
        (tmp_path / name).write_text(f"{name}\n", encoding="utf-8")
    (source,) = GitProvenance().sources(root, [root / name for name in case["read"]])
    assert source.dirty is case["expect"]["dirty"]
