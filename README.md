# onomasia

![Maintenance](https://img.shields.io/maintenance/yes/2026)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)](https://www.python.org/)
[![License: GPL](https://img.shields.io/badge/License-GPL--3.0-yellow.svg)](https://opensource.org/licenses/GPL-3.0)

Owns the glossaries and notations of texts, and generates their macros for LaTeX, MathJax and figure code.

---

## Overview

A research corpus names its concepts with terms and prints its quantities with symbols. A *consumer* of Onomasia, such as a corpus or a tool, holds both in records under its own configuration:

- a glossary declares the admitted terms, and the lexical rules forbidding other forms;
- a notation declares the symbols, with their typography.

Onomasia checks these records and composes their imports. Then, from the composed notations, Onomasia builds one macro table, serialized for each medium:

- a LaTeX package for documents;
- a MathJax preamble for Obsidian;
- a Python module for Matplotlib figures.

### Motivation

Two limitations are commonly observed when one corpus prints the same symbols in documents, notes and figures. First, each medium defines a symbol with its own macro, so a change of typography edits every medium, and the media drift apart. Second, the terms and symbols of a corpus are listed in prose only, so no tool detects two terms sharing a form or two symbols printed alike.

Onomasia removes both limitations. A notation entry is defined once, and every medium prints it from the same macro. The checks of Onomasia report each collision and each unresolved reference once, at the record introducing it. The vocabularies and outputs of a consumer live in [its configuration](docs/configuration.md), so one consumer never imposes its conventions on another.

### Status

Pre-alpha. The package checks glossaries, notations and overlays, and builds six products: three documents of its [contracts](docs/contracts.md) and three serializations of its macros. The checks of texts match terms in prose and macros in mathematics, for the glossaries, notations and audiences bound to each text through the tool Anagraphe. The [founding decision](docs/adr/formats-and-contracts.md) is accepted.

---

## Quick Start

Saved as `onomasia.yml` in `config/tools/` below the root of a consumer, or at that root, the following configuration reads the notations of the consumer and writes a LaTeX package for its notation `mixture`:

```yaml
schema_version: 1
records:
  notations: ["**/notation.yml"]
build:
  outputs:
    - {product: latex-package, notations: [mixture], path: build/mixture.sty}
```

The following command checks the records, then writes the package:

```console
onomasia build --root .
```

The [guide](docs/guide.md) covers the checks, the other outputs, and the two ports open to a consumer: the source of its records and the provenance of a build.

---

## Documentation

The [documentation index](docs/_index.md) is the entry point.

---

## Contributing

Contributions follow the [contribution guidelines](CONTRIBUTING.md).

---

## License

This project is licensed under the terms of the [GNU General Public License v3.0](LICENSE).
