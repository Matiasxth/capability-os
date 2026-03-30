"""Tests for the enhanced SecurityAuditor checks."""

import json
from pathlib import Path
from system.core.supervisor.security_auditor import SecurityAuditor


class TestGeneratedCodeCheck:
    def test_detects_eval_in_skill(self, tmp_path):
        skills_dir = tmp_path / "skills" / "my_skill" / "tools"
        skills_dir.mkdir(parents=True)
        (skills_dir / "handler.py").write_text("result = eval(user_input)")

        auditor = SecurityAuditor(tmp_path)
        findings = auditor._check_generated_code()
        assert len(findings) >= 1
        assert findings[0]["severity"] == "high"
        assert "eval" in findings[0]["detail"]

    def test_detects_exec_in_skill(self, tmp_path):
        skills_dir = tmp_path / "skills" / "bad_skill" / "tools"
        skills_dir.mkdir(parents=True)
        (skills_dir / "handler.py").write_text("exec('import os')")

        auditor = SecurityAuditor(tmp_path)
        findings = auditor._check_generated_code()
        assert len(findings) >= 1
        assert "exec" in findings[0]["detail"]

    def test_detects_import_in_skill(self, tmp_path):
        skills_dir = tmp_path / "skills" / "risky" / "tools"
        skills_dir.mkdir(parents=True)
        (skills_dir / "handler.py").write_text("mod = __import__('os')")

        auditor = SecurityAuditor(tmp_path)
        findings = auditor._check_generated_code()
        assert len(findings) >= 1

    def test_clean_skill_no_findings(self, tmp_path):
        skills_dir = tmp_path / "skills" / "safe_skill" / "tools"
        skills_dir.mkdir(parents=True)
        (skills_dir / "handler.py").write_text("def run(params):\n    return {'status': 'ok'}\n")

        auditor = SecurityAuditor(tmp_path)
        findings = auditor._check_generated_code()
        assert len(findings) == 0

    def test_no_skills_dir(self, tmp_path):
        auditor = SecurityAuditor(tmp_path)
        findings = auditor._check_generated_code()
        assert len(findings) == 0


class TestSettingsSecretsCheck:
    def test_detects_api_key_in_settings(self, tmp_path):
        system_dir = tmp_path / "system"
        system_dir.mkdir()
        settings = {"llm": {"api_key": "sk-1234567890abcdefghijklmnopqrstuvwxyz"}}
        (system_dir / "settings.json").write_text(json.dumps(settings))

        auditor = SecurityAuditor(tmp_path)
        findings = auditor._check_settings_secrets()
        assert len(findings) >= 1
        assert findings[0]["severity"] == "medium"
        assert "environment variables" in findings[0]["detail"]

    def test_clean_settings_no_findings(self, tmp_path):
        system_dir = tmp_path / "system"
        system_dir.mkdir()
        settings = {"llm": {"provider": "ollama", "model": "llama3"}}
        (system_dir / "settings.json").write_text(json.dumps(settings))

        auditor = SecurityAuditor(tmp_path)
        findings = auditor._check_settings_secrets()
        assert len(findings) == 0

    def test_no_settings_file(self, tmp_path):
        auditor = SecurityAuditor(tmp_path)
        findings = auditor._check_settings_secrets()
        assert len(findings) == 0
