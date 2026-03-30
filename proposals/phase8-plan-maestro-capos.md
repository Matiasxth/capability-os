# Plan Maestro CapOS — Funcionalidades Completas + Soluciones Técnicas

## Estado Actual
- 18 plugins running, 0 errores
- 73 funciones API, 173 endpoints backend
- 16 secciones en Control Center
- Frontend compila, tests pasan (226+)
- SDK tipado + ServiceContainer implementado

---

## SPRINT 1: Servidor Async + Concurrencia (Base técnica)

### Problema
El servidor actual (`ThreadingHTTPServer`) usa GIL — bloquea con 3+ usuarios simultáneos.

### Solución
Migrar a `uvicorn` + `asyncio` manteniendo compatibilidad con los handlers existentes.

### Archivos
| Archivo | Cambio |
|---------|--------|
| Nuevo: `system/core/ui_bridge/asgi_server.py` | Servidor ASGI con uvicorn |
| Nuevo: `system/core/ui_bridge/async_adapter.py` | Wrapper que convierte handlers sync → async |
| Mod: `docker-entrypoint.py` | Usar uvicorn en vez de HTTPServer |
| Mod: `system/core/ui_bridge/api_server.py` | Exponer app ASGI |

### Implementación
```python
# asgi_server.py — servidor ASGI mínimo
class ASGIApp:
    def __init__(self, service):
        self.service = service
        self.router = service._router

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._handle_ws(scope, receive, send)
```

### Resultado
- Soporta 50+ conexiones simultáneas sin bloqueo
- SSE streaming nativo (sin threads separados)
- WebSocket nativo (sin librería externa)
- Compatible con todos los handlers existentes

---

## SPRINT 2: Vector Store con sqlite-vec

### Problema
VectorStore actual usa cosine similarity en Python puro — O(n) por búsqueda, lento con 5,000+ memorias.

### Solución
Reemplazar por `sqlite-vec` (plugin SQLite para vectores) — misma interfaz, 100x más rápido.

### Archivos
| Archivo | Cambio |
|---------|--------|
| Nuevo: `system/core/memory/sqlite_vector_store.py` | VectorStore con sqlite-vec |
| Mod: `system/plugins/memory/plugin.py` | Usar sqlite_vector_store si disponible, fallback al actual |
| Mod: `requirements.txt` | Agregar sqlite-vec |

### Interfaz (misma que VectorStore actual)
```python
class SqliteVectorStore:
    def add(self, entry_id, vector, metadata=None) -> None
    def delete(self, entry_id) -> bool
    def search(self, query_vector, top_k=5) -> list[dict]
    def count(self) -> int
```

---

## SPRINT 3: Contract Validation + Plugin Safety

### Problema
Un plugin puede publicar un string como `ToolRuntimeContract` — Python no lo detecta.

### Archivos
| Archivo | Cambio |
|---------|--------|
| Mod: `system/container/service_container.py` | isinstance check en register_service |
| Nuevo: `system/sdk/validation.py` | Contract validator + test runner |
| Nuevo: `tests/unit/test_sdk_contracts.py` | Tests que verifican cada plugin cumple su Protocol |

### Implementación
```python
# En ServiceContainer.register_service:
def register_service(self, contract_type, implementation):
    if not isinstance(implementation, contract_type):
        raise TypeError(
            f"{type(implementation).__name__} does not implement {contract_type.__name__}"
        )
    self._services[contract_type] = implementation
```

---

## SPRINT 4: CLI Mode

### Problema
El sistema solo es accesible via web UI.

### Archivos
| Archivo | Cambio |
|---------|--------|
| Nuevo: `capabilityos/__init__.py` | Package |
| Nuevo: `capabilityos/__main__.py` | Entry point: `python -m capabilityos` |
| Nuevo: `capabilityos/cli/chat.py` | Chat interactivo + one-shot |
| Nuevo: `capabilityos/cli/status.py` | Estado del sistema |
| Nuevo: `capabilityos/cli/serve.py` | Iniciar servidor |
| Nuevo: `capabilityos/cli/plugins.py` | Listar/instalar/desinstalar plugins |
| Nuevo: `capabilityos/cli/formatter.py` | Output colorizado |

### Comandos
```bash
python -m capabilityos chat                    # Chat interactivo
python -m capabilityos chat "lista archivos"   # One-shot
python -m capabilityos status                  # Health del sistema
python -m capabilityos serve                   # Iniciar servidor
python -m capabilityos serve --port 9000       # Puerto custom
python -m capabilityos plugins list            # Listar plugins
python -m capabilityos plugins install <path>  # Instalar plugin
```

---

## SPRINT 5: Multi-Usuario (JWT + Roles)

