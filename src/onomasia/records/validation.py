"""
Validation of records against the packaged schemas of their formats.

Classes
-------
SchemaValidator
    Validator of the records of every format, built once from the packaged schemas.
"""

from importlib import resources
from typing import Iterator, Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
import yaml

from ..errors import OnomasiaError
from .model import RecordKind

SCHEMA_FOLDER = "data/schemas"
"""Package folder holding the schemas of the formats."""

SCHEMA_FILES = {
    RecordKind.GLOSSARY: "glossary.schema.yml",
    RecordKind.NOTATION: "notation.schema.yml",
    RecordKind.OVERLAY: "overlay.schema.yml",
}
"""Schema file of each format, in the package folder of the schemas."""


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
        registry: Registry = Registry().with_resources(
            (identifier, Resource.from_contents(schema)) for identifier, schema in schemas.items()
        )
        self._validators = {
            kind: Draft202012Validator(schemas[name], registry=registry)
            for kind, name in SCHEMA_FILES.items()
        }

    def errors(self, kind: RecordKind, data: object) -> Iterator[tuple[str, str]]:
        """Yield the pointer and the message of each violation of the schema of a format."""
        for error in sorted(
            self._validators[kind].iter_errors(data), key=lambda item: list(item.absolute_path)
        ):
            yield _pointer(error), error.message
