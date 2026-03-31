# Capability OS Wiki

Welcome to the Capability OS wiki -- your guide to building, extending, and operating CapOS.

## Quick Navigation

| Page | Description |
|------|-------------|
| [Getting Started](Getting-Started) | Installation, first run, LLM configuration |
| [Architecture](Architecture) | System design, plugin graph, request flow |
| [Plugin Development](Plugin-Development) | Create custom plugins with the SDK |
| [Frontend SDK](Frontend-SDK) | SDK-first architecture, domain modules, events |
| [API Reference](API-Reference) | 180+ REST endpoints by module |
| [Event Catalog](Event-Catalog) | 24 WebSocket event types with payloads |
| [Configuration](Configuration) | settings.json, environment variables, Docker |
| [Channels & Integrations](Channels-and-Integrations) | WhatsApp, Telegram, Slack, Discord + new channels |
| [Security](Security) | Progressive security, sandbox, auth, hardening |
| [Contributing](Contributing) | Bug reports, PRs, naming conventions |

## What is Capability OS?

An AI-powered operating system built on a **plugin architecture**. 21 plugins manage everything from natural language understanding and autonomous agent execution to visual workflow building, multi-channel messaging, and proactive scheduling.

**Key numbers:**
- 21 plugins with typed Protocol contracts
- 180+ REST endpoints
- 24 WebSocket event types
- 4 messaging channels (+ 5 UI-ready)
- 3 security levels
- 2 execution sandboxes (Process + Docker)
- 1 visual workflow builder

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, ASGI (uvicorn) |
| Frontend | React 18, Vite, ReactFlow, Monaco Editor |
| Database | SQLite (sqlite-vec for vectors) |
| Auth | JWT (24h expiry), 4 roles |
| Messaging | WebSocket + SSE |
| Container | Docker multi-stage build |
| CI | GitHub Actions |
| License | MIT |