### Archivos
| Archivo | Cambio |
|---------|--------|
| Nuevo: `system/core/auth/__init__.py` | Module |
| Nuevo: `system/core/auth/user_registry.py` | CRUD usuarios + bcrypt hashing |
| Nuevo: `system/core/auth/jwt_service.py` | Token generation + validation |
| Nuevo: `system/core/auth/auth_middleware.py` | Verificar JWT en cada request |
| Nuevo: `system/plugins/auth/plugin.py` | Plugin de autenticación |
| Nuevo: `system/frontend/app/src/pages/Login.jsx` | Página de login |
| Nuevo: `system/frontend/app/src/context/AuthContext.jsx` | Estado de auth |
| Mod: `system/frontend/app/src/App.jsx` | Auth guard + login redirect |
| Mod: `system/frontend/app/src/api.js` | Authorization header en requests |
| Mod: `system/core/ui_bridge/api_server.py` | Middleware de auth |
| Mod: Control Center | Sección "Users" para gestión |

### Roles
| Rol | Permisos |
|-----|----------|
| **owner** | Todo — crear usuarios, supervisor, L3 |
| **admin** | Todo excepto crear owners |
| **user** | Chat, tools L1/L2, workspaces asignados |
| **viewer** | Solo lectura |

### Flujo
1. Primera vez → crear usuario owner (onboarding)
2. Login → JWT token (24h expiry)
3. Cada request → Authorization: Bearer {token}
4. UI se adapta al rol (oculta features no permitidas)

---

## SPRINT 6: Visual Workflow Builder

### Archivos
| Archivo | Cambio |
|---------|--------|
| Nuevo: `system/frontend/app/src/pages/WorkflowEditor.jsx` | Página principal |
| Nuevo: `system/frontend/app/src/components/workflow/WorkflowCanvas.jsx` | ReactFlow canvas |
| Nuevo: `system/frontend/app/src/components/workflow/NodePalette.jsx` | Palette arrastrables |
| Nuevo: `system/frontend/app/src/components/workflow/NodeConfig.jsx` | Panel de config |
| Nuevo: `system/frontend/app/src/components/workflow/nodes/*.jsx` | Tipos de nodo |
| Nuevo: `system/core/workflow/workflow_registry.py` | CRUD workflows |
| Nuevo: `system/core/workflow/workflow_executor.py` | Ejecutar workflows |
| Nuevo: `system/plugins/workflows/plugin.py` | Plugin de workflows |
| Mod: `system/frontend/app/src/App.jsx` | Ruta /workflows |
| Mod: `system/frontend/app/src/api.js` | Funciones de workflow API |
| Mod: `package.json` | Agregar reactflow |

### Tipos de nodo
| Nodo | Función |
|------|---------|
| Trigger | Inicia workflow (schedule, webhook, manual) |
| Tool | Ejecuta un tool |
| Agent | Envía mensaje al agente |
| Condition | If/else basado en resultado |
| Loop | Repite sobre lista |
| Transform | Modifica datos |
| Output | Envía resultado (WhatsApp/Telegram/UI) |
| Delay | Espera tiempo |

---

## SPRINT 7: Plugin Marketplace + Hot-Reload

### Plugin Loader Externo
| Archivo | Cambio |
|---------|--------|
| Nuevo: `capabilityos/cli/marketplace.py` | `capos install/uninstall/search` |
| Mod: `system/container/plugin_loader.py` | Cargar desde pip packages |
| Nuevo: `system/container/hot_reload.py` | File watcher + reload |
| Mod: `system/container/service_container.py` | restart_plugin() method |

### Formato de distribución
```
capos-plugin-signal/
  capos-plugin.json       # Manifest
  plugin.py               # Entry point
  requirements.txt        # Dependencias
  setup.py                # pip installable
```

### Comandos
```bash
capos plugins search telegram      # Buscar en registry
capos plugins install capos-plugin-signal  # Desde pip
capos plugins install ./my-plugin  # Desde directorio local
capos plugins uninstall signal     # Desinstalar
capos plugins reload signal        # Hot-reload sin restart
```

### Hot-Reload
```python
class HotReloader:
    def reload_plugin(self, plugin_id):
        container.stop_plugin(plugin_id)
        importlib.reload(module)
        new_plugin = module.create_plugin()
        container.register_plugin(new_plugin)
        container.initialize_plugin(plugin_id)
        container.start_plugin(plugin_id)
```

---

## SPRINT 8: Sandbox Real para Ejecución

### Problema
Tools ejecutan comandos sin sandboxing real — solo clasificación L1/L2/L3.

### Archivos
| Archivo | Cambio |
|---------|--------|
| Nuevo: `system/core/sandbox/docker_sandbox.py` | Ejecutar en Docker container |
| Nuevo: `system/core/sandbox/process_sandbox.py` | Ejecutar con restricciones OS |
| Nuevo: `system/plugins/sandbox/plugin.py` | Plugin de sandbox |
| Mod: `system/tools/runtime.py` | Tool execution con sandbox |
| Mod: `system/core/security/security_service.py` | L3 = Docker sandbox obligatorio |

### Niveles
| Level | Sandbox |
|-------|---------|
| L1 | Sin sandbox (filesystem read, list) |
| L2 | Process sandbox (timeout, memory limit, no network) |
| L3 | Docker sandbox (container efímero, volumen read-only) |

---

## SPRINT 9: Más Canales

