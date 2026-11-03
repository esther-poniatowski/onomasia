---
tags:
  - specification
index: "[Onomasia documentation](docs/_index.md)"
aliases:
  - Configuration
---
# Configuration

Each consumer holds its configuration in the file `onomasia.yml` at its root. The configuration holds every value needed by Onomasia from the consumer, and its five sections answer five questions:

- where the records of the consumer live;
- which value sets the records use;
- how the symbols are named and printed;
- which outputs the build writes;
- how severely each check reports.

The packaged file `data/defaults.yml` supplies the vocabulary, the typography and the severities of a consumer that declares none. Onomasia stops at the first invalid value of the configuration, and names its key path. The following values are rejected:

- a file lying outside the root of the consumer;
- a `schema_version` other than 1;
- an unknown key, a missing required key, or a value of the wrong type;
- a `default_status` absent from the statuses;
- `digit_names` other than ten words of letters;
- a check absent from the catalog, or a severity other than `error`, `warning` and `off`.

## Keys

The file declares `schema_version: 1`, then five optional sections, whose keys are the following:

| Key | Content | Default |
| --- | --- | --- |
| `records.glossaries`, `records.notations`, `records.overlays` | the globs of the records of each format, relative to the root | no record |
| `records.exclude` | the globs or folders left out of every format | none |
| `vocabulary.statuses` | each status, with `requires_replacement` | `candidate`, `in-use`, `ratified`, `deprecated`; only `deprecated` requires a replacement |
| `vocabulary.default_status` | the status of an entry declaring none | `in-use` |
| `vocabulary.contexts` | each dimension of the contexts, with its values | no dimension |
| `vocabulary.relations` | the relations admitted between terms | `narrows`, `broadens` |
| `typography.base_placeholder` | the placeholder of the base in a template | `{{base}}` |
| `typography.macro_prefix` | the prefix of derived macro names | `ono` |
| `typography.digit_names` | the ten words replacing the digits 0 to 9 in a derived name | `Zero` to `Nine` |
| `typography.maximum_parameters` | the largest number of parameters of a macro | 9 |
| `build.denotes_targets` | the documents of denotes targets read by the build, relative to the root | none |
| `build.outputs` | the outputs to write | none |
| `checks.<check>` | the severity of a check: `error`, `warning` or `off` | the severity in the catalog |

A section `vocabulary` or `typography` replaces the packaged section as a whole. Therefore, a consumer declaring its own vocabulary declares all of it. The section `checks` changes only the checks named in it.

## Outputs

Each output names its product under `product` and its file under `path`, relative to the root. The other keys of an output depend on its product:

- a term table names its glossary under `glossary`;
- every other product names its notations under `notations`, composed in order, and may name overlays under `overlays`, each overlay changing one of those notations.

The six products are the following:

| Product | Content |
| --- | --- |
| `macro-table` | the document `onomasia:macro-table@1` |
| `macro-lookup` | the document `onomasia:macro-lookup@1` |
| `term-table` | the document `onomasia:term-table@1` |
| `latex-package` | a LaTeX package named after its file |
| `mathjax-preamble` | the definitions of the macros, for a preamble plugin of Obsidian |
| `python-expander` | a Python module expanding the macros in mathtext |

The [contracts](contracts.md) specify each product.

The following configuration reads the records of a vault, and writes a package and a lookup. The configuration also leaves the archive of the vault out, and turns one check off:

```yaml
schema_version: 1
records:
  glossaries: ["**/glossary.yml"]
  notations: ["**/notation.yml"]
  exclude: [archive]
build:
  denotes_targets: [build/gnomon/denotes-targets.yml]
  outputs:
    - {product: latex-package, notations: [mixture], path: build/onomasia/mixture.sty}
    - {product: macro-lookup, notations: [mixture], path: build/onomasia/lookup.yml}
checks:
  undeclared-entry: off
```
