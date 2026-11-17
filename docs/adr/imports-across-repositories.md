---
tags:
  - decision
status: proposed
created: 2026-11-17
index: "[Architecture decisions](docs/adr/_index.md)"
aliases:
  - Imports across repositories decision
---
# Imports across repositories

> [!QUESTION] Goal: how does a glossary import the entries of a glossary of another repository, read at a selected state, without a copy of it?

An import of Onomasia names a source record by its identifier, and the composer looks it up among the records of the consumer alone. Therefore, a glossary of another repository reaches a consumer only as a copy. The thesis holds such a copy, `vendor/mixture-input-encoding/glossary.yml`, of the glossary of Mixture, and its glossary imports `from: mixture-input-encoding`. A copy drifts from its source, and the consumer records no state of the source that the copy holds.

The [decision of Geonexus on cross-repository resolution](https://github.com/esther-poniatowski/geonexus/blob/main/docs/_decisions/cross-repository-record-resolution.md) states that Onomasia traverses the imports of glossaries, and fixes seven rules of an import closure: one selected state per repository, records keyed by `(repository, state, id)`, the declared order kept, a cycle rejected and a repeated target read once, duplicate entries across distinct sources rejected, limits from the consumer alone, and a receipt of every input. Anagraphe reads one verified record for Onomasia, through its [record resolver](https://github.com/esther-poniatowski/anagraphe/blob/main/docs/adr/0009-record-resolver.md) and its [Git provider of the selected states](https://github.com/esther-poniatowski/anagraphe/blob/main/docs/adr/0010-state-provider.md).

The present record settles four questions:

1. Which contracts admit a source in another repository?
2. At which level does Onomasia report an import whose state the machine cannot read?
3. Where does the receipt of the inputs lie?
4. Which limits bound a closure by default?

## Decision

The decision is proposed. Each question below states its recommended answer, which the researcher confirms or replaces.

**A source named by a logical target.** In the next version of each contract holding imports, the key `from` of an import admits either an identifier, which names a record of the repository holding the importing record, or a [logical target of Anagraphe](https://github.com/esther-poniatowski/anagraphe/blob/main/docs/guide/targets.md) `{repository, id}`. The target form declares `x-target-contract` with the contract of the importing record, so the check of the targets of Anagraphe also verifies that the source exists at its selected state and follows that contract. ^source-target

**The state from the consumer.** The resolution context of the root of the consumer selects the state of every repository that the closure reaches: a submodule of the root, or a repository of the section `resolution` of its configuration of Anagraphe. The consumer alone supplies the states and the remotes, as the decision of Geonexus requires. An identifier inside a source record names a record of the repository of that source; a target inside it names a repository of the context of the consumer. ^state

**The closure.** The composer keys each record by its repository, its commit and its identifier. The composer traverses the imports in their declared order, reads a repeated key once, and reports a key met again on its own path as `import-cycle`. Two distinct sources supplying one identifier with different entries keep the finding `import-conflict`. Each record of another repository is read through `read` of the record resolver of Anagraphe, which returns its verified bytes and their provenance. ^closure

**The failures of a read.** Each finding of the resolver on an import is reported at the pointer of its key `from`, under its own kind. A blocking finding of the resolver leaves the source out of the composition, so the entries of that source are absent from the checks of the consumer. ^failures

## Questions

1. **Contracts admitting a source in another repository.** Recommended: `onomasia:glossary@2` and `onomasia:notation@2` together, since both read the shared definition `import`, and `onomasia:notation@2` is already planned for the targets of `denotes`. The alternative publishes `onomasia:glossary@2` alone, with an import definition of its own, and leaves the notations to their planned version.
2. **Level of an unreadable import.** Recommended: an error. Without its source, the composition misses entries, so the checks of the consumer report or miss terms on a partial glossary, and the generated documents describe it. The gate of a host fetches the states first, through `anagraphe states fetch`. The alternative is a warning, as the check of the targets of Anagraphe reports an unreadable state, which keeps the gate usable on a host that does not fetch.
3. **Place of the receipt.** Recommended: an optional block `inputs` of each generated document, beside its block `sources`, listing each imported record with its repository, its commit, its identifier and the `sha256` digest of its bytes, ordered by `(repository, commit, id)`. An optional block keeps the version of the contract of the document. The alternative is a separate receipt file written by the build.
4. **Default limits.** Recommended: a depth of 8 imports, 64 records and 4 MiB of record bytes per closure, which the configuration of the consumer may lower or raise under a key `imports`. Imported content cannot change them. An exceeded limit is reported as `import-limit`, and the composer reads no further import of its branch.

## Constraints that decide the form

- The decision of Geonexus forbids imported content to supply a state, a remote or a limit, so all three come from the consumer.
- The [versioning rule](../contracts.md#^versioning) of Onomasia starts the next version of a contract when a key admits a new value, so `from` admits a target only in a new version.
- The record registry of the repository of a source must list the source. The glossary of Mixture declares its identifier through `x-identifier: id`, which the glossary schema of Onomasia holds since its commit `56f52f9`. Mixture materializes an earlier commit of that schema, so its registry does not list its glossary yet.
- The check of the targets of Anagraphe reads a target field typed by `x-target-contract`, including a field that admits another form, as a conditional field.

## Options weighed

**A key `repository` beside `from`.** An import would name its repository under a key of its own. The form departs from the logical targets of Anagraphe, so the check of the targets of Anagraphe would not verify it, and a second notation of a cross-repository address would exist.

**A copy refreshed by a command.** A command would copy a source glossary into the consumer, with its state recorded. The consumer then holds bytes that its gate cannot verify against the source, and the copy enters its registry and its exports, which the decision of Geonexus forbids.

## Migration

1. Mixture moves the commit of Onomasia in its schema resources past `56f52f9`, and its registry lists its glossary.
2. Onomasia publishes the new versions of the contracts, and composes the closure.
3. The thesis declares Mixture under `resolution.repositories`, imports `from: {repository: mixture-input-encoding, id: mixture-input-encoding}`, and removes `vendor/mixture-input-encoding/`. Its gate workflow fetches the states before its checks.

## Open points

- The authorized bundle of a closure, for a host without access to a private source, waits on the task `record-state-bundle` of Geonexus.
- The overlays of a notation in another repository follow the same form once `onomasia:overlay` admits a target.
