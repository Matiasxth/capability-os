# Capability OS

**The only local agent with formal contracts.**

Converts intents into executable, observable, and self-improving actions.
Secure by design, not by configuration.

```
docker-compose up          # install + run
open http://localhost:8000  # done
```

---

## Why Capability OS

| Feature | Capability OS | Typical agent frameworks |
|---|---|---|
| **Formal contracts** | Every capability and tool has a JSON Schema contract with inputs, outputs, strategy, and lifecycle | Tools are loose functions with optional docstrings |
| **Secure by design** | Command allowlist, workspace sandbox, timeout enforcement, confirmation for destructive actions | Security depends on developer discipline |
| **Built-in observability** | 8 event types + 4 KPIs + persistent traces — no Datadog needed | Requires external logging/tracing setup |
| **Self-improvement** | Detects capability gaps, suggests strategy optimizations, generates new contracts — user always approves | Manual iteration on prompts/tools |
| **MCP native** | Connects to any MCP server as tools; exposes capabilities as MCP tools for other agents | Separate adapters per integration |
| **Persistent memory** | Learns user preferences and execution patterns across sessions | Stateless between runs |

---

## Quick start

### Docker (recommended)

```bash
docker-compose up -d
```

Open `http://localhost:8000` — API and frontend served on a single port.

**Configure LLM:**
```bash
# Ollama (default — expects Ollama on host)
docker-compose up -d

# OpenAI
LLM_PROVIDER=openai OPENAI_API_KEY=sk-... docker-compose up -d
```

### Manual

```bash
# Backend
python -m system.core.ui_bridge.api_server

# Frontend
cd system/frontend/app && npm install && npm run dev
```

Requires Python 3.12+, Node.js 18+. Optional: `pip install playwright && python -m playwright install chromium` for browser capabilities.

---

## What you can do

**Automate code and projects**
```
> create a new React project called dashboard
Plan: create_project → inspect_project (2 steps)
Execute → Completed in 3200ms
```

**Automate the web**
```
> fetch https://example.com and extract all links
Plan: fetch_url → parse_html → extract_links (3 steps)
Execute → 12 links extracted
```

**WhatsApp automation** (with CDP session persistence — no QR re-scan)
```
> open whatsapp, search "Alice", send "Meeting at 3pm"
Plan: open_whatsapp_web → search_whatsapp_chat → send_whatsapp_message
Execute → delivered ✓✓
```

**Reusable sequences**
```
> save this plan as "daily-report"
> run sequence daily-report
```

**Self-improvement**
```
Control Center → Self-Improvement
  3 capability gaps detected → [Generate] [Ignore]
  1 optimization proposed: retry_policy for read_file → [Approve] [Discard]
```

---

## Architecture

```
User intent
  → IntentInterpreter (LLM)
    → PlanBuilder + PlanValidator
      → CapabilityEngine
        → Strategy interpreter (sequential | conditional | retry | fallback)
          → ToolRuntime → tool handler → result
        → ObservationLogger → MetricsCollector + ExecutionHistory
      → UserContext.learn()
```

| Layer | Components | Persistence |
|---|---|---|
| **Capabilities** | 47 contracts across 7 domains | `system/capabilities/contracts/v1/` |
| **Tools** | 30+ contracts (filesystem, execution, network, system, browser, mcp) | `system/tools/contracts/v1/` |
| **Engine** | Sequential, conditional, retry_policy, fallback strategies | In-memory per execution |
| **Observation** | 8 event types, 4 KPIs, trace persistence | `workspace/artifacts/` |
| **Memory** | MemoryManager, UserContext, ExecutionHistory | `workspace/memory/` |
| **Integrations** | Detector → Classifier → Planner → Generator → Bridge | `system/integrations/` |
| **Self-improvement** | GapAnalyzer, PerformanceMonitor, StrategyOptimizer, CapabilityGenerator | `workspace/proposals/` |
| **MCP** | Client (stdio/HTTP), ToolBridge, CapabilityGenerator, Server | Runtime |
| **UI** | React 18 + Vite, dark theme, Workspace + Control Center | `system/frontend/` |

---

## Configuration

`workspace/system/settings.json`:
```json
{
  "llm": { "provider": "ollama", "base_url": "http://127.0.0.1:11434", "model": "llama3.1:8b" },
  "browser": { "auto_start": true, "cdp_port": 0, "auto_restart_max_retries": 2 },
  "mcp": { "servers": [], "auto_discover_capabilities": false, "server_timeout_ms": 10000 },
  "workspace": { "artifacts_path": "./artifacts", "sequences_path": "./sequences" }
}
```

CDP tip: launch Chrome with `--remote-debugging-port=9222` and set `cdp_port: 9222` to skip WhatsApp QR re-authentication.

---

## Tests

```bash
# Backend (575 tests, ≥82% core coverage)
python -m pytest --cov=system.core --cov-fail-under=80

# Frontend
cd system/frontend/app && npm test -- --run
```

---

## Documentation

| Phase | Description |
|---|---|
| [Phase 1-4](README_PHASE1.md) | Core foundation: registries, engine, tools, integrations |
| [Phase 5](README_PHASE5.md) | UI bridge API + React frontend |
| [Phase 6-7](README_PHASE6.md) | Code modification, sequences, intent interpretation |
| [Phase 8-9](README_PHASE8.md) | Browser worker IPC + WhatsApp connector |
| [Phase 10-11](README_PHASE10.md) | Control Center, browser hardening |
| [Browser Hardening](README_BROWSER_HARDENING.md) | Worker isolation, DOM introspection |
| [Master Spec](capability_os_master_spec.md) | Full specification v1.1 |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on reporting bugs, proposing capabilities, adding integrations, and submitting PRs.

---

## License

MIT
