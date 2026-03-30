"""Memory plugin — wraps all memory subsystems into a single plugin."""
from .plugin import MemoryPlugin, create_plugin

__all__ = ["MemoryPlugin", "create_plugin"]
