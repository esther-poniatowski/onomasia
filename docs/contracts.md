---
tags:
  - specification
index: "[Onomasia documentation](docs/_index.md)"
aliases:
  - Contracts
---
# Contracts

The contracts of Onomasia fix the documents exchanged between Onomasia and the other tools. Onomasia writes three documents and three serializations of its macros. Onomasia reads two documents: the denotes targets for its macros, and the scope table for the checks of texts. The fields of each document are defined by a schema in the package folder `data/schemas`. This specification states their meaning. The [decision on formats and contracts](adr/formats-and-contracts.md) records the reason for each choice.

| Contract | Producer | Consumers | Schema |
| --- | --- | --- | --- |
| `onomasia:denotes-targets@3` | Gnomon | Onomasia | `denotes-targets.schema.yml` |
| `onomasia:scope-table@1` | Ekthesis | the checks of texts of Onomasia | `scope-table.schema.yml` |
| `onomasia:macro-table@2` | Onomasia | Gnomon | `macro-table.schema.yml` |
| `onomasia:macro-lookup@2` | Onomasia | the views of Gnomon, the documents rendered by Ekthesis | `macro-lookup.schema.yml` |
| `onomasia:term-table@1` | Onomasia | Hermeneia | `term-table.schema.yml` |

## Common fields

Every document names its contract under `contract`, and the records behind it under `sources`. Each item of `sources` describes one repository by three fields:

- `repository`, the location of the repository, without the user information that a remote URL may hold;
- `commit`, the full identifier of its commit;
- `dirty`, true when its working tree held uncommitted changes.

With these fields, a build records the commit of the notation used. When the root of the consumer lies in no Git repository, `sources` is empty. Onomasia validates an input document in two parts. The check `invalid-contract` reports a header breaking the schema or naming another contract, and Onomasia skips the whole document. The check `invalid-item` reports an item breaking the schema, at that item, and Onomasia skips the item only. ^common-fields

