"""
Validation of records against the packaged schemas of their formats.

A record names the version of its format under `_schema`, and the validator checks it against the
schema of that version, so that the records of every version read by this release stay valid. The
schemas reference the logical target of Anagraphe by its absolute identifier, and the validator
reads that resource from the package of Anagraphe.

Classes
-------
SchemaValidator
    Validator of the records of every format, built once from the packaged schemas.
"""

from importlib import resources
from typing import Iterator, Mapping

from anagraphe_read import ADDRESSING_ID, addressing_schema
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
import yaml

from ..errors import OnomasiaError
from .model import RecordKind

SCHEMA_FOLDER = "data/schemas"
"""Package folder holding the schemas of the formats."""

SCHEMA_FILES = {
    "onomasia:glossary@1": "glossary.v1.schema.yml",
    "onomasia:glossary@2": "glossary.schema.yml",
    "onomasia:notation@1": "notation.v1.schema.yml",
    "onomasia:notation@2": "notation.schema.yml",
    "onomasia:overlay@1": "overlay.v1.schema.yml",
    "onomasia:overlay@2": "overlay.schema.yml",
}
"""Schema file of each version of each format, in the package folder of the schemas."""


def _pointer(error: ValidationError) -> str:
    """JSON Pointer of the value that a validation error concerns."""
    tokens = (str(token).replace("~", "~0").replace("/", "~1") for token in error.absolute_path)
    return "".join(f"/{token}" for token in tokens)


class SchemaValidator:
    """
    Validator of the records of every format, built once from the packaged schemas.

    Raises
    ------
    OnomasiaError
        If a packaged schema fails to load, which is a defect of Onomasia.
    """

    def __init__(self) -> None:
        folder = resources.files(__package__.rsplit(".", 1)[0]).joinpath(SCHEMA_FOLDER)
        schemas: dict[str, Mapping[str, object]] = {}
        for path in folder.iterdir():
            if path.name.endswith(".schema.yml"):
                schema = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not isinstance(schema, Mapping):
                    raise OnomasiaError(f"{SCHEMA_FOLDER}/{path.name}: a schema is a mapping")
                schemas[str(schema["$id"])] = schema
        contents = [
            (identifier, Resource.from_contents(schema)) for identifier, schema in schemas.items()
        ]
        contents.append((ADDRESSING_ID, Resource.from_contents(addressing_schema())))
        registry: Registry = Registry().with_resources(contents)
        self._registry = registry
        self._schemas = schemas
        unknown = [name for kind in RecordKind for name in kind.schemas if name not in SCHEMA_FILES]
        if unknown:
            raise OnomasiaError("no schema file for " + ", ".join(unknown))
        self._validators = {
            name: Draft202012Validator(schemas[file], registry=registry)
            for name, file in SCHEMA_FILES.items()
        }

    def errors(self, schema: str, data: object) -> Iterator[tuple[str, str]]:
        """
        Yield the pointer and the message of each violation of the schema of one version of a
        format, named by its identifier, such as `onomasia:glossary@2`.

        Raises
        ------
        OnomasiaError
            If no packaged schema validates the version, which is a defect of Onomasia.
        """
        validator = self._validators.get(schema)
        if validator is None:
            raise OnomasiaError(f"no packaged schema of the format {schema}")
        for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
            yield _pointer(error), error.message

    def contract_errors(self, schema: str, data: object) -> Iterator[tuple[str, str]]:
        """
        Yield the pointer and the message of each violation of the schema of a contract.

        Raises
        ------
        OnomasiaError
            If no packaged schema carries the identifier, which is a defect of Onomasia.
        """
        if schema not in self._schemas:
            raise OnomasiaError(f"no packaged schema {schema}")
        validator = Draft202012Validator(self._schemas[schema], registry=self._registry)
        for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
            yield _pointer(error), error.message
