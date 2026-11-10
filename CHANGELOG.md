# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- A term or a notation entry names its replacement under `superseded_by`, formerly
  `replaced_by`, and the packaged status requiring a replacement is `superseded`, formerly
  `deprecated`, as the vault and its tools name them.
- `entry-status` also reports the printed body of a reported entry, with the replacement.
- A printed body opening on a letter matches only where no letter or backslash precedes it.

### Dependencies

- Merismos at commit `feb6654`, which reads Markdown as observed in Obsidian 1.15.0, and Anagraphe
  at its release `v0.2.2`, which pins the same Merismos.

### Added

- A lexical rule and a notation entry may carry `metadata`, as a term does.
- A form may be written as an object, `{literal: …}` or `{regex: …}`, with a `description`.
- A replacement may state its `condition`, printed in the advice of `forbidden-form`.
- Each character of a masked region reads as U+0000, which an expression may name.
- Without `--config`, `check` and `build` read `config/tools/onomasia.yml` or `onomasia.yml`
  below the root. When both files exist, the command stops with status 2 and names both; when
  neither exists, the message names both places. A given `--config` is read from the current
  folder, as before, and an absent file is an error.
- Without `--root`, the root is read from the new environment variable `ONOMASIA_ROOT`, and
  otherwise is the nearest folder, from the current one upwards, holding one of both files, and
  otherwise the current folder, formerly always the current folder.
- The short options `-r` for `--root` and `-c` for `--config`.
