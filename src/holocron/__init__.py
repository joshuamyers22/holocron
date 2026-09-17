"""Holocron's deliberately small top-level public API.

Statistical APIs are organized by domain beneath :mod:`holocron.design` and
:mod:`holocron.models`. They are not duplicated at the package root.
"""

from holocron import design, exceptions, models
from holocron._version import __version__

__all__ = ("__version__", "design", "exceptions", "models")
