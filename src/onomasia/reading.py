"""
Strict reader of the mappings of a configuration, reporting each error with its key path.

Classes
-------
Fields
    Reader of one mapping, rejecting the keys left unread.
"""

from typing import Mapping, Sequence

from .errors import ConfigurationError


class Fields:
    """
    Reader of one mapping, rejecting the keys left unread.

    Parameters
    ----------
    data : Mapping[str, object]
        Mapping to read.
    path : str
        Key path of the mapping in its file, used in error messages.
    origin : str
        Name of the file, used in error messages.

    Examples
    --------
    >>> fields = Fields({"globs": ["a/*.yml"]}, "records", "onomasia.yml")
    >>> fields.strings("globs")
    ('a/*.yml',)
    >>> fields.finish()
    """

    def __init__(self, data: Mapping[str, object], path: str, origin: str) -> None:
        self._data = data
        self._path = path
        self._origin = origin
        self._read: set[str] = set()

    def error(self, key: str, message: str) -> ConfigurationError:
        """Build the error of a key, prefixed with the file and the key path."""
        location = f"{self._path}.{key}" if self._path else key
        return ConfigurationError(f"{self._origin}: {location}: {message}")

    def _get(self, key: str) -> object:
        """Return the value of a key, recording that the key was read."""
        self._read.add(key)
        return self._data.get(key)

    def present(self, key: str) -> bool:
        """Whether the mapping holds the key, null included."""
        return key in self._data

    def value(self, key: str) -> object:
        """Read the value of a key, of any type, or None when it is absent."""
        return self._get(key)

    def integer(self, key: str) -> int:
        """Read a required integer."""
        value = self._get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise self.error(key, "expected an integer")
        return value

    def string(self, key: str) -> str:
        """Read a required non-empty string."""
        value = self._get(key)
        if not isinstance(value, str) or not value:
            raise self.error(key, "expected a non-empty string")
        return value

    def boolean(self, key: str) -> bool:
        """Read a required boolean."""
        value = self._get(key)
        if not isinstance(value, bool):
            raise self.error(key, "expected true or false")
        return value

    def strings(self, key: str, default: tuple[str, ...] | None = None) -> tuple[str, ...]:
        """Read a list of non-empty strings, or the default when the key is absent."""
        value = self._get(key)
        if value is None and default is not None:
            return default
        if not isinstance(value, Sequence) or isinstance(value, str):
            raise self.error(key, "expected a list of strings")
        if not all(isinstance(item, str) and item for item in value):
            raise self.error(key, "expected a list of non-empty strings")
        return tuple(str(item) for item in value)

    def items(self, key: str) -> tuple[object, ...]:
        """Read a list of any items, empty when the key is absent."""
        value = self._get(key)
        if value is None:
            return ()
        if not isinstance(value, Sequence) or isinstance(value, str):
            raise self.error(key, "expected a list")
        return tuple(value)

    def mapping(self, key: str) -> Mapping[str, object] | None:
        """Read a mapping, or None when the key is absent."""
        value = self._get(key)
        if value is None:
            return None
        if not isinstance(value, Mapping) or not all(isinstance(name, str) for name in value):
            raise self.error(key, "expected a mapping with string keys")
        return value

    def section(self, key: str) -> "Fields | None":
        """Read a nested mapping as a reader of its own, or None when the key is absent."""
        value = self.mapping(key)
        if value is None:
            return None
        path = f"{self._path}.{key}" if self._path else key
        return Fields(value, path, self._origin)

    def finish(self) -> None:
        """
        Reject every key of the mapping left unread.

        Raises
        ------
        ConfigurationError
            If the mapping holds a key that no reader read.
        """
        unknown = sorted(set(self._data) - self._read)
        if unknown:
            raise self.error(unknown[0], "unknown key")
