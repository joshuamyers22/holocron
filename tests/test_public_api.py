from __future__ import annotations

import importlib.util
import tomllib
import unittest
from importlib.resources import files
from pathlib import Path
from typing import cast

import holocron
from holocron import (
    design,
    exceptions,
    formula,
    graphics,
    models,
    reporting,
    validation,
)


class PublicApiTests(unittest.TestCase):
    def test_top_level_api_is_deliberately_small(self) -> None:
        self.assertEqual(
            holocron.__all__,
            (
                "__version__",
                "design",
                "exceptions",
                "formula",
                "graphics",
                "models",
                "reporting",
                "validation",
            ),
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
                "BackwardSelectionResult",
                "BinaryLogisticResult",
                "BuckleyJamesResult",
                "CensoredResponse",
                "CovarianceEstimate",
                "CovarianceResult",
                "CoefficientRobustness",
                "CoxResult",
                "GeneralizedLeastSquaresResult",
                "InferenceEstimate",
                "InfluenceObservation",
                "InfluenceResult",
                "LikelihoodResult",
                "ModelSummary",
                "NonparametricSurvivalResult",
                "OlsResult",
                "OrdinalDiagnostics",
                "OrdinalResult",
                "OrdinalTest",
                "PenalizedResult",
                "PenaltyTracePoint",
                "PenaltyTraceResult",
                "ParametricSurvivalResult",
                "PredictionResult",
                "ProportionalHazardsParametricResult",
                "QuantileRegressionResult",
                "RandomEffectsOrdinalResult",
                "ResidualResult",
                "RobustnessDiagnostics",
                "SelectionStep",
                "SurvivalCalibrationGroup",
                "SurvivalCurveResult",
                "SurvivalResidualResult",
                "SurvivalResponse",
                "SurvivalThresholdMetrics",
                "SurvivalValidationResult",
                "TurnbullResult",
                "VarianceComponentTest",
                "VarianceInflationFactor",
                "anova",
                "backward_select",
                "bootstrap_covariance",
                "contrast",
                "covariance",
                "fit_buckley_james",
                "fit_cph",
                "fit_glm",
                "fit_gls",
                "fit_lrm",
                "fit_npsurv",
                "fit_ols",
                "fit_ordinal_lrm",
                "fit_orm",
                "fit_penalized_lrm",
                "fit_penalized_ols",
                "fit_psm",
                "fit_quantile_regression",
                "fit_random_intercept_orm",
                "influence_diagnostics",
                "likelihood",
                "predict",
                "residuals",
                "robust_covariance",
                "robustness_diagnostics",
                "summarize",
                "survival_residuals",
                "trace_penalty",
                "to_proportional_hazards",
                "validate_survival_predictions",
                "variance_inflation_factors",
            ],
        )

    def test_graphics_namespace_exports_supported_plot_contracts(self) -> None:
        self.assertEqual(
            graphics.__all__,
            [
                "AxisSpec",
                "BandLayer",
                "BarLayer",
                "IntervalLayer",
                "LineLayer",
                "NomogramAxis",
                "NomogramGeometry",
                "NomogramOutcomeAxis",
                "NomogramOutcomeTick",
                "NomogramTick",
                "PlotMetadata",
                "PlotSpec",
                "PointLayer",
                "ReferenceLine",
                "TextAnnotation",
                "anova_plot_spec",
                "build_nomogram",
                "calibration_plot_spec",
                "contrast_plot_spec",
                "diagnostic_plot_spec",
                "effect_plot_spec",
                "render_svg",
                "render_nomogram_svg",
                "survival_plot_spec",
                "validation_plot_spec",
            ],
        )

    def test_validation_namespace_exports_only_supported_objects(self) -> None:
        self.assertEqual(
            validation.__all__,
            [
                "BinaryValidationIndices",
                "CalibrationEstimate",
                "ModelCalibrationResult",
                "ModelCalibrationSplit",
                "ModelValidationResult",
                "ModelValidationSplit",
                "OlsValidationIndices",
                "OptimismCorrectedCalibrationResult",
                "OptimismCorrectedMetric",
                "OptimismCorrectedValidationResult",
                "ProbabilityCalibrationGroup",
                "ProbabilityThresholdMetrics",
                "ProbabilityValidationResult",
                "ResampleExecution",
                "ResampleFailure",
                "ResampleFailureReason",
                "ResampleMetricCoverage",
                "ResamplePlan",
                "ResampleReport",
                "ResampleSplit",
                "ResampleSuccess",
                "SurvivalCalibrationGroup",
                "SurvivalThresholdMetrics",
                "SurvivalValidationResult",
                "calibrate_model",
                "optimism_correct_calibration",
                "optimism_correct_validation",
                "report_resample_execution",
                "run_resample_plan",
                "take_rows",
                "validate_model",
                "validate_probabilities",
                "validate_survival_predictions",
            ],
        )

    def test_reporting_namespace_exports_supported_table_contracts(self) -> None:
        self.assertEqual(
            reporting.__all__,
            [
                "TableColumn",
                "TableMetadata",
                "TableRow",
                "TableSpec",
                "anova_table",
                "contrast_table",
                "diagnostic_table",
                "escape_latex",
                "format_cell",
                "model_summary_table",
                "render_latex",
                "resample_report_table",
                "validation_table",
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
            "validation_evidence",
        )
        for module in removed:
            with self.subTest(module=module):
                self.assertIsNone(importlib.util.find_spec(f"holocron.{module}"))


if __name__ == "__main__":
    unittest.main()
