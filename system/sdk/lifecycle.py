"""Plugin lifecycle states."""
from __future__ import annotations
from enum import Enum


class PluginState(Enum):
    REGISTERED = "registered"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
