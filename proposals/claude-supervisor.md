# Claude Code como Supervisor del Sistema

## Visión

Claude Code actúa como un **meta-agente supervisor** de Capability OS que:
1. **Vigila** la salud y seguridad del sistema continuamente
2. **Diagnostica** errores cuando ocurren
3. **Repara** problemas creando skills/patches en tiempo real
4. **Evoluciona** el sistema creando nuevas capabilities cuando se necesitan

No es un chatbot — es un ingeniero de guardia que interviene automáticamente.

---

## Arquitectura

```
Capability OS (corriendo)
  │
  ├── Event Bus ──→ error, execution_complete, whatsapp_message, etc.
  │
  ├── Supervisor Daemon (Python, siempre corriendo)
  │   ├── Health Monitor (cada 60s)
  │   ├── Security Auditor (cada 5min)
  │   ├── Error Interceptor (en tiempo real via event_bus)
  │   └── Capability Gap Detector (cada 15min)
  │
  │   Cuando detecta un problema:
  │   └── Invoca Claude Code ──→ claude -p "prompt con contexto"
  │       │
  │       ├── Diagnóstico → explica qué pasó
  │       ├── Fix → genera código de corrección
  │       ├── Skill → crea nueva skill si falta una capability
  │       └── Report → guarda log para el usuario
  │
  └── Supervisor Dashboard (nueva sección en Control Center)
      ├── Estado del supervisor
      ├── Historial de intervenciones
      ├── Skills creadas automáticamente
      └── Configuración (qué puede hacer Claude)
```

---

## Módulos del Supervisor

### 1. Health Monitor
**Frecuencia**: cada 60 segundos
**Qué revisa**:
- `/health` endpoint responde
- LLM configurado y respondiendo
- Browser worker vivo (si configurado)
- WhatsApp conectado (si habilitado)
- Disco/memoria disponible
- Event bus funcionando (subscriber count > 0)

**Acción si falla**:
- Intenta restart automático del componente
- Si no puede: invoca Claude con contexto del error
- Claude analiza logs, sugiere fix

### 2. Security Auditor
**Frecuencia**: cada 5 minutos
**Qué revisa**:
- Archivos de settings no modificados por proceso externo
- Ningún proceso sospechoso corriendo
- API keys no expuestas en logs
- Requests a endpoints sensibles sin autorización
- Patrones de prompt injection en mensajes recibidos
- Integridad de security_rules.json

**Acción si detecta anomalía**:
- Log inmediato con severity (warning/critical)
- Si critical: pausa el componente afectado
- Invoca Claude para análisis forense
- Claude genera reporte + recomendación

### 3. Error Interceptor (tiempo real)
**Trigger**: event_bus emite "error" o "execution_complete" con status="error"
**Qué hace**:
1. Captura error completo (code, message, stack trace, inputs)
2. Clasifica severidad:
   - **Low**: tool timeout, file not found → log only
   - **Medium**: capability failed, LLM error → intentar auto-fix
   - **High**: security violation, system crash → invocar Claude inmediatamente
3. Para Medium/High:
   - Lee el archivo de código relacionado
   - Lee los últimos 20 logs
   - Construye prompt con todo el contexto
   - Invoca `claude -p` con el prompt
   - Claude responde con:
     - Diagnóstico (qué falló y por qué)
     - Fix (código corregido si es un bug)
     - Nueva skill (si falta una capability)

### 4. Capability Gap Detector
**Frecuencia**: cada 15 minutos
**Qué revisa**:
- Últimas 20 ejecuciones: cuántas fueron "unknown" o fallaron
- Mensajes del usuario que no se pudieron resolver
- Patrones: "el usuario pidió X pero no tenemos tool para Y"

**Acción**:
- Si detecta gap frecuente (3+ veces el mismo tipo):
  - Invoca Claude con: "Los usuarios piden frecuentemente [X]. No tenemos una capability para esto. Crea una skill."
  - Claude genera:
    - `SKILL.md` con instrucciones
    - Tool contract JSON
    - Implementación Python
    - Test básico
  - Lo guarda en `workspace/skills/auto-generated/`
  - Notifica al usuario en el dashboard

### 5. Skill Creator en Tiempo Real
**Trigger**: un tool falla o una capability no existe para lo que el usuario pide

