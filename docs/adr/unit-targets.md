---
tags:
  - decision
status: accepted
created: 2026-11-17
index: "[Architecture decisions](docs/adr/_index.md)"
aliases:
  - Unit targets decision
---
# Unit targets

> [!QUESTION] Goal: how does a notation name the unit of an entry as a logical target, and how do the outputs of Onomasia carry that unit?

An entry of `onomasia:notation@1` names its unit under `denotes`, as a text. [ADR 0006 of Anagraphe](https://github.com/esther-poniatowski/anagraphe/blob/main/docs/adr/0006-logical-targets.md) makes a reference to a unit a logical target `{repository, id, unit}`, and its step 4 moves the notations of Onomasia to that form. Three outputs of Onomasia carry the unit of an entry: `onomasia:denotes-targets@1`, read from Gnomon, and `onomasia:macro-table@1` and `onomasia:macro-lookup@1`, written by the build. The lookup keys the name of each macro by the text of its unit, and an object of JSON cannot take a mapping as a key. The researcher accepted the present record on 2026-11-17, together with the [decision on imports across repositories](imports-across-repositories.md), which publishes `onomasia:notation@2` as well.

## Decision

**A unit named by a logical target.** In `onomasia:notation@2`, the key `denotes` of an entry holds a logical target of Anagraphe that names a unit. A target without `repository` names a unit of the repository holding the notation. ^denotes

**Normalized targets in the outputs.** Every output of Onomasia carries the normalized target of a unit, its repository filled in, since a reader of the output may lie in another repository. Onomasia matches the unit of an entry with a unit of the denotes targets by their normalized targets, never by their texts. ^normalized

**Three new versions of the outputs.** `onomasia:denotes-targets@2` holds each unit as a normalized target, with its arguments. `onomasia:macro-table@2` holds the normalized target of each entry, or `null` for an entry that denotes no unit. In `onomasia:macro-lookup@2`, `targets` is an array of entries `{target, name}`, ordered by the repository, the identifier and the unit of the target. A reader builds its own map by comparing normalized targets, as the read package of Anagraphe compares them. ^outputs

## Constraints that decide the form

- An object of JSON takes a string as a key, so a lookup keyed by a target needs a string encoding of the target, or the form of an array.
- The [versioning rule](../contracts.md#^versioning) of Onomasia starts the next version of a contract when a key admits a new value.
- On 2026-11-17, every notation leaves `denotes` empty, the macro table and the lookup have no reader, and the generator of the denotes targets in Gnomon is still a task. Therefore, the new versions replace the first ones without a migration of a consumer.

## Options weighed

**A canonical text as the key of the lookup.** The lookup would keep an object, keyed by a text such as `repository/id#unit`. A reader could look a unit up directly. However, every read side would implement that encoding and its escaping, and the encoding would form a second notation of a target beside the mapping of Anagraphe.

## Open points

- Gnomon writes the denotes targets in the form of `onomasia:denotes-targets@2`, with its command `gnomon denotes-targets`. A repository reads them once its configuration of Onomasia names the generated file under `build.denotes_targets`, and no repository names one yet.
