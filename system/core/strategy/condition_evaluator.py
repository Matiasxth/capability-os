"""Evaluates condition expressions used in conditional strategy steps.

Supported formats:
  - ``{{expr}}``                    — truthy check
  - ``{{expr}} == literal``         — equality
  - ``{{expr}} != literal``         — inequality
  - ``{{expr}} > | < | >= | <= N``  — numeric comparison

Literals: integers, floats, ``true``, ``false``, ``null``, quoted strings.
"""
from __future__ import annotations

import re
from typing import Any

from system.core.state import StateManager


class ConditionError(ValueError):
    """Raised when a condition expression is malformed or cannot be evaluated."""


_TOKEN_RE = re.compile(r"\{\{([^{}]+)\}\}")
_COMPARE_RE = re.compile(
    r"^\s*(\{\{[^{}]+\}\})\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*$"
)


def evaluate_condition(condition: str, state_manager: StateManager) -> bool:
    condition = condition.strip()
    if not condition:
        raise ConditionError("Condition string must not be empty.")

    # Case 1: bare truthy — "{{expr}}"
    token_match = _TOKEN_RE.fullmatch(condition)
    if token_match:
        expr = token_match.group(1).strip()
        value = state_manager.resolve_expression(expr)
        return _truthy(value)

    # Case 2: comparison — "{{expr}} OP literal"
    cmp_match = _COMPARE_RE.match(condition)
    if cmp_match:
        lhs_token, operator, rhs_raw = cmp_match.groups()
        # Extract expression from {{ }}
        inner = _TOKEN_RE.match(lhs_token)
        if not inner:
            raise ConditionError(f"Invalid condition left-hand side: '{lhs_token}'.")
        expr = inner.group(1).strip()
        lhs = state_manager.resolve_expression(expr)
        rhs = _parse_literal(rhs_raw.strip())
        return _compare(lhs, operator, rhs)

    raise ConditionError(
        f"Invalid condition format: '{condition}'. "
        "Expected '{{expr}} OP literal' or '{{expr}}'."
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _truthy(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)) and value == 0:
        return False
    if isinstance(value, str) and value == "":
        return False
    return True


def _parse_literal(raw: str) -> Any:
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw in ("null", "none", "None"):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    if len(raw) >= 2 and raw[0] in ('"', "'") and raw[0] == raw[-1]:
        return raw[1:-1]
    return raw


def _compare(lhs: Any, operator: str, rhs: Any) -> bool:
    if operator == "==":
        return _coerce_equal(lhs, rhs)
    if operator == "!=":
        return not _coerce_equal(lhs, rhs)
    # Numeric comparisons
    try:
        l_num = float(lhs)
        r_num = float(rhs)
    except (TypeError, ValueError) as exc:
        raise ConditionError(
            f"Cannot apply '{operator}' between '{lhs}' and '{rhs}'."
        ) from exc
    if operator == ">":
        return l_num > r_num
    if operator == "<":
        return l_num < r_num
    if operator == ">=":
        return l_num >= r_num
    if operator == "<=":
        return l_num <= r_num
    raise ConditionError(f"Unknown operator '{operator}'.")


def _coerce_equal(lhs: Any, rhs: Any) -> bool:
    if lhs == rhs:
        return True
    try:
        return float(lhs) == float(rhs)
    except (TypeError, ValueError):
        pass
    return str(lhs) == str(rhs)
