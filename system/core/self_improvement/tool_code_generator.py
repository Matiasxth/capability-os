"""Generates tool implementation code (Python or Node.js) from a gap description.

Uses the LLM to produce a complete ``execute`` function that conforms to
the Capability OS tool handler contract.  Falls back to a template if
the LLM is unavailable.

Rule: generated code is NEVER executed in production — it must pass
through the sandbox validator first.
"""
from __future__ import annotations

import re
from typing import Any

from system.core.interpretation.llm_client import LLMClient, LLMClientError


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_PYTHON_SYSTEM = """
You are a Python code generator for Capability OS tools.
Rules:
1. Return ONLY the Python function — no prose, no markdown fences, no explanations.
2. The function must be named exactly "execute".
3. Signature: def execute(inputs: dict) -> dict:
4. All imports must be INSIDE the function body.
5. Allowed imports: json, re, math, datetime, urllib, pathlib, os.path, hashlib, base64, collections, itertools, functools, string, textwrap, csv, io, uuid, time, typing.
6. FORBIDDEN: subprocess, os.system, eval, exec, __import__, open() outside workspace, shutil.rmtree.
7. Must have try/except wrapping the main logic.
8. Must return a dict with at least a "status" key.
9. On error, return {"status": "error", "error": str(e)}.
""".strip()

_NODEJS_SYSTEM = """
You are a Node.js code generator for Capability OS tools.
Rules:
1. Return ONLY the JavaScript code — no prose, no markdown fences.
2. Export an async function named "execute".
3. Pattern: async function execute(inputs) { ... return {...}; }
4. module.exports = { execute };
5. Allowed requires: path, url, querystring, crypto, util, fs (read only within workspace).
6. FORBIDDEN: child_process, eval, Function constructor, require of arbitrary modules.
7. Must have try/catch wrapping the main logic.
8. Must return an object with at least a "status" property.
9. On error, return { status: "error", error: e.message }.
""".strip()

_USER_TEMPLATE = """
Generate a {runtime} tool implementation for:

Description: {description}

Expected inputs:
{inputs_desc}

Expected outputs:
{outputs_desc}

Return only the code, nothing else.
""".strip()


# ---------------------------------------------------------------------------
# Validation patterns
# ---------------------------------------------------------------------------

_PYTHON_FORBIDDEN = re.compile(
    r"\b(subprocess|os\.system|os\.popen|eval\s*\(|exec\s*\(|__import__)\b"
)

_NODEJS_FORBIDDEN = re.compile(
    r"\b(child_process|\.exec\s*\(|\.spawn\s*\(|eval\s*\(|Function\s*\()\b"
)


class ToolCodeGenerator:
    """Generates tool code via LLM with template fallback."""

    def __init__(self, llm_client: LLMClient | None = None):
        self._llm = llm_client

    def generate(self, gap: dict[str, Any], contract: dict[str, Any], runtime: str = "python") -> dict[str, Any]:
        """Generate code for the given runtime.

        Returns ``{code, runtime, valid, issues}`` where *valid* indicates
        the code passed static analysis (no forbidden patterns).
        """
        if runtime == "nodejs":
            return self.generate_nodejs(gap, contract)
        return self.generate_python(gap, contract)

    def generate_python(self, gap: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
        description = gap.get("description") or gap.get("intent") or gap.get("capability_id", "unknown task")
        code = self._call_llm(_PYTHON_SYSTEM, description, contract, "python")
        if code is None:
            code = _python_fallback(description, contract)
        issues = _check_python(code)
        return {"code": code, "runtime": "python", "valid": len(issues) == 0, "issues": issues}

    def generate_nodejs(self, gap: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
        description = gap.get("description") or gap.get("intent") or gap.get("capability_id", "unknown task")
        code = self._call_llm(_NODEJS_SYSTEM, description, contract, "nodejs")
        if code is None:
            code = _nodejs_fallback(description, contract)
        issues = _check_nodejs(code)
        return {"code": code, "runtime": "nodejs", "valid": len(issues) == 0, "issues": issues}

    def _call_llm(self, system: str, description: str, contract: dict[str, Any], runtime: str) -> str | None:
        if self._llm is None:
            return None
        inputs_desc = _describe_fields(contract.get("inputs", {}))
        outputs_desc = _describe_fields(contract.get("outputs", {}))
        prompt = _USER_TEMPLATE.format(
            runtime=runtime,
            description=description,
            inputs_desc=inputs_desc or "(none)",
            outputs_desc=outputs_desc or "(none)",
        )
        try:
            raw = self._llm.complete(system_prompt=system, user_prompt=prompt)
            return _strip_fences(raw)
        except LLMClientError:
            return None


# ---------------------------------------------------------------------------
# Static analysis
# ---------------------------------------------------------------------------

def _check_python(code: str) -> list[str]:
    issues: list[str] = []
    if "def execute" not in code:
        issues.append("Missing 'def execute' function.")
    for m in _PYTHON_FORBIDDEN.finditer(code):
        issues.append(f"Forbidden pattern: '{m.group()}'.")
    return issues


def _check_nodejs(code: str) -> list[str]:
    issues: list[str] = []
    if "function execute" not in code and "execute" not in code:
        issues.append("Missing 'execute' function.")
    for m in _NODEJS_FORBIDDEN.finditer(code):
        issues.append(f"Forbidden pattern: '{m.group()}'.")
    return issues


# ---------------------------------------------------------------------------
# Fallback templates
# ---------------------------------------------------------------------------

def _python_fallback(description: str, contract: dict[str, Any]) -> str:
    inputs = contract.get("inputs", {})
    params = ", ".join(f'inputs.get("{k}", "")' for k in inputs) or '"no inputs"'
    return f'''def execute(inputs: dict) -> dict:
    """{description}"""
    try:
        # TODO: implement actual logic
        result = str({params})
        return {{"status": "success", "result": result}}
    except Exception as e:
        return {{"status": "error", "error": str(e)}}
'''


def _nodejs_fallback(description: str, contract: dict[str, Any]) -> str:
    return f'''async function execute(inputs) {{
  // {description}
  try {{
    // TODO: implement actual logic
    const result = JSON.stringify(inputs);
    return {{ status: "success", result }};
  }} catch (e) {{
    return {{ status: "error", error: e.message }};
  }}
}}
module.exports = {{ execute }};
'''


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _describe_fields(fields: dict[str, Any]) -> str:
    lines: list[str] = []
    for name, spec in fields.items():
        if isinstance(spec, dict):
            t = spec.get("type", "string")
            req = " (required)" if spec.get("required") else ""
            desc = spec.get("description", "")
            lines.append(f"- {name}: {t}{req} — {desc}")
    return "\n".join(lines)


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop first and last fence lines
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
    return text
