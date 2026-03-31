"""Plugin loader — discovers and loads plugins from directories."""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import re
from pathlib import Path
from typing import Any

from system.sdk.manifest import PluginManifest

logger = logging.getLogger("capos.loader")


def _parse_ver(v: str) -> tuple[int, ...]:
    """Parse a version string into a tuple of ints."""
    return tuple(int(x) for x in re.split(r"[.\-]", v)[:3] if x.isdigit()) or (0,)


def _version_satisfies(version: str, constraint: str) -> bool:
    """Check if a version satisfies a constraint string.

    Supports: ``>=1.0.0``, ``<2.0.0``, ``==1.0.0``, ``>=1.0.0,<2.0.0``
    """
    ver = _parse_ver(version)
    for part in constraint.split(","):
        part = part.strip()
        if not part:
            continue
        for op in (">=", "<=", "==", "!=", ">", "<"):
            if part.startswith(op):
                target = _parse_ver(part[len(op):])
                if op == ">=" and not (ver >= target):
                    return False
                elif op == "<=" and not (ver <= target):
                    return False
                elif op == "==" and not (ver == target):
                    return False
                elif op == "!=" and not (ver != target):
                    return False
                elif op == ">" and not (ver > target):
                    return False
                elif op == "<" and not (ver < target):
                    return False
                break
    return True


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

        # SDK version compatibility check
        if manifest.sdk_min_version:
            try:
                from system.sdk import SDK_VERSION
                def _parse_ver(v: str) -> tuple[int, ...]:
                    return tuple(int(x) for x in v.split(".")[:3])
                if _parse_ver(SDK_VERSION) < _parse_ver(manifest.sdk_min_version):
                    logger.error(
                        f"Plugin {manifest.id} requires SDK >={manifest.sdk_min_version}, "
                        f"current: {SDK_VERSION} — skipping"
                    )
                    return None
            except Exception:
                pass  # If version parsing fails, load anyway
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
    def check_dependency_versions(
        manifest: PluginManifest,
        loaded_plugins: dict[str, Any],
    ) -> list[str]:
        """Verify dependency version constraints are satisfied.

        Returns list of violation messages (empty = all OK).
        """
        violations = []
        for dep_id, constraint in manifest.parsed_dependencies():
            if not constraint:
                continue  # No version constraint
            plugin = loaded_plugins.get(dep_id)
            if plugin is None:
                continue  # Missing dep checked elsewhere
            plugin_version = getattr(plugin, "version", "0.0.0")
            if not _version_satisfies(plugin_version, constraint):
                violations.append(
                    f"{dep_id}: requires {constraint}, found {plugin_version}"
                )
        return violations

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
