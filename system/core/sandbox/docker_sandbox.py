"""Docker sandbox — runs commands in ephemeral containers.

Used for Level 3 security tools: full isolation, no host access,
read-only workspace volume, network disabled.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class DockerSandbox:
    """Execute commands in ephemeral Docker containers."""

    def __init__(
        self,
        image: str = "python:3.12-slim",
        timeout_seconds: int = 60,
        max_memory_mb: int = 512,
        network_enabled: bool = False,
        workspace_mount: str | None = None,
    ) -> None:
        self.image = image
        self.timeout = timeout_seconds
        self.max_memory = f"{max_memory_mb}m"
        self.network = network_enabled
        self.workspace_mount = workspace_mount
        self._available: bool | None = None

    @property
    def available(self) -> bool:
        """Check if Docker is available on this system."""
        if self._available is None:
            try:
                r = subprocess.run(
                    ["docker", "info"],
                    capture_output=True, timeout=5,
                )
                self._available = r.returncode == 0
            except Exception:
                self._available = False
        return self._available

    def execute(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        """Run a command in an ephemeral Docker container.

        Returns: {status, stdout, stderr, exit_code, timed_out, container_used}
        """
        if not self.available:
            return {
                "status": "error",
                "stdout": "",
                "stderr": "Docker not available",
                "exit_code": -1,
                "timed_out": False,
                "container_used": False,
            }

        docker_cmd = [
            "docker", "run", "--rm",
            "--memory", self.max_memory,
            "--cpus", "1",
        ]

        if not self.network:
            docker_cmd.extend(["--network", "none"])

        if self.workspace_mount:
            docker_cmd.extend(["-v", f"{self.workspace_mount}:/workspace:ro"])
            docker_cmd.extend(["-w", "/workspace"])

        docker_cmd.extend([self.image, "sh", "-c", command])

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "status": "success" if result.returncode == 0 else "error",
                "stdout": result.stdout[:10000],
                "stderr": result.stderr[:5000],
                "exit_code": result.returncode,
                "timed_out": False,
                "container_used": True,
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "stdout": "",
                "stderr": f"Container timed out after {self.timeout}s",
                "exit_code": -1,
                "timed_out": True,
                "container_used": True,
            }
        except Exception as exc:
            return {
                "status": "error",
                "stdout": "",
                "stderr": str(exc),
                "exit_code": -1,
                "timed_out": False,
                "container_used": False,
            }

    def execute_python(self, code: str) -> dict[str, Any]:
        """Execute Python code in a Docker container."""
        escaped = code.replace("'", "'\\''")
        return self.execute(f"python3 -c '{escaped}'")
