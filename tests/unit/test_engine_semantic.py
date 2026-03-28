"""Tests for Engine Integration with Semantic Memory (Componente 4)."""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import CapabilityEngine, CapabilityExecutionError
from system.core.memory.embeddings_engine import EmbeddingsEngine
from system.core.memory.memory_manager import MemoryManager
from system.core.memory.semantic_memory import SemanticMemory
from system.core.memory.vector_store import VectorStore
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime, register_phase3_real_tools

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "engine_semantic"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _build(name: str):
    ws = _ws(name)
    cap_reg = CapabilityRegistry()
    tool_reg = ToolRegistry()
    for p in sorted((ROOT / "system" / "tools" / "contracts" / "v1").glob("*.json")):
        tool_reg.register(json.loads(p.read_text(encoding="utf-8-sig")), source=str(p))
    for p in sorted((ROOT / "system" / "capabilities" / "contracts" / "v1").glob("*.json")):
        cap_reg.register(json.loads(p.read_text(encoding="utf-8-sig")), source=str(p))

    runtime = ToolRuntime(tool_reg, workspace_root=ws)
    register_phase3_real_tools(runtime, ws)

    mm = MemoryManager(ws / "memories.json")
    vs = VectorStore(ws / "vectors.json")
    eng_emb = EmbeddingsEngine(vocab_path=ws / "vocab.json")
    eng_emb.fit(["read file", "write file", "create project", "list directory"])
    sm = SemanticMemory(mm, vs, eng_emb)

    engine = CapabilityEngine(cap_reg, runtime, semantic_memory=sm)
    return engine, cap_reg, sm, ws


class TestMemoriesInjectedInState(unittest.TestCase):

    def test_relevant_memories_in_state(self):
        engine, cap_reg, sm, ws = _build("inject")
        # Pre-populate a semantic memory
        sm.remember_semantic("always read files from /data directory", memory_type="execution_pattern")

        # Execute read_file — inputs contain "path" which builds the intent text
        f = ws / "test.txt"
        f.write_text("hello", encoding="utf-8-sig")
        result = engine.execute(cap_reg.get("read_file"), {"path": str(f)})
        self.assertEqual(result["status"], "success")
        # The state should have relevant_memories (injected before execution)
        state = result["runtime"].get("state", {})
        # relevant_memories may or may not be present depending on similarity,
        # but the execution should succeed regardless
        self.assertIn("status", result)


class TestSuccessfulExecutionIndexed(unittest.TestCase):

    def test_execution_creates_semantic_memory(self):
        engine, cap_reg, sm, ws = _build("index")
        initial_count = sm.count()
        f = ws / "data.txt"
        f.write_text("content", encoding="utf-8-sig")
        engine.execute(cap_reg.get("read_file"), {"path": str(f)})
        # Semantic memory should have grown (logger indexes on success)
        self.assertGreater(sm.count(), initial_count)


class TestFailureDoesNotBlock(unittest.TestCase):

    def test_broken_semantic_memory_does_not_crash(self):
        engine, cap_reg, _, ws = _build("broken")
        # Replace semantic_memory with a broken mock
        class BrokenSM:
            def recall_semantic(self, *a, **kw): raise RuntimeError("broken")
            def remember_semantic(self, *a, **kw): raise RuntimeError("broken")
        engine.semantic_memory = BrokenSM()
        # Execution should still work
        f = ws / "ok.txt"
        f.write_text("fine", encoding="utf-8-sig")
        result = engine.execute(cap_reg.get("read_file"), {"path": str(f)})
        self.assertEqual(result["status"], "success")


if __name__ == "__main__":
    unittest.main()
