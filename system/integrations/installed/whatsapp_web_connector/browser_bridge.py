"""WhatsApp Web browser bridge — uses Playwright headless to show QR in the UI.

Fallback for when Baileys is blocked (405). Opens a real Chromium instance,
navigates to WhatsApp Web, captures the QR code as a base64 image, and
detects when the user has scanned it.

The bridge keeps the browser alive so WhatsApp operations can run through it.
"""
from __future__ import annotations

import base64
import threading
import time
from typing import Any


class BrowserBridge:
    """Manages a Playwright Chromium session for WhatsApp Web."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None
        self._qr_b64: str | None = None
        self._logged_in = False
        self._status = "idle"  # idle | starting | qr_ready | connected | error
        self._error: str | None = None
        self._poll_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def status(self) -> str:
        return self._status

    @property
    def connected(self) -> bool:
        return self._logged_in

    def start(self, timeout_s: float = 30.0) -> dict[str, Any]:
        """Launch browser, navigate to WhatsApp Web, and wait for QR."""
        with self._lock:
            if self._status == "connected":
                return {"status": "connected", "connected": True}
            if self._status in ("starting", "qr_ready"):
                return self._current_state()

        self._status = "starting"
        self._error = None
        self._qr_b64 = None
        self._logged_in = False

        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            self._page = ctx.new_page()
            self._page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            self._status = "error"
            self._error = f"Browser launch failed: {exc}"
            self._cleanup()
            return {"status": "error", "error": self._error}

        # Wait for QR or logged-in state
        qr = self._wait_for_qr_or_login(timeout_s)
        if qr:
            return qr

        return self._current_state()

    def get_qr_image(self) -> str | None:
        """Return the latest QR as a data:image/png;base64 URL, or None."""
        if self._qr_b64:
            return f"data:image/png;base64,{self._qr_b64}"
        return None

    def refresh_qr(self) -> dict[str, Any]:
        """Re-capture the QR code from the page."""
        if self._page is None:
            return self._current_state()

        if self._logged_in:
            return {"status": "connected"}

        self._capture_qr()
        return self._current_state()

    def check_login(self) -> dict[str, Any]:
        """Check if the user has scanned the QR and is now logged in."""
        if self._page is None:
            return self._current_state()

        if self._check_logged_in():
            self._logged_in = True
            self._status = "connected"
            self._qr_b64 = None
            self._start_poll_thread()
            return {"status": "connected"}

        # Maybe QR refreshed
        self._capture_qr()
        return self._current_state()

    def close(self) -> dict[str, Any]:
        """Shut down browser."""
        self._cleanup()
        self._status = "idle"
        self._logged_in = False
        self._qr_b64 = None
        return {"status": "closed"}

    def send_message(self, chat_name: str, message: str, timeout_s: float = 30.0) -> dict[str, Any]:
        """Send a message via the WhatsApp Web UI."""
        if not self._logged_in or self._page is None:
            return {"status": "error", "error": "Not connected"}

        try:
            page = self._page
            # Click search
            search_sel = 'div[contenteditable="true"][data-tab="3"]'
            page.wait_for_selector(search_sel, timeout=10000)
            page.click(search_sel)
            page.fill(search_sel, chat_name)
            time.sleep(1.5)

            # Click first result
            page.keyboard.press("Enter")
            time.sleep(1)

            # Type message
            msg_sel = 'div[contenteditable="true"][data-tab="10"]'
            page.wait_for_selector(msg_sel, timeout=10000)
            page.click(msg_sel)
            page.fill(msg_sel, message)
            page.keyboard.press("Enter")
            time.sleep(0.5)

            return {"status": "success", "message": message, "chat_name": chat_name, "backend": "browser_bridge"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _current_state(self) -> dict[str, Any]:
        result: dict[str, Any] = {"status": self._status, "connected": self._logged_in}
        if self._qr_b64:
            result["qr_image"] = f"data:image/png;base64,{self._qr_b64}"
        if self._error:
            result["error"] = self._error
        return result

    def _wait_for_qr_or_login(self, timeout_s: float) -> dict[str, Any] | None:
        if self._page is None:
            return None
        deadline = time.monotonic() + timeout_s

        while time.monotonic() < deadline:
            # Check if already logged in
            if self._check_logged_in():
                self._logged_in = True
                self._status = "connected"
                self._qr_b64 = None
                self._start_poll_thread()
                return {"status": "connected", "connected": True}

            # Try to capture QR
            if self._capture_qr():
                self._status = "qr_ready"
                return self._current_state()

            time.sleep(1)

        self._status = "error"
        self._error = "Timeout waiting for WhatsApp Web to load"
        return self._current_state()

    def _capture_qr(self) -> bool:
        """Screenshot the QR canvas and store as base64."""
        if self._page is None:
            return False
        try:
            # WhatsApp Web renders QR in a canvas inside a div with data-ref
            qr_el = self._page.query_selector('canvas[aria-label="Scan this QR code to link a device!"]')
            if qr_el is None:
                qr_el = self._page.query_selector('div[data-ref] canvas')
            if qr_el is None:
                qr_el = self._page.query_selector('canvas')

            if qr_el:
                screenshot = qr_el.screenshot(type="png")
                self._qr_b64 = base64.b64encode(screenshot).decode()
                return True
        except Exception:
            pass
        return False

    def _check_logged_in(self) -> bool:
        """Detect if WhatsApp Web is past the QR/login screen."""
        if self._page is None:
            return False
        try:
            # Strategy 1: check if QR canvas is gone (it disappears after scan)
            qr_el = self._page.query_selector('canvas')
            has_qr = qr_el is not None

            # Strategy 2: look for chat-related elements (multiple selectors for robustness)
            indicators = [
                'div[aria-label="Chat list"]',
                'div[aria-label="Lista de chats"]',
                'div[data-tab="3"][contenteditable="true"]',
                'header span[data-icon="chat"]',
                'span[data-icon="menu"]',
                'span[data-icon="search"]',
                '#side',                              # main sidebar container
                'div[data-testid="chat-list"]',
                'div[data-testid="chatlist-header"]',
            ]
            for sel in indicators:
                el = self._page.query_selector(sel)
                if el:
                    return True

            # Strategy 3: if QR is gone and page has substantial content, assume logged in
            if not has_qr:
                body_text = self._page.evaluate("() => document.body.innerText.length")
                if isinstance(body_text, (int, float)) and body_text > 200:
                    return True

        except Exception:
            pass
        return False

    def debug_screenshot(self) -> dict[str, Any]:
        """Take a full page screenshot for debugging."""
        if self._page is None:
            return {"status": "error", "error": "No page"}
        try:
            screenshot = self._page.screenshot(type="png", full_page=False)
            b64 = base64.b64encode(screenshot).decode()
            url = self._page.url
            title = self._page.title()
            return {"status": "ok", "url": url, "title": title, "screenshot": f"data:image/png;base64,{b64}"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _start_poll_thread(self) -> None:
        """Poll for disconnection in background."""
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._poll_thread = threading.Thread(target=self._connection_watchdog, daemon=True)
        self._poll_thread.start()

    def _connection_watchdog(self) -> None:
        while self._logged_in and self._page is not None:
            time.sleep(10)
            try:
                if self._page is None:
                    break
                # Check if page is still on WhatsApp
                url = self._page.url
                if "web.whatsapp.com" not in url:
                    self._logged_in = False
                    self._status = "idle"
                    break
            except Exception:
                self._logged_in = False
                self._status = "idle"
                break

    def _cleanup(self) -> None:
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._browser = None
        self._page = None
        self._playwright = None
