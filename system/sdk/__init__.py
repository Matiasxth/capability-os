"""CapabilityOS Plugin SDK — typed contracts and plugin infrastructure."""

__version__ = "2.0.0"
SDK_VERSION = "2.0.0"

from .contracts import *  # noqa: F401,F403
from .plugin_types import BasePlugin, ToolPlugin, ChannelPlugin, MemoryPlugin, AgentPlugin, UIPlugin
from .lifecycle import PluginState
from .context import PluginContext
from .manifest import PluginManifest
from .errors import SDKError, ServiceNotFoundError, ContractViolationError, PermissionDeniedError
