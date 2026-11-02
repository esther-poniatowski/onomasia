"""
Check of the records of one consumer: loading, composition, and the record checks.

Functions
---------
check_records(configuration, source) -> list[Issue]
    Load, compose and check the records of a consumer.
"""

from .checks import CheckContext, run_record_checks
from .composition import Composer, Composition
from .configuration import Configuration
from .issues import Issue, IssueSink
from .records.model import RecordKind
from .records.validation import SchemaValidator
from .repository import FileRecordSource, RecordSource, load_records


def _compositions(composer: Composer, kind: RecordKind) -> list[Composition]:
    """Compose every record of a format, leaving out those on an import cycle."""
    compositions = (composer.compose(kind, record.identifier) for record in composer.records(kind))
    return [composition for composition in compositions if composition is not None]


def check_records(configuration: Configuration, source: RecordSource | None = None) -> list[Issue]:
    """
    Load, compose and check the records of a consumer.

    Parameters
    ----------
    configuration : Configuration
        Configuration of the consumer.
    source : RecordSource | None
        Provider of the records, or None to read the files matched by the configuration.

    Returns
    -------
    list[Issue]
        Issues found, sorted by resource, then pointer, then check.
    """
    sink = IssueSink(configuration.severities)
    source = source or FileRecordSource(configuration.root, configuration.records)
    composer = Composer(load_records(source, SchemaValidator(), sink), sink)
    notations = _compositions(composer, RecordKind.NOTATION)
    for overlay in composer.records(RecordKind.OVERLAY):
        applied = composer.apply_overlay(overlay)
        if applied is not None:
            notations.append(applied)
    context = CheckContext(
        glossaries=tuple(_compositions(composer, RecordKind.GLOSSARY)),
        notations=tuple(notations),
        vocabulary=configuration.vocabulary,
        typography=configuration.typography,
        sink=sink,
    )
    run_record_checks(context)
    return sorted(sink.issues, key=lambda issue: (issue.resource, issue.pointer, issue.check))
