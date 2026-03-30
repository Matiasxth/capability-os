# Vision

## What is Capability OS?

Capability OS is a **local-first AI operating system** that treats AI agents as team members, not just chatbots. It was born from a simple idea: what if your AI assistant could actually *do things* — manage files, browse the web, send messages, run commands — with the same security model as a real operating system?

## Why We Built This

Most AI agent frameworks fall into two extremes:

1. **Too restricted** — The AI can only answer questions. It can't touch files, run code, or interact with the real world.
2. **Too open** — The AI has unrestricted access to everything. One bad prompt and it deletes your files.

We wanted a third option: **freedom with accountability**. The AI can do anything, but dangerous operations require explicit human approval — just like `sudo` on Linux.

## Core Principles

### 1. Agents are Team Members
Agents aren't disposable scripts. They have names, personalities, expertise, and assigned projects. You create a "DevBot" for coding, a "WriterBot" for content, a "DataBot" for analysis — each with their own tools, behavior, and context.

### 2. Progressive Security by Design
Every operation is classified into three levels:
- **Free**: Read anything, query anything — no friction
- **Confirm**: Modify files, run commands — one click to approve
- **Protected**: Delete system files, access credentials — password required

This isn't bolted on. It's in the core of the execution loop.

### 3. Projects, Not Conversations
Conversations are ephemeral. Projects persist. Each project has a workspace (directory), assigned agents, status tracking, and session history. When you switch projects, your agent knows the context.

### 4. Multi-Channel by Default
Your AI should live where you are — not just in a web tab. Capability OS connects to WhatsApp, Telegram, Slack, and Discord. The same agents, same security, same tools — regardless of which app you message from.

### 5. Local-First, Cloud-Optional
Your data stays on your machine. The system runs locally. Cloud LLM providers are optional — you can use Ollama for fully offline operation. No telemetry, no data collection, no accounts required.

## How We're Different

| Approach | Capability OS | Typical AI Agents |
|----------|--------------|-------------------|
| **Execution model** | Iterative agent loop with real tool use | Single-shot prompts or rigid chains |
| **Security** | 3-level progressive classification | All-or-nothing permissions |
| **Agent identity** | Named agents with personality, tools, model | Anonymous, stateless functions |
| **Project awareness** | Workspaces with states, agents, history | No project concept |
| **UI** | Full web app with cyberpunk theme | Terminal-only or API-only |
| **Self-improvement** | Detects gaps, suggests optimizations | Manual iteration |

## Where We're Going

See [ROADMAP.md](ROADMAP.md) for the full plan. Key directions:

- **Proactive agents** that work in the background on scheduled tasks
- **Skill marketplace** for community-contributed tools
- **Multi-agent collaboration** where agents delegate tasks to each other
- **Voice interface** for hands-free interaction
- **Native function calling** for faster, more reliable tool use

## Built With

- **Python** — core engine, security, tools, API server
- **Node.js** — WhatsApp workers (Baileys + Puppeteer)
- **React 18 + Vite** — cyberpunk web frontend
- **Any LLM** — Groq, OpenAI, Anthropic, Gemini, DeepSeek, Ollama

## Philosophy

> Give the AI power. Give the human control. Make security invisible until it matters.

Capability OS is not trying to replace developers or automate away human judgment. It's a force multiplier — an AI teammate that handles the routine so you can focus on the creative.

---

*Created by [Matiasxth](https://github.com/Matiasxth) — 2026*
