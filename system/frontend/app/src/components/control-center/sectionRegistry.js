/**
 * Section Registry — each CC section is a lazy-loaded component.
 * To add a new section: create the file in sections/ and add one entry here.
 */
export const SECTION_REGISTRY = [
  { id: "system",           label: "System",       keywords: ["health", "status", "export", "import", "config"] },
  { id: "workspaces",       label: "Workspaces",   keywords: ["path", "folder", "project", "default"] },
  { id: "llm",              label: "LLM",          keywords: ["model", "provider", "api key", "groq", "ollama", "openai", "anthropic", "gemini", "deepseek"] },
  { id: "metrics",          label: "Metrics",      keywords: ["success rate", "execution", "performance", "duration"] },
  { id: "self-improvement", label: "Optimize",     keywords: ["gaps", "optimize", "strategy", "improvement"] },
  { id: "auto-growth",      label: "Auto-Growth",  keywords: ["proposal", "generate", "auto", "capability"] },
  { id: "mcp",              label: "MCP",          keywords: ["server", "tool", "protocol", "bridge"] },
  { id: "a2a",              label: "A2A",          keywords: ["agent", "delegate", "task", "skill"] },
  { id: "memory",           label: "Memory",       keywords: ["semantic", "search", "context", "compact", "clear"] },
  { id: "integrations",     label: "Integrations", keywords: ["telegram", "whatsapp", "slack", "discord", "channel"] },
  { id: "browser",          label: "Browser",      keywords: ["cdp", "chrome", "worker", "session"] },
  { id: "skills",           label: "Skills",       keywords: ["install", "uninstall", "package", "skill"] },
  { id: "agents",            label: "Agents",         keywords: ["agent", "bot", "assistant", "create", "personality"] },
  { id: "project-states",   label: "Project States", keywords: ["status", "icon", "label", "state", "project"] },
];
