"""Tests for the safe expression evaluator."""

import pytest
from system.core.strategy.safe_expression import safe_eval, UnsafeExpressionError


# --- Valid expressions ---

class TestBasicExpressions:
    def test_literal_true(self):
        assert safe_eval("True") is True

    def test_literal_false(self):
        assert safe_eval("False") is False

    def test_literal_number(self):
        assert safe_eval("42") == 42

    def test_literal_string(self):
        assert safe_eval("'hello'") == "hello"

    def test_literal_none(self):
        assert safe_eval("None") is None

    def test_comparison_eq(self):
        assert safe_eval("x == 5", {"x": 5}) is True
        assert safe_eval("x == 5", {"x": 3}) is False

    def test_comparison_neq(self):
        assert safe_eval("x != 5", {"x": 3}) is True

    def test_comparison_gt(self):
        assert safe_eval("x > 10", {"x": 15}) is True
        assert safe_eval("x > 10", {"x": 5}) is False

    def test_comparison_lt(self):
        assert safe_eval("x < 10", {"x": 5}) is True

    def test_comparison_gte(self):
        assert safe_eval("x >= 10", {"x": 10}) is True

    def test_comparison_lte(self):
        assert safe_eval("x <= 10", {"x": 10}) is True

    def test_boolean_and(self):
        assert safe_eval("x > 0 and x < 10", {"x": 5}) is True
        assert safe_eval("x > 0 and x < 10", {"x": 15}) is False

    def test_boolean_or(self):
        assert safe_eval("x > 10 or x < 0", {"x": -1}) is True
        assert safe_eval("x > 10 or x < 0", {"x": 5}) is False

    def test_not(self):
        assert safe_eval("not False") is True
        assert safe_eval("not True") is False

    def test_in_operator(self):
        assert safe_eval("'a' in items", {"items": ["a", "b", "c"]}) is True
        assert safe_eval("'z' in items", {"items": ["a", "b"]}) is False

    def test_not_in(self):
        assert safe_eval("'z' not in items", {"items": ["a", "b"]}) is True


class TestAttributeAccess:
    def test_dict_attribute(self):
        result = {"status": "success", "count": 42}
        assert safe_eval("result.status == 'success'", {"result": result}) is True

    def test_dict_subscript(self):
        result = {"status": "error"}
        assert safe_eval('result["status"] == "error"', {"result": result}) is True

    def test_nested_attribute(self):
        result = {"data": {"value": 10}}
        assert safe_eval("result.data.value > 5", {"result": result}) is True

    def test_missing_attribute_returns_none(self):
        result = {"status": "ok"}
        assert safe_eval("result.missing == None", {"result": result}) is True


class TestWorkflowConditions:
    """Test realistic workflow condition expressions."""

    def test_result_status_check(self):
        result = {"status": "success", "items": [1, 2, 3]}
        assert safe_eval("result.status == 'success'", {"result": result}) is True

    def test_result_with_none(self):
        assert safe_eval("result == None", {"result": None}) is True
        assert safe_eval("result != None", {"result": {"ok": True}}) is True

    def test_numeric_result(self):
        result = {"exit_code": 0}
        assert safe_eval("result.exit_code == 0", {"result": result}) is True


# --- Malicious inputs (must be rejected) ---

class TestMaliciousExpressions:
    def test_import_rejected(self):
        with pytest.raises(UnsafeExpressionError):
            safe_eval("__import__('os').system('rm -rf /')")

    def test_function_call_rejected(self):
        with pytest.raises(UnsafeExpressionError):
            safe_eval("print('hacked')")

    def test_lambda_rejected(self):
        with pytest.raises(UnsafeExpressionError):
            safe_eval("(lambda: 1)()")

    def test_exec_rejected(self):
        with pytest.raises(UnsafeExpressionError):
            safe_eval("exec('import os')")

    def test_comprehension_rejected(self):
        with pytest.raises(UnsafeExpressionError):
            safe_eval("[x for x in range(10)]")

    def test_generator_rejected(self):
        with pytest.raises(UnsafeExpressionError):
            safe_eval("(x for x in range(10))")

    def test_class_attribute_escape_rejected(self):
        with pytest.raises(UnsafeExpressionError):
            safe_eval("().__class__.__bases__[0].__subclasses__()")

    def test_dunder_access_via_getattr(self):
        with pytest.raises(UnsafeExpressionError):
            safe_eval("getattr(result, '__class__')", {"result": {}})

    def test_walrus_operator_rejected(self):
        with pytest.raises((UnsafeExpressionError, SyntaxError, ValueError)):
            safe_eval("(x := 5)")

    def test_assignment_rejected(self):
        with pytest.raises((SyntaxError, ValueError)):
            safe_eval("x = 5")

    def test_multiline_rejected(self):
        with pytest.raises((SyntaxError, ValueError)):
            safe_eval("import os\nos.system('ls')")


class TestEdgeCases:
    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            safe_eval("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            safe_eval("   ")

    def test_undefined_variable(self):
        with pytest.raises(ValueError, match="Undefined variable"):
            safe_eval("unknown_var == 5")

    def test_chained_comparison(self):
        assert safe_eval("0 < x < 10", {"x": 5}) is True
        assert safe_eval("0 < x < 10", {"x": 15}) is False

    def test_negative_number(self):
        assert safe_eval("-5 < 0") is True

    def test_tuple_literal(self):
        result = safe_eval("(1, 2, 3)")
        assert result == [1, 2, 3]
