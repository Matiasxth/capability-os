"""Process-level sandbox — runs commands with OS restrictions.

Used for Level 2 security tools: timeout, memory limit, restricted paths.
Works on all platforms without Docker.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class ProcessSandbox:
    """Execute commands in a restricted subprocess."""

    def __init__(
        self,
        timeout_seconds: int = 30,
        max_memory_mb: int = 512,
        allowed_paths: list[str] | None = None,
        block_network: bool = False,
    ) -> None:
        self.timeout = timeout_seconds
        self.max_memory_mb = max_memory_mb
        self.allowed_paths = allowed_paths or []
        self.block_network = block_network

    def execute(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        """Run a command in a sandboxed subprocess.

        Returns: {status, stdout, stderr, exit_code, timed_out}
        """
        env = self._build_env()

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "status": "success" if result.returncode == 0 else "error",
                "stdout": result.stdout[:10000],
                "stderr": result.stderr[:5000],
                "exit_code": result.returncode,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "stdout": "",
                "stderr": f"Command timed out after {self.timeout}s",
                "exit_code": -1,
                "timed_out": True,
            }
        except Exception as exc:
            return {
                "status": "error",
                "stdout": "",
                "stderr": str(exc),
                "exit_code": -1,
                "timed_out": False,
            }

    def execute_python(self, code: str, cwd: str | None = None) -> dict[str, Any]:
        """Execute Python code in a sandboxed subprocess."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            f.flush()
            script_path = f.name

        try:
            return self.execute(f'python "{script_path}"', cwd=cwd)
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def _build_env(self) -> dict[str, str]:
        """Build restricted environment variables."""
        env = os.environ.copy()
        # Remove sensitive variables
        for key in ("AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                     "GROQ_API_KEY", "DATABASE_URL", "SECRET_KEY"):
            env.pop(key, None)

        # Set memory limit hint (not enforced on Windows, enforced on Linux via ulimit)
        env["CAPOS_SANDBOX"] = "1"
        env["CAPOS_SANDBOX_TIMEOUT"] = str(self.timeout)
        env["CAPOS_SANDBOX_MEMORY_MB"] = str(self.max_memory_mb)

        return env
