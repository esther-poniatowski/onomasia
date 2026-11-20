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

- the option `-r`, `--root` names the root of the consumer. Without it, the root is the folder named by the environment variable `ONOMASIA_ROOT`, else the nearest folder, from the current one upwards, holding `onomasia.yml` at one of its places, else the current folder;
- the option `-c`, `--config` names the configuration file. Without it, Onomasia reads `onomasia.yml` at the one place of the root that holds it: the root itself, its subfolder `.config/`, or its subfolder `config/`. Two places holding the file stop the command with an error naming both.

Hodegos resolves the root and the places, as its [specification](https://github.com/esther-poniatowski/hodegos/blob/main/docs/specification.md) states. A configuration kept in another folder, such as `config/tools/`, is not searched, so the consumer names it with `--config` at each invocation.

A path passed to `--config` resolves against the current folder, the file must exist, and it must lie inside the root. A path written in the configuration resolves against the root.

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

The line opens on the resource and the JSON Pointer of the offending value, then gives the severity, the check and the message. The resource is the path of the offending file relative to the root: a record, an input document, or the configuration for an issue of an output. A record of another repository is located as `repository:path`: the identifier of its repository, a colon, and the path of the record within that repository. The path is read at the state selected by the consumer. Only the report of a run writes this form. The documents of the contracts name the repository and the commit in fields of their own. The last line counts the errors and the warnings. The command exits with one of three statuses:

- 0 when no error is reported;
- 1 when an error is reported;
- 2 when the configuration is missing, unreadable, outside the root or invalid.

The option `--format sarif` writes the issues as a findings log in the profile of the gate Elenchos. The log goes to the file named by `--output`, or to the standard output:

```console
onomasia check --root path/to/vault --format sarif --output build/onomasia.sarif
```

Each issue becomes one result of the log. The rule of the result is the check, and its level is the severity of the issue. Its locus is the JSON Pointer of the offending value in a record. A defect in a text takes a typed locus and a line instead. The typed locus `term:<glossary>` or `symbol:<notation>` names the record that declares the entry used. The form matched in the text separates two defects at one locus. With status 2, the log holds a failed run that states why the command could not run.

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

The command prints its issues as `onomasia check` does, followed by one line `wrote <path>` per output written. Its exit statuses and its option `--format sarif` are those of `onomasia check`. When the findings log goes to the standard output, the lines `wrote <path>` go to the standard error. When an error is reported, the build writes no output, so the former outputs stay whole. Otherwise, each output is replaced in one step. A check lowered to `warning` or `off` no longer stops the build: an output that cannot be built is then skipped, and the other outputs are written.

Every output records the sources of its records, read from the Git repository holding the root. When the root lies outside every Git repository, the list of sources is empty. A document also lists under `inputs` each record of another repository imported into its records, with its commit and its digest.

## Importing from another repository

A glossary or a notation of version 2 may import a record of another repository by a logical target, as the [formats](formats.md#^across) state. Onomasia reads the record at the state selected by the consumer, from the Git stores of the machine. A state missing from the machine is reported as the error `unreadable-target-state`, at the import. Therefore, a host fetches the states before its checks:

```console
anagraphe states fetch --root path/to/thesis
onomasia check --root path/to/thesis
```

The cache of the fetched states lies under the cache folder of the user, unless the environment variable `ANAGRAPHE_CACHE` names another folder. A caller of `check_records` or `build_outputs` may pass its own state provider of Anagraphe under the keyword `provider`, such as an in-memory provider in a test. Without one, both functions read the Git stores, through `default_provider()`.

## Printing symbols in figures

Matplotlib mathtext defines no macros, so figure code expands them first. The product `python-expander` writes a module without dependencies, and figure code imports that module without installing Onomasia. The following figure code imports the module written at `notation.py`, and expands a macro before mathtext reads the label:

```python
import matplotlib.pyplot as plt

from notation import expand

figure, axis = plt.subplots()
axis.set_xlabel("$" + expand(r"\onowOut") + "$")
```

The module fixes the typography of the notation at the time of its build. Its constant `SOURCES` records the commit of the records, and whether the working tree held uncommitted changes. Its constant `INPUT_DATA` records each record of another repository imported into the notations, with its commit and its digest.

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
_schema: onomasia:notation@2
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

The function `build_outputs` also accepts a provenance, under the keyword `provenance`, beside the source under the keyword `source`. A provenance is an object whose method `sources` receives the root and the files read by the build, and returns a tuple of `Source`, one per repository behind the records. The class `GitProvenance` marks a source dirty when its commit lacks one of these files, as the [common fields](contracts.md#^common-fields) define it.
