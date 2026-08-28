"""
Secure Python Sandbox Engine for Signal Score Calculation.

Provides AST-level static security inspection, restricted execution scope (__builtins__ lockdown),
and AST loop iteration limits to safely evaluate user-supplied Python formulas on extracted parameters.
"""

import ast
import math
import logging
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
    """Raised when safe user code fails during runtime or exceeds loop iteration limits."""
    pass


class ASTSecurityValidator(ast.NodeVisitor):
    """
    Traverses the Python AST to statically detect dangerous operations,
    such as imports, private/dunder attribute lookups, and forbidden builtins.
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

    # If the user already defined a function
    if stripped.startswith("def "):
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
    Executes user-supplied Python code in a secure sandboxed environment.
    
    Args:
        code_snippet: The user's Python code string.
        context_vars: Dictionary of variables (e.g., extracted parameters).
        timeout_seconds: Kept for API compatibility.

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

    # 4. Prepare execution scope with safe builtins, math, and variables in globals
    local_scope: Dict[str, Any] = {}
    global_scope: Dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        "math": math,
        "SandboxExecutionError": SandboxExecutionError,
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
    for key, val in local_scope.items():
        if callable(val) and not key.startswith("_"):
            calc_fn = val
            break
    if not calc_fn and "__signal_calc__" in local_scope:
        calc_fn = local_scope["__signal_calc__"]

    if not calc_fn or not callable(calc_fn):
        raise SandboxExecutionError("No executable function or calculation result found in snippet.")

    # 7. Run function with context
    try:
        result = calc_fn(extractions=context_vars, **valid_vars)
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
