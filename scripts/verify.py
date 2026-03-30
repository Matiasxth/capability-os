"""Capability OS — Post-deploy verification agent.

Runs after every build/restart to catch broken features before the user does.
Usage: python scripts/verify.py [--url http://localhost:8000]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
PROJECT = Path(__file__).resolve().parent.parent
DIST = PROJECT / "system" / "frontend" / "app" / "dist"

passed = 0
failed = 0
warnings = 0
errors: list[str] = []


def check(name: str, fn):
    global passed, failed
    try:
        result = fn()
        if result is True:
            print(f"  \033[32m✓\033[0m {name}")
            passed += 1
        else:
            print(f"  \033[31m✗\033[0m {name}: {result}")
            errors.append(f"{name}: {result}")
            failed += 1
    except Exception as e:
        print(f"  \033[31m✗\033[0m {name}: {e}")
        errors.append(f"{name}: {e}")
        failed += 1


def warn(name: str, msg: str):
    global warnings
    print(f"  \033[33m⚠\033[0m {name}: {msg}")
    warnings += 1


def get(path: str, timeout: float = 5.0) -> dict:
    req = Request(f"{URL}{path}")
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def post(path: str, body: dict | None = None, timeout: float = 10.0) -> dict:
    data = json.dumps(body or {}).encode()
    req = Request(f"{URL}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get_raw(path: str) -> str:
    req = Request(f"{URL}{path}")
    with urlopen(req, timeout=5) as r:
        return r.read().decode()


# ═══════════════════════════════════════════════════════
# Checks
# ═══════════════════════════════════════════════════════

print(f"\n\033[1mCapability OS Verification Agent\033[0m")
print(f"Target: {URL}\n")

# ── 1. System health ──
print("\033[36m[System]\033[0m")
check("Health endpoint responds", lambda: get("/health").get("status") == "ready" or "health returned: " + str(get("/health").get("status")))
check("LLM configured", lambda: get("/health").get("llm", {}).get("status") == "ready" or "llm status: " + str(get("/health").get("llm", {}).get("status")))

# ── 2. Frontend serving ──
print("\033[36m[Frontend]\033[0m")

def check_html_serves_latest():
    html = get_raw("/")
    # Find JS filename in dist
    import re
    match = re.search(r'src="/assets/(index-[^"]+\.js)"', html)
    if not match:
        return "No JS reference found in HTML"
    served_js = match.group(1)
    # Check file exists in dist
    dist_file = DIST / "assets" / served_js
    if not dist_file.exists():
        return f"HTML references {served_js} but file not in dist/"
    return True

check("HTML serves latest JS bundle", check_html_serves_latest)

def check_sw_not_caching():
    sw = get_raw("/sw.js")
    if "cache-first" in sw.lower():
        return "Service worker still uses cache-first strategy"
    if "capos-v1" in sw:
        return "Old service worker (v1) still being served"
    return True

check("Service worker is safe (no cache-first)", check_sw_not_caching)

def check_bundle_contains_features():
    html = get_raw("/")
    import re
    match = re.search(r'src="/assets/(index-[^"]+\.js)"', html)
    if not match:
        return "No JS bundle found"
    js = get_raw(f"/assets/{match.group(1)}")
    missing = []
    features = {
        "WhatsApp Hub": "Linked Devices",
        "Backend selector": "switch-backend",
        "WhatsApp session API": "session-status",
    }
    for name, marker in features.items():
        if marker not in js:
            missing.append(name)
    if missing:
        return f"Missing features in bundle: {', '.join(missing)}"
    return True

check("JS bundle contains all features", check_bundle_contains_features)

# ── 3. API endpoints ──
print("\033[36m[API Endpoints]\033[0m")
check("Settings endpoint", lambda: "settings" in get("/settings") or "no settings key")
check("Integrations list", lambda: isinstance(get("/integrations").get("integrations"), list) or "bad format")
check("Capabilities list", lambda: isinstance(get("/capabilities").get("capabilities"), list) or "bad format")

# ── 4. WhatsApp backends ──
print("\033[36m[WhatsApp]\033[0m")

def check_whatsapp_backends():
    try:
        d = get("/integrations/whatsapp/backends")
    except Exception as e:
        return f"Endpoint failed: {e}"
    backends = d.get("backends", [])
    if len(backends) != 3:
        return f"Expected 3 backends, got {len(backends)}"
    ids = {b["id"] for b in backends}
    expected = {"official", "browser", "baileys"}
    if ids != expected:
        return f"Backend IDs: {ids}, expected: {expected}"
    active = [b for b in backends if b.get("active")]
    if len(active) != 1:
        return f"Expected 1 active backend, got {len(active)}"
    return True

check("3 backends registered", check_whatsapp_backends)
check("Session status endpoint", lambda: "active" in get("/integrations/whatsapp/session-status") or "missing 'active' key")

def check_whatsapp_switch():
    r = post("/integrations/whatsapp/switch-backend", {"backend": "baileys"})
    if r.get("status") != "ok":
        return f"Switch to baileys failed: {r}"
    r2 = post("/integrations/whatsapp/switch-backend", {"backend": "browser"})
    if r2.get("status") != "ok":
        return f"Switch back to browser failed: {r2}"
    return True

check("Backend switching works", check_whatsapp_switch)

# ── 5. Browser backend ──
print("\033[36m[Browser Backend]\033[0m")

def check_browser_settings():
    s = get("/settings").get("settings", {})
    browser = s.get("browser", {})
    if "backend" not in browser:
        return "Missing browser.backend in settings"
    return True

check("Browser backend in settings", check_browser_settings)

# ── 6. Error notifier ──
print("\033[36m[Error Notifier]\033[0m")
notifier_file = PROJECT / "system" / "core" / "observation" / "error_notifier.py"
check("ErrorNotifier module exists", lambda: notifier_file.exists() or "file missing")

# ── 7. Launcher ──
print("\033[36m[Launcher]\033[0m")
launcher_file = PROJECT / "launcher.py"
bat_file = PROJECT / "CapabilityOS.bat"
check("launcher.py exists", lambda: launcher_file.exists() or "file missing")
check("CapabilityOS.bat exists", lambda: bat_file.exists() or "file missing")

# ═══════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════

print(f"\n\033[1mResults: {passed} passed, {failed} failed, {warnings} warnings\033[0m")
if errors:
    print(f"\n\033[31mFailures:\033[0m")
    for e in errors:
        print(f"  - {e}")
    print()

sys.exit(1 if failed > 0 else 0)
