---
tags:
  - specification
index: "[Onomasia documentation](docs/_index.md)"
aliases:
  - Record formats
---
# Record formats

A consumer of Onomasia declares its vocabulary in records of three formats: glossaries, notations and overlays. The schemas in the package folder `data/schemas` fix the fields of each format. This specification adds three points that a schema cannot state:

- the meaning of each field;
- the composition of records through their imports, and the application of overlays;
- the checks reading each field.

The [decision on formats and contracts](adr/formats-and-contracts.md) records the reason for each choice.

## Records and identifiers

Every record names its format under the key `_schema`, and its identifier under the key `id`. The key `_schema` also names the version of the format. Onomasia validates each record against the schema of its version. Onomasia reads the following versions:

- `onomasia:glossary@1` and `onomasia:glossary@2`;
- `onomasia:notation@1` and `onomasia:notation@2`;
- `onomasia:overlay@1` and `onomasia:overlay@2`.

A record matched by the globs of one format but naming another is rejected by the check `wrong-format`. An identifier is written in lowercase kebab case, such as `w-out`: groups of letters and digits, joined by single hyphens. Two kinds of uniqueness are required:

- two records of one format must not share an identifier, as the check `duplicate-record` enforces;
- two entries of one record must not share an identifier, even in two sections, as the check `duplicate-entry` enforces.

Every record, term, lexical rule and notation entry may carry a mapping `metadata` for the fields of the consumer. Onomasia reads no field of `metadata`. ^identifiers

## Composition of glossaries and notations

A glossary or a notation may import other records of its format, in two forms:

- a *merged* import, `{from: id}`, adopts the entries of its source, possibly restricted by `only` or reduced by `except`, never both;
- a *namespaced* import, `{from: id, as: alias}`, adopts no entry, and lets the record reference an entry of its source as `alias.id`.

The identifiers under `only` and `except` select entries in every section of the source. Each source is first composed through its own imports. An entry declared by the importing record shadows a merged entry of the same identifier. The composition reports six defects of imports:

| Check | Defect |
| --- | --- |
| `unresolved-import` | an import names no record of the format |
| `import-cycle` | the imports of a record lead back to it |
| `unresolved-import-entry` | `only` or `except` names an entry absent from the source |
| `import-conflict` | two merged sources supply one identifier with different entries |
| `duplicate-alias` | two imports of one record bind the same alias |
| `import-limit` | an import would take the closure of the record beyond a [limit](#^limits) |

^composition

### Imports across repositories

In `onomasia:glossary@2` and `onomasia:notation@2`, the key `from` takes one of two values: ^across

- an identifier, naming a record of the repository holding the importing record;
- a [logical target of Anagraphe](https://github.com/esther-poniatowski/anagraphe/blob/main/docs/guide/targets.md) `{repository, id}`, naming a record of any repository. A target without `repository` names a record of the repository holding the importing record. A target of an import never names a unit.

The schema of each contract declares `x-target-contract` on this key, with the contract of the importing record. Therefore, the check of the targets of Anagraphe also verifies that the source exists and follows that contract. In version 1, `from` admits an identifier only. The following import adopts the glossary `base` of the repository `lexicon`, except its term `curve`:

```yaml
_schema: onomasia:glossary@2
id: project
imports:
  - {from: {repository: lexicon, id: base}, except: [curve]}
```

The resolution context of the consumer selects the state of every repository reached by the imports. Each such repository is a submodule of the root of the consumer, or a repository declared under the key `resolution` of its [configuration of Anagraphe](configuration.md#^imports). Imported content supplies neither a state nor a remote. Inside a record of another repository, an identifier names a record of that repository, at the same state. A target inside that record names a repository of the context of the consumer. ^state

Onomasia reads each record of another repository through the record resolver of Anagraphe. The resolver returns the bytes of the record, verified against the selected state, with their provenance. The composer keys each record by its repository, its commit and its identifier, and traverses the imports in their declared order. Two properties follow from these keys:

- a record reached by several imports is read and composed once;
- an import leading back to a record on its own path of imports is reported as `import-cycle`, across repositories as within one.

Two distinct sources supplying one identifier with different entries are reported as `import-conflict`, as within one repository. ^closure

Onomasia reports each finding of the resolver at the key `from` of its import, under the kind of that finding, such as `unknown-repository` or `unreadable-target-state`. A kind absent from the catalog of checks is reported as `unresolved-import`, its message opening on the kind. A finding is an error by default when it leaves the source unread, since the checks of the consumer would otherwise run on a partial composition. Three findings let the source be read, and are reported as warnings at most:

- `renamed-repository`, for a retired identifier of a repository, followed to its successor;
- `renamed-target`, for a retired identifier of a record, followed to its successor;
- `unverified-target`, for a record read while the consumer lacks the schemas of its contract.

The repository of a source lists the source in its record registry. When the state of that repository holds no registry, the source stays unread, and its `unverified-target` is an error.

A record of another repository may break the schema of its format. Onomasia then reports each violation at the location of that record, written `repository:path` as in `lexicon:base.yml`, and reports its import as `unresolved-import`. The checks of the entries of a record run on the records of the consumer only, since a record of another repository is checked in its own repository. ^unread

A closure holds a record and every record reached by its imports, of the consumer and of other repositories. The configuration of the consumer limits each closure under its key [`imports`](configuration.md#^imports):

- `depth`, the levels of imports below the record, 8 by default;
- `records`, the records of the closure, the record itself included, 64 by default;
- `bytes`, the bytes of the documents of these records, 4 MiB by default.

An import exceeding a limit is reported as `import-limit`, and nothing of its source enters the closure or the composition. An import beyond the limit of depth is not read. An import exceeding the limit of records or of bytes is detected once its source is composed, and the closure of that source is itself held within the limits. ^limits

## Glossaries

A glossary, `onomasia:glossary@2`, holds two sections:

- `terms`, the admitted terms;
- `rules`, the lexical rules, each forbidding written forms.

A written form is either a literal, matched as whole words, or a regular expression written as `{regex: …}`, as the [matching of forms](#^matching) states. A term requires a label under `label` and a gloss under `gloss`, and admits the following optional fields:

| Field | Content |
| --- | --- |
| `forms` | the other written forms of the term |
| `source` | the origin of the term |
| `case_sensitive` | true when the forms of the term keep their case |
| `frames` | the constructions admitted for the term, written in the [grammar of frames](#^frames) |
| `alternatives` | other names of the concept, each with its label and, under `when`, the suited contexts of the vocabulary |
| `relations` | for each relation of the vocabulary, the terms related to the term |
| `status`, `superseded_by` | the [status](#^statuses) of the term, and the term superseding it |

The check `form-collision` compares the literal forms of the terms of one composed glossary, labels included. Each form is compared case-folded, unless its term sets `case_sensitive`. Regular expressions are never compared. ^glossaries

A lexical rule requires three fields:

- `forms`, the forbidden forms;
- `replace_with`, its replacements, each naming a term under `term` or giving an instruction under `instruction`, optionally restricted to contexts under `when`;
- `reason`, the reason of the rule.

A rule also admits three optional fields: `severity`, `status` and `case_sensitive`. The severity of a rule is `error` or `warning`. Two further fields serve the checks of texts:

- `audiences`, the audiences of the texts bound by the rule; a rule without `audiences` binds every text bound to its glossary;
- `exceptions`, the forms inside which a match of a forbidden form is admitted.

An audience of a rule binds a text when the [scope table](contracts.md#^scope-table) relates it to an audience of the text, and each audience relates to itself without a table. The check `rule-shadows-term` reports a rule forbidding a literal form of a term of the same composed glossary. A replacement may also state, under `condition`, the sense of the forbidden form served by the replacement. The check `forbidden-form` prints this condition after the replacement, so that the writer chooses the replacement fitting the sense of the text. ^lexical-rules

A literal form matches as whole words: no letter, digit, underscore or hyphen touches it on either side, so `regime` matches neither `regimes` nor `learning-regime`. The words of a literal form are separated in a text by spaces, non-breaking spaces included, holding one line break at most, so a form never spans two paragraphs, nor a masked region of the text. Each character of a masked region reads as the character U+0000, so an expression may name a masked region by `\x00`: the exception `population \x00+` admits a population named by a formula, as in `population $p$`. A regular expression is used as written, a leading global flag such as `(?i)` applying to the form alone. The check `invalid-form` reports an expression that does not compile, names a group, holds a backreference, or matches the empty string. A form ignores case unless its term or its rule sets `case_sensitive`. Among the literal forms of a term, its label included, the longest is tried first, so `gain field` wins over `gain`. A form may also be written as an object, `{literal: …}` or `{regex: …}`, to carry a `description`, such as the construction admitted by an exception. No check reads the description. ^matching

A frame is written as tokens separated by spaces:

- `~` stands for the term in any of its forms, exactly once and outside every optional part;
- a word is matched as a literal form;
- `[ … ]` holds an optional part, which may nest;
- `{a|b}` is a slot holding one of the terms named, each in any of its forms and under its own case, possibly after one determiner of the [configuration](configuration.md);
- `{}` is a slot holding any one word, possibly after one determiner.

For example, `~ of {input|stimulus} [in {}]` admits "gain of the input in V1" and "gain of a stimulus". The same frame rejects "gain of the noisy input". A frame is compiled into the text before the term and the text after it, so two occurrences admitted by one frame may share words, as in "the gain of the gain of noise". The check `invalid-frame` reports a frame holding no or several marks `~`, an unbalanced bracket or brace, a mark inside an optional part, a slot naming an empty term, or a slot naming no term of the glossary. The checks of texts leave a malformed frame out, and a term whose frames are all malformed is checked as if it declared none. ^frames

## Notations

A notation, `onomasia:notation@2`, holds two sections:

- `classes`, the typographic classes, each with an optional template under `template` and an optional gloss under `gloss`;
- `entries`, the symbols, each printed by its own body or by the template of its class.

In a class template, the configured placeholder stands for the base of an entry. The default placeholder is `{{base}}`. An entry gives either its full TeX under `body`, or its base under `base` together with a class holding a template. For example, the class `matrix` with the template `\boldsymbol{{{base}}}` prints the entry of base `W` as `\boldsymbol{W}`. ^printed-forms

An entry designates a *unit*: an object of research declared outside Onomasia, such as a quantity or the block anchor of a note. In `onomasia:notation@2`, the entry names the logical target of its unit under `denotes`, as a mapping `{repository, id, unit}`, and the other tools of the corpus address the unit by that target. A target without `repository` names a unit of the repository holding the notation. Onomasia normalizes each target by filling in that repository, from the manifest `repository.yml` of the repository. The check `unnormalized-target` reports a target left without repository when the repository holding the notation declares no identifier. The unit states the meaning of the entry, so an entry with a target omits the gloss. An entry without a target is *undeclared*. In that case, its gloss states its meaning, and the check `undeclared-entry` reports it as a warning. ^meaning

In `onomasia:notation@1`, `denotes` holds a text. Onomasia still reads such an entry as declared. A text carries no logical target. Therefore, the outputs write the target of such an entry as null, and the entry takes no argument from the [denotes targets](contracts.md#^denotes-targets).

Four keys of an entry fix its macro:

- `name`, the macro name, a word of the letters A to Z in either case; an entry without a name receives a name derived from its identifier;
- `entry`, true when the macro takes the optional entry argument, read by the body as `#1`;
- `separator`, the string joining the items of a variadic operator, all passed in one argument;
- `denotes`, whose target supplies the number of arguments, the binder and the variadic flag.

The [parameter rule](contracts.md#^parameters) maps these keys to the parameters of a macro. An entry also admits a `status` with its `superseded_by`, and `alternatives`, each giving another body under `body` with its contexts under `when`. ^macros

The check `body-collision` reports two entries of one composed notation printing the same body. A pair is admitted when one of its entries names the other under `overloads`. The field `overloads` lists the identifiers of the entries that print the body of the entry on purpose, such as one letter used for two quantities. A declaration admits one pair only: an entry overloading a second entry still collides with a third entry printing the same body. The check `unneeded-overload` reports an overload naming the entry itself or an entry printing another body, and the check `unresolved-reference` reports an overload naming no entry. An overlay declares no overload, so a collision created by an overlay stays an error. ^overloads

## Overlays

An overlay, `onomasia:overlay@2`, names under `overlays` the notation to change, by an identifier or by a logical target `{repository, id}`, as the key `from` of an [import](#^across) does. The schema declares `x-target-contract: ['onomasia:notation']` at the key `overlays`. In `onomasia:overlay@1`, `overlays` admits an identifier only. An overlay imports no record. Instead, Onomasia applies the overlay to the composed notation, by identifier:

- a class of the overlay replaces the class of the same identifier as a whole, so a class given without `template` removes the template;
- an entry of the overlay changes the body, the base or the class of the entry of the same identifier, and a new body or a new base replaces both former values.

The checks `unresolved-overlay` and `unknown-override` report an overlay naming an absent notation, class or entry. Besides these fields and `metadata`, the schema of an overlay admits no field. Therefore, every macro name, argument and target of the notation holds under every overlay. As a result, a note written with the macro names of the notation prints under any overlay. An output applies its overlays in the order of its list `overlays`, and each overlay changes the notation left by the earlier ones. ^overlays

Onomasia reads the notation named by an overlay as it reads the source of an import, with the same findings of the resolver and the same [limits](#^limits). The closure of an overlay holds the overlay and the closure of its notation. Each finding is reported at the key `overlays`. A notation that no repository provides is reported as `unresolved-overlay`. A document built under an overlay lists in `inputs` the records of other repositories imported by the notation that the overlay changes. An output names its notations by their identifiers in the consumer. Therefore, an overlay of a notation of another repository is checked with the records. An output naming such an overlay is reported as `unresolved-output`. ^remote-overlays

## Statuses

Each term, rule and entry may declare a status among the statuses of the vocabulary. An absent status stands for the default status. A status may require a replacement. Under such a status, a term or an entry names its replacement under `superseded_by`. A lexical rule names its replacements under `replace_with` in every case.

A status also states its effect on texts, under `in_texts` in the [configuration](configuration.md); each severity caps the severity of the check that reports the use:

- `term`, the severity of a use of a term or of the macro of an entry of the status, `off` when such a use is admitted;
- `rule`, the highest severity of a lexical rule of the status, `off` for a rule binding no text.

A status declaring no `in_texts` admits the use of its terms and caps no rule, as `term: off` and `rule: error` do. The packaged statuses report a superseded term as an error and a candidate term as a warning, lower a candidate rule to a warning, and make a superseded rule bind no text. ^statuses

## Checks of the records

The packaged file `data/defaults.yml` lists every check, with its default severity and its gloss. The checks fall in three groups. The command `onomasia build` runs the first two and writes the outputs. The command `onomasia check` runs all three and writes nothing, so a consumer whose check passes has a build that passes. The first group of checks reads the records, their compositions and the overlays. The second group reads the outputs declared by the configuration:

- the checks of each macro table built for an output: `reserved-prefix`, `macro-name-collision`, `ambiguous-target`, `too-many-parameters`, `missing-separator` and `macro-cycle`;
- the check of the input documents, `invalid-contract`;
- the check of the outputs themselves, `unresolved-output`.

The checks of the outputs see only the notations named by an output, so a notation named by no output escapes them.

The third group reads the texts declared by the configuration, against the records bound to each text. The [guide](guide.md#^texts) lists these checks.

A check of records reports each issue at one record, with the [JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901) of the offending value:

- a defect of one entry is reported in the record declaring the entry;
- a collision between two entries is reported in the record that first brings them together, at its own entry or at the import adopting the later entry.

Under this rule, a defect of a glossary imported by ten others is reported once. ^checks