A document written by Onomasia also lists under `inputs` each record of another repository [imported](formats.md#^across) by its records. Each item of `inputs` describes one record by four fields:

- `repository`, the identifier of its repository;
- `commit`, the commit selected by the resolution context of the consumer;
- `id`, the identifier of the record;
- `sha256`, the digest of the bytes of the record at that commit.

The items follow the order of the repository, then the commit, then the identifier. The block is optional. When the records of a document import from no other repository, the document omits the block. ^inputs

Every document written by Onomasia names a unit by a *normalized* logical target `{repository, id, unit}`, with its repository filled in. A reader of the document may lie in another repository. The denotes targets, read by Onomasia, may omit `repository`, so that their producer needs no identifier of the repository. ^targets

## Inputs

The *denotes targets* list the [units](formats.md#^meaning), each under `target` as a logical target, with the facts of its domain. A target without `repository` names a unit of the consumer, so Onomasia normalizes it by the identifier of the consumer. Onomasia then matches a unit with an entry by their normalized targets, never by a text. Each unit declares three facts, none of them typographic:

- `arguments`, the number of its arguments;
- `bound`, the slot, counted from 1, of the argument binding a variable;
- `list`, the slot, counted from 1, of the argument taking a list of items.

A slot must lie between 1 and `arguments`, and `bound` and `list` must name two different slots. The check `invalid-item` reports a unit breaking either condition, and Onomasia skips that unit. Onomasia derives the arguments of the macro from the three facts:

- the macro takes one mandatory argument per argument of the unit, so its arity is `arguments`;
- its binder is the slot `bound`;
- its argument at the slot `list` holds all the items of the list, joined by the separator of the entry.

For example, a union over an index set binds its index at slot 1 and takes its terms at slot 2, so it declares `arguments: 2`, `bound: 1` and `list: 2`. A unit absent from every document takes no argument, and passes unreported. For example, an entry designating the block anchor of a note takes no argument. When several documents name one unit, the later document wins. ^denotes-targets

The *scope table* maps each audience to its `ancestors` and its `descendants`. Ekthesis decides which audiences are related, and the checks of texts apply the table as written. A lexical rule scoped to an audience binds a text when that audience appears in the row of the audience of the text, in three cases:

- the rule audience is the audience of the text;
- the rule audience is an ancestor of the audience of the text;
- the rule audience is a descendant of the audience of the text.

An audience absent from the table relates to itself only. The key `texts.scope_table` of the [configuration](configuration.md) names the table. ^scope-table

## Macro table

The macro table holds one macro per entry of the notations composed for an output, their overlays applied. The table names those notations under `notations` and those overlays under `overlays`, and lists its macros under `entries`, sorted by name. Each macro states the fields of its entry and of its target:

| Field | Content |
| --- | --- |
| `id` | the identifier of the entry |
| `notation` | the record of the printed form: the notation declaring the entry, or the overlay that changed the entry |
| `target` | the normalized target of the unit denoted by the entry, or null for an entry naming no unit by a logical target |
| `name`, `body` | the macro name, and the TeX printed |
| `arity`, `binder`, `list` | the number of mandatory arguments, the slot of the argument binding a variable, and the slot of the argument taking a list of items |
| `entry` | true when the macro takes the entry argument |
| `separator` | the string joining the items of the list |
| `class` | the typographic class of the entry |

^macro-table

The parameters of a body depend on the entry argument:

- when `entry` is true, the parameter `#1` holds the entry argument, optional with an empty default, and the mandatory arguments follow from `#2`;
- otherwise, the mandatory arguments start at `#1`.

MathJax cannot test whether an optional argument was supplied. Therefore, the body must print correctly with an empty entry argument. A macro taking a list receives all its items in the argument at the slot `list`, joined by its separator. ^parameters

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

The macro lookup names its notations under `notations`, and pairs each unit, under `targets`, with the macro name to be written for it by a view. A view is a note generated from records. Such a note writes macro names instead of printed forms. Each item of `targets` holds the normalized target of a unit under `target` and its name under `name`. The items follow the order of the repository, then the identifier, then the unit of the target. A reader builds its own map by comparing normalized targets. An entry without a target has no item. An overlay keeps every name and every target, so a lookup built under overlays is identical to the lookup of its notations. The check `ambiguous-target` guarantees one name per unit, since a view could not choose between two names. ^lookup

## Term table

The term table gives Hermeneia the terms of one composed glossary, named under `glossary`. The table lists its terms under `terms`, sorted by identifier, and each term states four fields:

- `id`, its identifier;
- `forms`, its label, its other forms and the labels of its alternatives, each form written as a string or as `{regex: …}`, without the description given by its record;
- `status`, its status, the default status standing for an absent one;
- `gloss`, the text of its gloss with the `resource` declaring the term and the JSON Pointer of the gloss. For a term of the consumer, the resource is the path of its record relative to the root. For a term read from another repository, the resource is the path of its record within that repository.

A term read from another repository also states, in its `gloss`, the `repository` of its record and the `commit` of the state read. The schema admits the two fields only together. A term of the consumer omits both.

With this location, Hermeneia reports a defect of a gloss at its declaration. ^term-table

## Serializations

Each serialization renders one macro table, and defines each macro once. The three serializations differ in their medium:

- **LaTeX package**: each macro becomes `\newcommand{\name}[n]{body}`, or `\newcommand{\name}[n][]{body}` when it takes the entry argument, `n` being its number of parameters. The part `[n]` is left out when `n` is 0. Since `\newcommand` refuses an existing command, a declared name overwriting a command stops the build of the document.
- **MathJax preamble**: the same definitions, without the lines `\NeedsTeXFormat` and `\ProvidesPackage`, for a preamble plugin of Obsidian.
- **Python expander**: a generated module without dependencies. Its function `expand` replaces each macro of a mathtext string by its body, its arguments substituted, until no macro remains. A mandatory argument is a braced group, a control sequence or one character, after optional spaces. The entry argument stands between brackets after the name. The constant `SOURCES` of the module holds the sources of the table. The constant `INPUTS` holds the [inputs](#^inputs) of the table, each a mapping `{repository, commit, id, sha256}`.

The package and the preamble state their sources in their first line, a comment reading "no recorded source" when `sources` is empty. One comment line per input follows, written `% repository commit id sha256`. The input lines follow the order of the repository, then the commit, then the identifier. When the notations of a table import from no other repository, the package and the preamble hold no input line. ^serializations

## Versioning

Each contract carries its own version. Adding an optional field keeps the version. Every other change starts the next version: removing, renaming or adding a required field, or admitting a new value. ^versioning
