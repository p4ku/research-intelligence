import math
from django.test import TestCase
from research_intelligence.utils.sandbox import (
    execute_sandboxed_snippet,
    sanitize_and_validate_ast,
    SandboxSecurityError,
    SandboxExecutionError,
)


class SandboxSecurityAndEdgeCasesTestCase(TestCase):
    """
    Comprehensive security and edge-case unit tests for AST-level Sandboxed Python execution.
    """

    def test_forbidden_import_statement_blocked(self):
        code = "import os\nreturn 10.0"
        with self.assertRaises(SandboxSecurityError) as ctx:
            execute_sandboxed_snippet(code, {})
        self.assertIn("Imports are strictly forbidden", str(ctx.exception))

    def test_forbidden_from_import_statement_blocked(self):
        code = "from subprocess import check_output\nreturn 5.0"
        with self.assertRaises(SandboxSecurityError) as ctx:
            execute_sandboxed_snippet(code, {})
        self.assertIn("Imports are strictly forbidden", str(ctx.exception))

    def test_forbidden_eval_and_exec_calls_blocked(self):
        for bad_code in ["eval('1+1')", "exec('x=1')", "compile('x=1', '', 'exec')"]:
            with self.assertRaises(SandboxSecurityError):
                execute_sandboxed_snippet(bad_code, {})

    def test_forbidden_file_io_calls_blocked(self):
        for bad_code in ["open('/tmp/test', 'w')", "file('test')"]:
            with self.assertRaises(SandboxSecurityError):
                execute_sandboxed_snippet(bad_code, {})

    def test_forbidden_dunder_attribute_traversal_blocked(self):
        # Exploit: ().__class__.__base__.__subclasses__()
        exploit_code = "cls = ().__class__\nreturn 1.0"
        with self.assertRaises(SandboxSecurityError) as ctx:
            execute_sandboxed_snippet(exploit_code, {})
        self.assertIn("Access to private/dunder attribute", str(ctx.exception))

    def test_forbidden_introspection_identifiers_blocked(self):
        for name in ["globals", "locals", "vars", "dir", "getattr", "setattr", "delattr", "hasattr"]:
            code = f"x = {name}\nreturn 1.0"
            with self.assertRaises(SandboxSecurityError):
                execute_sandboxed_snippet(code, {})

    def test_infinite_while_loop_guard_protection(self):
        infinite_while = "while True:\n    pass\nreturn 1.0"
        with self.assertRaises(SandboxExecutionError) as ctx:
            execute_sandboxed_snippet(infinite_while, {})
        self.assertIn("infinite loop protection", str(ctx.exception))

    def test_infinite_for_loop_guard_protection(self):
        infinite_for = "for _ in range(20000):\n    pass\nreturn 1.0"
        with self.assertRaises(SandboxExecutionError) as ctx:
            execute_sandboxed_snippet(infinite_for, {})
        self.assertIn("infinite loop protection", str(ctx.exception))

    def test_safe_math_builtins_execution(self):
        code = """
score = math.sqrt(fit_score) * 10 + math.log(trl_level + 1)
return round(score, 2)
"""
        result = execute_sandboxed_snippet(code, {"fit_score": 16.0, "trl_level": 3.0})
        expected = round(math.sqrt(16.0) * 10 + math.log(4.0), 2)
        self.assertEqual(result, expected)

    def test_safe_builtins_collection_functions(self):
        code = "return max([fit_score, novelty_score, trl_level]) + min(1, 2, 3)"
        result = execute_sandboxed_snippet(code, {"fit_score": 5.0, "novelty_score": 8.0, "trl_level": 4.0})
        self.assertEqual(result, 9.0)

    def test_complex_multi_branch_conditional_formula(self):
        code = """
if trl_level < 3:
    score = 0.0
elif trl_level >= 7 and fit_score >= 8.0:
    score = 100.0 * (1.1 if novelty_score > 7 else 1.0)
else:
    score = 50.0 + 5.0 * novelty_score
return round(score, 1)
"""
        # Branch 1
        res1 = execute_sandboxed_snippet(code, {"trl_level": 2, "fit_score": 9.0, "novelty_score": 8.0})
        self.assertEqual(res1, 0.0)

        # Branch 2
        res2 = execute_sandboxed_snippet(code, {"trl_level": 7, "fit_score": 8.5, "novelty_score": 8.0})
        self.assertEqual(res2, 110.0)

        # Branch 3
        res3 = execute_sandboxed_snippet(code, {"trl_level": 5, "fit_score": 6.0, "novelty_score": 6.0})
        self.assertEqual(res3, 80.0)

    def test_syntax_error_handling(self):
        with self.assertRaises(SandboxExecutionError) as ctx:
            execute_sandboxed_snippet("return (1 + * 2)", {})
        self.assertIn("Syntax error", str(ctx.exception))

    def test_runtime_zero_division_error_handling(self):
        with self.assertRaises(SandboxExecutionError) as ctx:
            execute_sandboxed_snippet("return fit_score / 0.0", {"fit_score": 10.0})
        self.assertIn("division by zero", str(ctx.exception))

    def test_non_numeric_return_value_raises_error(self):
        with self.assertRaises(SandboxExecutionError) as ctx:
            execute_sandboxed_snippet("return 'Invalid String Score'", {})
        self.assertIn("non-numeric value", str(ctx.exception))

    def test_empty_or_none_snippet_defaults(self):
        self.assertEqual(execute_sandboxed_snippet("", {"val1": 10.5, "val2": 4.5}), 15.0)
        self.assertEqual(execute_sandboxed_snippet("   ", {}), 0.0)
        self.assertEqual(execute_sandboxed_snippet("return None", {}), 0.0)
