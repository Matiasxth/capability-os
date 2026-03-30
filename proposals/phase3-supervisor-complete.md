# Plan Maestro: Supervisor Claude + Hot-Reload + Proactividad + Function Calling Nativo

## Visión General

Estas 4 features se integran en un solo sistema: **Claude Code como cerebro operativo de CapOS** que no solo responde, sino que vigila, repara, evoluciona, y trabaja proactivamente — todo sin reiniciar el servidor.

```
┌─────────────────────────────────────────────────────────┐
│                   SUPERVISOR CLAUDE                      │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐│
│  │ Health   │  │ Security │  │ Error    │  │ Gap     ││
│  │ Monitor  │  │ Auditor  │  │ Intercept│  │ Detector││
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘│
│       │              │              │              │     │
│       └──────────────┴──────┬───────┴──────────────┘     │
│                             │                            │
│                    ┌────────▼────────┐                   │
│                    │  Claude Bridge  │                   │
│                    │  (claude -p)    │                   │
│                    └────────┬────────┘                   │
│                             │                            │
│          ┌──────────────────┼──────────────────┐        │
│          │                  │                  │        │
│  ┌───────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐ │
│  │ Skill Creator│  │ Code Fixer   │  │ Config      │ │
│  │ + Hot Reload │  │ (patches)    │  │ Optimizer   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │              PROACTIVE SCHEDULER                  │   │
│  │  Queue → Timer → Execute → Report → Learn        │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │          NATIVE FUNCTION CALLING                  │   │
│  │  OpenAI/Groq → native tools API (no text parse)  │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## PARTE 1: SUPERVISOR CLAUDE

### 1.1 Módulo Supervisor (`system/core/supervisor/`)

```
supervisor/
├── __init__.py
├── supervisor_daemon.py      # Orquestador principal (daemon thread)
├── health_monitor.py         # Vigila salud del sistema cada 60s
├── security_auditor.py       # Escanea seguridad cada 5min
├── error_interceptor.py      # Captura errores en tiempo real via event_bus
├── gap_detector.py           # Detecta capabilities faltantes cada 15min
├── claude_bridge.py          # Interfaz para invocar Claude Code CLI
├── skill_creator.py          # Genera skills completas + hot-reload
├── code_fixer.py             # Aplica patches de código en caliente
├── config_optimizer.py       # Ajusta configuración basado en métricas
├── supervisor_log.py         # Log estructurado de intervenciones
└── supervisor_channel.py     # Canal de comunicación con el usuario
```

### 1.2 Claude Bridge

```python
class ClaudeBridge:
    """Interfaz para invocar Claude Code CLI desde el sistema."""

    def __init__(self, project_root: Path, max_invocations_per_hour: int = 10):
        self._root = project_root
        self._rate_limiter = SlidingWindowLimiter(max_invocations_per_hour)
        self._log = []

    def analyze(self, context: str, max_tokens: int = 2000) -> str:
        """Pide a Claude que analice un problema. Retorna texto."""
        if not self._rate_limiter.allow():
            return "[Rate limited — esperando]"
        result = subprocess.run(
            ["claude", "-p", context],
            cwd=str(self._root),
            capture_output=True, text=True, timeout=300,
        )
        self._log.append({"timestamp": now(), "type": "analyze", "context": context[:200], "response_len": len(result.stdout)})
        return result.stdout

    def generate_code(self, spec: str, reference_files: list[str]) -> str:
        """Pide a Claude que genere código. Retorna código."""
        refs = "\n".join(f"--- {f} ---\n{Path(f).read_text()[:1000]}" for f in reference_files if Path(f).exists())
        prompt = f"{spec}\n\nReference code:\n{refs}\n\nReturn ONLY the code, no explanation."
        return self.analyze(prompt)

    def fix_error(self, error: str, file_path: str) -> dict:
        """Pide a Claude que corrija un error. Retorna {fixed_code, explanation}."""
        content = Path(file_path).read_text()[:3000] if Path(file_path).exists() else ""
        prompt = f"Fix this error:\n{error}\n\nFile: {file_path}\n{content}\n\nReturn JSON: {{\"fixed_code\": \"...\", \"explanation\": \"...\"}}"
        response = self.analyze(prompt)
        try:
            import json, re
            match = re.search(r'\{[\s\S]*\}', response)
            return json.loads(match.group(0)) if match else {"explanation": response}
        except:
            return {"explanation": response}

    def design_skill(self, description: str) -> dict:
        """Pide a Claude que diseñe una skill completa."""
        prompt = f"""Design a Capability OS tool for: {description}

Return JSON:
{{
  "id": "tool_id",
  "name": "Tool Name",
  "description": "What it does",
  "contract": {{...tool contract JSON...}},
  "implementation": "...Python handler code...",
  "dependencies": ["pip_package1"]
}}

Reference: tools in system/tools/contracts/v1/ and system/tools/implementations/"""
        response = self.analyze(prompt, max_tokens=4000)
        try:
            import json, re
            match = re.search(r'\{[\s\S]*\}', response)
            return json.loads(match.group(0)) if match else {}
        except:
            return {}

    @property
    def invocation_count(self) -> int:
        return len(self._log)

    @property
    def recent_log(self) -> list[dict]:
        return self._log[-20:]
