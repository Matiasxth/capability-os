from __future__ import annotations

import hashlib
import json
from typing import Any


class ElementMapper:
    """Maps raw DOM candidates to Capability OS interactive element model."""

    def map_elements(self, raw_elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        mapped: list[dict[str, Any]] = []
        for raw in raw_elements:
            element = self._map_single(raw)
            if element is None:
                continue
            mapped.append(element)
        return mapped

    def _map_single(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        selector = _as_str(raw.get("selector"))
        if not selector:
            return None

        tag = _as_str(raw.get("tag")).lower()
        attributes = _normalize_attributes(raw.get("attributes"))
        element_type = _resolve_element_type(tag, attributes)

        text = _as_str(raw.get("text"))
        aria_label = _as_str(raw.get("aria_label"))
        placeholder = _as_str(raw.get("placeholder"))
        xpath = _as_str(raw.get("xpath"))
        visible = bool(raw.get("visible", False))
        enabled = bool(raw.get("enabled", False))
        in_viewport = bool(raw.get("in_viewport", False))
        bounding_box = _normalize_bounding_box(raw.get("bounding_box"))

        dom_key = _build_dom_key(
            tag=tag,
            selector=selector,
            xpath=xpath,
            text=text,
            aria_label=aria_label,
            placeholder=placeholder,
            attributes=attributes,
        )

        return {
            "_dom_key": dom_key,
            "type": element_type,
            "text": text,
            "aria_label": aria_label,
            "placeholder": placeholder,
            "selector": selector,
            "xpath": xpath,
            "visible": visible,
            "enabled": enabled,
            "bounding_box": bounding_box,
            "in_viewport": in_viewport,
            "tag": tag,
            "attributes": attributes,
        }


def _resolve_element_type(tag: str, attributes: dict[str, str]) -> str:
    role = attributes.get("role", "").lower()
    input_type = attributes.get("type", "").lower()

    if tag == "a":
        return "link"
    if tag == "button":
        return "button"
    if tag == "input":
        return "input"
    if role == "button" or input_type in {"submit", "button"}:
        return "button"
    return "custom"


def _normalize_attributes(value: Any) -> dict[str, str]:
    attributes = {"id": "", "class": "", "role": "", "type": ""}
    if not isinstance(value, dict):
        return attributes
    for key in attributes:
        attributes[key] = _as_str(value.get(key))
    return attributes


def _normalize_bounding_box(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    return {
        "x": _as_float(value.get("x")),
        "y": _as_float(value.get("y")),
        "width": _as_float(value.get("width")),
        "height": _as_float(value.get("height")),
    }


def _build_dom_key(
    *,
    tag: str,
    selector: str,
    xpath: str,
    text: str,
    aria_label: str,
    placeholder: str,
    attributes: dict[str, str],
) -> str:
    fingerprint_payload = {
        "tag": tag,
        "selector": selector,
        "xpath": xpath,
        "text": text,
        "aria_label": aria_label,
        "placeholder": placeholder,
        "attributes": attributes,
    }
    serialized = json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def _as_str(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0
