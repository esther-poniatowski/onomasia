"""
Command-line interface for the `onomasia` package.

Defines commands available via `python -m onomasia` or `onomasia` if installed as a script.

Commands
--------
info : Display diagnostic information.
check : Check the records of a consumer.
build : Check the records, then write the declared outputs.

See Also
--------
typer.Typer
    Library for building CLI applications: https://typer.tiangolo.com/
"""

from pathlib import Path

import typer

from . import info, __version__
from .configuration import load_configuration
from .errors import OnomasiaError
from .issues import Issue, Severity
from .service import build_outputs, check_records

app = typer.Typer(add_completion=False, no_args_is_help=True)

CONFIGURATION_FILE = "onomasia.yml"
"""Name of the configuration file read at the root when none is passed."""


@app.command("info")
def cli_info() -> None:
    """Display version and platform diagnostics."""
    typer.echo(info())


@app.command("check")
def cli_check(
    root: Path = typer.Option(Path("."), "--root", help="Root of the consumer."),
    config: Path = typer.Option(
        None, "--config", help="Configuration file, onomasia.yml at the root by default."
    ),
) -> None:
    """Check the records of a consumer; exit 1 when an error is reported."""
    try:
        configuration = load_configuration(root, config or root / CONFIGURATION_FILE)
        issues = check_records(configuration)
    except OnomasiaError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(2) from error
    _print(issues)
    if any(issue.severity is Severity.ERROR for issue in issues):
        raise typer.Exit(1)


@app.command("build")
def cli_build(
    root: Path = typer.Option(Path("."), "--root", help="Root of the consumer."),
    config: Path = typer.Option(
        None, "--config", help="Configuration file, onomasia.yml at the root by default."
    ),
) -> None:
    """Check the records, then write the declared outputs, or nothing when an error is reported."""
    try:
        configuration = load_configuration(root, config or root / CONFIGURATION_FILE)
        result = build_outputs(configuration)
    except OnomasiaError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(2) from error
    _print(result.issues)
    for path in result.written:
        typer.echo(f"wrote {path}")
    if any(issue.severity is Severity.ERROR for issue in result.issues):
        raise typer.Exit(1)


def _print(issues: list[Issue]) -> None:
    """Print each issue on one line, then the counts of errors and warnings."""
    for issue in issues:
        location = f"{issue.resource}#{issue.pointer}" if issue.pointer else issue.resource
        typer.echo(f"{location}: {issue.severity.value} {issue.check}: {issue.message}")
    errors = sum(issue.severity is Severity.ERROR for issue in issues)
    typer.echo(f"{errors} errors, {len(issues) - errors} warnings")


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show the package version and exit."
    )
) -> None:
    """Root command for the package command-line interface."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()
