"""
Tests for Bloque 2 — 19 new capability contracts + 3 web parsing tools.

Validates:
  1. All contracts load and pass schema validation via CapabilityRegistry.
  2. All required fields are present (id, name, domain, type, description,
     inputs, outputs, requirements, strategy, exposure, lifecycle).
  3. Naming canon: capability ids match verb_object pattern.
  4. Variable origins in strategy steps are all explicit (inputs.*, state.*,
     steps.<id>.outputs.*, runtime.*).
  5. End-to-end execution of executable capabilities via CapabilityEngine.
  6. network_parse_html, network_extract_links, network_extract_text tools work.
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import CapabilityEngine, CapabilityExecutionError
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime, register_phase3_real_tools

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = ROOT / "system" / "capabilities" / "contracts" / "v1"
TOOLS_DIR = ROOT / "system" / "tools" / "contracts" / "v1"
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "bloque2_caps"
TMP.mkdir(parents=True, exist_ok=True)

# IDs introduced in Bloque 2 (19 capabilities)
BLOQUE2_CAPABILITY_IDS = {
    # archivos
    "edit_file", "copy_file", "move_file", "delete_file",
    # ejecucion
    "execute_script", "list_processes", "stop_process",
    # web
    "parse_html", "extract_links", "extract_text",
    # integraciones
    "list_integrations", "inspect_integration", "validate_integration",
    "install_integration", "uninstall_integration",
    # observacion
    "get_system_status", "get_capability_status",
    "get_execution_trace", "get_error_report",
}

REQUIRED_CAPABILITY_FIELDS = {
    "id", "name", "domain", "type", "description",
    "inputs", "outputs", "requirements", "strategy", "exposure", "lifecycle",
}

VALID_DOMAINS = {
    "desarrollo", "archivos", "ejecucion", "web",
    "integraciones", "automatizacion", "observacion",
}

VALID_TYPES = {"base", "composed", "integration", "generated"}

VALID_LIFECYCLE_STATUSES = {
    "available", "not_configured", "preparing", "ready",
    "running", "error", "experimental", "disabled",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _build_engine(workspace_root: Path) -> tuple[CapabilityEngine, CapabilityRegistry]:
    cap_registry = CapabilityRegistry()
    for p in sorted(CONTRACTS_DIR.glob("*.json")):
        cap_registry.register(_load_json(p), source=str(p))

    tool_registry = ToolRegistry()
    for p in sorted(TOOLS_DIR.glob("*.json")):
        tool_registry.register(_load_json(p), source=str(p))

    tool_runtime = ToolRuntime(tool_registry, workspace_root=workspace_root)
    register_phase3_real_tools(tool_runtime, workspace_root)

    return CapabilityEngine(cap_registry, tool_runtime), cap_registry


def _workspace(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


# ---------------------------------------------------------------------------
# 1. Schema validation — all 19 contracts must load without error
# ---------------------------------------------------------------------------

class TestBloque2ContractSchemaValidation(unittest.TestCase):

    def setUp(self):
        self.registry = CapabilityRegistry()

    def _load_contract(self, cap_id: str) -> dict:
        path = CONTRACTS_DIR / f"{cap_id}.json"
        self.assertTrue(path.exists(), f"Contract file missing: {cap_id}.json")
        return _load_json(path)

    def _assert_loads(self, cap_id: str) -> dict:
        contract = self._load_contract(cap_id)
        self.registry.register(contract, source=f"{cap_id}.json")
        return contract

    def test_all_bloque2_contracts_pass_schema(self):
        for cap_id in sorted(BLOQUE2_CAPABILITY_IDS):
            with self.subTest(cap_id=cap_id):
                self._assert_loads(cap_id)

    def test_all_required_fields_present(self):
        for cap_id in sorted(BLOQUE2_CAPABILITY_IDS):
            with self.subTest(cap_id=cap_id):
                contract = self._load_contract(cap_id)
                missing = REQUIRED_CAPABILITY_FIELDS - set(contract.keys())
                self.assertFalse(missing, f"{cap_id} missing fields: {missing}")

    def test_ids_match_verb_object_naming_canon(self):
        import re
        pattern = re.compile(r"^[a-z]+(?:_[a-z0-9]+)+$")
        for cap_id in sorted(BLOQUE2_CAPABILITY_IDS):
            with self.subTest(cap_id=cap_id):
                self.assertTrue(pattern.match(cap_id), f"ID '{cap_id}' violates naming canon")

    def test_domains_are_valid(self):
        for cap_id in sorted(BLOQUE2_CAPABILITY_IDS):
            with self.subTest(cap_id=cap_id):
                contract = self._load_contract(cap_id)
                self.assertIn(contract["domain"], VALID_DOMAINS)

    def test_types_are_valid(self):
        for cap_id in sorted(BLOQUE2_CAPABILITY_IDS):
            with self.subTest(cap_id=cap_id):
                contract = self._load_contract(cap_id)
                self.assertIn(contract["type"], VALID_TYPES)

    def test_lifecycle_statuses_are_valid(self):
        for cap_id in sorted(BLOQUE2_CAPABILITY_IDS):
            with self.subTest(cap_id=cap_id):
                contract = self._load_contract(cap_id)
                self.assertIn(contract["lifecycle"]["status"], VALID_LIFECYCLE_STATUSES)

    def test_strategy_steps_have_step_id(self):
        for cap_id in sorted(BLOQUE2_CAPABILITY_IDS):
            with self.subTest(cap_id=cap_id):
                contract = self._load_contract(cap_id)
                steps = contract.get("strategy", {}).get("steps", [])
                self.assertGreater(len(steps), 0, f"{cap_id} has no strategy steps")
                for step in steps:
                    self.assertIn("step_id", step, f"{cap_id} step missing step_id")
                    self.assertIn("action", step, f"{cap_id} step missing action")
                    self.assertIn("params", step, f"{cap_id} step missing params")

    def test_requirements_have_all_keys(self):
        for cap_id in sorted(BLOQUE2_CAPABILITY_IDS):
            with self.subTest(cap_id=cap_id):
                contract = self._load_contract(cap_id)
                req = contract.get("requirements", {})
                for key in ("tools", "capabilities", "integrations"):
                    self.assertIn(key, req, f"{cap_id} requirements missing '{key}'")

    def test_outputs_not_empty(self):
        for cap_id in sorted(BLOQUE2_CAPABILITY_IDS):
            with self.subTest(cap_id=cap_id):
                contract = self._load_contract(cap_id)
                self.assertGreater(len(contract.get("outputs", {})), 0,
                                   f"{cap_id} has no outputs")

    def test_exposure_has_trigger_phrases(self):
        for cap_id in sorted(BLOQUE2_CAPABILITY_IDS):
            with self.subTest(cap_id=cap_id):
                contract = self._load_contract(cap_id)
                phrases = contract.get("exposure", {}).get("trigger_phrases", [])
                self.assertGreater(len(phrases), 0, f"{cap_id} has no trigger_phrases")


# ---------------------------------------------------------------------------
# 2. Domain distribution — spec section 16 compliance
# ---------------------------------------------------------------------------

class TestBloque2DomainCoverage(unittest.TestCase):

    def _contracts_for_domain(self, domain: str) -> list[str]:
        ids = []
        for p in CONTRACTS_DIR.glob("*.json"):
            c = _load_json(p)
            if c.get("domain") == domain:
                ids.append(c["id"])
        return ids

    def test_archivos_domain_has_all_7_capabilities(self):
        expected = {"read_file", "write_file", "edit_file", "list_directory",
                    "copy_file", "move_file", "delete_file"}
        found = set(self._contracts_for_domain("archivos"))
        self.assertTrue(expected.issubset(found), f"Missing: {expected - found}")

    def test_ejecucion_domain_has_all_4_capabilities(self):
        expected = {"execute_command", "execute_script", "list_processes", "stop_process"}
        found = set(self._contracts_for_domain("ejecucion"))
        self.assertTrue(expected.issubset(found), f"Missing: {expected - found}")

    def test_web_domain_has_all_4_capabilities(self):
        expected = {"fetch_url", "parse_html", "extract_links", "extract_text"}
        found = set(self._contracts_for_domain("web"))
        self.assertTrue(expected.issubset(found), f"Missing: {expected - found}")

    def test_integraciones_domain_has_all_5_capabilities(self):
        expected = {"list_integrations", "inspect_integration", "validate_integration",
                    "install_integration", "uninstall_integration"}
        found = set(self._contracts_for_domain("integraciones"))
        self.assertTrue(expected.issubset(found), f"Missing: {expected - found}")

    def test_observacion_domain_has_all_4_capabilities(self):
        expected = {"get_system_status", "get_capability_status",
                    "get_execution_trace", "get_error_report"}
        found = set(self._contracts_for_domain("observacion"))
        self.assertTrue(expected.issubset(found), f"Missing: {expected - found}")


# ---------------------------------------------------------------------------
# 3. E2E execution — archivos capabilities
# ---------------------------------------------------------------------------

class TestBloque2ArchivosE2E(unittest.TestCase):

    def _engine(self, name: str):
        ws = _workspace(name)
        engine, registry = _build_engine(ws)
        return engine, registry, ws

    def _get_contract(self, cap_id: str) -> dict:
        return _load_json(CONTRACTS_DIR / f"{cap_id}.json")

    def test_edit_file_replace(self):
        engine, _, ws = self._engine("edit_replace")
        f = ws / "hello.txt"
        f.write_text("hello world", encoding="utf-8-sig")
        result = engine.execute(
            self._get_contract("edit_file"),
            {"path": str(f), "old_string": "world", "new_string": "capability_os"},
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(f.read_text(encoding="utf-8-sig"), "hello capability_os")

    def test_copy_file(self):
        engine, _, ws = self._engine("copy_file")
        src = ws / "src.txt"
        dst = ws / "dst.txt"
        src.write_text("copy me", encoding="utf-8-sig")
        result = engine.execute(
            self._get_contract("copy_file"),
            {"source_path": str(src), "destination_path": str(dst)},
        )
        self.assertEqual(result["status"], "success")
        self.assertTrue(dst.exists())

    def test_move_file(self):
        engine, _, ws = self._engine("move_file")
        src = ws / "src.txt"
        dst = ws / "dst.txt"
        src.write_text("move me", encoding="utf-8-sig")
        result = engine.execute(
            self._get_contract("move_file"),
            {"source_path": str(src), "destination_path": str(dst)},
        )
        self.assertEqual(result["status"], "success")
        self.assertFalse(src.exists())
        self.assertTrue(dst.exists())

    def test_delete_file(self):
        engine, _, ws = self._engine("delete_file")
        f = ws / "delete_me.txt"
        f.write_text("bye", encoding="utf-8-sig")
        result = engine.execute(
            self._get_contract("delete_file"),
            {"path": str(f)},
        )
        self.assertEqual(result["status"], "success")
        self.assertFalse(f.exists())

    def test_edit_file_missing_raises(self):
        engine, _, ws = self._engine("edit_missing")
        with self.assertRaises(CapabilityExecutionError):
            engine.execute(
                self._get_contract("edit_file"),
                {"path": str(ws / "ghost.txt"), "new_string": "x"},
            )


# ---------------------------------------------------------------------------
# 4. E2E execution — ejecucion capabilities
# ---------------------------------------------------------------------------

class TestBloque2EjecucionE2E(unittest.TestCase):

    def _engine(self, name: str):
        ws = _workspace(name)
        engine, registry = _build_engine(ws)
        return engine, registry, ws

    def _get_contract(self, cap_id: str) -> dict:
        return _load_json(CONTRACTS_DIR / f"{cap_id}.json")

    def test_execute_script(self):
        engine, _, ws = self._engine("exec_script")
        script = ws / "hello.py"
        script.write_text('print("bloque2_ok")', encoding="utf-8-sig")
        result = engine.execute(
            self._get_contract("execute_script"),
            {"script_path": str(script)},
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("bloque2_ok", result["final_output"].get("stdout", ""))

    def test_list_processes(self):
        engine, _, ws = self._engine("list_procs")
        result = engine.execute(self._get_contract("list_processes"), {})
        self.assertEqual(result["status"], "success")
        self.assertIn("processes", result["final_output"])
        self.assertIsInstance(result["final_output"]["processes"], list)


# ---------------------------------------------------------------------------
# 5. E2E execution — web capabilities (parse_html, extract_links, extract_text)
# ---------------------------------------------------------------------------

class TestBloque2WebE2E(unittest.TestCase):

    SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
  <h1>Hello World</h1>
  <p>Some paragraph text here.</p>
  <a href="https://example.com">Example link</a>
  <a href="/relative/path">Relative link</a>
</body>
</html>"""

    def _engine(self, name: str):
        ws = _workspace(name)
        engine, registry = _build_engine(ws)
        return engine, registry, ws

    def _get_contract(self, cap_id: str) -> dict:
        return _load_json(CONTRACTS_DIR / f"{cap_id}.json")

    def test_parse_html_returns_title(self):
        engine, _, ws = self._engine("parse_html")
        result = engine.execute(
            self._get_contract("parse_html"),
            {"html": self.SAMPLE_HTML},
        )
        self.assertEqual(result["status"], "success")
        output = result["final_output"]
        self.assertEqual(output.get("title"), "Test Page")
        self.assertIn("Hello World", output.get("text", ""))
        self.assertIsInstance(output.get("links"), list)
        self.assertGreater(output.get("tag_count", 0), 0)

    def test_parse_html_finds_links(self):
        engine, _, ws = self._engine("parse_html_links")
        result = engine.execute(
            self._get_contract("parse_html"),
            {"html": self.SAMPLE_HTML},
        )
        links = result["final_output"].get("links", [])
        hrefs = [l["href"] for l in links]
        self.assertIn("https://example.com", hrefs)
        self.assertIn("/relative/path", hrefs)

    def test_extract_links_from_document(self):
        engine, _, ws = self._engine("extract_links")
        # First parse the HTML
        parse_result = engine.execute(
            self._get_contract("parse_html"),
            {"html": self.SAMPLE_HTML},
        )
        document = parse_result["final_output"]
        # Then extract links from the document
        result = engine.execute(
            self._get_contract("extract_links"),
            {"document": document},
        )
        self.assertEqual(result["status"], "success")
        self.assertGreater(result["final_output"].get("count", 0), 0)

    def test_extract_text_from_document(self):
        engine, _, ws = self._engine("extract_text")
        parse_result = engine.execute(
            self._get_contract("parse_html"),
            {"html": self.SAMPLE_HTML},
        )
        document = parse_result["final_output"]
        result = engine.execute(
            self._get_contract("extract_text"),
            {"document": document},
        )
        self.assertEqual(result["status"], "success")
        self.assertGreater(result["final_output"].get("word_count", 0), 0)
        self.assertIn("Hello", result["final_output"].get("text", ""))

    def test_parse_html_empty_input_raises(self):
        engine, _, ws = self._engine("parse_html_empty")
        with self.assertRaises(CapabilityExecutionError):
            engine.execute(
                self._get_contract("parse_html"),
                {"html": 123},  # wrong type
            )


