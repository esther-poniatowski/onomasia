"""
Tests of the resolution of the root of a consumer and of its configuration file.

Hodegos locates both. The root is the folder given by `--root`, else by `ONOMASIA_ROOT`, else the
nearest folder, from the current one upwards, holding `onomasia.yml` at one of its places, else the
current folder. The places are the root, its `.config/` and its `config/`; two places holding a
file is an error. A named `--config` is read from the current folder.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from onomasia.cli import app
from onomasia.configuration import discover_configuration
from onomasia.errors import ConfigurationError

VALID = "_schema: onomasia:configuration@1\n"
"""Configuration that `onomasia check` reads with no error."""
INVALID = "_schema: onomasia:configuration@99\n"
"""Configuration that `onomasia check` rejects, with exit status 2."""
NESTED = Path("config/onomasia.yml")
"""Configuration in the subfolder `config/`, a place of the root."""


def _consumer(root: Path, files: dict[Path | str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _check(*arguments: str, env: dict[str, str] | None = None) -> int:
    return CliRunner().invoke(app, ["check", *arguments], env=env).exit_code


def test_lookup_reads_the_config_folder(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {NESTED: VALID})
    assert discover_configuration(root)[1] == root / NESTED
    assert _check("--root", str(root)) == 0


@pytest.mark.parametrize("folder", ["shared", "config/tools"])
def test_lookup_ignores_a_folder_that_no_rule_admits(tmp_path: Path, folder: str) -> None:
    root = _consumer(tmp_path, {f"{folder}/onomasia.yml": VALID})
    with pytest.raises(ConfigurationError, match="no configuration"):
        discover_configuration(root)


def test_lookup_reads_the_file_at_the_root_and_in_dot_config(tmp_path: Path) -> None:
    root = _consumer(tmp_path / "a", {"onomasia.yml": INVALID})
    assert discover_configuration(root)[1] == root / "onomasia.yml"
    assert _check("--root", str(root)) == 2
    other = _consumer(tmp_path / "b", {".config/onomasia.yml": VALID})
    assert discover_configuration(other)[1] == other / ".config/onomasia.yml"


def test_two_configuration_files_are_an_error_naming_both(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {NESTED: VALID, "onomasia.yml": VALID})
    with pytest.raises(ConfigurationError):
        discover_configuration(root)
    result = CliRunner().invoke(app, ["build", "--root", str(root)])
    assert result.exit_code == 2
    assert str(root / NESTED) in result.output
    assert str(root / "onomasia.yml") in result.output


def test_named_config_is_read_from_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _consumer(tmp_path / "consumer", {NESTED: INVALID, "settings/other.yml": VALID})
    monkeypatch.chdir(root / "settings")
    assert discover_configuration(root, Path("other.yml"))[1] == root / "settings/other.yml"
    assert _check("-r", str(root), "-c", "other.yml") == 0
    monkeypatch.chdir(tmp_path)
    assert _check("-r", str(root), "-c", "other.yml") == 2


def test_named_absent_config_is_an_error(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"onomasia.yml": VALID})
    with pytest.raises(ConfigurationError):
        discover_configuration(root, root / "absent.yml")
    assert _check("--root", str(root), "--config", str(root / "absent.yml")) == 2


def test_missing_configuration_names_the_places(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="in .config/ or in config/"):
        discover_configuration(tmp_path)
    result = CliRunner().invoke(app, ["build", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "no configuration: write onomasia.yml at the root" in result.output


def test_root_is_found_upwards_from_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _consumer(tmp_path / "consumer", {"onomasia.yml": INVALID, "notes/deep/a.md": "# A\n"})
    monkeypatch.chdir(root / "notes/deep")
    assert discover_configuration()[0] == root.resolve()
    result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 2
    assert "_schema" in result.output


def test_root_is_read_from_the_environment_below_the_option(tmp_path: Path) -> None:
    valid = _consumer(tmp_path / "valid", {"onomasia.yml": VALID})
    invalid = _consumer(tmp_path / "invalid", {"onomasia.yml": INVALID})
    assert _check(env={"ONOMASIA_ROOT": str(valid)}) == 0
    assert _check(env={"ONOMASIA_ROOT": str(invalid)}) == 2
    assert _check("--root", str(valid), env={"ONOMASIA_ROOT": str(invalid)}) == 0


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("records: {}\n", "write _schema: onomasia:configuration@1"),
        ("_schema: onomasia:configuration@9\n", "expected onomasia:configuration@1"),
        ("_schema: 1\n", "expected onomasia:configuration@1"),
        ("schema_version: 1\n", "schema_version: retired; write _schema: onomasia:configuration@1"),
    ],
)
def test_a_file_of_another_format_stops_with_status_2(
    tmp_path: Path, text: str, message: str
) -> None:
    root = _consumer(tmp_path, {"onomasia.yml": text})
    result = CliRunner().invoke(app, ["check", "--root", str(root)])
    assert result.exit_code == 2
    assert message in result.output


def test_the_identifier_of_the_format_is_accepted(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"onomasia.yml": "_schema: onomasia:configuration@1\n"})
    assert CliRunner().invoke(app, ["check", "--root", str(root)]).exit_code == 0
