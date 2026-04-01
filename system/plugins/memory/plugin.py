"""Memory plugin — provides ExecutionHistory, MemoryManager, SemanticMemory,
MarkdownMemory, and supporting infrastructure (EmbeddingsEngine, VectorStore,
UserContext, MemoryCompactor).

Publishes four contracts:
  - ExecutionHistoryContract
  - MemoryManagerContract
  - SemanticMemoryContract
  - MarkdownMemoryContract

Dependencies: capos.core.settings (reads workspace_root and agent settings).
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import (
    ExecutionHistoryContract,
    MarkdownMemoryContract,
    MemoryManagerContract,
    MetricsCollectorContract,
    SemanticMemoryContract,
    SettingsProvider,
)
from system.core.memory import (
    EmbeddingsEngine,
    ExecutionHistory,
    MarkdownMemory,
    MemoryCompactor,
    MemoryManager,
    SemanticMemory,
    UserContext,
    VectorStore,
)

log = logging.getLogger(__name__)


class MemoryPlugin:
    """Core memory plugin — owns every memory subsystem."""

    # ------------------------------------------------------------------
    # Plugin metadata
    # ------------------------------------------------------------------

    plugin_id: str = "capos.core.memory"
    plugin_name: str = "Memory"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings"]

    def __init__(self) -> None:
        # Subsystems — populated in initialize()
        self.execution_history: ExecutionHistory | None = None
        self.memory_manager: MemoryManager | None = None
        self.embeddings_engine: EmbeddingsEngine | None = None
        self.vector_store: VectorStore | None = None
        self.semantic_memory: SemanticMemory | None = None
        self.markdown_memory: MarkdownMemory | None = None
        self.compactor: MemoryCompactor | None = None
        self.user_context: UserContext | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        """Create all memory instances and publish contracts."""
        workspace = ctx.workspace_root
        memory_dir = workspace / "memory"

        # 1. ExecutionHistory (DB-backed when available)
        from system.sdk.contracts import DatabaseContract
        db = ctx.get_optional(DatabaseContract)
        self.execution_history = ExecutionHistory(
            data_path=memory_dir / "history.json",
            db=db,
        )

        # 2. MemoryManager
        self.memory_manager = MemoryManager(
            data_path=memory_dir / "memories.json",
        )

        # 3. UserContext (metrics are optional)
        metrics = ctx.get_optional(MetricsCollectorContract)
        self.user_context = UserContext(
            memory=self.memory_manager,
            metrics=metrics,
        )

        # 4. EmbeddingsEngine
        self.embeddings_engine = EmbeddingsEngine(
            vocab_path=memory_dir / "tfidf_vocab.json",
        )

        # 5. VectorStore — prefer sqlite-vec, fallback to JSON-based
        try:
            from system.core.memory.sqlite_vector_store import SqliteVectorStore
            sqlite_vs = SqliteVectorStore(data_path=memory_dir / "vectors.db")
            if sqlite_vs.available:
                self.vector_store = sqlite_vs
                log.info("VectorStore: sqlite-vec (accelerated)")
            else:
                self.vector_store = VectorStore(data_path=memory_dir / "vectors.json")
                log.info("VectorStore: JSON fallback")
        except Exception:
            self.vector_store = VectorStore(data_path=memory_dir / "vectors.json")
            log.info("VectorStore: JSON fallback")

        # 6. SemanticMemory
        self.semantic_memory = SemanticMemory(
            memory_manager=self.memory_manager,
            vector_store=self.vector_store,
            embeddings_engine=self.embeddings_engine,
        )

        # 7. MarkdownMemory
        self.markdown_memory = MarkdownMemory(
            memory_dir=memory_dir,
        )

        # 8. MemoryCompactor
        agent_settings = ctx.settings.get("agent", {})
        max_context_tokens = int(
            agent_settings.get("max_context_tokens", 4000)
            if isinstance(agent_settings, dict)
            else 4000
        )
        self.compactor = MemoryCompactor(
            markdown_memory=self.markdown_memory,
            max_context_tokens=max_context_tokens,
        )

        # 9. Initialize MEMORY.md with user prefs from memory_manager
        self._init_memory_md()

        # 10. Publish contracts
        ctx.publish_service(ExecutionHistoryContract, self.execution_history)
        ctx.publish_service(MemoryManagerContract, self.memory_manager)
        ctx.publish_service(SemanticMemoryContract, self.semantic_memory)
        ctx.publish_service(MarkdownMemoryContract, self.markdown_memory)

        log.info(
            "MemoryPlugin initialized — %d memories, %d history entries, %d vectors",
            self.memory_manager.count(),
            self.execution_history.count(),
            self.vector_store.count(),
        )

    def register_routes(self, router) -> None:
        from system.core.ui_bridge.handlers import memory_handlers
        router.add("GET", "/metrics", memory_handlers.get_metrics)
        router.add("GET", "/memory/context", memory_handlers.get_context)
        router.add("GET", "/memory/history", memory_handlers.get_history)
        router.add("POST", "/memory/history/chat", memory_handlers.save_chat)
        router.add("DELETE", "/memory/history/{exec_id}", memory_handlers.delete_history)
        router.add("POST", "/memory/sessions", memory_handlers.save_session)
        router.add("GET", "/memory/sessions/{exec_id}", memory_handlers.get_session)
        router.add("GET", "/memory/preferences", memory_handlers.get_preferences)
        router.add("POST", "/memory/preferences", memory_handlers.set_preferences)
        router.add("GET", "/memory/semantic/search", memory_handlers.search_semantic)
        router.add("POST", "/memory/semantic", memory_handlers.add_semantic)
        router.add("DELETE", "/memory/semantic/{mem_id}", memory_handlers.delete_semantic)
        router.add("DELETE", "/memory", memory_handlers.clear_all)
        router.add("POST", "/memory/compact", memory_handlers.compact_sessions)
        router.add("GET", "/memory/markdown", memory_handlers.get_markdown_memory)
        router.add("POST", "/memory/markdown", memory_handlers.save_markdown_memory)
        router.add("POST", "/memory/markdown/fact", memory_handlers.add_memory_fact)
        router.add("DELETE", "/memory/markdown/fact", memory_handlers.remove_memory_fact)
        router.add("GET", "/memory/daily", memory_handlers.get_daily_notes)
        router.add("GET", "/memory/summaries", memory_handlers.get_session_summaries)
        router.add("GET", "/memory/agent-context", memory_handlers.get_memory_agent_context)

    def start(self) -> None:
        """Nothing to start — all memory subsystems are passive."""

    def stop(self) -> None:
        """Nothing to stop — all memory subsystems flush on write."""

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _init_memory_md(self) -> None:
        """Seed MEMORY.md with user preferences if it doesn't exist yet."""
        if self.markdown_memory is None or self.memory_manager is None:
            return
        try:
            prefs = self.memory_manager.recall("user:custom_preferences")
            user_name = ""
            language = "auto"
            if isinstance(prefs, dict):
                user_name = str(prefs.get("name", ""))
                language = str(prefs.get("language", "auto"))
            self.markdown_memory.init_memory_md(
                user_name=user_name,
                language=language,
            )
        except Exception:
            pass  # Rule 5: never block execution


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> MemoryPlugin:
    """Entry-point factory used by the plugin loader."""
    return MemoryPlugin()
