"""Hot-reload — restart a plugin without restarting the entire system.

Usage:
    container.reload_plugin("capos.channels.telegram")
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from typing import Any

logger = logging.getLogger("capos.hot_reload")


def reload_plugin(container: Any, plugin_id: str) -> str | None:
    """Stop, reimport, and restart a plugin. Returns error string or None."""
    from system.sdk.lifecycle import PluginState

    plugin = container.get_plugin(plugin_id)
    if plugin is None:
        return f"Plugin '{plugin_id}' not found"

    # 1. Stop
    try:
        if container._states.get(plugin_id) == PluginState.RUNNING:
            container._stop_one(plugin_id)
        logger.info(f"Stopped plugin {plugin_id}")
    except Exception as exc:
        logger.warning(f"Stop failed for {plugin_id}: {exc}")

    # 2. Find and reload the module
    module_name = type(plugin).__module__
    module = sys.modules.get(module_name)
    if module is None:
        return f"Module '{module_name}' not in sys.modules"

    try:
        importlib.reload(module)
        logger.info(f"Reloaded module {module_name}")
    except Exception as exc:
        return f"Reload failed: {exc}"

    # 3. Create new plugin instance
    factory = getattr(module, "create_plugin", None)
    if factory is None:
        return f"Module '{module_name}' has no create_plugin()"

    try:
        new_plugin = factory()
    except Exception as exc:
        return f"Factory failed: {exc}"

    # 4. Replace in container
    container._plugins[plugin_id] = new_plugin
    container._states[plugin_id] = PluginState.REGISTERED

    # 5. Re-initialize and start
    err = container._initialize_one(plugin_id)
    if err:
        return err

    err = container._start_one(plugin_id)
    if err:
        return err

    logger.info(f"Hot-reloaded plugin {plugin_id}")
    return None


def install_plugin_from_path(container: Any, plugin_path: str) -> tuple[str | None, str | None]:
    """Load a plugin from a directory path and register it.

    Returns (plugin_id, error).
    """
    from pathlib import Path
    from system.container.plugin_loader import PluginLoader

    path = Path(plugin_path).resolve()
    if not path.exists():
        return None, f"Path not found: {path}"

    results = PluginLoader.load_from_directory(path.parent)
    for plugin, manifest in results:
        if Path(plugin_path).name in manifest.id or path.name in manifest.id:
            container.register_plugin(plugin, manifest)
            err = container._initialize_one(plugin.plugin_id)
            if err:
                return plugin.plugin_id, err
            err = container._start_one(plugin.plugin_id)
            if err:
                return plugin.plugin_id, err
            return plugin.plugin_id, None

    # Try loading directly
    try:
        spec = importlib.util.spec_from_file_location(
            f"capos_plugin_{path.name}",
            str(path / "plugin.py") if path.is_dir() else str(path),
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            factory = getattr(module, "create_plugin", None)
            if factory:
                plugin = factory()
                container.register_plugin(plugin)
                err = container._initialize_one(plugin.plugin_id)
                if err:
                    return plugin.plugin_id, err
                err = container._start_one(plugin.plugin_id)
                if err:
                    return plugin.plugin_id, err
                return plugin.plugin_id, None
    except Exception as exc:
        return None, f"Load failed: {exc}"

    return None, "No plugin found at path"
