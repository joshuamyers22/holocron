"""Statistical model estimators and owned result types."""

from holocron.models.glm import fit_glm, fit_lrm
from holocron.models.linear import OlsResult, fit_ols
from holocron.models.logistic import BinaryLogisticResult
from holocron.models.postfit import (
    AnovaResult,
    AnovaTest,
    CovarianceResult,
    InferenceEstimate,
    LikelihoodResult,
    ModelSummary,
    PredictionResult,
    ResidualResult,
    anova,
    contrast,
    covariance,
    likelihood,
    predict,
    residuals,
    summarize,
)

__all__ = [
    "AnovaResult",
    "AnovaTest",
    "BinaryLogisticResult",
    "CovarianceResult",
    "InferenceEstimate",
    "LikelihoodResult",
    "ModelSummary",
    "OlsResult",
    "PredictionResult",
    "ResidualResult",
    "anova",
    "contrast",
    "covariance",
    "fit_glm",
    "fit_lrm",
    "fit_ols",
    "likelihood",
    "predict",
    "residuals",
    "summarize",
]
