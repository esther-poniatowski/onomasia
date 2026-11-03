---
tags:
  - specification
index: "[Onomasia documentation](docs/_index.md)"
aliases:
  - Contracts
---
# Contracts

The contracts of Onomasia fix the documents exchanged between Onomasia and the other tools. Onomasia writes three documents and three serializations of its macros. Onomasia reads one document, the denotes targets, and specifies a second one, the scope table, for the checks of texts to come. The fields of each document are defined by a schema in the package folder `data/schemas`. This specification states their meaning. The [decision on formats and contracts](adr/formats-and-contracts.md) records the reason for each choice.

| Contract | Producer | Consumers | Schema |
| --- | --- | --- | --- |
| `onomasia:denotes-targets@1` | Gnomon | Onomasia | `denotes-targets.schema.yml` |
| `onomasia:scope-table@1` | Ekthesis | the checks of texts of Onomasia, not yet implemented | `scope-table.schema.yml` |
| `onomasia:macro-table@1` | Onomasia | Gnomon | `macro-table.schema.yml` |
| `onomasia:macro-lookup@1` | Onomasia | the views of Gnomon, the documents rendered by Ekthesis | `macro-lookup.schema.yml` |
| `onomasia:term-table@1` | Onomasia | Hermeneia | `term-table.schema.yml` |

## Common fields

Every document names its contract under `contract`, and the records behind it under `sources`. Each item of `sources` describes one repository by three fields:

- `repository`, the location of the repository;
- `commit`, the full identifier of its commit;
- `dirty`, true when its working tree held uncommitted changes.

With these fields, a build records the commit of the notation used. When the root of the consumer lies in no Git repository, `sources` is empty. An input document breaking its schema is reported by the check `invalid-contract`, at the document itself. ^common-fields

## Inputs

The *denotes targets* list the [units](formats.md#^meaning) whose arguments Onomasia reads. Each unit declares three properties of its arguments:

- `arity`, the number of its arguments;
- `binder`, the position, counted from 1, of the argument binding a variable;
- `variadic`, true for an operator taking a list of items.

A unit absent from every document takes no argument, and passes unreported. For example, an entry designating the block anchor of a note takes no argument. When several documents name one unit, the later document wins. The producer gives a variadic unit the arity 1, since its items travel in one argument; Onomasia copies the arity without checking it. ^denotes-targets

The *scope table* maps each audience to its `ancestors` and its `descendants`. Ekthesis decides which audiences are related, and the checks of texts will apply the table as written. A lexical rule scoped to an audience will bind a text when that audience appears in the row of the audience of the text, in three cases:

- the rule audience is the audience of the text;
- the rule audience is an ancestor of the audience of the text;
- the rule audience is a descendant of the audience of the text.

An audience absent from the table relates to itself only. No key of the configuration names the scope table yet. ^scope-table

## Macro table

The macro table holds one macro per entry of the notations composed for an output, their overlays applied. The table names those notations under `notations` and those overlays under `overlays`, and lists its macros under `entries`, sorted by name. Each macro states the fields of its entry and of its target:

| Field | Content |
| --- | --- |
| `id` | the identifier of the entry |
| `notation` | the record of the printed form: the notation declaring the entry, or the overlay that changed the entry |
| `target` | the unit denoted by the entry, or null |
| `name`, `body` | the macro name, and the TeX printed |
| `arity`, `binder` | the number of mandatory arguments, and the position of the binding argument |
| `entry` | true when the macro takes the entry argument |
| `separator` | the string joining the items of a variadic operator |
| `class` | the typographic class of the entry |

^macro-table

The parameters of a body depend on the entry argument:

- when `entry` is true, the parameter `#1` holds the entry argument, optional with an empty default, and the mandatory arguments follow from `#2`;
- otherwise, the mandatory arguments start at `#1`.

MathJax cannot test whether an optional argument was supplied. Therefore, the body must print correctly with an empty entry argument. A variadic macro receives its items in its one argument, joined by its separator. ^parameters

A derived name is built from the identifier of its entry in three steps:

- the prefix `typography.macro_prefix` of the [configuration](configuration.md), `ono` by default, is written first;
- each hyphen is removed, and the letter after it is capitalized;
- each digit is replaced by its word.

The identifier `w-out` gives `onowOut`, and `sigma2` gives `onosigmaTwo`. A declared name never starts with that prefix. Within one table, three properties hold:

- each name is unique;
- each unit is denoted by one entry at most;
- no body calls itself through the bodies of other macros.

Both commands check these properties, and the [catalog of checks](formats.md#^checks) names the checks run. ^names

## Macro lookup

The macro lookup names its notations under `notations`, and maps each unit, under `targets`, to the macro name to be written for it by a view. A view is a note generated from records. Such a note writes macro names instead of printed forms. An undeclared entry has no row. An overlay keeps every name and every target, so a lookup built under overlays is identical to the lookup of its notations. The check `ambiguous-target` guarantees one name per unit, since a view could not choose between two names. ^lookup

## Term table

The term table gives Hermeneia the terms of one composed glossary, named under `glossary`. The table lists its terms under `terms`, sorted by identifier, and each term states four fields:

- `id`, its identifier;
- `forms`, its label, its other forms and the labels of its alternatives;
- `status`, its status, the default status standing for an absent one;
- `gloss`, the text of its gloss with the `resource` declaring the term and the JSON Pointer of the gloss.

With this location, Hermeneia reports a defect of a gloss at its declaration. ^term-table

## Serializations

Each serialization renders one macro table, and defines each macro once. The three serializations differ in their medium:

- **LaTeX package**: each macro becomes `\newcommand{\name}[n]{body}`, or `\newcommand{\name}[n][]{body}` when it takes the entry argument, `n` being its number of parameters. The part `[n]` is left out when `n` is 0. Since `\newcommand` refuses an existing command, a declared name overwriting a command stops the build of the document.
- **MathJax preamble**: the same definitions, without the lines `\NeedsTeXFormat` and `\ProvidesPackage`, for a preamble plugin of Obsidian.
- **Python expander**: a generated module without dependencies. Its function `expand` replaces each macro of a mathtext string by its body, its arguments substituted, until no macro remains. A mandatory argument is a braced group, a control sequence or one character, after optional spaces. The entry argument stands between brackets after the name. The constant `SOURCES` of the module holds the sources of the table.

The package and the preamble state their sources in their first line, a comment reading "no recorded source" when `sources` is empty. ^serializations

## Versioning

Each contract carries its own version. Adding an optional field keeps the version. Every other change starts the next version: removing, renaming or adding a required field, or admitting a new value. ^versioning