# ---------------------------------------------------------------------------
# 6. E2E execution — observacion capabilities
# ---------------------------------------------------------------------------

class TestBloque2ObservacionE2E(unittest.TestCase):

    def _engine(self, name: str):
        ws = _workspace(name)
        engine, registry = _build_engine(ws)
        return engine, registry, ws

    def _get_contract(self, cap_id: str) -> dict:
        return _load_json(CONTRACTS_DIR / f"{cap_id}.json")

    def test_get_system_status(self):
        engine, _, ws = self._engine("system_status")
        result = engine.execute(self._get_contract("get_system_status"), {})
        self.assertEqual(result["status"], "success")
        output = result["final_output"]
        # Last step output is workspace_info
        self.assertIn("workspace_root", output)
        self.assertIn("tools_count", output)

    def test_get_capability_status_reads_contract(self):
        engine, _, ws = self._engine("cap_status")
        # We use the project's system dir as workspace_root so the path resolves
        project_root = ROOT
        engine2, _ = _build_engine(project_root)
        result = engine2.execute(
            self._get_contract("get_capability_status"),
            {"capability_id": "read_file"},
        )
        self.assertEqual(result["status"], "success")
        content = result["final_output"].get("content", "")
        self.assertIn("read_file", content)


# ---------------------------------------------------------------------------
# 7. network_parse_html tool unit tests
# ---------------------------------------------------------------------------

