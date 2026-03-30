"""Plugin loader — discovers and loads plugins from directories."""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

from system.sdk.manifest import PluginManifest

logger = logging.getLogger("capos.loader")


class PluginLoader:
    """Discovers and loads plugins from file system."""

    @staticmethod
    def load_from_directory(plugins_dir: Path) -> list[tuple[Any, PluginManifest]]:
        """Scan directory for plugins. Each subdir with capos-plugin.json is a plugin."""
        results: list[tuple[Any, PluginManifest]] = []
        if not plugins_dir.exists():
            return results

        for subdir in sorted(plugins_dir.iterdir()):
            if not subdir.is_dir() or subdir.name.startswith(("_", ".")):
                continue
            manifest_path = subdir / "capos-plugin.json"
            if not manifest_path.exists():
                # Try __init__.py with MANIFEST
                init_path = subdir / "__init__.py"
                if init_path.exists():
                    try:
                        result = PluginLoader._load_from_module(subdir)
                        if result:
                            results.append(result)
                    except Exception as exc:
                        logger.error(f"Failed loading plugin {subdir.name}: {exc}")
                continue

            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = PluginManifest.from_dict(data)
                module_name, func_name = manifest.entry_point.rsplit(":", 1)
                module_path = subdir / (module_name.replace(".", "/") + ".py")
                if not module_path.exists():
                    module_path = subdir / module_name / "__init__.py"

                spec = importlib.util.spec_from_file_location(
                    f"capos_plugin_{manifest.id}", str(module_path),
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    factory = getattr(module, func_name)
                    plugin = factory()
                    results.append((plugin, manifest))
                    logger.info(f"Loaded plugin: {manifest.id}")
            except Exception as exc:
                logger.error(f"Failed loading {subdir.name}: {exc}")

        return results

    @staticmethod
    def _load_from_module(subdir: Path) -> tuple[Any, PluginManifest] | None:
        """Load from a Python module that exports MANIFEST and create_plugin."""
        spec = importlib.util.spec_from_file_location(
            f"capos_plugin_{subdir.name}",
            str(subdir / "__init__.py"),
        )
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        manifest_data = getattr(module, "MANIFEST", None)
        factory = getattr(module, "create_plugin", None)
        if manifest_data and factory:
            manifest = PluginManifest.from_dict(manifest_data) if isinstance(manifest_data, dict) else manifest_data
            return factory(), manifest
        return None
