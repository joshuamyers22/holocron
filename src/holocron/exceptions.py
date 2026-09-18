"""Stable exception categories for Holocron's public API."""


class HolocronError(Exception):
    """Base class for errors raised deliberately by Holocron."""


class InputValidationError(HolocronError, ValueError):
    """Input data or a statistical specification violates its contract."""


class RankDeficiencyError(InputValidationError):
    """A design matrix does not satisfy the estimator's rank contract."""


class ConvergenceError(HolocronError):
    """An iterative estimator did not meet its declared convergence contract."""


class SeparationError(ConvergenceError):
    """A binary model has no finite unpenalized maximum-likelihood estimate."""


class NumericalError(HolocronError, ArithmeticError):
    """A supported computation cannot produce a numerically valid result."""


class UnsupportedFeatureError(HolocronError, NotImplementedError):
    """A requested statistical combination is intentionally unsupported."""


__all__ = (
    "HolocronError",
    "InputValidationError",
    "ConvergenceError",
    "NumericalError",
    "RankDeficiencyError",
    "SeparationError",
    "UnsupportedFeatureError",
)
