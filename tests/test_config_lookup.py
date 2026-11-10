"""
Tests of the lookup of the configuration file below the root of a consumer.

Without `--config`, a command reads `config/tools/onomasia.yml` below the root, then
`onomasia.yml`. A named `--config` is read as before the lookup.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from onomasia.cli import app
from onomasia.configuration import locate_configuration
from onomasia.errors import ConfigurationError

VALID = "schema_version: 1\n"
"""Configuration that `onomasia check` reads with no error."""
INVALID = "schema_version: 99\n"
"""Configuration that `onomasia check` rejects, with exit status 2."""
NESTED = Path("config/tools/onomasia.yml")


def _consumer(root: Path, files: dict[Path | str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _check(*arguments: str) -> int:
    return CliRunner().invoke(app, ["check", *arguments]).exit_code


def test_lookup_prefers_the_file_of_config_tools(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {NESTED: VALID, "onomasia.yml": INVALID})
    assert locate_configuration(root) == root / NESTED
    assert _check("--root", str(root)) == 0


def test_lookup_falls_back_on_the_file_at_the_root(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {"onomasia.yml": INVALID})
    assert locate_configuration(root) == root / "onomasia.yml"
    assert _check("--root", str(root)) == 2


def test_named_config_is_read_unchanged(tmp_path: Path) -> None:
    root = _consumer(tmp_path, {NESTED: INVALID, "onomasia.yml": VALID})
    named = root / "onomasia.yml"
    assert locate_configuration(root, named) == named
    assert _check("--root", str(root), "--config", str(named)) == 0


def test_missing_configuration_names_both_places(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="config/tools/onomasia.yml or onomasia.yml"):
        locate_configuration(tmp_path)
    result = CliRunner().invoke(app, ["build", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "no configuration at config/tools/onomasia.yml or onomasia.yml" in result.output
