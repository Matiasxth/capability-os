"""Safe expression evaluator using AST parsing.

Replaces unsafe ``eval()`` for workflow condition nodes.
Only allows:
- Comparisons: ==, !=, >, <, >=, <=
- Boolean ops: and, or, not
- Attribute access: result.status, result["key"]
- Literals: strings, numbers, booleans, None
- The ``in`` operator for membership tests

Rejects: function calls, imports, assignments, lambdas, comprehensions.
"""
from __future__ import annotations

import ast
import operator
from typing import Any


class UnsafeExpressionError(ValueError):
    """Raised when an expression contains disallowed AST nodes."""


# Allowed comparison operators
_CMP_OPS: dict[type, Any] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.Lt: operator.lt,
    ast.GtE: operator.ge,
    ast.LtE: operator.le,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

# Allowed boolean operators
_BOOL_OPS: dict[type, Any] = {
    ast.And: all,
    ast.Or: any,
}

# Allowed unary operators
_UNARY_OPS: dict[type, Any] = {
    ast.Not: operator.not_,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# AST node types we allow
_ALLOWED_NODES = (
    ast.Expression,
    ast.Compare,
    ast.BoolOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Attribute,
    ast.Subscript,
    ast.Index,       # Python 3.8 compat
    ast.Load,
    ast.Tuple,
    ast.List,
    # Comparison operator nodes
    ast.Eq, ast.NotEq, ast.Gt, ast.Lt, ast.GtE, ast.LtE,
    ast.Is, ast.IsNot, ast.In, ast.NotIn,
    # Boolean operator nodes
    ast.And, ast.Or,
    # Unary operator nodes
    ast.Not, ast.USub, ast.UAdd,
)


def safe_eval(expression: str, variables: dict[str, Any] | None = None) -> Any:
    """Evaluate a simple expression safely.

    Args:
        expression: A Python-like expression string.
        variables: Name bindings available in the expression (e.g. ``{"result": {...}}``).

    Returns:
        The evaluated result.

    Raises:
        UnsafeExpressionError: If the expression contains disallowed constructs.
        ValueError: If the expression cannot be parsed.
    """
    variables = variables or {}

    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression syntax: {exc}") from exc

    _validate(tree)
    return _eval_node(tree.body, variables)


def _validate(tree: ast.AST) -> None:
    """Walk the AST and reject any disallowed node types."""
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise UnsafeExpressionError(
                f"Disallowed expression construct: {type(node).__name__}. "
                f"Only comparisons, boolean ops, attribute access, and literals are allowed."
            )


def _eval_node(node: ast.AST, variables: dict[str, Any]) -> Any:
    """Recursively evaluate an AST node."""

    # Literal values: 42, "hello", True, None
    if isinstance(node, ast.Constant):
        return node.value

    # Variable names: result, status
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ValueError(f"Undefined variable: '{node.id}'")
        return variables[node.id]

    # Attribute access: result.status
    if isinstance(node, ast.Attribute):
        obj = _eval_node(node.value, variables)
        attr = node.attr
        if isinstance(obj, dict):
            return obj.get(attr)
        return getattr(obj, attr, None)

    # Subscript access: result["key"] or result[0]
    if isinstance(node, ast.Subscript):
        obj = _eval_node(node.value, variables)
        # Python 3.8 wraps in ast.Index, 3.9+ uses slice directly
        sl = node.slice
        if isinstance(sl, ast.Index):
            sl = sl.value  # type: ignore[attr-defined]
        key = _eval_node(sl, variables)
        try:
            return obj[key]
        except (KeyError, IndexError, TypeError):
            return None

    # Comparisons: a == b, a > b, a in b
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, variables)
        for op_node, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, variables)
            op_fn = _CMP_OPS.get(type(op_node))
            if op_fn is None:
                raise UnsafeExpressionError(f"Unsupported comparison: {type(op_node).__name__}")
            if not op_fn(left, right):
                return False
            left = right
        return True

    # Boolean ops: a and b, a or b
    if isinstance(node, ast.BoolOp):
        fn = _BOOL_OPS.get(type(node.op))
        if fn is None:
            raise UnsafeExpressionError(f"Unsupported boolean op: {type(node.op).__name__}")
        values = [_eval_node(v, variables) for v in node.values]
        return fn(values)

    # Unary ops: not x, -x
    if isinstance(node, ast.UnaryOp):
        fn = _UNARY_OPS.get(type(node.op))
        if fn is None:
            raise UnsafeExpressionError(f"Unsupported unary op: {type(node.op).__name__}")
        return fn(_eval_node(node.operand, variables))

    # Tuple/List literals: (1, 2), [1, 2]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_eval_node(el, variables) for el in node.elts]

    raise UnsafeExpressionError(f"Unsupported node: {type(node).__name__}")
