"""Workspace Monitor — analyzes workspaces, detects issues, auto-cleans.

Scans workspace directories for:
- Hardcoded API keys/secrets
- Missing config files (.gitignore, README, .env)
- Unused/large/duplicate files
- Security patterns (eval, exec)
- TODOs and FIXMEs
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

# Patterns for detecting hardcoded secrets
SECRET_PATTERNS = [
    re.compile(r'["\']sk-[a-zA-Z0-9]{20,}["\']'),
    re.compile(r'["\']gsk_[a-zA-Z0-9]{20,}["\']'),
    re.compile(r'["\']sk-ant-[a-zA-Z0-9]{20,}["\']'),
    re.compile(r'["\']AIza[a-zA-Z0-9_-]{35}["\']'),
    re.compile(r'["\']ghp_[a-zA-Z0-9]{36}["\']'),
    re.compile(r'api_key\s*=\s*["\'][^"\']{15,}["\']', re.I),
    re.compile(r'password\s*=\s*["\'][^"\']{8,}["\']', re.I),
]

SECURITY_PATTERNS = [
    re.compile(r'\beval\s*\('),
    re.compile(r'\bexec\s*\('),
    re.compile(r'\b__import__\s*\('),
    re.compile(r'\bos\.system\s*\('),
]

SKIP_DIRS = {"node_modules", "__pycache__", ".git", "dist", "venv", ".venv", "build", "env", ".tox", ".mypy_cache"}
CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".rb", ".php", ".sh"}
ALL_EXTS = CODE_EXTS | {".json", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".md", ".txt", ".html", ".css"}

PROJECT_TEMPLATES = {
    "python": {
        "directories": ["src/", "tests/", "docs/"],
        "files": {".gitignore": "__pycache__/\n*.pyc\n.env\nvenv/\ndist/\n*.egg-info/\n", "requirements.txt": "", "README.md": "# Project\n"},
    },
    "python_web": {
        "directories": ["src/", "tests/", "static/", "templates/"],
        "files": {".gitignore": "__pycache__/\n*.pyc\n.env\nvenv/\n", "requirements.txt": "", "README.md": "# Project\n", ".env.example": "API_KEY=\n"},
    },
    "react": {
        "directories": ["src/", "public/", "tests/"],
        "files": {".gitignore": "node_modules/\ndist/\n.env\n", "package.json": "{}", "README.md": "# Project\n"},
    },
    "data_science": {
        "directories": ["data/", "notebooks/", "models/", "reports/", "src/"],
        "files": {".gitignore": "__pycache__/\n*.pyc\n.env\ndata/\nmodels/\n*.pkl\n", "requirements.txt": "", "README.md": "# Project\n"},
    },
}


class WorkspaceMonitor:
    """Analyzes and manages workspace health."""

    def analyze(self, workspace_path: str | Path) -> dict[str, Any]:
        """Full workspace analysis."""
        root = Path(workspace_path)
        if not root.exists():
            return {"error": f"Path not found: {workspace_path}"}

        files_info = self._scan_files(root)
        issues = self._detect_all_issues(root, files_info)
        languages = self._detect_languages(files_info)
        structure = self._detect_structure(root)

        total_size = sum(f.get("size", 0) for f in files_info)
        suggestions = self._generate_suggestions(issues, structure)

        return {
            "total_files": len(files_info),
            "total_size": self._format_size(total_size),
            "total_size_bytes": total_size,
            "languages": languages,
            "issues": issues,
            "suggestions": suggestions,
            "structure": structure,
        }

    def detect_issues(self, workspace_path: str | Path) -> list[dict[str, Any]]:
        """Just the issues."""
        root = Path(workspace_path)
        files_info = self._scan_files(root)
        return self._detect_all_issues(root, files_info)

    def suggest_structure(self, project_type: str) -> dict[str, Any]:
        """Suggest project structure based on type."""
        template = PROJECT_TEMPLATES.get(project_type, PROJECT_TEMPLATES.get("python", {}))
        return {"type": project_type, **template}

    def auto_clean(self, workspace_path: str | Path, dry_run: bool = True) -> dict[str, Any]:
        """Clean unnecessary files. dry_run=True shows what would be deleted."""
        root = Path(workspace_path)
        to_delete: list[dict[str, Any]] = []
        space_saved = 0

        for item in root.rglob("*"):
            rel = str(item.relative_to(root))

            # __pycache__ directories
            if item.is_dir() and item.name == "__pycache__":
                size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                to_delete.append({"path": rel, "type": "directory", "reason": "Python cache", "size": size})
                space_saved += size
                continue

            if not item.is_file():
                continue

            # .pyc files
            if item.suffix == ".pyc":
                to_delete.append({"path": rel, "type": "file", "reason": "Compiled Python", "size": item.stat().st_size})
                space_saved += item.stat().st_size

            # .tmp, .bak files
            if item.suffix in (".tmp", ".bak", ".swp", ".swo"):
                to_delete.append({"path": rel, "type": "file", "reason": "Temporary file", "size": item.stat().st_size})
                space_saved += item.stat().st_size

            # Empty files (except __init__.py)
            if item.stat().st_size == 0 and item.name != "__init__.py" and item.suffix in CODE_EXTS:
                to_delete.append({"path": rel, "type": "file", "reason": "Empty file", "size": 0})

        if not dry_run:
            for item in to_delete:
                target = root / item["path"]
                try:
                    if item["type"] == "directory":
                        shutil.rmtree(str(target))
                    else:
                        target.unlink()
                except Exception:
                    pass

        return {
            "dry_run": dry_run,
            "items": to_delete[:50],
            "total_items": len(to_delete),
            "space_saved": self._format_size(space_saved),
            "space_saved_bytes": space_saved,
        }

    def generate_readme_prompt(self, workspace_path: str | Path) -> str:
        """Generate a prompt for Claude to create a README."""
        root = Path(workspace_path)
        structure = self._detect_structure(root)
        files = self._scan_files(root)
        languages = self._detect_languages(files)

        # Read entry points for context
        entry_content = ""
        for ep in structure.get("entry_points", []):
            ep_path = root / ep
            if ep_path.exists():
                entry_content += f"\n--- {ep} ---\n{ep_path.read_text(encoding='utf-8', errors='replace')[:500]}\n"

        return (
            f"Generate a README.md for this project.\n\n"
            f"Structure: {structure.get('type', 'unknown')} project\n"
            f"Files: {len(files)} total\n"
            f"Languages: {languages}\n"
            f"Has git: {structure.get('has_git', False)}\n"
            f"Has tests: {structure.get('has_tests', False)}\n"
            f"Entry points: {structure.get('entry_points', [])}\n"
            f"\nKey files:\n{entry_content}\n\n"
            f"Write a concise, professional README with: title, description, setup, usage."
        )

    # ── Internal ──

    def _scan_files(self, root: Path) -> list[dict[str, Any]]:
        files = []
        for item in root.rglob("*"):
            if any(p in item.parts for p in SKIP_DIRS):
                continue
            if item.is_file() and item.suffix in ALL_EXTS:
                try:
                    files.append({"path": str(item.relative_to(root)), "ext": item.suffix, "size": item.stat().st_size})
                except Exception:
                    pass
        return files

    def _detect_all_issues(self, root: Path, files: list[dict]) -> list[dict[str, Any]]:
        issues = []
        issues.extend(self._detect_hardcoded_keys(root, files))
        issues.extend(self._detect_missing_config(root))
        issues.extend(self._detect_large_files(files))
        issues.extend(self._detect_security_patterns(root, files))
        issues.extend(self._detect_todos(root, files))
        return issues

    def _detect_hardcoded_keys(self, root: Path, files: list[dict]) -> list[dict]:
        issues = []
        for f in files[:100]:
            if Path(f["path"]).suffix not in CODE_EXTS:
                continue
            try:
                content = (root / f["path"]).read_text(encoding="utf-8", errors="replace")[:10000]
                for pattern in SECRET_PATTERNS:
                    matches = pattern.findall(content)
                    if matches:
                        issues.append({"type": "hardcoded_key", "file": f["path"], "severity": "high",
                                       "detail": f"Potential secret found ({len(matches)} match{'es' if len(matches)>1 else ''})"})
                        break
            except Exception:
                pass
        return issues

    def _detect_missing_config(self, root: Path) -> list[dict]:
        issues = []
        if not (root / ".gitignore").exists():
            issues.append({"type": "no_gitignore", "severity": "medium", "detail": "Project has no .gitignore"})
        if not (root / "README.md").exists() and not (root / "readme.md").exists():
            issues.append({"type": "no_readme", "severity": "medium", "detail": "Project has no README"})
        return issues

    def _detect_large_files(self, files: list[dict]) -> list[dict]:
        return [{"type": "large_file", "file": f["path"], "severity": "low",
                 "detail": f"Large file: {self._format_size(f['size'])}"}
                for f in files if f["size"] > 1_000_000]

    def _detect_security_patterns(self, root: Path, files: list[dict]) -> list[dict]:
        issues = []
        for f in files[:50]:
            if Path(f["path"]).suffix not in {".py", ".js"}:
                continue
            try:
                content = (root / f["path"]).read_text(encoding="utf-8", errors="replace")[:5000]
                for pattern in SECURITY_PATTERNS:
                    if pattern.search(content):
                        issues.append({"type": "security_pattern", "file": f["path"], "severity": "medium",
                                       "detail": f"Dangerous pattern: {pattern.pattern}"})
                        break
            except Exception:
                pass
        return issues

    def _detect_todos(self, root: Path, files: list[dict]) -> list[dict]:
        issues = []
        todo_re = re.compile(r'#\s*(TODO|FIXME|HACK|XXX)\b', re.I)
        count = 0
        for f in files[:80]:
            if Path(f["path"]).suffix not in CODE_EXTS:
                continue
            try:
                content = (root / f["path"]).read_text(encoding="utf-8", errors="replace")[:5000]
                matches = todo_re.findall(content)
                count += len(matches)
            except Exception:
                pass
        if count > 0:
            issues.append({"type": "todos", "severity": "info", "detail": f"{count} TODO/FIXME comments found"})
        return issues

    def _detect_languages(self, files: list[dict]) -> dict[str, int]:
        langs: dict[str, int] = {}
        ext_map = {".py": "Python", ".js": "JavaScript", ".jsx": "React", ".ts": "TypeScript",
                   ".tsx": "React/TS", ".json": "JSON", ".md": "Markdown", ".html": "HTML",
                   ".css": "CSS", ".yml": "YAML", ".yaml": "YAML", ".sh": "Shell"}
        for f in files:
            lang = ext_map.get(f["ext"], "Other")
            langs[lang] = langs.get(lang, 0) + 1
        return dict(sorted(langs.items(), key=lambda x: -x[1]))

    def _detect_structure(self, root: Path) -> dict[str, Any]:
        has_git = (root / ".git").exists()
        has_tests = any((root / d).exists() for d in ["tests", "test", "__tests__"])
        has_docs = any((root / d).exists() for d in ["docs", "documentation"])
        entry_points = [f.name for f in root.iterdir() if f.is_file() and f.name in ("main.py", "app.py", "index.js", "index.ts", "server.py", "manage.py")]
        # Detect project type
        ptype = "unknown"
        if (root / "requirements.txt").exists() or (root / "setup.py").exists():
            ptype = "python"
        if (root / "package.json").exists():
            ptype = "node" if ptype == "unknown" else "fullstack"
        if any(f.suffix == ".ipynb" for f in root.rglob("*.ipynb")):
            ptype = "data_science"
        return {"type": ptype, "has_git": has_git, "has_tests": has_tests, "has_docs": has_docs, "entry_points": entry_points}

    def _generate_suggestions(self, issues: list[dict], structure: dict) -> list[str]:
        suggestions = []
        types = {i["type"] for i in issues}
        if "no_gitignore" in types:
            suggestions.append(f"Create .gitignore for {structure.get('type', 'unknown')} project")
        if "no_readme" in types:
            suggestions.append("Generate README.md with project documentation")
        if "hardcoded_key" in types:
            suggestions.append("Move hardcoded secrets to .env file")
        if "large_file" in types:
            suggestions.append("Add large files to .gitignore")
        if not structure.get("has_tests"):
            suggestions.append("Add tests directory")
        return suggestions

    @staticmethod
    def _format_size(bytes: int) -> str:
        if bytes < 1024:
            return f"{bytes}B"
        if bytes < 1024 * 1024:
            return f"{bytes/1024:.1f}KB"
        return f"{bytes/(1024*1024):.1f}MB"