**Flujo**:
```
1. Usuario: "convierte este PDF a texto"
2. AgentLoop: no tiene tool para PDF
3. AgentLoop retorna: "No tengo esa capacidad"
4. Supervisor detecta el gap
5. Supervisor invoca Claude:
   "El usuario pidió convertir PDF a texto pero no existe
    un tool para esto. Crea uno.

    Requisitos:
    - Tool contract JSON en system/tools/contracts/v1/
    - Handler Python en system/tools/implementations/
    - Registrar en tool_runtime

    Contexto del sistema: [architecture summary]
    Tools existentes como referencia: [filesystem_read_file contract]"

6. Claude genera:
   - pdf_to_text.json (contract)
   - pdf_tools.py (implementation)
   - Registration code

7. Supervisor:
   - Guarda los archivos
   - Hot-reload el tool en el runtime (sin restart)
   - Notifica al usuario: "Creé una nueva capability: pdf_to_text"

8. Usuario puede reintentar y funciona
```

---

## Implementación Técnica

### Nuevo módulo: `system/core/supervisor/`

```
supervisor/
├── __init__.py
├── supervisor_daemon.py    # Main loop, orchestrates all monitors
├── health_monitor.py       # Health checks
├── security_auditor.py     # Security scanning
├── error_interceptor.py    # Real-time error handling
├── gap_detector.py         # Capability gap detection
├── skill_creator.py        # Auto-generate skills via Claude
├── claude_bridge.py        # Interface to invoke Claude Code CLI
└── supervisor_log.py       # Structured logging for all interventions
```

### claude_bridge.py
```python
class ClaudeBridge:
    """Invokes Claude Code CLI for analysis and code generation."""

    def analyze(self, context: str) -> str:
        """Ask Claude to analyze a problem. Returns text analysis."""
        result = subprocess.run(
            ["claude", "-p", context],
            capture_output=True, text=True, timeout=300,
            cwd=PROJECT_ROOT,
        )
        return result.stdout

    def generate_skill(self, description: str, reference_files: list[str]) -> dict:
        """Ask Claude to generate a complete skill package."""
        prompt = f"""Generate a Capability OS skill for: {description}

        Return a JSON with:
        - contract: the tool contract JSON
        - implementation: Python code for the handler
        - registration: code to register in tool_runtime

        Reference files for format:
        {self._read_references(reference_files)}
        """
        response = self.analyze(prompt)
        return self._parse_skill_response(response)

    def fix_code(self, error: str, file_path: str, file_content: str) -> str:
        """Ask Claude to fix a bug. Returns corrected code."""
        prompt = f"""Fix this error in Capability OS:

        Error: {error}
        File: {file_path}

        Current code:
        {file_content}

        Return ONLY the corrected code, nothing else.
        """
        return self.analyze(prompt)
```

### supervisor_daemon.py
```python
class SupervisorDaemon:
    """Main supervisor loop — runs in background thread."""

    def __init__(self, event_bus, health_provider, claude_bridge):
        self._monitors = [
            HealthMonitor(health_provider, interval=60),
            SecurityAuditor(interval=300),
            GapDetector(interval=900),
        ]
        self._error_interceptor = ErrorInterceptor(claude_bridge)
        self._skill_creator = SkillCreator(claude_bridge)

        # Subscribe to error events
        event_bus.subscribe(self._on_event)

    def start(self):
        """Start all monitors in background threads."""
        for monitor in self._monitors:
            monitor.start()
        self._running = True

    def _on_event(self, event):
        """React to system events in real-time."""
        if event["type"] == "error":
            self._error_interceptor.handle(event)
        elif event["type"] == "execution_complete":
            if event["data"].get("status") == "error":
                self._error_interceptor.handle(event)
```

### Hot-reload de skills
```python
class SkillCreator:
    """Creates and hot-loads new skills without system restart."""

    def create_and_load(self, description, tool_runtime, tool_registry):
        # 1. Claude generates the skill
        skill = self._claude.generate_skill(description, REFERENCE_FILES)

        # 2. Save contract to disk
        contract_path = TOOLS_DIR / f"{skill['id']}.json"
        contract_path.write_text(json.dumps(skill['contract']))

        # 3. Save implementation
        impl_path = IMPL_DIR / f"{skill['id']}_auto.py"
        impl_path.write_text(skill['implementation'])

        # 4. Hot-load into running system
        tool_registry.register(skill['contract'])

        # 5. Dynamic import and register handler
        module = importlib.import_module(f"system.tools.implementations.{skill['id']}_auto")
        handler = getattr(module, skill['handler_name'])
        tool_runtime.register_handler(skill['id'], handler)

        # 6. Log and notify
        self._log_creation(skill)
        event_bus.emit("skill_created", {"skill_id": skill['id'], "auto": True})
```

---

## Configuración del Supervisor

