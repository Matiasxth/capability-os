"""Executes generated Python code in an isolated subprocess.

Security layers:
  1. Static analysis rejects forbidden imports/patterns before execution.
  2. Code runs in a fresh subprocess with controlled env (no secrets).
  3. Mandatory timeout (default 30s).
  4. Working directory locked to workspace sandbox dir.
  5. Output parsed from stdout JSON only — no shared memory.

Rule: this module is the ONLY place generated Python code is ever executed.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4


_FORBIDDEN_RE = re.compile(
    r"\b(subprocess|os\.system|os\.popen|eval\s*\(|exec\s*\(|__import__|"
    r"shutil\.rmtree|os\.remove|os\.unlink|os\.rmdir)\b"
)

_WRAPPER_TEMPLATE = '''
import json, sys
sys.path.insert(0, {project_root!r})

{user_code}

if __name__ == "__main__":
    _raw_inputs = sys.stdin.read()
    _inputs = json.loads(_raw_inputs) if _raw_inputs.strip() else {{}}
    try:
        _result = execute(_inputs)
    except Exception as _exc:
        _result = {{"status": "error", "error": str(_exc)}}
    sys.stdout.write(json.dumps(_result, ensure_ascii=True, default=str))
'''


class PythonSandboxError(RuntimeError):
    """Raised when sandbox execution is rejected or fails."""


class PythonSandbox:
    """Runs generated Python in an isolated subprocess."""

    def __init__(
        self,
        sandbox_dir: str | Path,
        timeout_sec: int = 30,
        project_root: str | Path | None = None,
    ):
        self._sandbox_dir = Path(sandbox_dir).resolve()
        self._timeout = max(1, int(timeout_sec))
        self._project_root = str(Path(project_root).resolve()) if project_root else str(Path(__file__).resolve().parents[3])

    def execute(self, code: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run *code* in a subprocess and return the result dict.

        Returns ``{success, output, error, duration_ms}``.
        """
        # 1. Static check
        issues = self._static_check(code)
        if issues:
            return {"success": False, "output": {}, "error": f"Blocked: {'; '.join(issues)}", "duration_ms": 0}

        # 2. Write temp file
        self._sandbox_dir.mkdir(parents=True, exist_ok=True)
        file_id = uuid4().hex[:8]
        script_path = self._sandbox_dir / f"temp_{file_id}.py"

        wrapper = _WRAPPER_TEMPLATE.format(project_root=self._project_root, user_code=code)
        script_path.write_text(wrapper, encoding="utf-8")

        # 3. Execute
        env = self._safe_env()
        input_json = json.dumps(inputs or {}, ensure_ascii=True)
        t0 = time.perf_counter()

        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                input=input_json,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=str(self._sandbox_dir),
                env=env,
            )
        except subprocess.TimeoutExpired:
            self._cleanup(script_path)
            dur = int((time.perf_counter() - t0) * 1000)
            return {"success": False, "output": {}, "error": f"Timeout after {self._timeout}s.", "duration_ms": dur}
        except Exception as exc:
            self._cleanup(script_path)
            dur = int((time.perf_counter() - t0) * 1000)
            return {"success": False, "output": {}, "error": str(exc), "duration_ms": dur}

        dur = int((time.perf_counter() - t0) * 1000)
        self._cleanup(script_path)

        # 4. Parse output
        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "Unknown error").strip()[:500]
            return {"success": False, "output": {}, "error": error_text, "duration_ms": dur}

        stdout = result.stdout.strip()
        if not stdout:
            return {"success": False, "output": {}, "error": "No output produced.", "duration_ms": dur}

        try:
            output = json.loads(stdout)
        except json.JSONDecodeError:
            return {"success": False, "output": {}, "error": f"Invalid JSON output: {stdout[:200]}", "duration_ms": dur}

        if not isinstance(output, dict):
            return {"success": False, "output": {}, "error": "Output must be a dict.", "duration_ms": dur}

        is_error = output.get("status") == "error"
        return {
            "success": not is_error,
            "output": output,
            "error": output.get("error", "") if is_error else "",
            "duration_ms": dur,
        }

    @staticmethod
    def _static_check(code: str) -> list[str]:
        issues: list[str] = []
        for m in _FORBIDDEN_RE.finditer(code):
            issues.append(f"Forbidden: '{m.group()}'")
        return issues

    @staticmethod
    def _safe_env() -> dict[str, str]:
        """Build a minimal environment without secrets."""
        env: dict[str, str] = {}
        for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "PYTHONPATH"):
            val = os.environ.get(key)
            if val:
                env[key] = val
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    @staticmethod
    def _cleanup(path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