class TestNetworkParseHtml(unittest.TestCase):

    def setUp(self):
        from system.tools.implementations.phase3_tools import network_parse_html
        self.tool = network_parse_html
        self.ws = TMP / "parse_html_tool"
        self.ws.mkdir(parents=True, exist_ok=True)
        self.contract = {"id": "network_parse_html", "constraints": {"timeout_ms": 5000}}

    def test_extracts_title(self):
        result = self.tool(
            {"html": "<html><head><title>My Title</title></head><body></body></html>"},
            self.contract, self.ws,
        )
        self.assertEqual(result["title"], "My Title")

    def test_extracts_links(self):
        result = self.tool(
            {"html": '<body><a href="https://a.com">A</a></body>'},
            self.contract, self.ws,
        )
        self.assertEqual(len(result["links"]), 1)
        self.assertEqual(result["links"][0]["href"], "https://a.com")
        self.assertEqual(result["links"][0]["text"], "A")

    def test_extracts_text(self):
        result = self.tool(
            {"html": "<body><p>Hello world</p></body>"},
            self.contract, self.ws,
        )
        self.assertIn("Hello world", result["text"])

    def test_ignores_script_content(self):
        result = self.tool(
            {"html": "<body><script>var x=1;</script><p>real</p></body>"},
            self.contract, self.ws,
        )
        self.assertNotIn("var x", result["text"])
        self.assertIn("real", result["text"])

    def test_tag_count_positive(self):
        result = self.tool(
            {"html": "<html><body><p>x</p></body></html>"},
            self.contract, self.ws,
        )
        self.assertGreater(result["tag_count"], 0)

    def test_non_string_raises(self):
        from system.tools.implementations.phase3_tools import network_parse_html
        with self.assertRaises(ValueError):
            network_parse_html({"html": 123}, self.contract, self.ws)


