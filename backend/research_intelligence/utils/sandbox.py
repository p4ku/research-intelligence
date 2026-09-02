"""
Secure Python Sandbox Engine for Signal Score Calculation.

Provides AST-level static security inspection, restricted execution scope (__builtins__ lockdown),
and AST loop iteration limits to safely evaluate user-supplied Python formulas on extracted parameters.
"""

import ast
import math
import logging
import concurrent.futures
from typing import Dict, Any, Union, Optional

logger = logging.getLogger(__name__)

# List of dangerous built-in names and identifiers that are strictly forbidden
FORBIDDEN_NAMES = {
    "__import__",
    "eval",
    "exec",
    "compile",
    "open",
    "file",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "globals",
    "locals",
    "vars",
    "dir",
    "breakpoint",
    "exit",
    "quit",
    "input",
    "print",
    "help",
    "memoryview",
    "super",
    "type",
    "classmethod",
    "staticmethod",
    "property",
    "object",
}

# Whitelist of safe builtins available to the user's snippet
SAFE_BUILTINS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "len": len,
    "sum": sum,
    "pow": pow,
    "divmod": divmod,
    "all": all,
    "any": any,
    "sorted": sorted,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "range": range,
    "math": math,
    "None": None,
    "True": True,
    "False": False,
}


class SandboxSecurityError(Exception):
    """Raised when user code violates security policies (AST analysis or dunder escape attempt)."""
    pass


class SandboxExecutionError(Exception):
    """Raised when safe user code fails during runtime, times out, or exceeds loop iteration limits."""
    pass


class ASTSecurityValidator(ast.NodeVisitor):
    """
    Traverses the Python AST to statically detect dangerous operations,
    such as imports, private/dunder attribute lookups, forbidden builtins,
    unbounded comprehensions, and dangerous exponentiation/replication.
    """

    def visit_Import(self, node):
        raise SandboxSecurityError(f"Imports are strictly forbidden in signal score code (line {node.lineno}).")

    def visit_ImportFrom(self, node):
        raise SandboxSecurityError(f"Imports are strictly forbidden in signal score code (line {node.lineno}).")

    def visit_Attribute(self, node):
        # Disallow access to any attribute starting with '_' (e.g. __class__, __subclasses__, __globals__)
        if node.attr.startswith("_"):
            raise SandboxSecurityError(
                f"Access to private/dunder attribute '{node.attr}' is forbidden (line {node.lineno})."
            )
        self.generic_visit(node)

    def visit_Name(self, node):
        # Allow internal loop counter
        if node.id == "__loop_iter__":
            self.generic_visit(node)
            return

        # Disallow forbidden builtins or identifiers
        if node.id in FORBIDDEN_NAMES or node.id.startswith("__"):
            raise SandboxSecurityError(
                f"Access to forbidden identifier '{node.id}' is blocked for security (line {node.lineno})."
            )
        self.generic_visit(node)

    def visit_Call(self, node):
        # If calling a function directly by name, check name
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_NAMES:
                raise SandboxSecurityError(
                    f"Calling function '{node.func.id}' is forbidden (line {node.lineno})."
                )
            if node.func.id == "pow" and len(node.args) >= 2:
                exp_arg = node.args[1]
                if isinstance(exp_arg, ast.Constant) and isinstance(exp_arg.value, (int, float)):
                    if exp_arg.value > 100 or exp_arg.value < -100:
                        raise SandboxSecurityError(f"Exponent exceeds safety limit (max +/-100) (line {node.lineno}).")
        self.generic_visit(node)

    def visit_BinOp(self, node):
        if isinstance(node.op, ast.Pow):
            # Check exponent if constant
            if isinstance(node.right, ast.Constant) and isinstance(node.right.value, (int, float)):
                if node.right.value > 100 or node.right.value < -100:
                    raise SandboxSecurityError(f"Exponent exceeds safety limit (max +/-100) (line {node.lineno}).")
            elif isinstance(node.left, ast.Constant) and isinstance(node.left.value, (int, float)) and node.left.value > 1000:
                raise SandboxSecurityError(f"Base exceeds safety limit for dynamic exponentiation (line {node.lineno}).")
        elif isinstance(node.op, ast.Mult):
            # Check for sequence replication bombs e.g. 'a' * 10000000 or [0] * 10000000
            if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                if isinstance(node.right, ast.Constant) and isinstance(node.right.value, int) and node.right.value > 10000:
                    raise SandboxSecurityError(f"String replication exceeds safety limit (max 10000) (line {node.lineno}).")
            elif isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
                if isinstance(node.left, ast.Constant) and isinstance(node.left.value, int) and node.left.value > 10000:
                    raise SandboxSecurityError(f"String replication exceeds safety limit (max 10000) (line {node.lineno}).")
        self.generic_visit(node)

    def _validate_comprehension_generators(self, generators, lineno):
        for gen in generators:
            if isinstance(gen.iter, ast.Call) and isinstance(gen.iter.func, ast.Name) and gen.iter.func.id == "range":
                for arg in gen.iter.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, int) and arg.value > 10000:
                        raise SandboxSecurityError(f"Comprehension range exceeds safety limit (max 10000) (line {lineno}).")

    def visit_ListComp(self, node):
        self._validate_comprehension_generators(node.generators, node.lineno)
        self.generic_visit(node)

    def visit_SetComp(self, node):
        self._validate_comprehension_generators(node.generators, node.lineno)
        self.generic_visit(node)

    def visit_DictComp(self, node):
        self._validate_comprehension_generators(node.generators, node.lineno)
        self.generic_visit(node)

    def visit_GeneratorExp(self, node):
        self._validate_comprehension_generators(node.generators, node.lineno)
        self.generic_visit(node)


