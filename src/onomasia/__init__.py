"""
Glossaries and notations of texts: their records, their composition, their checks, and the macros
that print their symbols.

The public interface loads the configuration of a consumer, checks its records, and exposes the
typed records and the ports through which a consumer supplies them.

Variables
---------
__version__ : str, default "0.0.0+unknown"
    Version of the package. If the package metadata is unavailable (e.g. in editable or source-only
    environments), a fallback value is provided (PEP 440 compliant).
__all__ : list
    Public objects exposed by this package.

Functions
---------
info() -> str
    Format diagnostic information about the package and platform.

Examples
--------
To programmatically retrieve the package version, a string:

    >>> import onomasia
    >>> isinstance(onomasia.__version__, str)
    True

See Also
--------
importlib.metadata.version
    Function to retrieve the version of a package.
PackageNotFoundError
    Exception raised when the package is not found in the environment.
"""

from importlib.metadata import version, PackageNotFoundError
import platform

from .configuration import Configuration, default_configuration, load_configuration
from .errors import ConfigurationError, OnomasiaError
from .issues import Issue, Severity
from .records.model import Entry, LexicalRule, Record, RecordKind, Term, TypographicClass
from .repository import FileRecordSource, RawDocument, RecordSource
from .service import check_records

try:
    if __package__ is None:  # erroneous script execution
        raise PackageNotFoundError
    __version__ = version(__package__)
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "Configuration",
    "ConfigurationError",
    "Entry",
    "FileRecordSource",
    "Issue",
    "LexicalRule",
    "OnomasiaError",
    "RawDocument",
    "Record",
    "RecordKind",
    "RecordSource",
    "Severity",
    "Term",
    "TypographicClass",
    "check_records",
    "default_configuration",
    "info",
    "load_configuration",
    "__version__",
]


def info() -> str:
    """Format diagnostic information on package and platform."""
    platform_name = f"{platform.system()} Python {platform.python_version()}"
    return f"{__package__} {__version__} | Platform: {platform_name}"
