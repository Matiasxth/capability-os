"""Orchestrates code generation → sandbox execution → correction loop.

Process:
  1. Run generated code in the correct sandbox with test inputs.
  2. Verify outputs match expected shape from the contract.
  3. If execution fails, ask the LLM to fix the code (max 3 attempts).
  4. If all attempts fail, return validated=False with the last error.

Rule: the validator NEVER installs the code — it only validates.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from system.core.interpretation.llm_client import LLMClient, LLMClientError
from system.core.self_improvement.nodejs_sandbox import NodejsSandbox
from system.core.self_improvement.python_sandbox import PythonSandbox
from system.core.self_improvement.tool_code_generator import ToolCodeGenerator


_MAX_ATTEMPTS = 3

_FIX_SYSTEM = """
You are a code fixer. The previous code failed with the error shown below.
Fix ONLY the bug. Return the complete corrected code — same rules as before.
Return ONLY code, no prose.
""".strip()

_FIX_USER = """
Original code:
```
{code}
```

Error:
{error}

Return the corrected code only.
""".strip()


class ToolValidator:
    """Validates generated tool code via sandbox execution with auto-correction."""

    def __init__(
        self,
        python_sandbox: PythonSandbox,
        nodejs_sandbox: NodejsSandbox,
        code_generator: ToolCodeGenerator | None = None,
        llm_client: LLMClient | None = None,
    ):
        self._py_sb = python_sandbox
        self._js_sb = nodejs_sandbox
        self._gen = code_generator
        self._llm = llm_client

    def validate(
        self,
        code: str,
        contract: dict[str, Any],
        runtime: str = "python",
    ) -> dict[str, Any]:
        """Validate *code* by running it in a sandbox with test inputs.

        Returns ``{validated, runtime, code, test_output, attempts, error}``.
        """
        test_inputs = _generate_test_inputs(contract)
        expected_output_keys = set(contract.get("outputs", {}).keys())

        current_code = code
        last_error = ""

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            sb_result = self._run_sandbox(current_code, test_inputs, runtime)

            if sb_result["success"]:
                # Check output shape
                output = sb_result["output"]
                missing = expected_output_keys - set(output.keys()) - {"status", "error"}
                if not missing or not expected_output_keys:
                    return {
                        "validated": True,
                        "runtime": runtime,
                        "code": current_code,
                        "test_output": output,
                        "attempts": attempt,
                        "error": "",
                    }
                last_error = f"Missing output keys: {', '.join(sorted(missing))}"
            else:
                last_error = sb_result.get("error", "Unknown sandbox error")

            # Try LLM correction (if available and not last attempt)
            if attempt < _MAX_ATTEMPTS:
                fixed = self._attempt_fix(current_code, last_error, runtime)
                if fixed is not None:
                    current_code = fixed
                    continue
                # No LLM → can't fix, bail out
                break

        return {
            "validated": False,
            "runtime": runtime,
            "code": current_code,
            "test_output": {},
            "attempts": min(attempt, _MAX_ATTEMPTS),
            "error": last_error,
        }

    def _run_sandbox(self, code: str, inputs: dict[str, Any], runtime: str) -> dict[str, Any]:
        if runtime == "nodejs":
            return self._js_sb.execute(code, inputs)
        return self._py_sb.execute(code, inputs)

    def _attempt_fix(self, code: str, error: str, runtime: str) -> str | None:
        """Ask LLM to fix the code. Returns corrected code or None."""
        if self._llm is None:
            return None
        prompt = _FIX_USER.format(code=code, error=error)
        try:
            raw = self._llm.complete(system_prompt=_FIX_SYSTEM, user_prompt=prompt)
            fixed = _strip_fences(raw)
            if "execute" in fixed:
                return fixed
        except (LLMClientError, Exception):
            pass
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_test_inputs(contract: dict[str, Any]) -> dict[str, Any]:
    """Build plausible test inputs from the contract's input spec."""
    inputs_spec = contract.get("inputs", {})
    test: dict[str, Any] = {}
    for name, spec in inputs_spec.items():
        if not isinstance(spec, dict):
            continue
        field_type = spec.get("type", "string")
        if field_type == "string":
            test[name] = spec.get("description", name)[:50] or "test"
        elif field_type == "integer":
            test[name] = 1
        elif field_type == "number":
            test[name] = 1.0
        elif field_type == "boolean":
            test[name] = True
        elif field_type == "array":
            test[name] = []
        elif field_type == "object":
            test[name] = {}
        else:
            test[name] = "test"
    return test


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
    return text
