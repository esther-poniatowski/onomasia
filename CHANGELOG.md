# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- A lexical rule and a notation entry may carry `metadata`, as a term does.
- A form may be written as an object, `{literal: …}` or `{regex: …}`, with a `description`.
- A replacement may state its `condition`, printed in the advice of `forbidden-form`.
