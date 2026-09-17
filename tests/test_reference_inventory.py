from __future__ import annotations

import unittest

from tools.build_reference_inventory import (
    namespace_statements,
    parse_description,
    parse_namespace,
)


class ReferenceInventoryTests(unittest.TestCase):
    def test_parses_multiline_namespace_and_quoted_symbols(self) -> None:
        text = """
        export(alpha, "%ia%") # trailing comment
        importFrom(stats,
                   lm, predict)
        S3method('coef<-', fitted)
        """
        calls = parse_namespace(text)
        self.assertEqual(calls[0].name, "export")
        self.assertEqual(calls[0].arguments, ("alpha", "%ia%"))
        self.assertEqual(calls[1].arguments, ("stats", "lm", "predict"))
        self.assertEqual(calls[2].arguments, ("coef<-", "fitted"))

    def test_rejects_unbalanced_namespace(self) -> None:
        with self.assertRaisesRegex(ValueError, "unbalanced"):
            namespace_statements("export(alpha")

    def test_parses_description_continuation_lines(self) -> None:
        fields = parse_description(
            "Package: rms\nDescription: first line\n  second line\nVersion: 8.2-0\n"
        )
        self.assertEqual(fields["Description"], "first line second line")
        self.assertEqual(fields["Version"], "8.2-0")
