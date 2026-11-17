---
tags:
  - tasks
aliases:
  - Project goals
---
# Project goals

This list holds the goals of `onomasia` that span several parts of the project.

## Logical targets

- [x] Publish `onomasia:notation@2`, whose `denotes` is a logical target of Anagraphe naming a unit, with the outputs `onomasia:denotes-targets@2`, `onomasia:macro-table@2` and `onomasia:macro-lookup@2` that the [decision on unit targets](docs/adr/unit-targets.md) fixes, as step 4 of the migration of [ADR 0006 of Anagraphe](https://github.com/esther-poniatowski/anagraphe/blob/main/docs/adr/0006-logical-targets.md) orders; match a denotes target to an entry by the normalized target instead of its text. `onomasia:notation@2` also admits the imports of the [decision on imports across repositories](docs/adr/imports-across-repositories.md) 🆔 notation-logical-targets ✅ 2026-11-17

## Arguments of a macro

- [ ] Decide the arity of a unit that is both a binder and variadic. The [rule of the denotes targets](docs/contracts.md#^denotes-targets) gives a variadic unit the arity 1, since its items travel in one argument, whereas `binder` names a further argument for the bound variable; `gnomon denotes-targets` gives such a unit the arity 2. Fix the rule, then align the generator of Gnomon. No record schema of Gnomon declares such a unit yet 🆔 variadic-binder
