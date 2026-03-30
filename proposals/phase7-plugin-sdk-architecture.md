# Plan: Plugin SDK + Service Container + Arquitectura Modular

## Objetivo
Transformar CapOS de un monolito acoplado (69 componentes en 1 constructor) a una arquitectura modular con SDK tipado, sin romper el sistema existente.

---

## ESTRUCTURA FINAL

```
system/
  sdk/                          # Plugin SDK (contratos tipados)
    __init__.py
    contracts.py                # Protocol classes para servicios
    plugin_types.py             # BasePlugin, ToolPlugin, ChannelPlugin, etc.
    lifecycle.py                # PluginState enum
    context.py                  # PluginContext (inyeccion de dependencias)
    manifest.py                 # PluginManifest dataclass

  container/                    # Service Container (reemplaza god object)
    __init__.py
    service_container.py        # Registro, resolucion, lifecycle
    plugin_loader.py            # Descubrimiento desde dirs/packages

  plugins/                      # Plugins built-in (migrados del god object)
    core_services/plugin.py     # Settings, ToolRegistry, Security, Health
    memory/plugin.py            # MemoryManager, Semantic, Markdown, Compactor
    agent/plugin.py             # AgentLoop, AgentRegistry, ToolUseAdapter
    capabilities/plugin.py      # Engine, Interpreter, LLMClient
    skills/plugin.py            # SkillRegistry, DomainRegistry
    workspace/plugin.py         # WorkspaceRegistry, FileBrowser
    supervisor/plugin.py        # SupervisorDaemon, SkillCreator
    scheduler/plugin.py         # TaskQueue, ProactiveScheduler
    voice/plugin.py             # STT, TTS
    browser/plugin.py           # BrowserSessionManager
    mcp/plugin.py               # MCPClient, MCPToolBridge
    a2a/plugin.py               # A2AServer, AgentCardBuilder
    growth/plugin.py            # GapAnalyzer, AutoInstall
    sequences/plugin.py         # SequenceRunner, SequenceRegistry
    channels/
      telegram/plugin.py
      slack/plugin.py
      discord/plugin.py
      whatsapp/plugin.py
```

---

## SDK: CONTRATOS CORE

### contracts.py (Protocol classes)

```python
@runtime_checkable
class SettingsProvider(Protocol):
    def load_settings(self) -> dict[str, Any]: ...
    def get_settings(self, *, mask_secrets: bool = True) -> dict[str, Any]: ...
    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]: ...

@runtime_checkable
class ToolRegistryContract(Protocol):
    def get(self, tool_id: str) -> dict[str, Any] | None: ...
    def list_all(self) -> list[dict[str, Any]]: ...
    def register(self, contract: dict[str, Any]) -> None: ...

@runtime_checkable
class ToolRuntimeContract(Protocol):
    def execute(self, action: str, params: dict[str, Any]) -> Any: ...
    def register_handler(self, tool_id: str, handler: Any) -> None: ...

@runtime_checkable
class SecurityServiceContract(Protocol):
    def classify(self, tool_id: str = "", inputs: dict | None = None) -> int: ...

@runtime_checkable
class MemoryManagerContract(Protocol):
    def recall(self, key: str) -> Any: ...
    def remember(self, key: str, value: Any) -> None: ...

@runtime_checkable
class ExecutionHistoryContract(Protocol):
    def upsert_chat(self, session_id: str, intent: str, ...) -> None: ...
    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]: ...
    def get_by_workspace(self, workspace_id: str) -> list[dict[str, Any]]: ...

@runtime_checkable
class AgentLoopContract(Protocol):
    def run(self, message: str, ...) -> Any: ...

@runtime_checkable
class IntentInterpreterContract(Protocol):
    def interpret(self, text: str) -> dict[str, Any]: ...
    def chat_response(self, text: str, user_name: str) -> str: ...

@runtime_checkable
class EventBusContract(Protocol):
    def emit(self, event_type: str, data: dict | None = None) -> None: ...
    def subscribe(self, callback: Any) -> Any: ...
```

### plugin_types.py (Tipos de plugin)

```python
@runtime_checkable
class BasePlugin(Protocol):
    plugin_id: str          # "capos.channels.telegram"
    plugin_name: str        # "Telegram Channel"
    version: str            # "1.0.0"
    dependencies: list[str] # ["capos.core.settings"]

    def initialize(self, ctx: PluginContext) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...

@runtime_checkable
class ToolPlugin(BasePlugin, Protocol):
    def register_tools(self, registry, runtime) -> list[str]: ...

@runtime_checkable
class ChannelPlugin(BasePlugin, Protocol):
    channel_id: str
    def get_status(self) -> dict: ...
    def configure(self, settings: dict) -> None: ...
    def send_message(self, target: str, text: str) -> dict: ...
    def register_routes(self, router) -> None: ...

@runtime_checkable
class MemoryPlugin(BasePlugin, Protocol):
    def store(self, key: str, value: Any) -> None: ...
    def retrieve(self, key: str) -> Any: ...
    def search(self, query: str, limit: int = 10) -> list: ...
```

