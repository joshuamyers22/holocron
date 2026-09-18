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
from holocron.models.regularization import (
    CovarianceEstimate,
    PenalizedResult,
    bootstrap_covariance,
    fit_penalized_lrm,
    fit_penalized_ols,
    robust_covariance,
)

__all__ = [
    "AnovaResult",
    "AnovaTest",
    "BinaryLogisticResult",
    "CovarianceEstimate",
    "CovarianceResult",
    "InferenceEstimate",
    "LikelihoodResult",
    "ModelSummary",
    "OlsResult",
    "PenalizedResult",
    "PredictionResult",
    "ResidualResult",
    "anova",
    "bootstrap_covariance",
    "contrast",
    "covariance",
    "fit_glm",
    "fit_lrm",
    "fit_ols",
    "fit_penalized_lrm",
    "fit_penalized_ols",
    "likelihood",
    "predict",
    "residuals",
    "robust_covariance",
    "summarize",
]
