"""Start the CapOS server from CLI."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .formatter import header, dim, success


def run_serve(host: str = "0.0.0.0", port: int = 8000, sync: bool = False) -> None:
    project_root = Path(__file__).resolve().parents[2]

    # Set environment for docker-entrypoint
    os.environ["HOST"] = host
    os.environ["PORT"] = str(port)
    os.environ["WORKSPACE_ROOT"] = str(project_root)
    if sync:
        os.environ["CAPOS_ASYNC"] = "0"

    print(header("CapabilityOS Server"))
    print(dim(f"  Mode: {'sync' if sync else 'async (uvicorn)'}"))
    print(dim(f"  Port: {port}"))
    print()

    # Import and run the entrypoint (file has hyphen: docker-entrypoint.py)
    sys.path.insert(0, str(project_root))
    import importlib.util
    spec = importlib.util.spec_from_file_location("docker_entrypoint", str(project_root / "docker-entrypoint.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()
