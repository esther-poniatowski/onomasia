"""
Command-line interface for the `onomasia` package.

Defines commands available via `python -m onomasia` or `onomasia` if installed as a script.

Commands
--------
info : Display diagnostic information.
check : Run every check of a build, and the checks of texts, without writing the outputs.
build : Check the records, then write the declared outputs.

Both commands take the root from `--root`, else from `ONOMASIA_ROOT`, else from the nearest folder,
from the current one upwards, holding a configuration, else from the current folder. A path named by
`--config` is read from the current folder. Both commands report their issues as text lines, or with
`--format sarif` as a findings log in the profile of the gate Elenchos, written to `--output` or to
the standard output.

See Also
--------
typer.Typer
    Library for building CLI applications: https://typer.tiangolo.com/
"""

import json
from pathlib import Path

import typer

from . import info, __version__
from .configuration import Configuration, discover_configuration, load_configuration
from .errors import OnomasiaError
from .findings import sarif_log
from .issues import Issue, Severity
from .service import build_outputs, check_records, default_provider

app = typer.Typer(add_completion=False, no_args_is_help=True)

ROOT_HELP = (
    "Root of the consumer; by default the folder of ONOMASIA_ROOT, else the nearest folder, from "
    "the current one upwards, holding a configuration, else the current folder."
)
CONFIG_HELP = (
    "Configuration file, relative to the current folder; by default onomasia.yml at the root, in "
    ".config/, or in config/."
)
FORMAT_HELP = "Report format: `text`, or `sarif` for a findings log in the profile of Elenchos."
OUTPUT_HELP = "File of the report; standard output by default."
FORMATS = ("text", "sarif")
"""Formats of the report of the issues."""
EXIT_STOPPED = 2
"""Exit status of a command that cannot run."""


def _report(
    issues: list[Issue],
    output_format: str,
    output: Path | None,
    stopped: str = "",
) -> None:
    """Write the report of a run: text lines, or a findings log naming `stopped` when the run
    could not start."""
    if output_format == "sarif":
        log = sarif_log(issues, stopped or None)
        text = json.dumps(log, indent=2, ensure_ascii=False) + "\n"
    elif stopped:
        typer.echo(f"error: {stopped}", err=True)
        return
    else:
        text = "\n".join(_lines(issues)) + "\n"
    if output is None:
        typer.echo(text, nl=False)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def _checked_format(output_format: str) -> None:
    """Stop with status 2 on a format that the commands do not write."""
    if output_format not in FORMATS:
        typer.echo(f"error: --format takes text or sarif, not {output_format}", err=True)
        raise typer.Exit(EXIT_STOPPED)


def _configuration(root: Path | None, config: Path | None) -> Configuration:
    """Configuration of the consumer at the root given or found, from the file named or found."""
    resolved, path = discover_configuration(root, config)
    return load_configuration(resolved, path)


@app.command("info")
def cli_info() -> None:
    """Display version and platform diagnostics."""
    typer.echo(info())


@app.command("check")
def cli_check(
    root: Path | None = typer.Option(None, "--root", "-r", help=ROOT_HELP),
    config: Path | None = typer.Option(None, "--config", "-c", help=CONFIG_HELP),
    output_format: str = typer.Option("text", "--format", help=FORMAT_HELP),
    output: Path | None = typer.Option(None, "--output", "-o", help=OUTPUT_HELP),
) -> None:
    """Run every check of a build and of the texts without writing; exit 1 on an error."""
    _checked_format(output_format)
    try:
        configuration = _configuration(root, config)
        issues = check_records(configuration, provider=default_provider())
    except OnomasiaError as error:
        _report([], output_format, output, str(error))
        raise typer.Exit(EXIT_STOPPED) from error
    _report(issues, output_format, output)
    if any(issue.severity is Severity.ERROR for issue in issues):
        raise typer.Exit(1)


@app.command("build")
def cli_build(
    root: Path | None = typer.Option(None, "--root", "-r", help=ROOT_HELP),
    config: Path | None = typer.Option(None, "--config", "-c", help=CONFIG_HELP),
    output_format: str = typer.Option("text", "--format", help=FORMAT_HELP),
    output: Path | None = typer.Option(None, "--output", "-o", help=OUTPUT_HELP),
) -> None:
    """Check the records, then write the declared outputs, or nothing when an error is reported."""
    _checked_format(output_format)
    try:
        configuration = _configuration(root, config)
        result = build_outputs(configuration, provider=default_provider())
    except OnomasiaError as error:
        _report([], output_format, output, str(error))
        raise typer.Exit(EXIT_STOPPED) from error
    _report(list(result.issues), output_format, output)
    for path in result.written:
        typer.echo(f"wrote {path}", err=output_format == "sarif" and output is None)
    if any(issue.severity is Severity.ERROR for issue in result.issues):
        raise typer.Exit(1)


def _lines(issues: list[Issue]) -> list[str]:
    """Write each issue on one line, then the counts of errors and warnings."""
    lines = []
    for issue in issues:
        location = f"{issue.resource}#{issue.pointer}" if issue.pointer else issue.resource
        if issue.line is not None:
            location = f"{location}:{issue.line}"
        lines.append(f"{location}: {issue.severity.value} {issue.check}: {issue.message}")
    errors = sum(issue.severity is Severity.ERROR for issue in issues)
    lines.append(f"{errors} errors, {len(issues) - errors} warnings")
    return lines


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
