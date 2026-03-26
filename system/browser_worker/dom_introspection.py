from __future__ import annotations

import re
from typing import Any


class DOMIntrospectionEngine:
    """Extract normalized interactive element candidates from active page DOM."""

    _EXTRACTION_SCRIPT = r"""
({ limit }) => {
  const MAX_ITEMS = Math.max(1, Math.min(Number(limit || 300), 1000));
  const selectors = [
    "button",
    "a[href]",
    "input[type='submit']",
    "input[type='button']",
    "[role='button']",
    "[onclick]",
    "[tabindex]",
  ];

  const cssEscape = (value) => {
    try {
      if (window.CSS && typeof window.CSS.escape === "function") {
        return window.CSS.escape(String(value));
      }
    } catch (e) {}
    return String(value).replace(/([ !"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])/g, "\\$1");
  };

  const normalizeText = (value) => {
    if (typeof value !== "string") return "";
    return value.replace(/\s+/g, " ").trim();
  };

  const buildSelector = (element) => {
    if (!element || element.nodeType !== 1) {
      return "";
    }
    if (element.id) {
      return "#" + cssEscape(element.id);
    }

    const parts = [];
    let current = element;
    let depth = 0;
    while (current && current.nodeType === 1 && depth < 8) {
      const tag = (current.tagName || "").toLowerCase();
      if (!tag) break;

      let part = tag;
      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(
          (child) => child.tagName === current.tagName
        );
        if (siblings.length > 1) {
          const index = siblings.indexOf(current) + 1;
          part += `:nth-of-type(${index})`;
        }
      }
      parts.unshift(part);
      if (current.id) {
        parts[0] = "#" + cssEscape(current.id);
        break;
      }
      current = parent;
      depth += 1;
    }
    return parts.join(" > ");
  };

  const buildXPath = (element) => {
    if (!element || element.nodeType !== 1) {
      return "";
    }
    if (element.id) {
      return `//*[@id="${String(element.id).replace(/"/g, '\\"')}"]`;
    }
    const segments = [];
    let current = element;
    while (current && current.nodeType === 1) {
      const tag = (current.tagName || "").toLowerCase();
      if (!tag) break;
      let index = 1;
      let sibling = current.previousElementSibling;
      while (sibling) {
        if ((sibling.tagName || "").toLowerCase() === tag) {
          index += 1;
        }
        sibling = sibling.previousElementSibling;
      }
      segments.unshift(`${tag}[${index}]`);
      current = current.parentElement;
    }
    return "/" + segments.join("/");
  };

  const isElementVisible = (element, rect) => {
    if (!element) return false;
    if (element.hidden) return false;
    if (rect.width <= 0 || rect.height <= 0) return false;

    let style;
    try {
      style = window.getComputedStyle(element);
    } catch (e) {
      return true;
    }
    if (!style) return true;
    if (style.display === "none") return false;
    if (style.visibility === "hidden" || style.visibility === "collapse") return false;
    if (Number(style.opacity || "1") <= 0.01) return false;
    return true;
  };

  const isInViewport = (rect) => {
    const vw = window.innerWidth || document.documentElement.clientWidth || 0;
    const vh = window.innerHeight || document.documentElement.clientHeight || 0;
    if (vw <= 0 || vh <= 0) return false;
    return rect.bottom > 0 && rect.right > 0 && rect.left < vw && rect.top < vh;
  };

  const isElementEnabled = (element) => {
    if (!element) return false;
    const ariaDisabled = String(element.getAttribute("aria-disabled") || "").toLowerCase();
    if (ariaDisabled === "true") return false;
    if (typeof element.disabled === "boolean" && element.disabled) return false;
    return true;
  };

  const candidates = [];
  const seen = new Set();
  for (const selector of selectors) {
    const nodes = document.querySelectorAll(selector);
    for (const node of nodes) {
      if (!node || seen.has(node)) continue;
      seen.add(node);
      candidates.push(node);
      if (candidates.length >= MAX_ITEMS) break;
    }
    if (candidates.length >= MAX_ITEMS) break;
  }

  const output = [];
  for (const element of candidates) {
    const tag = (element.tagName || "").toLowerCase();
    const rect = element.getBoundingClientRect();
    const visible = isElementVisible(element, rect);
    const inViewport = isInViewport(rect);
    const role = element.getAttribute("role") || "";
    const inputType = element.getAttribute("type") || "";
    const className =
      typeof element.className === "string"
        ? element.className
        : (element.className && element.className.baseVal) || "";

    output.push({
      tag,
      text: normalizeText(element.innerText || element.textContent || ""),
      aria_label: normalizeText(element.getAttribute("aria-label") || ""),
      placeholder: normalizeText(element.getAttribute("placeholder") || ""),
      selector: buildSelector(element),
      xpath: buildXPath(element),
      visible,
      enabled: isElementEnabled(element),
      bounding_box: {
        x: Number.isFinite(rect.x) ? rect.x : 0,
        y: Number.isFinite(rect.y) ? rect.y : 0,
        width: Number.isFinite(rect.width) ? rect.width : 0,
        height: Number.isFinite(rect.height) ? rect.height : 0,
      },
      in_viewport: inViewport,
      attributes: {
        id: element.id || "",
        class: String(className || ""),
        role: String(role || ""),
        type: String(inputType || ""),
      },
    });
  }

  return output;
}
"""

    def extract_interactive_elements(
        self,
        page: Any,
        *,
        visible_only: bool = True,
        in_viewport_only: bool = False,
        text_contains: str | None = None,
        limit: int = 300,
    ) -> list[dict[str, Any]]:
        if page is None:
            return []

        payload = {"limit": max(1, min(int(limit), 1000))}
        raw_items = page.evaluate(self._EXTRACTION_SCRIPT, payload)
        if not isinstance(raw_items, list):
            return []

        normalized: list[dict[str, Any]] = []
        query = _normalize_query(text_contains)
        for item in raw_items:
            normalized_item = _normalize_item(item)
            if normalized_item is None:
                continue

            if visible_only and not normalized_item["visible"]:
                continue
            if in_viewport_only and not normalized_item["in_viewport"]:
                continue
            if query and not _matches_query(normalized_item, query):
                continue

            normalized.append(normalized_item)
        return normalized


