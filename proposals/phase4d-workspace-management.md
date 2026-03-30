# Fase D: Workspace Management — Supervisor interviene en workspaces

## Contexto
El Supervisor puede crear skills y agentes pero no gestiona los workspaces activamente. Los usuarios necesitan que el sistema analice sus proyectos, detecte problemas, sugiera estructura, genere documentación y limpie archivos innecesarios.

## Módulos

### 1. Workspace Analyzer

Análisis completo de un workspace:

```python
analyze(workspace_id) → {
  "total_files": 142,
  "total_size": "23.4 MB",
  "languages": {"python": 45, "javascript": 30, "json": 20, "markdown": 10},
  "issues": [
    {"type": "hardcoded_key", "file": "config.py", "line": 12, "severity": "high",
     "detail": "API key found: sk-..."},
    {"type": "no_gitignore", "severity": "medium",
     "detail": "Project has no .gitignore file"},
    {"type": "unused_file", "file": "old_backup.py", "severity": "low",
     "detail": "File not imported or referenced anywhere"},
    {"type": "large_file", "file": "data.csv", "size": "15MB", "severity": "low",
     "detail": "Large file should be in .gitignore"},
    {"type": "no_readme", "severity": "medium"},
    {"type": "no_tests", "severity": "low"},
    {"type": "duplicate_file", "files": ["utils.py", "helpers.py"], "severity": "low"},
  ],
  "suggestions": [
    "Create .gitignore for Python project",
    "Move API key from config.py to .env",
    "Delete old_backup.py (unused)",
    "Add data.csv to .gitignore",
    "Generate README.md",
  ],
  "structure": {
    "type": "python_project",
    "has_git": true,
    "has_tests": false,
    "has_docs": false,
    "entry_points": ["main.py", "app.py"],
  }
}
```

### 2. Issue Detectors

Cada detector escanea un tipo de problema:

| Detector | Busca | Severity |
|----------|-------|----------|
| `HardcodedKeyDetector` | API keys, tokens, passwords en código | High |
| `MissingConfigDetector` | Sin .gitignore, .env, README | Medium |
| `UnusedFileDetector` | Archivos no importados/referenciados | Low |
| `LargeFileDetector` | Archivos > 1MB que no deberían estar en git | Low |
| `DuplicateDetector` | Archivos con contenido idéntico o muy similar | Low |
| `SecurityPatternDetector` | eval(), exec(), os.system() en código | Medium |
| `DeprecatedImportDetector` | Imports de librerías deprecadas | Low |
| `TODODetector` | TODO, FIXME, HACK, XXX en código | Info |

### 3. Auto-Structure

Cuando se crea un workspace nuevo, sugiere estructura según el tipo de proyecto:

```
"python_web" → {
  "directories": ["src/", "tests/", "static/", "templates/"],
  "files": [".gitignore", "requirements.txt", "README.md", ".env.example"],
  "gitignore_content": "__pycache__/\n*.pyc\n.env\nvenv/\n"
}

"react" → {
  "directories": ["src/", "public/", "tests/"],
  "files": [".gitignore", "package.json", "README.md"],
}

"data_science" → {
  "directories": ["data/", "notebooks/", "models/", "reports/"],
  "files": [".gitignore", "requirements.txt", "README.md"],
}
```

### 4. Auto-Documentation via Claude

El Supervisor puede generar:
- **README.md** — basado en la estructura y código del proyecto
- **Docstrings** — para funciones sin documentar
- **CHANGELOG** — basado en git log
- **API docs** — para endpoints HTTP detectados

### 5. Auto-Clean

Identifica y elimina (con confirmación):
- `__pycache__/` directories
- `.pyc` files
- `node_modules/` duplicados
- Archivos temporales (.tmp, .log viejos, .bak)
- Archivos vacíos

### 6. Proactive Workspace Monitoring

El Supervisor revisa periódicamente los workspaces activos:
- Cada vez que se abre un workspace → análisis rápido
- Si detecta issue high → notifica inmediatamente
- Si detecta 5+ issues → sugiere auto-clean

## Implementación

### Archivos a crear

**`system/core/supervisor/workspace_monitor.py`**
```python
class WorkspaceMonitor:
    def analyze(self, workspace_path: str) -> dict
    def detect_issues(self, workspace_path: str) -> list[dict]
    def suggest_structure(self, project_type: str) -> dict
    def auto_clean(self, workspace_path: str, dry_run: bool = True) -> dict
    def generate_readme(self, workspace_path: str, claude_bridge) -> str
```

**Issue detectors** (dentro de workspace_monitor.py):
- `_detect_hardcoded_keys(path)` — regex scan de archivos Python/JS
- `_detect_missing_config(path)` — check .gitignore, README, .env
- `_detect_unused_files(path)` — analiza imports y referencias
- `_detect_large_files(path)` — archivos > 1MB
- `_detect_todos(path)` — busca TODO/FIXME

### Archivos a modificar

**`handlers/supervisor_handlers.py`** o nuevo **`handlers/workspace_analysis_handlers.py`**:
- `GET /workspaces/{id}/analyze` → análisis completo
- `GET /workspaces/{id}/issues` → solo issues
- `POST /workspaces/{id}/auto-clean` → limpiar (dry_run=true para preview)
- `POST /workspaces/{id}/generate-readme` → Claude genera README
- `POST /workspaces/{id}/suggest-structure` → sugiere estructura

**`api_server.py`**: registrar rutas

**`ControlCenter.jsx`**: sección en Workspaces con:
- Botón "Analyze" por workspace
- Vista de issues con severidad y color
- Botón "Auto-Clean" con preview de qué se eliminará
- Botón "Generate README" que invoca Claude

**`docker-entrypoint.py`**: no necesita cambios (ya tiene /workspaces en prefixes)

## Verificación
1. GET /workspaces/{id}/analyze → retorna issues y suggestions
2. Issue "hardcoded_key" detecta API keys en código
3. Issue "no_gitignore" detecta falta de .gitignore
4. Auto-clean dry_run muestra qué se eliminaría
5. Auto-clean real elimina __pycache__ y .pyc
6. Generate README crea un README basado en el proyecto
7. Suggest structure propone carpetas según tipo de proyecto
