"""Tests for Plugin SDK — contract validation and plugin compliance."""
import unittest
from system.sdk.validation import validate_plugin, validate_contract


class TestPluginValidation(unittest.TestCase):
    """Every built-in plugin must pass BasePlugin validation."""

    PLUGIN_FACTORIES = [
        ("core_services", "system.plugins.core_services.plugin"),
        ("memory", "system.plugins.memory.plugin"),
        ("agent", "system.plugins.agent.plugin"),
        ("capabilities", "system.plugins.capabilities.plugin"),
        ("workspace", "system.plugins.workspace.plugin"),
        ("supervisor", "system.plugins.supervisor.plugin"),
        ("scheduler", "system.plugins.scheduler.plugin"),
        ("skills", "system.plugins.skills.plugin"),
        ("voice", "system.plugins.voice.plugin"),
        ("browser", "system.plugins.browser.plugin"),
        ("mcp", "system.plugins.mcp.plugin"),
        ("a2a", "system.plugins.a2a.plugin"),
        ("growth", "system.plugins.growth.plugin"),
        ("sequences", "system.plugins.sequences.plugin"),
        ("telegram", "system.plugins.channels.telegram.plugin"),
        ("slack", "system.plugins.channels.slack.plugin"),
        ("discord", "system.plugins.channels.discord.plugin"),
        ("whatsapp", "system.plugins.channels.whatsapp.plugin"),
    ]

    def test_all_plugins_have_required_attributes(self):
        """Every plugin must have plugin_id, plugin_name, version, dependencies."""
        for name, module_path in self.PLUGIN_FACTORIES:
            with self.subTest(plugin=name):
                module = __import__(module_path, fromlist=["create_plugin"])
                plugin = module.create_plugin()
                violations = validate_plugin(plugin)
                self.assertEqual(violations, [], f"Plugin '{name}' violations: {violations}")

    def test_all_plugins_have_unique_ids(self):
        """No two plugins share the same plugin_id."""
        ids = []
        for name, module_path in self.PLUGIN_FACTORIES:
            module = __import__(module_path, fromlist=["create_plugin"])
            plugin = module.create_plugin()
            ids.append(plugin.plugin_id)
        self.assertEqual(len(ids), len(set(ids)), f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}")

    def test_all_plugins_have_dependencies_as_list(self):
        """Dependencies must be a list of strings."""
        for name, module_path in self.PLUGIN_FACTORIES:
            with self.subTest(plugin=name):
                module = __import__(module_path, fromlist=["create_plugin"])
                plugin = module.create_plugin()
                deps = plugin.dependencies
                self.assertIsInstance(deps, list)
                for d in deps:
                    self.assertIsInstance(d, str)


class TestContractValidation(unittest.TestCase):
    """Contract validator catches bad implementations."""

    def test_valid_implementation_passes(self):
        from system.sdk.contracts import MemoryManagerContract
        from system.core.memory.memory_manager import MemoryManager
        import tempfile, os
        path = os.path.join(tempfile.mkdtemp(), "test_mem.json")
        mm = MemoryManager(path)
        violations = validate_contract(MemoryManagerContract, mm)
        self.assertEqual(violations, [])

    def test_string_fails_as_contract(self):
        from system.sdk.contracts import ToolRuntimeContract
        violations = validate_contract(ToolRuntimeContract, "not a runtime")
        self.assertTrue(len(violations) > 0)


class TestServiceContainerValidation(unittest.TestCase):
    """ServiceContainer warns on contract violations."""

    def test_register_service_warns_on_bad_type(self):
        from system.container.service_container import ServiceContainer
        from system.sdk.contracts import ToolRuntimeContract
        from pathlib import Path
        import logging

        container = ServiceContainer(
            workspace_root=Path("."),
            project_root=Path("."),
            settings={},
            event_bus=None,
        )
        # Should not raise, but should log warning
        with self.assertLogs("capos.container", level="WARNING"):
            container.register_service(ToolRuntimeContract, "bad_value")


if __name__ == "__main__":
    unittest.main()