def _normalize_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    selector = _to_clean_string(item.get("selector"))
    if not selector:
        return None

    bounding_box = _normalize_bounding_box(item.get("bounding_box"))
    attributes = _normalize_attributes(item.get("attributes"))

    return {
        "tag": _to_clean_string(item.get("tag")).lower(),
        "text": _to_clean_string(item.get("text")),
        "aria_label": _to_clean_string(item.get("aria_label")),
        "placeholder": _to_clean_string(item.get("placeholder")),
        "selector": selector,
        "xpath": _to_clean_string(item.get("xpath")),
        "visible": bool(item.get("visible", False)),
        "enabled": bool(item.get("enabled", False)),
        "bounding_box": bounding_box,
        "in_viewport": bool(item.get("in_viewport", False)),
        "attributes": attributes,
    }


def _normalize_bounding_box(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    return {
        "x": _to_float(value.get("x")),
        "y": _to_float(value.get("y")),
        "width": _to_float(value.get("width")),
        "height": _to_float(value.get("height")),
    }


def _normalize_attributes(value: Any) -> dict[str, str]:
    attrs: dict[str, str] = {"id": "", "class": "", "role": "", "type": ""}
    if not isinstance(value, dict):
        return attrs
    for key in attrs:
        attrs[key] = _to_clean_string(value.get(key))
    return attrs


def _to_clean_string(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _normalize_query(text_contains: str | None) -> str:
    if not isinstance(text_contains, str):
        return ""
    return re.sub(r"\s+", " ", text_contains).strip().lower()


def _matches_query(item: dict[str, Any], query: str) -> bool:
    text_parts = [
        item.get("text", ""),
        item.get("aria_label", ""),
        item.get("placeholder", ""),
    ]
    combined = " ".join(part for part in text_parts if isinstance(part, str)).lower()
    return query in combined
