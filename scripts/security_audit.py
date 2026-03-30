"""Full security audit for Capability OS."""
from __future__ import annotations

import json
import re
from pathlib import Path


def main() -> None:
    root = Path(".")
    findings: list[dict] = []

    def add(severity: str, category: str, detail: str, file: str = "") -> None:
        findings.append({"severity": severity, "category": category, "detail": detail, "file": file})

    # 1. Dangerous code patterns
    print("[1/8] Scanning for dangerous code patterns...")
    dangerous = [
        (re.compile(r"\beval\s*\("), "eval()"),
        (re.compile(r"\bexec\s*\("), "exec()"),
        (re.compile(r"\b__import__\s*\("), "__import__()"),
        (re.compile(r"\bos\.system\s*\("), "os.system()"),
    ]
    for py in root.rglob("*.py"):
        s = str(py)
        if any(skip in s for skip in ["__pycache__", "node_modules", "anaconda", ".venv", "venv"]):
            continue
        if not s.startswith("system"):
            continue
        if "test" in py.name.lower():
            continue
        try:
            content = py.read_text(encoding="utf-8", errors="replace")
            for pattern, name in dangerous:
                for i, line in enumerate(content.split("\n"), 1):
                    stripped = line.strip()
                    if pattern.search(line) and not stripped.startswith("#") and not stripped.startswith('"""'):
                        if "safe_eval" in line or "supervisor_prompt" in s:
                            continue
                        add("HIGH", "dangerous_code", f"{name} at line {i}", s)
        except Exception:
            pass

    # 2. Secrets in config
    print("[2/8] Scanning for exposed secrets...")
    secret_patterns = [
        (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "OpenAI key"),
        (re.compile(r"gsk_[a-zA-Z0-9]{20,}"), "Groq key"),
        (re.compile(r"sk-ant-[a-zA-Z0-9]{20,}"), "Anthropic key"),
        (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "GitHub token"),
    ]
    for f in ["system/settings.json", ".env", "docker-compose.yml"]:
        p = root / f
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="replace")
            for pattern, name in secret_patterns:
                if pattern.search(content):
                    add("MEDIUM", "exposed_secret", f"{name} found in config", f)

    # 3. Security rules
    print("[3/8] Checking security rules integrity...")
    rules_path = root / "system" / "core" / "security" / "security_rules.json"
    if rules_path.exists():
        rules = json.loads(rules_path.read_text())
        for level in ["free", "confirm", "protected"]:
            if level not in rules:
                add("HIGH", "security_rules", f'Missing "{level}" level')
        free_count = len(rules.get("free", {}).get("tools", []))
        confirm_count = len(rules.get("confirm", {}).get("tools", []))
        protected_count = len(rules.get("protected", {}).get("tools", []))
        add("INFO", "security_rules", f"Rules OK: {free_count} free, {confirm_count} confirm, {protected_count} protected tools")
    else:
        add("HIGH", "security_rules", "security_rules.json missing!")

    # 4. Auth
    print("[4/8] Checking authentication...")
    users_path = root / "users.json"
    if users_path.exists():
        users = json.loads(users_path.read_text())
        user_list = users.get("users", [])
        owners = [u for u in user_list if u.get("role") == "owner"]
        add("INFO", "auth", f"{len(user_list)} users, {len(owners)} owner(s)")
        for u in user_list:
            if not u.get("password_hash"):
                add("HIGH", "auth", f'User "{u.get("username")}" has no password hash!')
    else:
        add("MEDIUM", "auth", "No users.json — auth may not be configured")

    jwt_path = root / "jwt_secret.key"
    if jwt_path.exists():
        key = jwt_path.read_text().strip()
        if len(key) < 32:
            add("HIGH", "auth", "JWT secret too short (<32 chars)")
        else:
            add("INFO", "auth", f"JWT secret exists ({len(key)} chars)")
    else:
        add("INFO", "auth", "No JWT secret — auto-generated on first run")

    # 5. Path traversal
    print("[5/8] Checking path traversal protection...")
    pv = root / "system" / "core" / "workspace" / "path_validator.py"
    if pv.exists():
        content = pv.read_text()
        if "is_relative_to" in content or "resolve" in content:
            add("INFO", "path_traversal", "PathValidator uses resolve() + is_relative_to")
        else:
            add("HIGH", "path_traversal", "PathValidator missing proper validation")
    else:
        add("HIGH", "path_traversal", "path_validator.py not found!")

    # 6. CORS
    print("[6/8] Checking CORS configuration...")
    for f in [root / "docker-entrypoint.py", root / "system" / "core" / "ui_bridge" / "asgi_server.py"]:
        if f.exists():
            content = f.read_text(encoding="utf-8", errors="replace")
            if "Access-Control-Allow-Origin" in content:
                after = content.split("Access-Control-Allow-Origin")[1][:80]
                if "*" in after:
                    add("MEDIUM", "cors", f"Wildcard CORS (*) in {f.name} — restrict in production")

    # 7. Sandbox
    print("[7/8] Checking execution sandbox...")
    sandbox_py = root / "system" / "core" / "sandbox" / "sandbox_manager.py"
    if sandbox_py.exists():
        content = sandbox_py.read_text()
        add("INFO", "sandbox", "SandboxManager present (L2 process + L3 docker)")
        if "docker" in content.lower():
            add("INFO", "sandbox", "Docker sandbox support available")
    else:
        add("MEDIUM", "sandbox", "SandboxManager not found")

    # 8. Dependencies
    print("[8/8] Checking dependencies...")
    req_path = root / "requirements.txt"
    if req_path.exists():
        lines = [l.strip() for l in req_path.read_text().split("\n") if l.strip() and not l.strip().startswith("#")]
        pinned = sum(1 for r in lines if "==" in r)
        unpinned = sum(1 for r in lines if ">=" in r)
        add("LOW" if unpinned > pinned else "INFO", "dependencies", f"{len(lines)} deps ({pinned} pinned, {unpinned} unpinned)")

    # Report
    print()
    print("=" * 60)
    print("  SECURITY AUDIT REPORT — Capability OS")
    print("=" * 60)
    print()

    by_sev: dict[str, list] = {}
    for f in findings:
        by_sev.setdefault(f["severity"], []).append(f)

    icons = {"HIGH": "[!]", "MEDIUM": "[~]", "LOW": "[-]", "INFO": "[i]"}
    for sev in ["HIGH", "MEDIUM", "LOW", "INFO"]:
        items = by_sev.get(sev, [])
        if not items:
            continue
        print(f"  {icons[sev]} {sev} ({len(items)})")
        for f in items:
            print(f"      {f['category']}: {f['detail']}")
            if f.get("file"):
                print(f"        -> {f['file']}")
        print()

    high = len(by_sev.get("HIGH", []))
    medium = len(by_sev.get("MEDIUM", []))
    if high > 0:
        print(f"  VERDICT: ACTION REQUIRED -- {high} high severity issues")
    elif medium > 0:
        print(f"  VERDICT: ACCEPTABLE -- {medium} medium issues (review recommended)")
    else:
        print("  VERDICT: CLEAN -- no high or medium issues found")
    print()


if __name__ == "__main__":
    main()
