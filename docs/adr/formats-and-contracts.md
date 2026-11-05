---
tags:
  - decision
status: accepted
created: 2026-11-03
revised: 2026-11-05
index: "[Architecture decisions](docs/adr/_index.md)"
aliases:
  - Formats and contracts decision
---
# Formats and contracts

> [!QUESTION] Goal: in which formats does a consumer declare its vocabulary, how does Onomasia print its symbols, and which documents does it exchange with the other tools?

The [decision on designation and typography](https://github.com/esther-poniatowski/geonexus/blob/main/docs/_decisions/designation-and-typography.md) of Geonexus creates Onomasia, and assigns it six responsibilities:

- the glossaries, notations, typographic classes and overlays of a consumer;
- the lexical rules scoped by audience;
- the engine composing records through imports, with their statuses and collisions;
- the macro table and its three serializations;
- the contracts of `denotes`, of the scope table, of the macro lookup and of the term table;
- the checks matching terms in prose and symbols in mathematics.

The same decision orders the graph of contracts. Merismos, Kleisis, Elenchos and Anagraphe come before Onomasia, and Hermeneia, Ekthesis and Gnomon come after it. The present record settles three questions left open by the designation decision:

- how a consumer writes its records;
- how Onomasia derives its macros and reports its checks;
- where Onomasia meets its consumers.

The [record formats](../formats.md), the [configuration](../configuration.md) and the [contracts](../contracts.md) state the result normatively.

## Decision

**A tool independent of its consumers.** Onomasia imports no code of a consumer. Onomasia reads a consumer through its configuration and two ports only: the source of the records, and the provenance of a build. The consumers depend on Onomasia, never the reverse. ^independence

**Formats of its own.** A glossary, a notation and an overlay each follow a schema of Onomasia, designed from the designation decision. ^formats

**Lexical rules inside glossaries.** A glossary holds its terms and its rules, and an import composes both. ^rules-in-glossaries

**Printed forms from class templates.** A typographic class may declare a template, and an entry gives its base and its class. An entry may still write its body in full. ^class-templates

**Overlays in a format of their own.** The schema of an overlay admits classes and the [printed values of entries](../formats.md#^overlays) only. Therefore, an overlay cannot change a name, an argument or a target. ^overlay-format

**Core fields and declared vocabularies.** A term, a lexical rule and a notation entry each hold a fixed set of fields, whose meanings the format states. The statuses, the context dimensions and the relations are vocabularies declared in the configuration of the consumer. Every other field of a consumer goes under `metadata`, left unread by Onomasia. ^term-fields

**Descriptions of forms and conditions of replacements.** A form written as an object may carry a `description`, such as the construction admitted by an exception, and no check reads it. A replacement may state under `condition` the sense of the forbidden form served by the replacement, and the check `forbidden-form` prints the condition with the replacement. ^form-descriptions

**One composition engine for glossaries and notations.** The [composition](../formats.md#^composition) of glossaries and of notations follows one algorithm. That algorithm treats every section of every format alike. An overlay is applied by a separate step, after the composition of its notation. ^composition

**A catalog of checks.** Every check is listed with its default severity in the packaged defaults. A consumer changes a severity or turns a check off, and cannot name a check absent from the catalog. ^catalog

**A check as a build without its writes.** The command `onomasia check` runs the build in full, every check of the catalog included, and writes no output. Therefore, a consumer whose check passes has a build that passes. ^check-as-build

**Collisions reported where their entries meet.** A collision is reported at the record that first brings its two entries together, and never again at a record importing it. ^collisions

**Arguments from the denotes targets.** A macro takes its arity, its binder and its variadic flag from the unit that its entry denotes. ^arguments

**Derived macro names under a reserved prefix.** An entry without a declared name receives a [name derived](../contracts.md#^names) from its identifier, under the prefix of the configuration. No declared name may start with the prefix. ^derived-names

**The entry argument as an optional first parameter.** A macro taking the entry argument reads it as `#1`, with an empty default, and its mandatory arguments follow. ^entry-argument

**A build writing all its outputs or none.** A build reporting an error writes no output, and every other build replaces each output in one step. A consumer lowering the severity of a check accepts that the build skips an output that cannot be built, and writes the others. ^atomic-build

**Printed forms unique within a composed notation, except declared overloads.** The check `body-collision` reports two entries of one composed notation printing the same body, unless one entry names the other under [`overloads`](../formats.md#^overloads). The check `unneeded-overload` reports a declaration that no shared body justifies. The notations bound to a text compose into one macro table, checked with the text, so this check covers every pair of printed forms usable in one text. ^unique-bodies

**Checks of texts after Anagraphe.** Onomasia checks records and builds outputs now. Onomasia matches terms in prose and symbols in mathematics only once Anagraphe resolves binding keys. ^texts-after-anagraphe

## Constraints that decide the form

- **Several corpora consume Onomasia.** Each corpus declares its own statuses, contexts and relations, so a value set of one corpus cannot become a constant of the tool.
- **A glossary is imported by many records.** A check run on every composition reports an inherited defect once per importer, unless it reports each defect at one record.
- **A control word of TeX holds letters only.** An identifier of Onomasia may hold hyphens and digits, so it cannot always serve as a macro name.
- **The command `\newcommand` refuses an existing command.** A name such as `\nu` already exists, so a name derived without a prefix could stop the build of a document.
- **MathJax cannot test whether an optional argument was supplied.** Therefore, the body of a macro must print correctly with the default value of its entry argument.
- **Obsidian holds one macro table for a vault.** Therefore, an overlay shows only in builds, and must keep every name written in a note.
- **Matplotlib mathtext defines no macros.** Figure code needs the bodies themselves, expanded before mathtext reads a label.
- **Anagraphe resolves the bindings of texts.** The designation decision assigns this task to Anagraphe, so Onomasia does not decide which glossary, notation and audiences bind a text.
- **The records of Mixture carry fields beyond the core.** Its 529 symbols carry labels, sources, arguments and spaces. These fields belong to the units of Gnomon, once these units exist. Each of its 51 exceptions describes its admitted construction, and 8 of its replacements serve one sense of the forbidden form only.
- **Builds of documents read the outputs.** A partial output, or an output written from records holding an error, would print wrong symbols without any report.

## Options weighed

**Boundary with the consumers.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The glossary checker of Geonexus carried into the package | Reuses tested code | The checker imports helpers of Geonexus, so the tool would depend on one of its consumers |
| **A tool independent of its consumers, reached through ports** | Every corpus uses Onomasia on equal terms | Taken |

**Formats of the records.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The formats of Geonexus under new identifiers | A faster start, and a direct migration | The first release would lack `denotes`, typographic classes, overlays and rules scoped by audience, all required by the designation decision |
| **Formats of its own** | The formats carry `denotes`, classes, overlays and scoped rules from the start | Taken. Geonexus and Mixture migrate their records in a later step |

**Location of the lexical rules.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Lexicon files, a third format holding rules only | Rules shared without terms | One more binding key and one more graph of imports |
| **Rules inside glossaries** | One file and one binding key per vocabulary | Taken |

**Printed form of an entry.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Explicit bodies only, the class a label for the checks | A simpler format | Restyling a class edits every entry of it |
| **Class templates, an explicit body admitted** | Restyling a class edits one template, or overrides it in an overlay | Taken |

**Form of an overlay.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| A notation carrying the key `overlays` | One format fewer | A check run on the parsed records, instead of the schema, must confine each overlay to the four printed values |
| **A format of its own** | An invalid overlay fails its schema before any check runs | Taken |

**Fields of a term.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Every field of Geonexus, with fixed value sets | The easiest migration for Geonexus and Mixture | The value sets of one vault become constants of the tool |
| **Core fields, declared vocabularies, and free metadata** | Each corpus keeps its value sets and its own fields | Taken |

**Fields of a lexical rule and of a notation entry beyond the core.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Metadata on terms only, the other fields of an entry in a file beside the notation | No change of format | Two files to keep in step until the units of Gnomon carry the fields |
| Metadata on terms only, the other fields dropped | No change of format | The migration of the units must read the fields from the history of the former records |
| **Metadata on terms, rules and entries** | One file, no field lost, and one rule for every section of a glossary or a notation | Taken |

**Description of a form.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| A YAML comment above the form | No change of format | The description escapes the schema and every tool reading the records |
| **A description on a form written as an object** | Checked by the schema, and readable by tools | Taken |

**Sense of the forbidden form served by a replacement.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The condition folded into an instruction | No change of format | The replacement names no term, so the label and the status of the term are no longer read |
| A YAML comment | No change of format | The condition no longer reaches the writer through the issue |
| **A field `condition`, printed in the advice** | The writer chooses the replacement fitting the sense of the text | Taken |

**Bindings of texts.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| A resolver injected into the core, with an adapter reading explicit bindings from the configuration | Texts checked at once | The adapter would add a format of explicit bindings to the configuration, to be retired when Anagraphe resolves binding keys. The researcher chose to avoid that provisional format |
| **Checks of texts after Anagraphe** | No provisional format of bindings | Taken. Until then, Onomasia checks no text |

**Scope of the command `onomasia check`.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The checks of records only, the checks of outputs left to the build | The check reads no denotes targets | The check passes where the build fails, so a hook or a pipeline running the check lets a reserved prefix or an ambiguous target through |
| A macro table also built for each notation alone | A notation named by no output is checked too | One defect is reported twice, alone and within an output, and the collisions between notations depend on the notations combined by an output |
| **Every check of the build, without writing** | The check passes exactly when the build passes | Taken. A consumer whose denotes targets are missing fails its check, as its build would fail |

**Location of a reported collision.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Every composition holding the collision | No record of the merged sources | An inherited collision is reported once per importer |
| Only a composition declaring one of the two entries | Each local collision reported once | A collision between two imported entries, or one caused by the template of an overlay, goes unreported |
| **The composition that first brings the two entries together** | Every collision reported exactly once | Taken. Each composition keeps its merged sources, and compares its collisions with those of its sources |

**Name of a macro.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The identifier of the entry | No second name | Hyphens and digits break the grammar of a control word, and a letter-only identifier may overwrite a command of TeX |
| A name declared by every entry | Every name chosen by an author | Every entry must be named by hand, although a view generated from records reads its names from the lookup |
| **A declared name, or a name derived under a reserved prefix** | Short names declared by authors, and, for the other entries, names unable to overwrite a command of TeX | Taken |

**Admission of a shared printed form.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| A warning instead of an error, until the checks of texts exist | No declaration to write | A guarantee that holds today is lost |
| A check of the printed forms used in each text only | A collision counts only where a text meets it | The check waits for the binding keys of Anagraphe, and detects no further pair, since a text binds one composed notation |
| **An error for each pair not declared under `overloads`** | Every shared body is either intended or reported | Taken. A stale declaration is reported by `unneeded-overload` |

**Form of the entry argument.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| A mandatory argument | One form in every dialect | Every use without an entry writes empty braces |
| A second macro for the entry form | Two simple bodies | Each entry takes two names, and the lookup maps one unit to two macros |
| **An optional first parameter with an empty default** | One name, written bare in each use without an entry | Taken. In return, each body must print correctly with an empty entry |

**Outputs of a build reporting an error.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Writing the outputs unaffected by the error | Partial progress | An output may read a record holding the error, so a document would print from a defective table without any report |
| **No output written** | The former outputs stay whole and consistent | Taken |

## Open points

- The checks of texts, now decided by the [decision on text checks](text-checks.md). That decision keeps the classification of raw TeX symbols open.
- The migration of the records of Geonexus and Mixture to the formats of Onomasia.