class LoopGuardTransformer(ast.NodeTransformer):
    """
    Injects loop iteration limits into while and for loops to prevent infinite hanging.
    """
    def __init__(self, max_iterations: int = 10000):
        super().__init__()
        self.max_iterations = max_iterations

    def visit_While(self, node):
        self.generic_visit(node)
        guard_ast = ast.parse(
            f"__loop_iter__ += 1\nif __loop_iter__ > {self.max_iterations}:\n    raise SandboxExecutionError('Execution loop limit ({self.max_iterations}) exceeded (infinite loop protection)')"
        ).body
        node.body = guard_ast + node.body
        return node

    def visit_For(self, node):
        self.generic_visit(node)
        guard_ast = ast.parse(
            f"__loop_iter__ += 1\nif __loop_iter__ > {self.max_iterations}:\n    raise SandboxExecutionError('Execution loop limit ({self.max_iterations}) exceeded (infinite loop protection)')"
        ).body
        node.body = guard_ast + node.body
        return node


def sanitize_and_validate_ast(source_code: str) -> ast.AST:
    """
    Parses and validates user Python source code against security rules,
    and applies loop guard transformations.
    Raises SandboxSecurityError if any violations are found.
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        raise SandboxExecutionError(f"Syntax error in signal score code: {e}")

    # 1. Security validation
    validator = ASTSecurityValidator()
    validator.visit(tree)

    # 2. Loop guard transformation
    transformer = LoopGuardTransformer()
    transformed_tree = transformer.visit(tree)
    ast.fix_missing_locations(transformed_tree)
    return transformed_tree


def _wrap_snippet_to_callable(code_snippet: str) -> str:
    """
    Wraps the user's snippet into a callable Python function body.
    Supports:
    - Snippets with top-level `return <expr>`
    - Snippets setting `score = ...` or `signal_score = ...`
    - Single expressions (e.g. `w1 * e1 + w2 * e2`)
    - Explicit function definitions (e.g. `def compute_signal_score(...)`)
    """
    stripped = code_snippet.strip()
    if not stripped:
        return "def __signal_calc__(extractions=None, **kwargs):\n    return 0.0"

    # If the user already defined the canonical main scoring function
    if (
        stripped.startswith("def compute_signal_score(")
        or stripped.startswith("def calculate_score(")
        or stripped.startswith("def signal_score(")
        or stripped.startswith("def calculate_signal_score(")
    ):
        return stripped

    # Try parsing as a pure expression first (e.g. `fit_score * 2 + trl_level` or `w1 * 0.3 + w2 * 0.7`)
    try:
        ast.parse(stripped, mode='eval')
        return f"def __signal_calc__(extractions=None, **kwargs):\n    return ({stripped})"
    except SyntaxError:
        pass

    # Indent lines for function body
    lines = stripped.split("\n")
    indented_lines = "\n".join(f"    {line}" for line in lines)

    # Wrap inside function body with loop iteration counter initialization
    wrapper = (
        "def __signal_calc__(extractions=None, **kwargs):\n"
        "    __loop_iter__ = 0\n"
        "    signal_score = None\n"
        "    score = None\n"
        f"{indented_lines}\n"
        "    if signal_score is not None:\n"
        "        return signal_score\n"
        "    if score is not None:\n"
        "        return score\n"
        "    return 0.0\n"
    )
    return wrapper


def execute_sandboxed_snippet(
    code_snippet: str,
    context_vars: Dict[str, Any],
    timeout_seconds: float = 2.0
) -> float:
    """
    Executes user-supplied Python code in a secure sandboxed environment with strict timeout.
    
    Args:
        code_snippet: The user's Python code string.
        context_vars: Dictionary of variables (e.g., extracted parameters).
        timeout_seconds: Maximum permitted execution duration before raising SandboxExecutionError.

    Returns:
        float: The computed numeric signal score.
    """
    if not code_snippet or not code_snippet.strip():
        # Fallback default: sum of numeric context values or 0.0
        numeric_vals = [v for v in context_vars.values() if isinstance(v, (int, float))]
        return float(sum(numeric_vals)) if numeric_vals else 0.0

    # 1. Wrap snippet into callable format
    wrapped_code = _wrap_snippet_to_callable(code_snippet)

    # 2. Static AST Security Validation and Loop Guard Injection
    ast_tree = sanitize_and_validate_ast(wrapped_code)

    # 3. Filter valid context variables for global and kwargs injection
    valid_vars = {
        k: v for k, v in context_vars.items()
        if isinstance(k, str) and k.isidentifier() and not k.startswith("_") and k not in FORBIDDEN_NAMES
    }

    EXCLUDED_NAMES = {
        *SAFE_BUILTINS.keys(),
        *FORBIDDEN_NAMES,
        "SandboxExecutionError",
        "SandboxSecurityError",
        "math",
        "extractions",
        "signal_score",
        "score",
        "__loop_iter__",
    }

    # 3.1 Safely initialize any undeclared variable names referenced in the AST snippet to 0.0 default
    for node in ast.walk(ast_tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            var_name = node.id
            if (
                var_name not in valid_vars
                and var_name not in EXCLUDED_NAMES
                and not var_name.startswith("__")
                and var_name.isidentifier()
            ):
                valid_vars[var_name] = 0.0

    # 4. Prepare execution scope with safe builtins, math, and variables in globals
    local_scope: Dict[str, Any] = {}
    global_scope: Dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        "math": math,
        "SandboxExecutionError": SandboxExecutionError,
        "SandboxSecurityError": SandboxSecurityError,
        **valid_vars,
    }

    # 5. Compile transformed AST
    try:
        compiled_code = compile(ast_tree, "<signal_score_sandbox>", "exec")
    except Exception as e:
        raise SandboxExecutionError(f"Compilation error: {e}")

    # 6. Execute definition and retrieve function
    try:
        exec(compiled_code, global_scope, local_scope)
    except SandboxExecutionError:
        raise
    except SandboxSecurityError:
        raise
    except Exception as e:
        raise SandboxExecutionError(f"Error during signal score definition: {e}")

    calc_fn = None
    # If the user snippet was wrapped into __signal_calc__, execute that wrapper
    if "__signal_calc__" in local_scope and callable(local_scope["__signal_calc__"]):
        calc_fn = local_scope["__signal_calc__"]
    else:
        # Check for explicit canonical score function names first
        for candidate_name in ("compute_signal_score", "calculate_signal_score", "signal_score", "score"):
            if candidate_name in local_scope and callable(local_scope[candidate_name]):
                calc_fn = local_scope[candidate_name]
                break
        if not calc_fn:
            for key, val in local_scope.items():
                if callable(val) and not key.startswith("_"):
                    calc_fn = val
                    break

    if not calc_fn or not callable(calc_fn):
        raise SandboxExecutionError("No executable function or calculation result found in snippet.")

    # 7. Run function with context under strict timeout enforcement
    def _run_calc():
        return calc_fn(extractions=context_vars, **valid_vars)

    try:
        effective_timeout = max(0.1, float(timeout_seconds or 2.0))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_calc)
            try:
                result = future.result(timeout=effective_timeout)
            except concurrent.futures.TimeoutError:
                raise SandboxExecutionError(f"Signal score execution timed out ({effective_timeout:.1f}s limit exceeded).")
    except ZeroDivisionError:
        logger.warning("ZeroDivisionError encountered during signal score evaluation; defaulting score to 0.0.")
        return 0.0
    except SandboxExecutionError:
        raise
    except SandboxSecurityError:
        raise
    except Exception as e:
        raise SandboxExecutionError(f"Error during signal score execution: {e}")

    if result is None:
        return 0.0

    try:
        return float(result)
    except (ValueError, TypeError) as e:
        raise SandboxExecutionError(f"Signal score returned non-numeric value '{result}': {e}")