```

### 1.3 Health Monitor

```python
class HealthMonitor:
    """Verifica salud del sistema periódicamente."""

    interval_s = 60

    checks = [
        ("api_health", lambda: requests.get("http://localhost:8000/health", timeout=5).ok),
        ("llm_available", lambda svc: svc.intent_interpreter.llm_client.adapter is not None),
        ("event_bus_alive", lambda: event_bus.subscriber_count > 0),
        ("workspace_writable", lambda svc: Path(svc.workspace_root).exists()),
        ("disk_space", lambda: shutil.disk_usage("/").free > 100_000_000),  # 100MB min
    ]

    def run_checks(self) -> list[dict]:
        results = []
        for name, check in self.checks:
            try:
                ok = check() if not callable(check) else check(self._service)
                results.append({"check": name, "ok": ok})
            except Exception as exc:
                results.append({"check": name, "ok": False, "error": str(exc)})
        return results

    def on_failure(self, failed_checks: list[dict]):
        # 1. Intentar auto-fix (restart componente)
        # 2. Si no puede: invocar Claude Bridge
        # 3. Notificar al usuario
```

### 1.4 Security Auditor

```python
class SecurityAuditor:
    """Escanea seguridad periódicamente."""

    interval_s = 300

    def audit(self) -> list[dict]:
        findings = []

        # 1. Verificar que settings.json no tenga API keys expuestas en logs
        findings += self._check_exposed_keys()

        # 2. Verificar integridad de security_rules.json
        findings += self._check_security_rules()

        # 3. Verificar que no haya procesos sospechosos
        findings += self._check_processes()

        # 4. Verificar que los puertos solo sirven lo esperado
        findings += self._check_ports()

        # 5. Escanear mensajes recientes por prompt injection
        findings += self._check_injection_attempts()

        return findings
```

### 1.5 Error Interceptor

```python
class ErrorInterceptor:
    """Captura errores en tiempo real y decide acción."""

    severity_levels = {
        "file_not_found": "low",
        "timeout": "low",
        "permission_denied": "medium",
        "capability_not_found": "medium",
        "tool_execution_error": "medium",
        "security_violation": "high",
        "system_crash": "critical",
        "auth_error": "high",
    }

    def handle(self, event: dict):
        error_code = event.get("data", {}).get("error_code", "unknown")
        severity = self.severity_levels.get(error_code, "medium")

        if severity == "low":
            self._log_only(event)
        elif severity == "medium":
            self._diagnose_and_suggest(event)
        elif severity in ("high", "critical"):
            self._invoke_claude_immediately(event)

    def _invoke_claude_immediately(self, event):
        # Lee archivos relevantes, construye contexto
        # Invoca Claude Bridge con el error completo
        # Aplica fix si es posible
        # Notifica al usuario
```

### 1.6 Gap Detector

```python
class GapDetector:
    """Detecta capabilities que los usuarios piden pero no existen."""

    interval_s = 900

    def detect(self) -> list[dict]:
        # Lee últimas 50 ejecuciones del historial
        # Filtra las que retornaron "unknown" o "capability_not_found"
        # Agrupa por patrón (qué pidió el usuario)
        # Si un patrón se repite 3+ veces → es un gap

        gaps = []
        for pattern, count in frequent_failures.items():
            if count >= 3:
                gaps.append({
                    "pattern": pattern,
                    "count": count,
                    "suggested_capability": self._suggest(pattern),
                })
        return gaps

    def auto_create(self, gap: dict):
        """Invoca Claude para crear la skill que falta."""
        skill = self._claude.design_skill(gap["pattern"])
        if skill:
            self._skill_creator.create_and_hot_load(skill)
            self._notify(f"Nueva skill creada: {skill['name']}")
