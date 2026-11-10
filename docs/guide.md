---
tags:
  - guide
index: "[Onomasia documentation](docs/_index.md)"
aliases:
  - Onomasia guide
---
# Using Onomasia

A consumer of Onomasia checks its glossaries and notations, then builds the macros that print its symbols in LaTeX, in Obsidian and in figures. This guide assumes two prerequisites:

- an environment holding Onomasia, installed as [the contribution guidelines](../CONTRIBUTING.md) describe;
- a [configuration](configuration.md) at the root of the consumer.

## Locating the consumer

Both commands of Onomasia read one consumer, located by two options:

- the option `--root` names the root of the consumer, the current folder by default;
- the option `--config` names the configuration file. Without it, Onomasia reads `config/tools/onomasia.yml` below the root, and otherwise `onomasia.yml` at the root.

A path passed to `--config` resolves against the current folder, and the file must lie inside the root.

## Checking the records

Before building, a consumer finds the defects of its records and of its outputs. The command `onomasia check` runs every check of a build, then the checks of texts, as the [catalog of checks](formats.md#^checks) lists them, and writes no output. Therefore, when the check of a consumer passes, its build passes. The following command checks a vault:

```console
onomasia check --root path/to/vault
```

Each issue prints on one line, as in the following output:

```text
notes/notation.yml#/entries/lam: warning undeclared-entry: the entry denotes no unit
0 errors, 1 warnings
```

The line opens on the resource and the JSON Pointer of the offending value, then gives the severity, the check and the message. The resource is the path of the offending file relative to the root: a record, an input document, or the configuration for an issue of an output. The last line counts the errors and the warnings. The command exits with one of three statuses:

- 0 when no error is reported;
- 1 when an error is reported;
- 2 when the configuration is missing, unreadable, outside the root or invalid.

## Checking the texts

A consumer declaring the section `texts` of its configuration checks its texts too, with the same command `onomasia check`. Each text is checked against the glossaries, the notations and the audiences bound to it. Anagraphe resolves these bindings along the directory chain, so a text declares them in its frontmatter, or inherits them from the index of an enclosing folder. The section `bindings` of the Anagraphe configuration names the key of each role:

```yaml
bindings:
  index: _index.md
  roles:
    onomasia.glossary: {key: glossary}
    onomasia.notation: {key: notation}
    onomasia.audiences: {key: audiences}
```

Only a text bound to a glossary or a notation is read and checked. Before its prose is matched, the regions of the kinds listed under `texts.masked` are masked through Merismos: by default its frontmatter, its code, its mathematics and the destinations of its links. A wikilink without an alias displays its destination, so that destination stays prose. No form spans a masked region. The checks of texts report eight kinds of issue:

| Check | Issue |
| --- | --- |
| `forbidden-form` | a form forbidden by a lexical rule binding the text, outside the exceptions of the rule |
| `frame-mismatch` | a term written outside every frame admitted for it |
| `term-status` | a term whose status reports its use in texts, with its replacement |
| `entry-status` | the macro of a notation entry whose status reports its use, or its printed body taking no parameter, with the macro of its replacement |
| `unknown-macro` | a macro under the reserved prefix that the bound notations do not define |
| `raw-printed-form` | the printed body of an entry whose use is admitted, holding a control sequence and taking no parameter, written instead of its macro |
| `unresolved-text-binding` | a binding naming a glossary or a notation that no record holds, reported at its declaration |
| `unreadable-text` | a text that cannot be read as UTF-8 |

Each issue of a text prints its line after the resource, as in `notes/a.md:6: error forbidden-form: …`. The status of a term, an entry or a rule caps the severity of its issue below the severity of its check, as its [effect on texts](formats.md#^statuses) states. A declaration that Anagraphe cannot read, and a text that the Anagraphe configuration requires to be bound, are reported by the check of Anagraphe. ^texts

## Building the outputs

To print its symbols, a consumer writes the outputs declared under the key `build` of its configuration. The command `onomasia build` runs the checks of the records and of the outputs, then writes the outputs:

```console
onomasia build --root path/to/vault
```

The command prints its issues as `onomasia check` does, followed by one line `wrote <path>` per output written. Its exit statuses are those of `onomasia check`. When an error is reported, the build writes no output, so the former outputs stay whole. Otherwise, each output is replaced in one step. A check lowered to `warning` or `off` no longer stops the build: an output that cannot be built is then skipped, and the other outputs are written.

Every output records the sources of its records, read from the Git repository holding the root. When the root lies outside every Git repository, the list of sources is empty.

## Printing symbols in figures

Matplotlib mathtext defines no macros, so figure code expands them first. The product `python-expander` writes a module without dependencies, and figure code imports that module without installing Onomasia. The following figure code imports the module written at `notation.py`, and expands a macro before mathtext reads the label:

```python
import matplotlib.pyplot as plt

from notation import expand

figure, axis = plt.subplots()
axis.set_xlabel("$" + expand(r"\onowOut") + "$")
```

The module fixes the typography of the notation at the time of its build. Its constant `SOURCES` records the commit of the records, and whether the working tree held uncommitted changes.

## Supplying records from another source

A consumer holding its records outside files passes a source of its own to the functions `check_records` and `build_outputs`. The source is an object whose method `documents` yields one `RawDocument` per record, with three fields:

- its resource, the name reported in the location of each issue;
- its text, the YAML of the record;
- its expected format, a member of `RecordKind`.

The following source serves notations held in a mapping from resources to texts:

```python
from pathlib import Path

from onomasia import RawDocument, RecordKind, check_records, default_configuration

NOTATION = """
_schema: onomasia:notation@1
id: store
entries:
  lam: {gloss: a free parameter, body: '\\lambda'}
"""


class Store:
    def __init__(self, texts):
        self.texts = texts

    def documents(self):
        for resource, text in self.texts.items():
            yield RawDocument(resource, text, RecordKind.NOTATION)


issues = check_records(default_configuration(Path(".")), Store({"store/notation.yml": NOTATION}))
```

The function `build_outputs` also accepts a provenance, under the keyword `provenance`, beside the source under the keyword `source`. A provenance is an object whose method `sources` receives the root and returns a tuple of `Source`, one per repository behind the records.
