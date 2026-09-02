"""
Unit tests for safe_format_prompt utility.
"""

from django.test import SimpleTestCase
from research_intelligence.utils.prompt_formatter import safe_format_prompt


class PromptFormatterTestCase(SimpleTestCase):
    def test_standard_placeholders(self):
        tmpl = "Title: {title}\nCriteria: {acceptance_criteria}\nAbstract: {abstract}"
        ctx = {
            "title": "Quantum Attention",
            "acceptance_criteria": "Must study QPU",
            "abstract": "We evaluate quantum circuits."
        }
        res = safe_format_prompt(tmpl, ctx)
        self.assertIn("Title: Quantum Attention", res)
        self.assertIn("Criteria: Must study QPU", res)
        self.assertIn("Abstract: We evaluate quantum circuits.", res)

    def test_double_curlies_normalized(self):
        tmpl = "Paper: {{title}} with abstract: {{abstract}}"
        ctx = {"title": "Fast Inference", "abstract": "Speeding up LLMs."}
        res = safe_format_prompt(tmpl, ctx)
        self.assertEqual(res, "Paper: Fast Inference with abstract: Speeding up LLMs.")

    def test_json_and_latex_braces_do_not_crash_or_corrupt(self):
        # A template containing JSON schemas and LaTeX syntax that would crash str.format()
        tmpl = (
            "Evaluate document: {title}\n"
            "Return JSON matching: {\"decision\": true, \"complexity\": \"\\mathcal{O}(n)\", \"score\": 0.95}\n"
            "Criteria: {acceptance_criteria}\n"
            "Extra unescaped: {} and {not_in_ctx}"
        )
        ctx = {
            "title": "Scaling Law Paper",
            "acceptance_criteria": "LLM scaling experiments"
        }
        res = safe_format_prompt(tmpl, ctx)
        # title and acceptance_criteria replaced
        self.assertIn("Evaluate document: Scaling Law Paper", res)
        self.assertIn("Criteria: LLM scaling experiments", res)
        # JSON and LaTeX syntax preserved without raising KeyError / ValueError
        self.assertIn("{\"decision\": true, \"complexity\": \"\\mathcal{O}(n)\", \"score\": 0.95}", res)
        self.assertIn("Extra unescaped: {} and {not_in_ctx}", res)

    def test_empty_and_none_templates(self):
        self.assertEqual(safe_format_prompt("", {"title": "X"}), "")
        self.assertEqual(safe_format_prompt(None, {"title": "X"}), "")
