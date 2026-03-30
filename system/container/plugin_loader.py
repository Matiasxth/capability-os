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
                # Recurse one level deeper for nested plugins (e.g. channels/telegram/)
                for nested in sorted(subdir.iterdir()):
                    if not nested.is_dir() or nested.name.startswith(("_", ".")):
                        continue
                    nested_manifest = nested / "capos-plugin.json"
                    if nested_manifest.exists():
                        try:
                            result = PluginLoader._load_single(nested, nested_manifest)
                            if result:
                                results.append(result)
                        except Exception as exc:
                            logger.error(f"Failed loading nested plugin {nested.name}: {exc}")
                continue

            try:
                result = PluginLoader._load_single(subdir, manifest_path)
                if result:
                    results.append(result)
            except Exception as exc:
                logger.error(f"Failed loading {subdir.name}: {exc}")

        return results

    @staticmethod
    def _load_single(plugin_dir: Path, manifest_path: Path) -> tuple[Any, PluginManifest] | None:
        """Load a single plugin from its directory and manifest file."""
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = PluginManifest.from_dict(data)
        module_name, func_name = manifest.entry_point.rsplit(":", 1)
        module_path = plugin_dir / (module_name.replace(".", "/") + ".py")
        if not module_path.exists():
            module_path = plugin_dir / module_name / "__init__.py"

        spec = importlib.util.spec_from_file_location(
            f"capos_plugin_{manifest.id}", str(module_path),
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            factory = getattr(module, func_name)
            plugin = factory()
            logger.info(f"Loaded plugin: {manifest.id}")
            return (plugin, manifest)
        return None

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
