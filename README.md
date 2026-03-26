# Capability OS

Sistema modular para ejecutar capabilities, sequences, browser automation e integraciones sobre un runtime determinista.

Este repositorio ya incluye:
- engine + tool runtime + state + observabilidad
- UI Workspace por intención (`/`)
- Control Center (`/control-center`)
- Browser Worker aislado por IPC
- Integration System (incluyendo WhatsApp Web Connector)

---

## 1. Requisitos

- Python 3.11+ (recomendado 3.12+)
- Node.js 18+
- npm 9+

Opcional (para browser tools/capabilities):
- `playwright` + Chromium

```powershell
pip install playwright
python -m playwright install chromium
```

---

## 2. Arranque rápido

### Backend API (UI Bridge)

Desde la raíz del proyecto:

```powershell
python -m system.core.ui_bridge.api_server
```

Por defecto queda en:
- `http://127.0.0.1:8000`

### Frontend

```powershell
cd system/frontend/app
npm install
npm run dev
```

Abrir:
- `http://127.0.0.1:5173`

---

## 3. Uso de la UI

## Workspace (`/`)
- Escribes intención
- Generas plan (`/plan`)
- Confirmas y ejecutas
- Ves timeline, estado, errores y outputs

## Control Center (`/control-center`)
- Configurar LLM
- Ver estado/restart del browser worker
- Gestionar integraciones (validate/enable/disable)
- Configurar paths de workspace
- Ver health general del sistema

---

## 4. Configuración central

Se guarda en:

- `workspace/system/settings.json`

Estructura:

```json
{
  "llm": {
    "provider": "ollama",
    "base_url": "http://127.0.0.1:11434",
    "model": "llama3.1:8b",
    "api_key": "",
    "timeout_ms": 30000
  },
  "browser": {
    "auto_start": true
  },
  "workspace": {
    "artifacts_path": "E:/AI/Capability OS/artifacts",
    "sequences_path": "E:/AI/Capability OS/sequences"
  }
}
```

Notas:
- `api_key` se enmascara en `GET /settings`.
- Si faltan campos, hay fallback por variables de entorno (compatibilidad).
- Los paths se validan dentro del workspace (aislamiento).

---

## 5. Endpoints principales

### Workspace/Execution
- `GET /capabilities`
- `GET /capabilities/{capability_id}`
- `POST /interpret`
- `POST /plan`
- `POST /execute`
- `GET /executions/{execution_id}`
- `GET /executions/{execution_id}/events`

### Integrations
- `GET /integrations`
- `GET /integrations/{id}`
- `POST /integrations/{id}/validate`
- `POST /integrations/{id}/enable`
- `POST /integrations/{id}/disable`

### Control Center
- `GET /status`
- `GET /health`
- `GET /settings`
- `POST /settings`
- `POST /llm/test`
- `POST /browser/restart`

---

## 6. Tests

### Backend

```powershell
python -m pytest -q tests/unit
```

### Frontend

```powershell
cd system/frontend/app
npm test -- --run
```

---

## 7. Troubleshooting rápido

## “LLM muestra ollama pero no cargué nada”
- Es el fallback por defecto cuando no hay config explícita.
- No implica conexión real.
- Usa `Test Connection` en Control Center (`POST /llm/test`).

## Error `playwright_not_installed`
- Instalar Playwright + Chromium:

```powershell
pip install playwright
python -m playwright install chromium
```

## Browser worker caído
- Desde Control Center usar `Restart Worker`
- O endpoint `POST /browser/restart`

---

## 8. Documentación por fase

En la raíz tienes:
- `README_PHASE1.md` ... `README_PHASE11.md`
- `README_BROWSER_HARDENING.md`
- `capability_os_master_spec.md` (fuente de verdad funcional)

