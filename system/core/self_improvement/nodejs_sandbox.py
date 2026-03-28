"""Executes generated Node.js code in an isolated subprocess.

Same security model as PythonSandbox:
  1. Static analysis rejects forbidden requires/patterns.
  2. Code runs in a fresh subprocess (node) via stdin/stdout JSON.
  3. Mandatory timeout.
  4. Working directory locked to workspace sandbox dir.
  5. Graceful fallback if Node.js is not installed.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from uuid import uuid4


_FORBIDDEN_RE = re.compile(
    r"""(?:require\s*\(\s*['"]child_process['"]|"""
    r"""require\s*\(\s*['"]cluster['"]|"""
    r"""\beval\s*\(|"""
    r"""\bFunction\s*\()""",
    re.VERBOSE,
)

_RUNNER_TEMPLATE = '''
const mod = require({module_path});
process.stdin.setEncoding("utf-8");
let data = "";
process.stdin.on("data", chunk => data += chunk);
process.stdin.on("end", async () => {{
  const inputs = data.trim() ? JSON.parse(data) : {{}};
  try {{
    const result = await mod.execute(inputs);
    process.stdout.write(JSON.stringify(result));
  }} catch (e) {{
    process.stdout.write(JSON.stringify({{ status: "error", error: e.message || String(e) }}));
  }}
}});
'''


def _find_node() -> str | None:
    """Return the node executable path, or None."""
    return shutil.which("node")


class NodejsSandbox:
    """Runs generated Node.js in an isolated subprocess."""

    def __init__(
        self,
        sandbox_dir: str | Path,
        timeout_sec: int = 30,
    ):
        self._sandbox_dir = Path(sandbox_dir).resolve()
        self._timeout = max(1, int(timeout_sec))

    def execute(self, code: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run *code* via ``node`` and return the result dict.

        Returns ``{success, output, error, duration_ms}``.
        """
        node = _find_node()
        if node is None:
            return {"success": False, "output": {}, "error": "Node.js is not installed.", "duration_ms": 0}

        issues = self._static_check(code)
        if issues:
            return {"success": False, "output": {}, "error": f"Blocked: {'; '.join(issues)}", "duration_ms": 0}

        self._sandbox_dir.mkdir(parents=True, exist_ok=True)
        uid = uuid4().hex[:8]
        module_path = self._sandbox_dir / f"temp_{uid}.js"
        runner_path = self._sandbox_dir / f"runner_{uid}.js"

        module_path.write_text(code, encoding="utf-8")
        runner_code = _RUNNER_TEMPLATE.format(module_path=json.dumps(str(module_path).replace("\\", "/")))
        runner_path.write_text(runner_code, encoding="utf-8")

        env = self._safe_env()
        input_json = json.dumps(inputs or {}, ensure_ascii=True)
        t0 = time.perf_counter()

        try:
            result = subprocess.run(
                [node, str(runner_path)],
                input=input_json,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=str(self._sandbox_dir),
                env=env,
            )
        except subprocess.TimeoutExpired:
            self._cleanup(module_path, runner_path)
            dur = int((time.perf_counter() - t0) * 1000)
            return {"success": False, "output": {}, "error": f"Timeout after {self._timeout}s.", "duration_ms": dur}
        except Exception as exc:
            self._cleanup(module_path, runner_path)
            dur = int((time.perf_counter() - t0) * 1000)
            return {"success": False, "output": {}, "error": str(exc), "duration_ms": dur}

        dur = int((time.perf_counter() - t0) * 1000)
        self._cleanup(module_path, runner_path)

        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "Unknown error").strip()[:500]
            return {"success": False, "output": {}, "error": error_text, "duration_ms": dur}

        stdout = result.stdout.strip()
        if not stdout:
            return {"success": False, "output": {}, "error": "No output produced.", "duration_ms": dur}

        try:
            output = json.loads(stdout)
        except json.JSONDecodeError:
            return {"success": False, "output": {}, "error": f"Invalid JSON: {stdout[:200]}", "duration_ms": dur}

        if not isinstance(output, dict):
            return {"success": False, "output": {}, "error": "Output must be an object.", "duration_ms": dur}

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
            issues.append(f"Forbidden: '{m.group().strip()}'")
        return issues

    @staticmethod
    def _safe_env() -> dict[str, str]:
        env: dict[str, str] = {}
        for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "NODE_PATH", "APPDATA"):
            val = os.environ.get(key)
            if val:
                env[key] = val
        return env

    @staticmethod
    def _cleanup(*paths: Path) -> None:
        for p in paths:
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass
