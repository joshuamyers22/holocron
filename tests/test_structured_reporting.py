from __future__ import annotations

import unittest
from pathlib import Path
from typing import cast

from holocron.design import DesignSpec
from holocron.exceptions import InputValidationError
from holocron.models import (
    anova,
    contrast,
    fit_ols,
    influence_diagnostics,
    robustness_diagnostics,
    summarize,
    trace_penalty,
    validate_survival_predictions,
    variance_inflation_factors,
)
from holocron.reporting import (
    TableColumn,
    TableMetadata,
    TableRow,
    TableSpec,
    anova_table,
    contrast_table,
    diagnostic_table,
    escape_latex,
    model_summary_table,
    render_latex,
    resample_report_table,
    validation_table,
)
from holocron.validation import (
    ResamplePlan,
    optimism_correct_validation,
    report_resample_execution,
    run_resample_plan,
    validate_model,
    validate_probabilities,
)
from reference.contracts import validate_document

ROOT = Path(__file__).resolve().parents[1]
TABLE_SCHEMA = ROOT / "schemas/table-spec.schema.json"


class TableSpecificationTests(unittest.TestCase):
    def test_raw_values_round_trip_and_validate_against_schema(self) -> None:
        table = TableSpec(
            table_id="safe-table",
            kind="custom",
            title="Raw results",
            caption="Numbers remain numbers in the source contract.",
            columns=(
                TableColumn("term", "Term", "text", "left", 0),
                TableColumn("estimate", "Estimate", "number", "right", 4),
                TableColumn("p", "p", "p-value", "right", 3),
            ),
            rows=(
                TableRow("row-1", ("x_1", 1.23456, 0.0002)),
                TableRow("row-2", ("missing", None, None)),
            ),
            notes=("Missing values are explicit null cells.",),
            metadata=(TableMetadata("source", "unit-test"),),
        )

        restored = TableSpec.from_json(table.to_json())

        self.assertEqual(restored, table)
        self.assertEqual(restored.fingerprint, table.fingerprint)
        self.assertIsInstance(restored.rows[0].values[1], float)
        self.assertEqual(restored.rows[0].values[1], 1.23456)
        validate_document(table.to_dict(), TABLE_SCHEMA)

    def test_contract_rejects_invalid_types_fields_and_duplicates(self) -> None:
        columns = (TableColumn("count", "Count", "integer", "right", 0),)
        with self.assertRaisesRegex(InputValidationError, "integers"):
            TableSpec("bad", "custom", "Bad", columns, (TableRow("row", (1.2,)),))
        with self.assertRaisesRegex(InputValidationError, "one value per column"):
            TableSpec("bad", "custom", "Bad", columns, (TableRow("row", ()),))

        document = TableSpec(
            "ok", "custom", "OK", columns, (TableRow("row", (1,)),)
        ).to_dict()
        document["unknown"] = True
        with self.assertRaisesRegex(InputValidationError, "invalid fields"):
            TableSpec.from_dict(document)

        duplicate = (
            TableSpec("ok", "custom", "OK", columns, (TableRow("row", (1,)),))
            .to_json()
            .replace('"kind":"custom"', '"kind":"custom","kind":"custom"')
        )
        with self.assertRaisesRegex(InputValidationError, "invalid table"):
            TableSpec.from_json(duplicate)


class LatexRendererTests(unittest.TestCase):
    def test_latex_is_deterministic_formats_cells_and_escapes_all_text(self) -> None:
        table = TableSpec(
            "unsafe-table",
            "custom",
            r"A&B_1 $x$ \input{bad}",
            (
                TableColumn("term", "Term & value", "text", "left", 0),
                TableColumn("estimate", "Estimate", "number", "right", 2),
                TableColumn("p", "p", "p-value", "right", 3),
            ),
            (TableRow("row", (r"x_1 \input{evil}", -0.001, 0.0002)),),
            notes=("100% caller_text",),
        )

        latex = render_latex(table)

        self.assertEqual(latex, render_latex(table))
        self.assertIn(r"\caption{A\&B\_1 \$x\$ \textbackslash{}input\{bad\}}", latex)
        self.assertIn(r"x\_1 \textbackslash{}input\{evil\}", latex)
        self.assertIn(r"$<0.001$", latex)
        self.assertIn("0.00", latex)
        self.assertNotIn(r"\input{", latex)
        self.assertTrue(latex.endswith("\\end{table}\n"))
        self.assertEqual(
            escape_latex("a#b~c^d"),
            r"a\#b\textasciitilde{}c\textasciicircum{}d",
        )
        self.assertEqual(escape_latex("line\nbreak"), "line break")

    def test_tabular_only_mode_and_type_checks(self) -> None:
        table = TableSpec(
            "small",
            "custom",
            "Small",
            (TableColumn("value", "Value", "number", "right", 1),),
            (TableRow("row", (None,)),),
        )
        fragment = render_latex(table, include_table_environment=False)
        self.assertTrue(fragment.startswith("\\begin{tabular}"))
        self.assertIn(r"\textemdash{}", fragment)
        self.assertNotIn("\\begin{table}", fragment)
        with self.assertRaisesRegex(InputValidationError, "boolean"):
            render_latex(table, include_table_environment=1)  # type: ignore[arg-type]


class ReportingAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.x = tuple(float(value) for value in range(-3, 9))
        self.y = (1.1, 1.8, 2.4, 3.2, 3.7, 5.1, 5.5, 6.8, 7.4, 8.1, 9.3, 9.9)
        self.design_spec = DesignSpec.from_formula("y ~ x")
        self.design = self.design_spec.transform({"x": self.x})
        self.fit = fit_ols(self.y, self.design)

    def test_postfit_adapters_preserve_declared_statistics(self) -> None:
        summary = summarize(self.fit)
        estimate = contrast(self.fit, {"asis(x)": 1.0}, name="slope")
        term_tests = anova(self.fit, self.design_spec)

        summary_spec = model_summary_table(summary)
        contrast_spec = contrast_table((estimate,))
        anova_spec = anova_table(term_tests)

        self.assertEqual(
            summary_spec.rows[1].values[1], summary.coefficients[1].estimate
        )
        self.assertEqual(contrast_spec.rows[0].values[6], estimate.p_value)
        self.assertEqual(anova_spec.rows[0].values[2], term_tests.tests[0].statistic)
        self.assertEqual(summary_spec.kind, "model-summary")
        self.assertEqual(anova_spec.kind, "anova")
        self.assertEqual(
            summary_spec.rows[0].values[-7], summary.likelihood.log_likelihood
        )
        self.assertEqual(summary_spec.rows[1].values[-7:], (None,) * 7)

    def test_validation_adapters_preserve_missing_and_horizon_values(self) -> None:
        probability = validate_probabilities(
            (0, 1, 0, 1, 0, 1, 1, 0),
            (0.1, 0.7, 0.4, 0.6, 0.55, 0.8, 0.35, 0.45),
            calibration_groups=4,
        )
        survival = validate_survival_predictions(
            (1, 2, 3, 4),
            (1, 1, 1, 1),
            ((0.2,), (0.5,), (0.5,), (0.8,)),
            (2.5,),
        )

        probability_spec = validation_table(probability)
        survival_spec = validation_table(survival, table_id="survival-validation")

        self.assertEqual(probability_spec.rows[0].values[1], probability.auc)
        lr_p = next(
            row
            for row in probability_spec.rows
            if row.values[0] == "likelihood ratio p value"
        )
        self.assertIsNone(lr_p.values[1])
        self.assertEqual(lr_p.values[2], probability.likelihood_ratio_p_value)
        self.assertEqual(survival_spec.rows[0].values[0], 2.5)
        self.assertEqual(survival_spec.rows[0].values[2], 0.875)
        self.assertEqual(survival_spec.rows[0].values[-3:], (None, None, None))

    def test_resampling_and_diagnostic_adapters_are_structured(self) -> None:
        plan = ResamplePlan.k_fold(len(self.y), folds=3, seed=4)
        execution = run_resample_plan(plan, lambda split: len(split.assessment_indices))
        report = report_resample_execution(execution, metric_contributors={"score": 3})
        influence = influence_diagnostics(self.fit, self.y, self.design)
        vifs = variance_inflation_factors(self.fit)
        robust = robustness_diagnostics(
            self.fit,
            self.y,
            self.design,
            clusters=tuple(index // 2 for index in range(len(self.y))),
        )
        trace = trace_penalty(
            self.fit, self.y, self.design, (0.0, 0.5, 1.0), criterion="aic"
        )
        corrected = optimism_correct_validation(
            validate_model(self.fit, self.y, self.design, plan)
        )

        report_spec = resample_report_table(report)
        influence_spec = diagnostic_table(influence)
        vif_spec = diagnostic_table(vifs, table_id="vif")
        robust_spec = diagnostic_table(robust, table_id="robust")
        trace_spec = diagnostic_table(trace, table_id="trace")
        corrected_spec = validation_table(corrected, table_id="corrected")

        self.assertEqual(report_spec.rows[0].values[1:], (3, 0, 1.0, 1.0))
        self.assertEqual(len(influence_spec.rows), len(self.y))
        self.assertEqual(vif_spec.rows[0].values[0], "asis(x)")
        self.assertAlmostEqual(cast(float, vif_spec.rows[0].values[1]), 1.0)
        self.assertEqual(robust_spec.rows[0].values[0], "Intercept")
        self.assertEqual(len(trace_spec.rows), 3)
        self.assertEqual(
            corrected_spec.rows[0].values[-1],
            corrected.metrics[0].contributing_resamples,
        )


if __name__ == "__main__":
    unittest.main()