```json
{
  "supervisor": {
    "enabled": true,
    "claude_path": "claude",
    "health_interval_s": 60,
    "security_interval_s": 300,
    "gap_detection_interval_s": 900,
    "auto_fix_enabled": true,
    "auto_skill_creation": true,
    "max_claude_invocations_per_hour": 10,
    "severity_threshold": "medium",
    "notify_user": true,
    "log_path": "workspace/supervisor/",
    "permissions": {
      "can_modify_code": true,
      "can_create_skills": true,
      "can_restart_components": true,
      "can_modify_security_rules": false,
      "can_access_credentials": false
    }
  }
}
```

---

## Dashboard del Supervisor (Control Center)

Nueva sección "Supervisor" con:

### Panel de Estado
- Supervisor: Running/Stopped
- Health: OK / Warning / Critical
- Security: Clean / Alert
- Last check: timestamp
- Claude invocations: N/hour

### Historial de Intervenciones
```
[14:23] 🔍 Health check: LLM timeout detected
[14:23] 🔧 Auto-fix: restarted LLM client with circuit breaker reset
[14:25] ✅ Health restored

[15:01] ⚠️ Error intercepted: filesystem_write_file failed (permission denied)
[15:01] 🤖 Claude analyzed: path outside workspace, suggested adding as workspace
[15:01] 📋 Report saved to supervisor/2026-03-30_15-01.md

[16:30] 💡 Gap detected: users requested "convert PDF" 4 times, no capability exists
[16:30] 🤖 Claude generating skill: pdf_to_text
[16:31] ✅ Skill created and hot-loaded: pdf_to_text
```

### Skills Auto-Generadas
Lista de skills que Claude creó automáticamente, con:
- Nombre, descripción, fecha
- Estado: active / disabled
- Botones: View code, Disable, Delete

### Configuración
- Toggle: auto-fix, auto-skill-creation
- Severity threshold slider
- Max invocations/hour
- Permissions checkboxes

---

## Niveles de Intervención de Claude

```
Nivel 0: OBSERVAR
  Solo loguea, no actúa.
  Para: health checks normales, low severity errors.

Nivel 1: DIAGNOSTICAR
  Analiza el problema, genera reporte, notifica al usuario.
  Para: medium severity, capability gaps recurrentes.

Nivel 2: REPARAR
  Modifica código, crea skills, reinicia componentes.
  Para: high severity, errores que bloquean al usuario.
  Requiere: auto_fix_enabled = true

Nivel 3: EVOLUCIONAR
  Crea nuevas capabilities, mejora prompts, optimiza configuración.
  Para: gaps detectados, patrones de uso, optimizaciones.
  Requiere: auto_skill_creation = true
```

---

## Seguridad del Supervisor

El supervisor tiene su propio set de permisos:
- **Puede**: leer logs, leer código, crear archivos en workspace/skills/
- **Puede** (si configurado): modificar tools, reiniciar componentes
- **NUNCA puede**: modificar security_rules.json, acceder a API keys, eliminar archivos del sistema
- **Rate limited**: máximo N invocaciones de Claude por hora
- **Auditable**: cada acción se loguea con timestamp, contexto, y resultado

---

## Flujo Completo de Auto-Healing

```
1. Usuario: "descarga esta imagen y conviértela a PNG"
2. Agent: llama network_http_get → obtiene imagen
3. Agent: intenta filesystem_write_file → OK
4. Agent: necesita convertir formato → no tiene tool
5. Agent responde: "No tengo la capacidad de convertir imágenes"

6. Supervisor detecta gap (agent dijo "no tengo capacidad")
7. Supervisor invoca Claude:
   "El agente no pudo convertir una imagen a PNG.
    Crea un tool que convierta imágenes entre formatos.
    Usa Pillow (PIL) si disponible."

8. Claude genera:
   - image_convert.json (contract)
   - image_tools.py (handler usando PIL)

9. Supervisor hot-loads el tool
10. Supervisor notifica: "Nueva skill: image_convert"

11. Próxima vez que el usuario pida lo mismo:
    Agent tiene el tool y lo ejecuta directamente ✓
```

---

## Estimación de Implementación

| Componente | Esfuerzo | Prioridad |
|-----------|----------|-----------|
| claude_bridge.py | Bajo | 1 |
| error_interceptor.py | Medio | 1 |
| health_monitor.py | Bajo | 2 |
| supervisor_daemon.py | Medio | 2 |
| skill_creator.py + hot-reload | Alto | 3 |
| security_auditor.py | Medio | 3 |
| gap_detector.py | Medio | 4 |
| Dashboard UI | Medio | 4 |

Total estimado: 4 fases de implementación.
