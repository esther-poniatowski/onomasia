---
tags:
  - decision
status: proposed
created: 2026-11-04
revised: 2026-11-04
index: "[Architecture decisions](docs/adr/_index.md)"
aliases:
  - Text checks decision
---
# Text checks

> [!QUESTION] Goal: how does Onomasia check a text against the glossaries, the notations and the audiences bound to it?

The [decision on designation and typography](https://github.com/esther-poniatowski/geonexus/blob/main/docs/_decisions/designation-and-typography.md) of Geonexus assigns to Onomasia the matching of terms in prose and of symbols in mathematics, and the checks of lexical rules scoped by audience. The glossary checker of Geonexus did this work before, and retires once Onomasia covers it. The [founding decision](formats-and-contracts.md) deferred these checks until Anagraphe resolved the bindings of texts. The present record settles four questions:

- how a text is bound and read;
- how forms and frames match;
- how statuses act on texts;
- what the checks of mathematics cover.

## Decision

**Bindings through Anagraphe.** Onomasia reads three roles, `onomasia.glossary`, `onomasia.notation` and `onomasia.audiences`, through the [bindings of Anagraphe](https://github.com/esther-poniatowski/anagraphe/blob/main/docs/guide/bindings.md), each merging by `override`. A role absent from the Anagraphe configuration binds no text. ^bindings

**Prose and mathematics through Merismos.** Before prose is matched, the regions of the kinds declared under `texts.masked` are filled with a character that is no space, so no form spans them. The destination of a wikilink without an alias stays prose, since the link displays it. The container prefixes of quotations and the markers of callouts are blanked with spaces. The mathematics is read from the content of each region of the kinds declared under `texts.math`. ^regions

**Whole words, within one paragraph.** A literal form matches when no letter, digit, underscore or hyphen touches it, and its words are separated by spaces holding one line break at most. The longest literal form of a term is tried first, and a leading global flag of a regular expression applies to the form alone. ^matching

**Malformed forms and frames as findings.** Onomasia reports a regular expression that does not compile, names a group, holds a backreference or matches the empty string, as a defect of its record. A frame that is malformed or names an absent term is reported the same way. The checks of texts leave such a form or frame out. ^malformed

**Statuses declaring their effect on texts.** Each status states, under `in_texts`, the severity of a use of a term or an entry of the status, and the highest severity of a rule of the status. ^statuses

**The full grammar of frames.** A frame holds the mark `~` once, words, optional parts `[ … ]`, slots naming terms `{a|b}` and slots of any one word `{}`, a slot admitting one determiner of the configuration before it. The words of a frame follow the case of its term, and each slot term keeps its own case. A frame is matched as its two halves around an occurrence, so two occurrences admitted by one frame may share words. ^frames

**Mathematics checked at the level of macros.** The mathematics of a text is checked for three uses:

- a macro of an entry whose status reports its use;
- a macro under the reserved prefix, defined by none of the bound notations;
- the printed body of an entry, written instead of its macro, when the body holds a control sequence and takes no parameter.

One issue names every macro printing a body, and the longest body wins where one body opens another. The body of an entry whose use is reported is not sought.

The notations bound to a text compose into one macro table, whose defects are reported once per combination. ^macros

## Constraints that decide the form

- **The vault uses none of these checks today.** Every glossary and notation of Geonexus sits in an excluded folder. The latent content of Mixture holds 19 forbidden entries, all with exceptions, no frame, and a notation of 529 symbols.
- **The old checker crashes on malformed input.** A frame with two marks, or a variant written as a regular expression with a global flag, raised an error and stopped the run.
- **A hyphenated compound is one word.** The old boundaries matched `regime` inside `learning-regime`, and a multiword form across blank lines and across masked formulas.
- **Statuses belong to the consumer.** The old checker hard-coded `deprecated` and `candidate`, whereas Onomasia declares statuses in the configuration of each consumer.
- **Notations are macro tables.** A text written for Onomasia calls macros, and the old classification of raw TeX produced 1,178 findings on the notes of Mixture, many from known artefacts of its tokenizer.

## Options weighed

**Effect of statuses on texts.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Statuses requiring a replacement act, the others not | A simpler vocabulary | A candidate term or rule gives no warning |
| **Each status declares its effect under `in_texts`** | Every effect is a value of the consumer, and the packaged values reproduce the old behaviour | Taken |

**Checks of mathematics.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The old classification of raw TeX: fonts conflicting with a registered symbol, unregistered symbols recurring in two notes | Covers texts written without macros | Noisy, and its token grammar holds known artefacts; deferred until a corpus written with macros shows the need |
| **Checks at the level of macros** | Each finding names a macro of the bound notations | Taken |

**Grammar of frames.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| Words, `~`, `[ ]` and `{}` only | A smaller grammar | Loses the slots naming terms of the old grammar |
| Frames deferred | No grammar to maintain | The field `frames` of the glossaries would be read by no check |
| **The full old grammar, its defects removed** | The constructions of the old glossaries stay expressible | Taken |

**Boundaries of a literal form.**

| Option | Benefit | Reason it is not taken |
| --- | --- | --- |
| The old boundaries, a hyphen separating words | No change of reading | A form forbidden alone is reported inside the compounds that a glossary admits |
| **A hyphen joining words, one line break at most between the words of a form** | A match stays inside one word and one paragraph | Taken |

## Differences from the glossary checker of Geonexus

Beyond the decisions above, five readings of the old checker change, each by a format or a constraint of Onomasia:

- an exception of a rule is a form containing the forbidden match, so the old tests `neighbours` and the window of the paragraph are gone; an exception of the kind `neighbours` becomes a regular expression;
- an exception relying on the blanks left by masked mathematics, such as `populations?\s{2,}\S`, no longer admits its match, since a masked region holds no space;
- a text bound to no value is reported by the check of Anagraphe for the files that its condition `required` selects, not by Onomasia;
- the advice of a deprecated symbol names the macro of its replacement only, no longer the other symbols of the same term;
- a printed body is matched exactly, with no tolerance of spaces inside it.

## Open points

- The classification of raw TeX symbols, if a corpus written with macros shows the need.
- The migration of the glossaries and notations of Geonexus and Mixture to the formats of Onomasia. The checks of texts read the migrated records.
