"""
Services of Onomasia on one consumer: the check of its records, and the build of its outputs.

Both services run the same assembly: they load, compose and check the records, read the input
documents, and compute every declared output in memory, which runs the checks of the outputs. The
check stops there, so that a check passes exactly when the build passes. The build then writes the
outputs only when no error was reported, each file replaced in one step, so that a failed build
leaves the former outputs whole.

Classes
-------
BuildResult
    Issues of a build, and the files that it wrote.

Functions
---------
check_records(configuration, source) -> list[Issue]
    Run every check of a consumer without writing any output.
build_outputs(configuration, source, provenance) -> BuildResult
    Check the records of a consumer, then write its declared outputs.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile

import yaml

from .checks import CheckContext, run_record_checks
from .composition import Composer, Composition
from .configuration import Configuration, Output, Product
from .contracts import (
    macro_lookup_document,
    macro_table_document,
    read_scope_table,
    read_signatures,
    term_table_document,
)
from .issues import Issue, IssueSink
from .provenance import GitProvenance, ProvenanceProvider, Source
from .records.model import RecordKind
from .records.validation import SchemaValidator
from .repository import FileRecordSource, RecordSource, load_records, matched_files
from .texts.bindings import AnagrapheBindings, BindingSource
from .texts.checks import TextChecker
from .typography.serializers import serializer
from .typography.table import MacroTable, TargetSignature, build_macro_table


@dataclass(frozen=True)
class BuildResult:
    """
    Issues of a build, and the files that it wrote.

    Attributes
    ----------
    issues : list[Issue]
        Issues found, sorted by resource, then pointer, then check.
    written : tuple[Path, ...]
        Files written, empty when an error was reported.
    """

    issues: list[Issue]
    written: tuple[Path, ...]


def _compositions(composer: Composer, kind: RecordKind) -> list[Composition]:
    """Compose every record of a format, leaving out those on an import cycle."""
    compositions = (composer.compose(kind, record.identifier) for record in composer.records(kind))
    return [composition for composition in compositions if composition is not None]


def _checked(
    configuration: Configuration,
    source: RecordSource | None,
    sink: IssueSink,
    validator: SchemaValidator,
) -> Composer:
    """Load, compose and check the records of a consumer, returning the composer."""
    source = source or FileRecordSource(configuration.root, configuration.records)
    composer = Composer(load_records(source, validator, sink), sink)
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
    return composer


def _sorted(sink: IssueSink) -> list[Issue]:
    """Issues of a sink, each identical issue kept once, sorted by resource, then pointer, then
    line, then check; an issue is reported twice when a macro table checked for the texts is also
    built for an output."""
    return sorted(
        dict.fromkeys(sink.issues),
        key=lambda issue: (issue.resource, issue.pointer, issue.line or 0, issue.check),
    )


def check_records(
    configuration: Configuration,
    source: RecordSource | None = None,
    bindings: BindingSource | None = None,
) -> list[Issue]:
    """
    Run every check of a consumer, those of its outputs included, without writing any output.

    The check is a build that writes nothing: it reads the same inputs and reports the issues of
    `build_outputs`, so that a consumer whose check passes has a build that passes. When the
    consumer declares texts, the check also reads each text against the records bound to it.

    Parameters
    ----------
    configuration : Configuration
        Configuration of the consumer.
    source : RecordSource | None
        Provider of the records, or None to read the files matched by the configuration.
    bindings : BindingSource | None
        Provider of the bindings of the texts, or None to resolve them through Anagraphe.

    Returns
    -------
    list[Issue]
        Issues found, sorted by resource, then pointer, then line, then check.
    """
    sink = IssueSink(configuration.severities)
    composer, signatures, _ = _assemble(configuration, source, (), sink)
    if configuration.texts is not None:
        _check_texts(configuration, composer, signatures, bindings, sink)
    return _sorted(sink)


def _check_texts(
    configuration: Configuration,
    composer: Composer,
    signatures: dict[str, TargetSignature],
    bindings: BindingSource | None,
    sink: IssueSink,
) -> None:
    """Check every text of the consumer against the records bound to it."""
    texts = configuration.texts
    assert texts is not None
    root = configuration.root
    scope = (
        read_scope_table(texts.scope_table, root, SchemaValidator(), sink)
        if texts.scope_table is not None
        else None
    )
    checker = TextChecker(
        texts,
        configuration.vocabulary,
        configuration.typography,
        composer,
        bindings or AnagrapheBindings(root, texts.anagraphe),
        signatures,
        scope,
        sink,
    )
    for resource in matched_files(root, texts.paths, texts.exclude):
        if not checker.binds(resource):
            continue
        try:
            source = (root / resource).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            sink.report("unreadable-text", resource, "", f"cannot read the text: {error}")
            continue
        checker.check(resource, source)


class _Builder:
    """Computation of the outputs of one build, from its composer and its inputs."""

    def __init__(
        self,
        configuration: Configuration,
        composer: Composer,
        signatures: dict[str, TargetSignature],
        sources: tuple[Source, ...],
        sink: IssueSink,
    ) -> None:
        self._configuration = configuration
        self._composer = composer
        self._signatures = signatures
        self._sources = sources
        self._sink = sink

    def _unresolved(self, index: int, key: str, message: str) -> None:
        """Report an output naming a record that the consumer does not hold."""
        self._sink.report(
            "unresolved-output",
            self._configuration.resource,
            f"/build/outputs/{index}/{key}",
            message,
        )

    def _table(self, index: int, output: Output) -> MacroTable | None:
        """Build the macro table of an output: its notations composed, its overlays applied."""
        compositions: list[Composition] = []
        for notation in output.notations:
            composition = self._composer.compose(RecordKind.NOTATION, notation)
            if composition is None:
                self._unresolved(index, "notations", f"no notation {notation}")
                return None
            compositions.append(composition)
        overlays = {
            record.identifier: record for record in self._composer.records(RecordKind.OVERLAY)
        }
        for name in output.overlays:
            overlay = overlays.get(name)
            if overlay is None or overlay.overlays not in output.notations:
                self._unresolved(
                    index, "overlays", f"no overlay {name} of the notations of the output"
                )
                return None
            position = output.notations.index(overlay.overlays or "")
            applied = self._composer.apply_overlay(overlay, compositions[position])
            if applied is not None:
                compositions[position] = applied
        return build_macro_table(
            compositions,
            output.overlays,
            self._signatures,
            self._configuration.typography,
            self._sink,
        )

    def content(self, index: int, output: Output) -> str | None:
        """Compute the text of one output, or None when it cannot be built."""
        if output.product is Product.TERM_TABLE:
            composition = self._composer.compose(RecordKind.GLOSSARY, output.glossary or "")
            if composition is None:
                self._unresolved(index, "glossary", f"no glossary {output.glossary}")
                return None
            document = term_table_document(
                composition, self._sources, self._configuration.vocabulary.default_status
            )
            return yaml.safe_dump(document, allow_unicode=True, sort_keys=False)
        table = self._table(index, output)
        if table is None:
            return None
        if output.product is Product.MACRO_TABLE:
            return yaml.safe_dump(
                macro_table_document(table, self._sources), allow_unicode=True, sort_keys=False
            )
        if output.product is Product.MACRO_LOOKUP:
            return yaml.safe_dump(
                macro_lookup_document(table, self._sources), allow_unicode=True, sort_keys=False
            )
        return serializer(output.product)(table, self._sources, output.path)


def _write(path: Path, text: str) -> None:
    """Write a file in one step, through a temporary file of the same folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(temporary, path)


