---
tags:
  - decision
status: accepted
created: 2026-11-17
index: "[Architecture decisions](docs/adr/_index.md)"
aliases:
  - Imports across repositories decision
---
# Imports across repositories

> [!QUESTION] Goal: how does a glossary import the entries of a glossary of another repository, read at a selected state, without a copy of it?

An import of Onomasia names its source record by an identifier. The composer looks that identifier up among the records of the consumer alone. Therefore, a glossary of another repository reaches a consumer only as a copy. The thesis holds such a copy of the glossary of Mixture, `vendor/mixture-input-encoding/glossary.yml`, and its own glossary imports `from: mixture-input-encoding`. A copy drifts from its source, and the consumer records no state of the copied source.

The [decision of Geonexus on cross-repository resolution](https://github.com/esther-poniatowski/geonexus/blob/main/docs/_decisions/cross-repository-record-resolution.md) states that Onomasia traverses the imports of glossaries. That decision fixes seven rules of an import closure:

1. one selected state for each repository;
2. records keyed by `(repository, state, id)`;
3. the declared order kept;
4. a cycle rejected, and a repeated target read once;
5. duplicate entries across distinct sources rejected;
6. limits set by the consumer alone;
7. a receipt of every input.

Anagraphe reads one verified record for Onomasia, through its [record resolver](https://github.com/esther-poniatowski/anagraphe/blob/main/docs/adr/0009-record-resolver.md) and its [Git provider of the selected states](https://github.com/esther-poniatowski/anagraphe/blob/main/docs/adr/0010-state-provider.md). The researcher accepted the present record on 2026-11-17.

## Decision

**A source named by a logical target.** The key `from` of an import admits two forms. An identifier names a record of the repository holding the importing record. A [logical target of Anagraphe](https://github.com/esther-poniatowski/anagraphe/blob/main/docs/guide/targets.md) `{repository, id}` names a record of any repository. The target form declares `x-target-contract` with the contract of the importing record. Therefore, the check of the targets of Anagraphe also verifies that the source exists and follows that contract. ^source-target

**Two new versions of the contracts.** `onomasia:glossary@2` and `onomasia:notation@2` admit the target form, since both contracts read the shared definition `import`. `onomasia:notation@2` also takes the targets of `denotes`, which are already planned for that version. ^versions

**The state from the consumer.** The resolution context of the consumer selects the state of every repository that the closure reaches. Each such repository is a submodule of the root, or a repository of the key `resolution` in the configuration of Anagraphe. The consumer alone supplies the states and the remotes. An identifier inside a source record names a record of the repository of that source. A target inside a source record names a repository of the context of the consumer. ^state

**The closure.** The composer keys each record by its repository, its commit and its identifier, and traverses the imports in their declared order. A repeated key is read once. A key met again on its own path of imports is reported as `import-cycle`. When two distinct sources supply one identifier with different entries, the composer reports `import-conflict`, as it does within one repository. Each record of another repository is read through the operation `read` of the record resolver, which returns its verified bytes and their provenance. ^closure

**An unread source as an error.** Onomasia reports each finding of the resolver at the key `from` of its import, under the kind of that finding. Every finding that leaves a source unread is an error. Without its source, the composition lacks entries, so the checks of the consumer run on a partial glossary. Therefore, the gate of a host fetches the states first, with `anagraphe states fetch`. ^unread

**The receipt in the generated documents.** Each generated document holds an optional block `inputs` beside its block `sources`. The block lists each imported record of another repository with its repository, its commit, its identifier and the `sha256` digest of its bytes. The entries follow the order of `(repository, commit, id)`. An optional block keeps the version of the contract of the document. ^receipt

**Limits set by the consumer.** A closure holds at most 8 levels of imports, 64 records and 4 MiB of record bytes by default. The configuration of the consumer may change each limit under its key `imports`, and imported content cannot. An exceeded limit is reported as `import-limit`. Beyond the depth limit, the composer reads no further import of the branch. A source whose closure exceeds the record or the byte limit stays out of the composition; that source is read first, which stays bounded since its own closure obeys the same limits. ^limits

## Constraints that decide the form

- The decision of Geonexus forbids imported content to supply a state, a remote or a limit. Therefore, all three come from the consumer.
- The [versioning rule](../contracts.md#^versioning) of Onomasia starts the next version of a contract when a key admits a new value. Therefore, `from` admits a target only in a new version.
- The record registry of the repository of a source must list the source. The glossary schema of Onomasia declares `x-identifier: id` since its commit `56f52f9`. Mixture materializes an earlier commit of that schema, so its registry does not list its glossary yet.
- The check of the targets of Anagraphe reads a target field that also admits another form as a conditional field, and still reads its `x-target-contract`.

## Options weighed

**A key `repository` beside `from`.** An import would name its repository under a key of its own. This form departs from the logical targets of Anagraphe, so the check of Anagraphe would not verify it. The workspace would also hold a second notation of an address in another repository.

**A copy refreshed by a command.** A command would copy a source glossary into the consumer, with its state recorded. The gate of the consumer could not verify those bytes against the source. The copy would also enter the registry and the exports of the consumer, which the decision of Geonexus forbids.

**`onomasia:glossary@2` alone.** The glossary contract would hold an import definition of its own, and the notations would wait for their planned version. The two contracts would then read two definitions of one key.

**An unread source as a warning.** Anagraphe reports an unreadable state as a warning, which keeps the gate usable on a host without a fetch step. However, for Onomasia, an unread source changes the result of every check of the consumer.

**A separate receipt file.** The build would write the receipt beside the generated documents. Then, a reader of one document would need a second file to know its inputs.

## Migration

1. Mixture moves the commit of Onomasia in its schema resources past `56f52f9`, and its registry lists its glossary.
2. Onomasia publishes the new versions of the contracts, and composes the closure.
3. The thesis declares Mixture under `resolution.repositories` and imports `from: {repository: mixture-input-encoding, id: mixture-input-encoding}`. Then, the thesis removes `vendor/mixture-input-encoding/`, and its gate workflow fetches the states before its checks.

## Open points

- The authorized bundle of a closure waits on the task `record-state-bundle` of Geonexus. A host without access to a private source needs it.
- The overlays of a notation follow the same form once `onomasia:overlay` admits a target.
