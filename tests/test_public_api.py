from __future__ import annotations

import importlib.util
import tomllib
import unittest
from importlib.resources import files
from pathlib import Path
from typing import cast

import holocron
from holocron import design, exceptions, formula, models


class PublicApiTests(unittest.TestCase):
    def test_top_level_api_is_deliberately_small(self) -> None:
        self.assertEqual(
            holocron.__all__,
            ("__version__", "design", "exceptions", "formula", "models"),
        )
        self.assertRegex(holocron.__version__, r"^\d+(?:\.\d+)+(?:[A-Za-z0-9.+-]*)$")

    def test_import_and_distribution_versions_match(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        document = cast(
            dict[str, object],
            tomllib.loads((repository / "pyproject.toml").read_text()),
        )
        project = cast(dict[str, object], document["project"])
        self.assertEqual(holocron.__version__, project["version"])

    def test_distribution_is_marked_as_typed(self) -> None:
        self.assertTrue(files("holocron").joinpath("py.typed").is_file())

    def test_design_namespace_exports_only_supported_objects(self) -> None:
        self.assertEqual(
            design.__all__,
            [
                "DataDistribution",
                "DesignMatrix",
                "DesignSpec",
                "DistributionRange",
                "GeneratedColumn",
                "RestrictedCubicSplineSpec",
                "VariableDistribution",
            ],
        )

    def test_formula_namespace_exports_only_supported_nodes(self) -> None:
        self.assertEqual(
            formula.__all__,
            [
                "CategoricalTerm",
                "Formula",
                "IdentityTerm",
                "LinearSplineTerm",
                "OrderedTerm",
                "PolynomialTerm",
                "RestrictedCubicSplineTerm",
                "RestrictedInteractionTerm",
                "Variable",
            ],
        )

    def test_models_namespace_exports_only_supported_estimators(self) -> None:
        self.assertEqual(
            models.__all__,
            [
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
            ],
        )

    def test_public_errors_preserve_builtin_catch_categories(self) -> None:
        with self.assertRaises(ValueError):
            raise exceptions.InputValidationError("invalid input")
        with self.assertRaises(ArithmeticError):
            raise exceptions.NumericalError("numerical failure")
        with self.assertRaises(exceptions.ConvergenceError):
            raise exceptions.SeparationError("separated")
        with self.assertRaises(NotImplementedError):
            raise exceptions.UnsupportedFeatureError("unsupported")

    def test_template_application_modules_are_not_shipped(self) -> None:
        removed = (
            "analysis_cli",
            "cli",
            "dataset",
            "dataset_cli",
            "evidence",
            "ingest",
            "model",
            "regression",
            "time_validation_cli",
            "validation",
            "validation_evidence",
        )
        for module in removed:
            with self.subTest(module=module):
                self.assertIsNone(importlib.util.find_spec(f"holocron.{module}"))


if __name__ == "__main__":
    unittest.main()
