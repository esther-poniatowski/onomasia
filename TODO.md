---
tags:
  - tasks
aliases:
  - Project goals
---
# Project goals

This list holds the goals of `onomasia` that span several parts of the project.

## Logical targets

- [ ] Publish `onomasia:notation@2`, whose `denotes` is a logical target of Anagraphe naming a unit, and `onomasia:denotes-targets@2`, whose targets name their repository, as step 4 of the migration of [ADR 0006 of Anagraphe](https://github.com/esther-poniatowski/anagraphe/blob/main/docs/adr/0006-logical-targets.md) orders; match a denotes target to an entry by the normalized target instead of its text. Decide first how the outputs `onomasia:macro-table@1` and `onomasia:macro-lookup@1` name a unit: the lookup keys each macro name by the text of a target, and a mapping cannot key a JSON object. On 2026-11-14, no notation uses `denotes` and no tool reads these outputs, so the task waits for the first notation that denotes a unit, or for the generator of the denotes targets in Gnomon (task `denotes-targets` of Gnomon) 🆔 notation-logical-targets