```

### 1.7 Supervisor Channel (comunicación con el usuario)

```python
class SupervisorChannel:
    """Envía mensajes al usuario desde el supervisor."""

    def notify(self, message: str, severity: str = "info"):
        # 1. Emit event_bus → aparece en la UI como toast/notification
        event_bus.emit("supervisor_message", {
            "message": message,
            "severity": severity,
            "timestamp": now(),
        })

        # 2. Si WhatsApp conectado y severity >= "warning":
        #    enviar mensaje por WhatsApp
        if severity in ("warning", "critical") and self._whatsapp_connected:
            self._whatsapp_manager.send_message(self._owner_phone, f"🛡️ CapOS: {message}")

        # 3. Guardar en log del supervisor
        self._log.append({"message": message, "severity": severity, "timestamp": now()})
```

---

## PARTE 2: HOT-RELOAD DE SKILLS

### 2.1 Skill Creator con Hot-Reload

```python
class SkillCreator:
    """Crea skills y las carga en el sistema sin reiniciar."""

    def create_and_hot_load(self, skill_spec: dict) -> dict:
        tool_id = skill_spec["id"]

        # 1. Guardar contrato JSON
        contract_path = TOOLS_DIR / f"{tool_id}.json"
        contract_path.write_text(json.dumps(skill_spec["contract"], indent=2))

        # 2. Guardar implementación Python
        impl_path = IMPL_DIR / f"{tool_id}_auto.py"
        impl_path.write_text(skill_spec["implementation"])

        # 3. Instalar dependencias si necesita
        for dep in skill_spec.get("dependencies", []):
            subprocess.run([sys.executable, "-m", "pip", "install", dep], timeout=60)

        # 4. Hot-load: registrar en registries en caliente
        self._tool_registry.register(skill_spec["contract"])

        # 5. Import dinámico del handler
        import importlib
        spec = importlib.util.spec_from_file_location(tool_id, str(impl_path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        handler = getattr(module, skill_spec.get("handler_name", f"handle_{tool_id}"))

        # 6. Registrar handler en runtime
        self._tool_runtime.register_handler(tool_id, handler)

        # 7. Actualizar lista de tools del AgentLoop (sin reiniciar)
        self._agent_loop._all_tools = build_tool_definitions(self._tool_registry)
        self._agent_loop._default_tools = self._agent_loop._resolve_tools(None)

        # 8. Agregar a security rules (Level 2 por defecto para tools nuevos)
        self._security_service._confirm_tools.add(tool_id)

        # 9. Notificar
        event_bus.emit("skill_created", {"tool_id": tool_id, "auto": True})

        return {"status": "success", "tool_id": tool_id, "hot_loaded": True}
```

### 2.2 Endpoint para hot-reload manual

```
POST /skills/hot-load
{
  "contract": {...},
  "implementation": "def handle_my_tool(params, contract): ...",
  "handler_name": "handle_my_tool"
}
→ Carga el tool sin reiniciar
```

---

## PARTE 3: PROACTIVIDAD (SCHEDULER + QUEUE)

### 3.1 Task Queue

```python
# Archivo: workspace/queue.json
{
  "tasks": [
    {
      "id": "task_abc123",
      "description": "Enviar resumen diario por WhatsApp",
      "schedule": "daily_18:00",  // cron-like
      "agent_id": "agt_default",
      "action": {"type": "agent_message", "message": "Genera un resumen de la actividad de hoy"},
      "channel": "whatsapp",      // donde enviar el resultado
      "enabled": true,
      "last_run": "2026-03-30T18:00:00Z",
      "created_by": "user"        // o "supervisor"
    }
  ]
}
```

### 3.2 Proactive Scheduler

```python
class ProactiveScheduler:
    """Ejecuta tareas programadas y revisa el sistema periódicamente."""

    CYCLES = {
        "quick":  {"interval_s": 1800, "description": "Quick check: queue ready tasks"},
        "deep":   {"interval_s": 14400, "description": "Deep work: optimize, analyze patterns"},
        "daily":  {"interval_s": 86400, "description": "Daily summary + next day prep"},
    }

    def __init__(self, agent_loop, queue_path, channels):
        self._agent_loop = agent_loop
        self._queue = TaskQueue(queue_path)
        self._channels = channels

    def start(self):
        for cycle_name, config in self.CYCLES.items():
            threading.Thread(
                target=self._cycle_loop,
                args=(cycle_name, config["interval_s"]),
                daemon=True,
            ).start()

    def _cycle_loop(self, name, interval):
        while True:
            time.sleep(interval)
            try:
                if name == "quick":
                    self._run_ready_tasks()
                elif name == "deep":
                    self._deep_analysis()
                elif name == "daily":
                    self._daily_summary()
            except Exception as exc:
                print(f"[SCHEDULER] {name} error: {exc}", flush=True)

    def _run_ready_tasks(self):
        """Ejecuta tareas cuyo schedule indica que es hora."""
        for task in self._queue.get_ready():
            result = self._execute_task(task)
            self._queue.mark_completed(task["id"], result)
            if task.get("channel"):
                self._send_result(task["channel"], result)

    def _execute_task(self, task):
        """Ejecuta una tarea usando el AgentLoop."""
        action = task.get("action", {})
        if action.get("type") == "agent_message":
            events = []
            gen = self._agent_loop.run(
                action["message"],
                agent_config=self._get_agent_config(task.get("agent_id")),
            )
            for event in gen:
                events.append(event)
            final = next((e["text"] for e in reversed(events) if e.get("event") == "agent_response"), "")
            return {"status": "success", "response": final}
        return {"status": "unknown_action"}

    def _daily_summary(self):
        """Genera resumen del día y lo envía al usuario."""
        prompt = (
            "Genera un resumen de la actividad de hoy en el sistema. "
            "Incluye: tareas ejecutadas, errores detectados, skills creadas, "
            "mensajes procesados. Formato conciso, máximo 5 puntos."
        )
        events = list(self._agent_loop.run(prompt))
        summary = next((e["text"] for e in reversed(events) if e.get("event") == "agent_response"), "Sin actividad")

        # Enviar por todos los canales activos
        for channel in self._channels:
            if channel.connected:
                channel.send(f"📊 Resumen diario de CapOS:\n\n{summary}")

    def _deep_analysis(self):
        """Análisis profundo: patrones de uso, optimizaciones."""
        # Revisar métricas de los últimos 4 horas
        # Detectar tools más usados vs menos usados
        # Sugerir optimizaciones de configuración
        # Ejecutar gap_detector
```

### 3.3 API del Scheduler

```
GET  /scheduler/tasks          → listar tareas
POST /scheduler/tasks          → crear tarea
POST /scheduler/tasks/{id}     → actualizar
DELETE /scheduler/tasks/{id}   → eliminar
POST /scheduler/tasks/{id}/run → ejecutar ahora
GET  /scheduler/status         → estado del scheduler
```

### 3.4 UI del Scheduler (Control Center)

Nueva sección "Scheduler" con:
- Lista de tareas programadas con toggle on/off
- Crear tarea: descripción, schedule (dropdown: cada 30min, cada hora, diario, custom cron), agente, canal de envío
- Historial de ejecuciones
- Próxima ejecución de cada tarea

---

## PARTE 4: FUNCTION CALLING NATIVO

### 4.1 Problema Actual
- Groq bloquea requests de `urllib` (Cloudflare error 1010)
- El sistema usa text-based fallback que funciona pero es lento e impreciso

### 4.2 Solución: Usar el adapter existente del LLMClient

```python
# En tool_use_adapter.py:

def _openai_native_turn(self, messages, tools, system_prompt):
    """Usa el adapter existente del LLMClient que YA funciona con Groq."""
    adapter = getattr(self._client, "adapter", None)
    if adapter is None:
        return self._text_turn(messages, tools, system_prompt)

    # El adapter tiene .complete() que hace el HTTP request
    # Necesitamos extenderlo para soportar tools

    # Opción 1: Agregar método complete_with_tools() al adapter
    if hasattr(adapter, "complete_with_tools"):
        return adapter.complete_with_tools(system_prompt, messages, tools)

    # Opción 2: Monkey-patch el request del adapter para incluir tools
    # El OpenAIAPIAdapter ya hace POST a /chat/completions
    # Solo necesitamos agregar el campo "tools" al body
```

### 4.3 Cambios en OpenAIAPIAdapter

```python
# En llm_client.py — agregar método al adapter:

class OpenAIAPIAdapter:
    def complete_with_tools(self, system_prompt, messages, tools):
        """Extensión para function calling nativo."""
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "tools": [{"type": "function", "function": t} for t in tools],
        }
        # Usa el mismo método HTTP que .complete() usa
        # (que ya funciona con Groq a través de su custom HTTP handler)
        response = self._post_chat(body)  # nuevo método interno
        return self._parse_tool_response(response)
```

### 4.4 Beneficios
- **Más rápido**: el LLM retorna JSON estructurado directamente
- **Más preciso**: no depende de text parsing
- **Más confiable**: menos errores de formato
- **Compatible**: fallback a text mode si el provider no soporta tools

---

## PARTE 5: INTEGRACIONES ADICIONALES PARA CONTROL

### 5.1 System Monitor Tool
Nuevo tool `system_monitor` que el agente puede usar:
- `system_monitor_processes` — listar procesos con CPU/RAM
- `system_monitor_disk` — uso de disco
- `system_monitor_network` — puertos abiertos, conexiones
- `system_monitor_performance` — métricas del sistema

### 5.2 Package Manager Tool
Nuevo tool `package_manager`:
- `package_install` — pip install / npm install
- `package_uninstall` — pip uninstall / npm uninstall
- `package_list` — listar paquetes instalados
- `package_update` — actualizar paquetes
- Security: Level 2 (confirm) para install, Level 3 para uninstall del sistema

### 5.3 Git Integration Tool
Nuevo tool `git_operations`:
- `git_status` — estado del repo
- `git_diff` — cambios pendientes
- `git_commit` — crear commit (Level 2)
- `git_push` — push a remote (Level 2)
- `git_log` — historial de commits

### 5.4 Backup Tool
Nuevo tool `backup_system`:
- `backup_create` — snapshot de settings, agents, workspaces, memory
- `backup_restore` — restaurar desde snapshot
- `backup_list` — listar backups disponibles
- Automático: el scheduler puede programar backups diarios

---

## DASHBOARD DEL SUPERVISOR (Control Center)

### Nueva sección "Supervisor"

```
┌──────────────────────────────────────────────┐
│ SUPERVISOR                                    │
│                                               │
│ Status: ● Running    Claude: 3/10 invocations │
│ Health: ✅ OK        Security: ✅ Clean       │
│                                               │
│ ┌─────────────────────────────────────────┐  │
│ │ Recent Interventions                     │  │
│ │ [14:23] 🔍 Health OK (5/5 checks)       │  │
│ │ [15:01] ⚠️ Error: file not found        │  │
│ │ [15:01] 🤖 Claude: suggested fix         │  │
│ │ [16:30] 💡 Gap: "PDF convert" (4x)      │  │
│ │ [16:31] ✅ Skill created: pdf_to_text    │  │
│ └─────────────────────────────────────────┘  │
│                                               │
│ ┌─────────────────────────────────────────┐  │
│ │ Auto-Generated Skills                    │  │
│ │ pdf_to_text    ✅ active   [Disable]     │  │
│ │ csv_parser     ✅ active   [Disable]     │  │
│ └─────────────────────────────────────────┘  │
│                                               │
│ ┌─────────────────────────────────────────┐  │
│ │ Scheduled Tasks                          │  │
│ │ Daily summary  ● 18:00  WhatsApp  [Edit] │  │
│ │ Health check   ● 1min   Internal  [Edit] │  │
│ │ Backup         ● daily  System    [Edit] │  │
│ │                        [+ Add Task]      │  │
│ └─────────────────────────────────────────┘  │
│                                               │
│ ┌─────────────────────────────────────────┐  │
│ │ Configuration                            │  │
│ │ Auto-fix:            [● ON]              │  │
│ │ Auto-skill creation: [● ON]              │  │
│ │ Max Claude/hour:     [10]                │  │
│ │ Severity threshold:  [medium ▾]          │  │
│ │ Notify via WhatsApp: [● ON]              │  │
│ └─────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

---

## ORDEN DE IMPLEMENTACIÓN

### Sprint 1: Foundation (Function Calling + Hot-Reload)
1. Extender OpenAIAPIAdapter con `complete_with_tools()`
2. Actualizar ToolUseAdapter para usar native cuando disponible
3. Implementar SkillCreator con hot-reload
4. Endpoint `/skills/hot-load`
5. Test: crear skill via API → usarla inmediatamente sin restart

### Sprint 2: Supervisor Core
6. Claude Bridge (invocación CLI)
7. Health Monitor
8. Error Interceptor
9. Supervisor Daemon (orquesta monitores)
10. Supervisor Channel (notificaciones)
11. Dashboard básico en CC

### Sprint 3: Proactividad
12. Task Queue (CRUD + persistencia)
13. Proactive Scheduler (3 ciclos)
14. API del scheduler
15. UI del scheduler en CC
16. Daily summary automático

### Sprint 4: Intelligence
17. Gap Detector
18. Auto-skill creation (Claude genera + hot-loads)
19. Security Auditor
20. Code Fixer
21. Config Optimizer

### Sprint 5: Extra Tools
22. System Monitor tool
23. Package Manager tool
24. Git Integration tool
25. Backup tool
26. Dashboard completo del supervisor

---

## ARCHIVOS A CREAR

| Archivo | Sprint |
|---------|--------|
| `system/core/supervisor/__init__.py` | 2 |
| `system/core/supervisor/supervisor_daemon.py` | 2 |
| `system/core/supervisor/health_monitor.py` | 2 |
| `system/core/supervisor/security_auditor.py` | 4 |
| `system/core/supervisor/error_interceptor.py` | 2 |
| `system/core/supervisor/gap_detector.py` | 4 |
| `system/core/supervisor/claude_bridge.py` | 2 |
| `system/core/supervisor/skill_creator.py` | 1 |
| `system/core/supervisor/code_fixer.py` | 4 |
| `system/core/supervisor/config_optimizer.py` | 4 |
| `system/core/supervisor/supervisor_log.py` | 2 |
| `system/core/supervisor/supervisor_channel.py` | 2 |
| `system/core/scheduler/__init__.py` | 3 |
| `system/core/scheduler/task_queue.py` | 3 |
| `system/core/scheduler/proactive_scheduler.py` | 3 |
| `system/core/ui_bridge/handlers/supervisor_handlers.py` | 2 |
| `system/core/ui_bridge/handlers/scheduler_handlers.py` | 3 |
| `system/tools/implementations/system_monitor_tools.py` | 5 |
| `system/tools/implementations/package_manager_tools.py` | 5 |
| `system/tools/implementations/git_tools.py` | 5 |
| `system/tools/implementations/backup_tools.py` | 5 |

## ARCHIVOS A MODIFICAR

| Archivo | Sprint | Cambio |
|---------|--------|--------|
| `system/core/interpretation/llm_client.py` | 1 | Agregar complete_with_tools a adapters |
| `system/core/agent/tool_use_adapter.py` | 1 | Usar native function calling |
| `system/core/agent/agent_loop.py` | 1 | Hot-reload tools list |
| `system/core/ui_bridge/api_server.py` | 1-5 | Instanciar supervisor, scheduler, rutas |
| `system/core/settings/settings_service.py` | 2 | Settings del supervisor |
| `system/frontend/app/src/pages/ControlCenter.jsx` | 2-3 | Secciones Supervisor + Scheduler |
| `system/frontend/app/src/components/control-center/sectionRegistry.js` | 2 | Registrar secciones |
| `system/frontend/app/src/api.js` | 2-3 | API functions |
| `docker-entrypoint.py` | 2 | API prefixes |

---

## VERIFICACIÓN POR SPRINT

### Sprint 1
- [ ] `POST /agent` con Groq usa function calling nativo (no text parse)
- [ ] `POST /skills/hot-load` crea tool → usable inmediatamente sin restart
- [ ] Agent puede llamar el tool recién creado

### Sprint 2
- [ ] Supervisor aparece en CC con status "Running"
- [ ] Health monitor reporta 5/5 checks
- [ ] Error en tool → supervisor detecta y muestra en log
- [ ] Claude Bridge invocable (claude -p funciona)

### Sprint 3
- [ ] Crear tarea programada desde UI
- [ ] Tarea se ejecuta en el horario configurado
- [ ] Daily summary se genera y envía por WhatsApp

### Sprint 4
- [ ] Gap detector identifica capability faltante
- [ ] Claude genera skill automáticamente
- [ ] Skill se hot-loads y funciona
- [ ] Security auditor reporta "Clean"

### Sprint 5
- [ ] `system_monitor` muestra CPU/RAM/disco
- [ ] `package_install` instala paquete pip (con confirmación)
- [ ] `git_commit` crea commit (con confirmación)
- [ ] Backup automático funciona
