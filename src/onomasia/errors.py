"""
Exceptions raised by Onomasia.

A defect of a record is an issue, reported and counted, never an exception. An exception stops
the run when Onomasia cannot proceed at all: an invalid configuration, or a packaged file that
fails to load.

Classes
-------
OnomasiaError
    Base of every exception raised by Onomasia.
ConfigurationError
    The configuration of a consumer is missing, malformed, or names an unknown value.
"""


class OnomasiaError(Exception):
    """Base of every exception raised by Onomasia."""


class ConfigurationError(OnomasiaError):
    """The configuration of a consumer is missing, malformed, or names an unknown value."""