def _assemble(
    configuration: Configuration,
    source: RecordSource | None,
    sources: tuple[Source, ...],
    sink: IssueSink,
) -> tuple[Composer, dict[str, TargetSignature], list[tuple[Path, str | None]]]:
    """Check the records, read the inputs, and compute the text of each output, writing nothing;
    return the composer and the signatures, for the checks of texts."""
    validator = SchemaValidator()
    composer = _checked(configuration, source, sink, validator)
    signatures = read_signatures(
        configuration.build.denotes_targets, configuration.root, validator, sink
    )
    builder = _Builder(configuration, composer, signatures, sources, sink)
    contents = [
        (output.path, builder.content(index, output))
        for index, output in enumerate(configuration.build.outputs)
    ]
    return composer, signatures, contents


def build_outputs(
    configuration: Configuration,
    source: RecordSource | None = None,
    provenance: ProvenanceProvider | None = None,
) -> BuildResult:
    """
    Check the records of a consumer, then write its declared outputs.

    Parameters
    ----------
    configuration : Configuration
        Configuration of the consumer, whose section `build` declares the outputs.
    source : RecordSource | None
        Provider of the records, or None to read the files matched by the configuration.
    provenance : ProvenanceProvider | None
        Provider of the sources of the records, or None to read the Git repository of the root.

    Returns
    -------
    BuildResult
        Issues found, and the files written, none when an error was reported.
    """
    sink = IssueSink(configuration.severities)
    sources = (provenance or GitProvenance()).sources(configuration.root)
    _, _, contents = _assemble(configuration, source, sources, sink)
    if sink.has_errors():
        return BuildResult(_sorted(sink), ())
    written: list[Path] = []
    for path, text in contents:
        if text is not None:
            _write(path, text)
            written.append(path)
    return BuildResult(_sorted(sink), tuple(written))