### context.py (Inyeccion de dependencias)

```python
class PluginContext:
    workspace_root: Path
    project_root: Path
    settings: dict
    event_bus: EventBusContract

    def get_service(self, contract_type: type) -> Any:
        """Resuelve un servicio por Protocol type."""
        ...

    def get_service_optional(self, contract_type: type) -> Any | None:
        """Como get_service pero retorna None si no existe."""
        ...

    def get_plugin_settings(self, plugin_id: str) -> dict:
        """Settings especificos del plugin."""
        ...
```

---

## SERVICE CONTAINER

```python
class ServiceContainer:
    def register_plugin(self, plugin, manifest=None) -> None
    def register_service(self, contract_type, implementation) -> None
    def get_service(self, contract_type) -> Any
    def get_plugin(self, plugin_id) -> Any | None

    def initialize_all(self) -> None   # Topological sort + initialize()
    def start_all(self) -> None        # start() en orden
    def stop_all(self) -> None         # stop() en orden inverso
    def get_status(self) -> dict       # Estado de todos los plugins
```

Lifecycle: REGISTERED -> INITIALIZING -> INITIALIZED -> STARTING -> RUNNING -> STOPPING -> STOPPED

---

## PLUGIN MANIFEST (capos-plugin.json)

```json
{
  "id": "capos.channels.telegram",
  "name": "Telegram Channel",
  "version": "1.0.0",
  "plugin_types": ["channel"],
  "dependencies": ["capos.core.settings", "capos.core.capabilities"],
  "entry_point": "plugin:create_plugin",
  "settings_key": "telegram",
  "auto_start": true
}
```

---

## GRAFO DE DEPENDENCIAS

```
capos.core.settings           (sin deps - carga primero)
  |
  +-- capos.core.tools         (deps: settings)
  |     +-- capos.core.capabilities  (deps: settings, tools)
  |     |     +-- capos.core.agent   (deps: capabilities, tools, memory)
  |     |     +-- capos.core.mcp     (deps: capabilities, tools)
  |     |     +-- capos.core.growth  (deps: capabilities, tools)
  |     +-- capos.core.skills  (deps: tools)
  |
  +-- capos.core.memory        (deps: settings)
  +-- capos.channels.telegram  (deps: settings, capabilities)
  +-- capos.channels.slack     (deps: settings, capabilities)
  +-- capos.channels.discord   (deps: settings, capabilities)
  +-- capos.channels.whatsapp  (deps: settings, capabilities, tools)
  +-- capos.core.workspace     (deps: settings)
  +-- capos.core.scheduler     (deps: settings, agent)
  +-- capos.core.supervisor    (deps: settings, agent, skills)
  +-- capos.core.voice         (deps: settings)
  +-- capos.core.browser       (deps: settings, tools)
```

---

## MIGRACION (7 etapas incrementales)

### Etapa 1: Fundacion (SDK + Container)
- Crear system/sdk/ con todos los contracts
- Crear system/container/ con ServiceContainer
- Tests unitarios del container
- NO tocar api_server.py

### Etapa 2: Core Services Plugin
- Extraer: Settings, ToolRegistry, CapabilityRegistry, ToolRuntime, Security, Health
- api_server.py crea el container y delega a el
- Coexistencia: self.settings_service = container.get_service(SettingsProvider)

### Etapa 3: Memory Plugin
- Extraer: MemoryManager, SemanticMemory, MarkdownMemory, Compactor, History
- Publicar como servicios en el container

### Etapa 4: Channel Plugins (mayor valor)
- Extraer: Telegram, Slack, Discord, WhatsApp como plugins independientes
- Cada uno con su manifest, lifecycle, routes
- Eliminar ~120 lineas del god object

### Etapa 5: Remaining Plugins
- Agent, Capabilities, Skills, Workspace, MCP, A2A, Growth, Supervisor, Scheduler, Sequences, Voice, Browser
- Cada uno como plugin con manifest y lifecycle

### Etapa 6: Retirar God Object
- api_server.__init__ = crear container + cargar plugins + inicializar
- Handlers reciben container en vez de service
- _build_router() recolecta rutas de todos los plugins

### Etapa 7: Plugin Loader + Hot-Reload
- Cargar plugins externos desde directorio
- pip install capos-plugin-xxx
- Hot-reload con watchdog

---

## VERIFICACION POR ETAPA

Cada etapa debe pasar:
- [ ] pytest existentes sin cambios
- [ ] Frontend conecta normalmente
- [ ] SSE streaming funciona
- [ ] Canales responden (si estan configurados)
- [ ] Event bus emite eventos correctamente
- [ ] GET /status muestra todos los plugins y su estado
