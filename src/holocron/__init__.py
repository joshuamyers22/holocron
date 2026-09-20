"""Holocron's deliberately small top-level public API.

Statistical APIs are organized by domain beneath :mod:`holocron.design`,
:mod:`holocron.graphics`, :mod:`holocron.models`, :mod:`holocron.reporting`,
and :mod:`holocron.validation`. Migration assessment is organized beneath
:mod:`holocron.migration`. Domain APIs are not duplicated at the package root.
"""

from holocron import (
    design,
    exceptions,
    formula,
    graphics,
    migration,
    models,
    reporting,
    validation,
)
from holocron._version import __version__

__all__ = (
    "__version__",
    "design",
    "exceptions",
    "formula",
    "graphics",
    "migration",
    "models",
    "reporting",
    "validation",
)
