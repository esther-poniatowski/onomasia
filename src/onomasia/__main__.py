"""
Entry point for the `onomasia` package, invoked as a module.

Usage
-----
To launch the command-line interface, execute::

    python -m onomasia


See Also
--------
onomasia.cli: Module implementing the application's command-line interface.
"""

from .cli import app

app()