### Nuevos canales como plugins independientes
| Canal | Plugin | Librería |
|-------|--------|----------|
| Signal | `system/plugins/channels/signal/plugin.py` | signal-cli-rest-api |
| Matrix | `system/plugins/channels/matrix/plugin.py` | matrix-nio |
| Microsoft Teams | `system/plugins/channels/teams/plugin.py` | botbuilder-python |
| Email (IMAP/SMTP) | `system/plugins/channels/email/plugin.py` | imaplib + smtplib |
| Webhook genérico | `system/plugins/channels/webhook/plugin.py` | HTTP POST receiver |

Cada uno sigue el patrón exacto de los 4 canales existentes — ~60 líneas de plugin.py.

---

## SPRINT 10: PWA + Notificaciones Push

### Archivos
| Archivo | Cambio |
|---------|--------|
| Mod: `system/frontend/app/public/manifest.json` | PWA manifest completo |
| Nuevo: `system/frontend/app/public/sw.js` | Service Worker para offline |
| Nuevo: `system/frontend/app/src/hooks/usePush.js` | Push notification hook |
| Mod: `system/frontend/app/src/App.jsx` | Install prompt + push registration |
| Nuevo: `system/core/push/push_service.py` | Web Push (VAPID) backend |
| Nuevo: `system/plugins/push/plugin.py` | Plugin de notificaciones |

### Resultado
- Instalar como app en Android/iOS desde Chrome
- Notificaciones push cuando el agente completa una tarea
- Funciona offline (UI cached, reconnect al volver)

---

## SPRINT 11: Tests Completos + CI

### Archivos
| Archivo | Cambio |
|---------|--------|
| Nuevo: `tests/unit/test_sdk_contracts.py` | Cada plugin cumple Protocol |
| Nuevo: `tests/unit/test_container_lifecycle.py` | Init/start/stop ordering |
| Nuevo: `tests/unit/test_plugin_isolation.py` | Plugin falla → resto sigue |
| Nuevo: `tests/integration/test_agent_e2e.py` | Agent complete flow |
| Nuevo: `tests/integration/test_channel_e2e.py` | Message in → response out |
| Nuevo: `.github/workflows/ci.yml` | GitHub Actions CI |
| Nuevo: `pytest.ini` update | Coverage config |

### Targets
- Cobertura > 80%
- CI verde en cada PR
- Contract tests para todos los Protocol
- E2E test del ciclo chat → agent → tool → response

---

## SPRINT 12: Boundary Enforcement + Docs

### Boundary Lint
| Archivo | Cambio |
|---------|--------|
| Nuevo: `scripts/check_plugin_boundaries.py` | Detecta imports cruzados entre plugins |
| Nuevo: `.github/workflows/lint.yml` | Ejecuta boundary check en CI |

### Regla
```
PROHIBIDO: from system.plugins.channels.telegram import X
              (desde cualquier otro plugin)
PERMITIDO: from system.sdk.contracts import TelegramConnectorContract
              (via contrato tipado)
```

### Documentación
| Archivo | Contenido |
|---------|-----------|
| Nuevo: `docs/plugin-development.md` | Guía para crear plugins |
| Nuevo: `docs/sdk-reference.md` | Referencia de contratos y tipos |
| Nuevo: `docs/architecture.md` | Diagrama de la arquitectura modular |
| Mod: `README.md` | Actualizar con nueva arquitectura |

---

## ORDEN DE EJECUCIÓN

| Sprint | Nombre | Esfuerzo | Dependencias | Impacto |
|--------|--------|----------|-------------|---------|
| 1 | Servidor Async | Alto | Ninguna | Habilita multi-user |
| 2 | sqlite-vec | Bajo | Ninguna | Performance memoria |
| 3 | Contract Validation | Bajo | Ninguna | Seguridad SDK |
| 4 | CLI Mode | Medio | Ninguna | Acceso terminal |
| 5 | Multi-Usuario | Alto | Sprint 1 | Core feature |
| 6 | Visual Workflow | Alto | Ninguna (npm: reactflow) | Core feature |
| 7 | Marketplace + Hot-Reload | Medio | Sprint 3 | Extensibilidad |
| 8 | Sandbox Real | Medio | Ninguna | Seguridad |
| 9 | Más Canales | Medio | Ninguna | Reach |
| 10 | PWA + Push | Medio | Sprint 1 | Mobile |
| 11 | Tests + CI | Medio | Sprint 3 | Calidad |
| 12 | Boundaries + Docs | Bajo | Sprint 7 | Mantenibilidad |

### Prioridad recomendada
```
INMEDIATO (Sprints 1-3): Base técnica — async, vectors, validation
CORTO     (Sprints 4-6): Features core — CLI, multi-user, workflows
MEDIO     (Sprints 7-9): Extensibilidad — marketplace, sandbox, canales
LARGO     (Sprints 10-12): Polish — PWA, tests, documentación
```

---

## VERIFICACIÓN POR SPRINT

Cada sprint debe pasar:
- [ ] Tests existentes sin regresiones
- [ ] Frontend compila sin errores
- [ ] Container: 18+ plugins running, 0 errors
- [ ] verify.py: 16/16 checks
- [ ] Nuevo feature funciona end-to-end
