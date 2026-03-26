from __future__ import annotations

import unittest
from typing import Any

from system.browser_worker.element_registry import ElementRegistry


def _mapped(
    dom_key: str,
    *,
    selector: str,
    text: str = "",
    tag: str = "button",
) -> dict[str, Any]:
    return {
        "_dom_key": dom_key,
        "type": "button",
        "text": text,
        "aria_label": "",
        "placeholder": "",
        "selector": selector,
        "xpath": f"/html/body/{tag}[1]",
        "visible": True,
        "enabled": True,
        "bounding_box": {"x": 10.0, "y": 20.0, "width": 120.0, "height": 32.0},
        "in_viewport": True,
        "tag": tag,
        "attributes": {"id": "", "class": "", "role": "button", "type": "button"},
    }


class ElementRegistryTests(unittest.TestCase):
    def test_assigns_incremental_ids_and_keeps_them_stable_for_same_dom(self) -> None:
        registry = ElementRegistry()
        first = registry.reconcile(
            session_id="session_a",
            page_url="https://example.com/",
            mapped_elements=[
                _mapped("dom_a", selector="#a", text="A"),
                _mapped("dom_b", selector="#b", text="B"),
            ],
        )
        second = registry.reconcile(
            session_id="session_a",
            page_url="https://example.com/",
            mapped_elements=[
                _mapped("dom_a", selector="#a", text="A"),
                _mapped("dom_b", selector="#b", text="B"),
            ],
        )

        self.assertEqual([item["element_id"] for item in first], ["el_001", "el_002"])
        self.assertEqual([item["element_id"] for item in second], ["el_001", "el_002"])

    def test_assigns_new_id_only_for_new_dom_key(self) -> None:
        registry = ElementRegistry()
        registry.reconcile(
            session_id="session_a",
            page_url="https://example.com/",
            mapped_elements=[_mapped("dom_a", selector="#a", text="A")],
        )
        second = registry.reconcile(
            session_id="session_a",
            page_url="https://example.com/",
            mapped_elements=[
                _mapped("dom_a", selector="#a", text="A"),
                _mapped("dom_c", selector="#c", text="C"),
            ],
        )

        self.assertEqual([item["element_id"] for item in second], ["el_001", "el_002"])

    def test_resets_counter_when_page_url_changes(self) -> None:
        registry = ElementRegistry()
        registry.reconcile(
            session_id="session_a",
            page_url="https://example.com/one",
            mapped_elements=[_mapped("dom_a", selector="#a")],
        )
        changed = registry.reconcile(
            session_id="session_a",
            page_url="https://example.com/two",
            mapped_elements=[_mapped("dom_new", selector="#new")],
        )

        self.assertEqual(changed[0]["element_id"], "el_001")

    def test_remove_and_invalidate_clear_lookup(self) -> None:
        registry = ElementRegistry()
        listed = registry.reconcile(
            session_id="session_a",
            page_url="https://example.com/",
            mapped_elements=[_mapped("dom_a", selector="#a")],
        )
        element_id = listed[0]["element_id"]

        self.assertIsNotNone(registry.get(session_id="session_a", element_id=element_id))
        registry.remove(session_id="session_a", element_id=element_id)
        self.assertIsNone(registry.get(session_id="session_a", element_id=element_id))

        registry.reconcile(
            session_id="session_a",
            page_url="https://example.com/",
            mapped_elements=[_mapped("dom_a", selector="#a")],
        )
        registry.invalidate(session_id="session_a")
        self.assertIsNone(registry.get(session_id="session_a", element_id="el_001"))


if __name__ == "__main__":
    unittest.main()
