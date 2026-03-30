"""SandboxManager — routes tool execution to the appropriate sandbox level.

Level 1: No sandbox (direct execution)
Level 2: ProcessSandbox (timeout, memory limit, restricted env)
Level 3: DockerSandbox (ephemeral container, no network, read-only mount)
"""
from __future__ import annotations

import logging
from typing import Any

from .process_sandbox import ProcessSandbox
from .docker_sandbox import DockerSandbox

logger = logging.getLogger("capos.sandbox")


class SandboxManager:
    """Routes command execution to the appropriate sandbox based on security level."""

    def __init__(
        self,
        workspace_root: str = "",
        process_timeout: int = 30,
        docker_timeout: int = 60,
        docker_image: str = "python:3.12-slim",
        max_memory_mb: int = 512,
    ) -> None:
        self.workspace_root = workspace_root
        self.process_sandbox = ProcessSandbox(
            timeout_seconds=process_timeout,
            max_memory_mb=max_memory_mb,
        )
        self.docker_sandbox = DockerSandbox(
            image=docker_image,
            timeout_seconds=docker_timeout,
            max_memory_mb=max_memory_mb,
            workspace_mount=workspace_root if workspace_root else None,
        )

    @property
    def docker_available(self) -> bool:
        return self.docker_sandbox.available

    def execute(self, command: str, security_level: int = 1, cwd: str | None = None) -> dict[str, Any]:
        """Execute a command at the specified security level.

        Level 1: Direct execution (no sandbox)
        Level 2: Process sandbox (restricted subprocess)
        Level 3: Docker sandbox (ephemeral container)
        """
        if security_level >= 3:
            if self.docker_sandbox.available:
                logger.info(f"L3 sandbox: docker exec: {command[:80]}")
                return self.docker_sandbox.execute(command, cwd=cwd)
            else:
                logger.warning("Docker not available, falling back to process sandbox")
                return self.process_sandbox.execute(command, cwd=cwd)

        elif security_level >= 2:
            logger.info(f"L2 sandbox: process exec: {command[:80]}")
            return self.process_sandbox.execute(command, cwd=cwd)

        else:
            # Level 1: direct (this shouldn't normally be called through sandbox)
            import subprocess
            try:
                result = subprocess.run(
                    command, shell=True, cwd=cwd,
                    capture_output=True, text=True, timeout=60,
                    encoding="utf-8", errors="replace",
                )
                return {
                    "status": "success" if result.returncode == 0 else "error",
                    "stdout": result.stdout[:10000],
                    "stderr": result.stderr[:5000],
                    "exit_code": result.returncode,
                    "timed_out": False,
                }
            except Exception as exc:
                return {"status": "error", "stdout": "", "stderr": str(exc), "exit_code": -1, "timed_out": False}

    def get_status(self) -> dict[str, Any]:
        return {
            "docker_available": self.docker_available,
            "process_sandbox": True,
            "process_timeout": self.process_sandbox.timeout,
            "docker_timeout": self.docker_sandbox.timeout,
            "docker_image": self.docker_sandbox.image,
        }
