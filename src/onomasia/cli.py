"""
Command-line interface for the `onomasia` package.

Defines commands available via `python -m onomasia` or `onomasia` if installed as a script.

Commands
--------
info : Display diagnostic information.
check : Run every check of a build, and the checks of texts, without writing the outputs.
build : Check the records, then write the declared outputs.

See Also
--------
typer.Typer
    Library for building CLI applications: https://typer.tiangolo.com/
"""

from pathlib import Path

import typer

from . import info, __version__
from .configuration import load_configuration, locate_configuration
from .errors import OnomasiaError
from .issues import Issue, Severity
from .service import build_outputs, check_records

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command("info")
def cli_info() -> None:
    """Display version and platform diagnostics."""
    typer.echo(info())


@app.command("check")
def cli_check(
    root: Path = typer.Option(Path("."), "--root", help="Root of the consumer."),
    config: Path = typer.Option(
        None,
        "--config",
        help="Configuration file; config/tools/onomasia.yml, then onomasia.yml, below the root "
        "by default.",
    ),
) -> None:
    """Run every check of a build and of the texts without writing; exit 1 on an error."""
    try:
        configuration = load_configuration(root, locate_configuration(root, config))
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
        None,
        "--config",
        help="Configuration file; config/tools/onomasia.yml, then onomasia.yml, below the root "
        "by default.",
    ),
) -> None:
    """Check the records, then write the declared outputs, or nothing when an error is reported."""
    try:
        configuration = load_configuration(root, locate_configuration(root, config))
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
        if issue.line is not None:
            location = f"{location}:{issue.line}"
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