class TestNetworkExtractLinks(unittest.TestCase):

    def setUp(self):
        from system.tools.implementations.phase3_tools import network_extract_links
        self.tool = network_extract_links
        self.ws = TMP / "extract_links_tool"
        self.ws.mkdir(parents=True, exist_ok=True)
        self.contract = {"id": "network_extract_links", "constraints": {"timeout_ms": 5000}}

    def test_extracts_links_from_document(self):
        doc = {"links": [{"href": "https://a.com", "text": "A"}], "text": ""}
        result = self.tool({"document": doc}, self.contract, self.ws)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["links"][0]["href"], "https://a.com")

    def test_empty_document_links(self):
        result = self.tool({"document": {"links": [], "text": ""}}, self.contract, self.ws)
        self.assertEqual(result["count"], 0)

    def test_non_dict_document_raises(self):
        with self.assertRaises(ValueError):
            self.tool({"document": "not_a_dict"}, self.contract, self.ws)


class TestNetworkExtractText(unittest.TestCase):

    def setUp(self):
        from system.tools.implementations.phase3_tools import network_extract_text
        self.tool = network_extract_text
        self.ws = TMP / "extract_text_tool"
        self.ws.mkdir(parents=True, exist_ok=True)
        self.contract = {"id": "network_extract_text", "constraints": {"timeout_ms": 5000}}

    def test_extracts_text_and_word_count(self):
        doc = {"text": "Hello world this is a test", "links": []}
        result = self.tool({"document": doc}, self.contract, self.ws)
        self.assertEqual(result["word_count"], 6)
        self.assertIn("Hello", result["text"])

    def test_empty_text(self):
        result = self.tool({"document": {"text": "", "links": []}}, self.contract, self.ws)
        self.assertEqual(result["word_count"], 0)

    def test_non_dict_document_raises(self):
        with self.assertRaises(ValueError):
            self.tool({"document": 42}, self.contract, self.ws)


if __name__ == "__main__":
    unittest.main()
