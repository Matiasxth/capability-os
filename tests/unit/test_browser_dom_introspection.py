from __future__ import annotations

import unittest
from typing import Any

from system.browser_worker.dom_introspection import DOMIntrospectionEngine


class _FakePage:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = list(rows)
        self.last_script: str | None = None
        self.last_payload: dict[str, Any] | None = None

    def evaluate(self, script: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self.last_script = script
        self.last_payload = payload
        return list(self._rows)


def _row(
    *,
    tag: str,
    selector: str,
    text: str = "",
    aria_label: str = "",
    placeholder: str = "",
    visible: bool = True,
    enabled: bool = True,
    in_viewport: bool = True,
    box: dict[str, Any] | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tag": tag,
        "text": text,
        "aria_label": aria_label,
        "placeholder": placeholder,
        "selector": selector,
        "xpath": f"/html/body/{tag}[1]",
        "visible": visible,
        "enabled": enabled,
        "in_viewport": in_viewport,
        "bounding_box": box or {"x": 12, "y": 20, "width": 100, "height": 32},
        "attributes": attributes or {"id": "", "class": "", "role": "", "type": ""},
    }


class DOMIntrospectionEngineTests(unittest.TestCase):
    def test_extract_interactive_elements_normalizes_rows(self) -> None:
        page = _FakePage(
            [
                _row(
                    tag="button",
                    selector="#send",
                    text="Send",
                    attributes={"id": "send", "class": "btn", "role": "button", "type": "button"},
                ),
                _row(
                    tag="a",
                    selector="a:nth-of-type(1)",
                    text="Open docs",
                    attributes={"id": "", "class": "link", "role": "", "type": ""},
                ),
            ]
        )
        engine = DOMIntrospectionEngine()

        elements = engine.extract_interactive_elements(page, visible_only=False, limit=5)

        self.assertEqual(len(elements), 2)
        self.assertIsNotNone(page.last_script)
        assert page.last_script is not None
        self.assertIn('"button"', page.last_script)
        self.assertIn('"a[href]"', page.last_script)
        self.assertEqual(page.last_payload, {"limit": 5})
        self.assertEqual(elements[0]["tag"], "button")
        self.assertEqual(elements[1]["tag"], "a")
        self.assertEqual(elements[0]["selector"], "#send")
        self.assertIsInstance(elements[0]["bounding_box"]["width"], float)
        self.assertGreater(elements[0]["bounding_box"]["width"], 0.0)

    def test_extract_applies_visible_viewport_and_text_filters(self) -> None:
        page = _FakePage(
            [
                _row(tag="button", selector="#visible", text="Primary Send", visible=True, in_viewport=True),
                _row(tag="a", selector="#hidden", text="Hidden Link", visible=False, in_viewport=True),
                _row(tag="button", selector="#off", text="Secondary", visible=True, in_viewport=False),
            ]
        )
        engine = DOMIntrospectionEngine()

        elements = engine.extract_interactive_elements(
            page,
            visible_only=True,
            in_viewport_only=True,
            text_contains="send",
        )

        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0]["selector"], "#visible")

    def test_extract_ignores_invalid_rows(self) -> None:
        page = _FakePage(
            [
                {"tag": "button"},  # missing selector
                _row(tag="button", selector="#ok"),
                "bad-row",  # invalid shape
            ]
        )
        engine = DOMIntrospectionEngine()

        elements = engine.extract_interactive_elements(page, visible_only=False)

        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0]["selector"], "#ok")


if __name__ == "__main__":
    unittest.main()
