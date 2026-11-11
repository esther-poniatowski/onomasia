"""
Tests of the resolution of the root of a consumer and of its configuration file.

The root is the folder given by `--root`, else by `ONOMASIA_ROOT`, else the nearest folder, from
the current one upwards, holding `config/tools/onomasia.yml` or `onomasia.yml`, else the current
folder. Without `--config`, a command reads the one of both files that exists below the root, and
both existing is an error. A named `--config` is read from the current folder.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from onomasia.cli import app
from onomasia.configuration import find_root, locate_configuration
from onomasia.errors import ConfigurationError

VALID = "_schema: onomasia:configuration@1\n"
"""Configuration that `onomasia check` reads with no error."""
INVALID = "_schema: onomasia:configuration@99\n"
"""Configuration that `onomasia check` rejects, with exit status 2."""
NESTED = Path("config/tools/onomasia.yml")


def _consumer(root: Path, files: dict[Path | str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _check(*arguments: str, env: dict[str, str] | None = None) -> int:
    return CliRunner().invoke(app, ["check", *arguments], env=env).exit_code


def test_lookup_reads_the_file_of_config_tools(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {NESTED: VALID})
    assert locate_configuration(root) == root / NESTED
    assert _check("--root", str(root)) == 0


def test_lookup_reads_the_file_at_the_root(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"onomasia.yml": INVALID})
    assert locate_configuration(root) == root / "onomasia.yml"
    assert _check("--root", str(root)) == 2


def test_two_configuration_files_are_an_error_naming_both(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {NESTED: VALID, "onomasia.yml": VALID})
    with pytest.raises(ConfigurationError, match="two configuration files"):
        locate_configuration(root)
    result = CliRunner().invoke(app, ["build", "--root", str(root)])
    assert result.exit_code == 2
    assert str(root / NESTED) in result.output
    assert str(root / "onomasia.yml") in result.output


def test_named_config_is_read_from_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _consumer(tmp_path / "consumer", {NESTED: INVALID, "settings/other.yml": VALID})
    monkeypatch.chdir(root / "settings")
    assert locate_configuration(root, Path("other.yml")) == root / "settings/other.yml"
    assert _check("-r", str(root), "-c", "other.yml") == 0
    monkeypatch.chdir(tmp_path)
    assert _check("-r", str(root), "-c", "other.yml") == 2


def test_named_absent_config_is_an_error(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {NESTED: VALID})
    with pytest.raises(ConfigurationError, match="no configuration file"):
        locate_configuration(root, root / "absent.yml")
    assert _check("--root", str(root), "--config", str(root / "absent.yml")) == 2


def test_missing_configuration_names_both_places(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="config/tools/onomasia.yml or onomasia.yml"):
        locate_configuration(tmp_path)
    result = CliRunner().invoke(app, ["build", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "no configuration at config/tools/onomasia.yml or onomasia.yml" in result.output


def test_root_is_found_upwards_from_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _consumer(tmp_path / "consumer", {NESTED: INVALID, "notes/deep/a.md": "# A\n"})
    assert find_root(root / "notes/deep") == root.resolve()
    assert find_root(tmp_path) == tmp_path.resolve()
    monkeypatch.chdir(root / "notes/deep")
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
