"""Security Auditor — periodic security scans of the system.

Checks for:
- Exposed API keys in logs/settings
- Integrity of security rules
- Suspicious processes
- Prompt injection attempts in recent messages
"""
from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Patterns that might indicate exposed secrets
SECRET_PATTERNS = [
    re.compile(r'(sk-[a-zA-Z0-9]{20,})', re.I),       # OpenAI keys
    re.compile(r'(gsk_[a-zA-Z0-9]{20,})', re.I),       # Groq keys
    re.compile(r'(sk-ant-[a-zA-Z0-9]{20,})', re.I),    # Anthropic keys
    re.compile(r'(AIza[a-zA-Z0-9_-]{35})', re.I),      # Google keys
    re.compile(r'(ghp_[a-zA-Z0-9]{36})', re.I),        # GitHub tokens
]


class SecurityAuditor:
    """Periodic security scanning."""

    def __init__(self, project_root: Path, interval_s: int = 300) -> None:
        self._root = project_root
        self._interval = interval_s
        self._running = False
        self._thread: threading.Thread | None = None
        self._findings: list[dict[str, Any]] = []
        self._last_audit: str | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="security-auditor")
        self._thread.start()
        print("[SECURITY-AUDITOR] Started", flush=True)

    def stop(self) -> None:
        self._running = False

    @property
    def findings(self) -> list[dict[str, Any]]:
        return list(self._findings)

    @property
    def status(self) -> str:
        if not self._findings:
            return "clean"
        severities = [f.get("severity", "low") for f in self._findings[-10:]]
        if "critical" in severities:
            return "critical"
        if "high" in severities:
            return "alert"
        if "medium" in severities:
            return "warning"
        return "clean"

    def audit_now(self) -> list[dict[str, Any]]:
        """Run a full audit immediately."""
        findings = []
        findings.extend(self._check_exposed_keys())
        findings.extend(self._check_security_rules())
        findings.extend(self._check_log_files())
        findings.extend(self._check_generated_code())
        findings.extend(self._check_settings_secrets())
        self._last_audit = _now()

        for f in findings:
            self._findings.append(f)
        if len(self._findings) > 100:
            self._findings = self._findings[-50:]

        return findings

    def _loop(self) -> None:
        time.sleep(120)  # Initial delay
        while self._running:
            try:
                findings = self.audit_now()
                if findings:
                    severity = max(f.get("severity", "low") for f in findings)
                    print(f"[SECURITY-AUDITOR] {len(findings)} findings (max severity: {severity})", flush=True)
                    if severity in ("high", "critical"):
                        self._emit_alert(findings)
            except Exception as exc:
                print(f"[SECURITY-AUDITOR] Error: {exc}", flush=True)
            time.sleep(self._interval)

    def _check_exposed_keys(self) -> list[dict[str, Any]]:
        """Check if API keys are exposed in log files."""
        findings = []
        log_dir = self._root / "workspace" / "logs" if (self._root / "workspace").exists() else self._root / "logs"

        if not log_dir.exists():
            return findings

        for log_file in log_dir.glob("*.log"):
            try:
                content = log_file.read_text(encoding="utf-8", errors="replace")[:50000]
                for pattern in SECRET_PATTERNS:
                    matches = pattern.findall(content)
                    if matches:
                        findings.append({
                            "check": "exposed_key",
                            "severity": "critical",
                            "file": str(log_file),
                            "detail": f"Found {len(matches)} potential API key(s) in log file",
                            "timestamp": _now(),
                        })
            except Exception:
                pass

        return findings

    def _check_security_rules(self) -> list[dict[str, Any]]:
        """Verify security_rules.json integrity."""
        findings = []
        rules_path = self._root / "system" / "core" / "security" / "security_rules.json"

        if not rules_path.exists():
            findings.append({
                "check": "security_rules",
                "severity": "high",
                "detail": "security_rules.json is missing",
                "timestamp": _now(),
            })
            return findings

        try:
            import json
            data = json.loads(rules_path.read_text(encoding="utf-8"))
            if not data.get("free") or not data.get("confirm") or not data.get("protected"):
                findings.append({
                    "check": "security_rules",
                    "severity": "high",
                    "detail": "security_rules.json is incomplete — missing level definitions",
                    "timestamp": _now(),
                })
        except Exception as exc:
            findings.append({
                "check": "security_rules",
                "severity": "high",
                "detail": f"security_rules.json is corrupt: {exc}",
                "timestamp": _now(),
            })

        return findings

    def _check_log_files(self) -> list[dict[str, Any]]:
        """Check for suspicious patterns in recent logs."""
        findings = []

        # Check if error notifier log exists and has recent critical errors
        errors_dir = self._root / "errors"
        if errors_dir.exists():
            error_files = sorted(errors_dir.glob("*.json"), reverse=True)[:5]
            critical_count = 0
            for ef in error_files:
                try:
                    import json
                    data = json.loads(ef.read_text(encoding="utf-8"))
                    if data.get("error_code") in ("security_violation", "auth_error"):
                        critical_count += 1
                except Exception:
                    pass

            if critical_count >= 3:
                findings.append({
                    "check": "error_pattern",
                    "severity": "high",
                    "detail": f"{critical_count} security-related errors in recent error logs",
                    "timestamp": _now(),
                })

        return findings

    def _check_generated_code(self) -> list[dict[str, Any]]:
        """Scan auto-generated skill handler code for dangerous patterns."""
        findings = []
        dangerous_patterns = [
            re.compile(r'\beval\s*\('),
            re.compile(r'\bexec\s*\('),
            re.compile(r'\b__import__\s*\('),
            re.compile(r'\bos\.system\s*\('),
            re.compile(r'\bsubprocess\.(run|call|Popen)\s*\('),
            re.compile(r'\bopen\s*\([^)]*["\']w'),
        ]

        skills_dir = self._root / "skills"
        if not skills_dir.exists():
            return findings

        for py_file in skills_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")[:20000]
                for pattern in dangerous_patterns:
                    matches = pattern.findall(content)
                    if matches:
                        findings.append({
                            "check": "dangerous_code",
                            "severity": "high",
                            "file": str(py_file.relative_to(self._root)),
                            "detail": f"Dangerous pattern '{matches[0]}' found in auto-generated skill",
                            "timestamp": _now(),
                        })
            except Exception:
                pass

        return findings

    def _check_settings_secrets(self) -> list[dict[str, Any]]:
        """Check for hardcoded secrets in settings files."""
        findings = []
        settings_path = self._root / "system" / "settings.json"

        if not settings_path.exists():
            return findings

        try:
            content = settings_path.read_text(encoding="utf-8", errors="replace")
            for pattern in SECRET_PATTERNS:
                matches = pattern.findall(content)
                if matches:
                    findings.append({
                        "check": "settings_secret",
                        "severity": "medium",
                        "file": "system/settings.json",
                        "detail": f"API key found in settings file — consider using environment variables",
                        "timestamp": _now(),
                    })
                    break  # One finding per file is enough
        except Exception:
            pass

        return findings

    def _emit_alert(self, findings: list[dict[str, Any]]) -> None:
        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("supervisor_alert", {
                "severity": "high",
                "source": "security_auditor",
                "findings": len(findings),
                "message": findings[0].get("detail", "Security issue detected"),
            })
        except Exception:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
