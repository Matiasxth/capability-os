/**
 * CapOS WebSocket Event Types — canonical catalog.
 * All events flow through EventBus → WebSocket → sdk.events.
 *
 * Usage:
 *   import { EVENTS } from "./eventTypes";
 *   sdk.events.on(EVENTS.EXECUTION_COMPLETE, (e) => { ... });
 */

/** @enum {string} */
export const EVENTS = {
  // ── Message Reception ──
  TELEGRAM_MESSAGE:    "telegram_message",
  WHATSAPP_MESSAGE:    "whatsapp_message",
  SLACK_MESSAGE:       "slack_message",
  DISCORD_MESSAGE:     "discord_message",

  // ── Session / Execution ──
  SESSION_UPDATED:     "session_updated",
  EXECUTION_COMPLETE:  "execution_complete",

  // ── Settings & Configuration ──
  SETTINGS_UPDATED:    "settings_updated",
  CONFIG_IMPORTED:     "config_imported",
  PREFERENCES_UPDATED: "preferences_updated",

  // ── Workspace ──
  WORKSPACE_CHANGED:   "workspace_changed",

  // ── Memory ──
  MEMORY_CLEARED:      "memory_cleared",

  // ── Integrations ──
  INTEGRATION_CHANGED: "integration_changed",

  // ── Growth & Optimization ──
  GROWTH_UPDATE:       "growth_update",

  // ── MCP ──
  MCP_CHANGED:         "mcp_changed",

  // ── A2A ──
  A2A_CHANGED:         "a2a_changed",

  // ── Browser ──
  BROWSER_CHANGED:     "browser_changed",

  // ── Supervisor ──
  SUPERVISOR_ALERT:    "supervisor_alert",
  SUPERVISOR_ACTION:   "supervisor_action",
  SKILL_CREATED:       "skill_created",

  // ── Scheduler ──
  SCHEDULER_CYCLE:     "scheduler_cycle",

  // ── Auth ──
  AUTH_SETUP_COMPLETE: "auth_setup_complete",

  // ── Errors ──
  ERROR:               "error",

  // ── Processed ──
  WHATSAPP_MESSAGE_PROCESSED: "whatsapp_message_processed",
};

/** Events that indicate history should be reloaded */
export const HISTORY_EVENTS = [
  EVENTS.TELEGRAM_MESSAGE,
  EVENTS.WHATSAPP_MESSAGE,
  EVENTS.SLACK_MESSAGE,
  EVENTS.DISCORD_MESSAGE,
  EVENTS.SESSION_UPDATED,
  EVENTS.EXECUTION_COMPLETE,
  EVENTS.MEMORY_CLEARED,
];

/** Events → user-friendly toast labels */
export const EVENT_LABELS = {
  [EVENTS.SETTINGS_UPDATED]:    "Settings updated",
  [EVENTS.CONFIG_IMPORTED]:     "Config imported",
  [EVENTS.WORKSPACE_CHANGED]:   "Workspace updated",
  [EVENTS.GROWTH_UPDATE]:       "Growth updated",
  [EVENTS.INTEGRATION_CHANGED]: "Integration updated",
  [EVENTS.MCP_CHANGED]:         "MCP updated",
  [EVENTS.A2A_CHANGED]:         "A2A updated",
  [EVENTS.BROWSER_CHANGED]:     "Browser updated",
  [EVENTS.PREFERENCES_UPDATED]: "Preferences saved",
  [EVENTS.MEMORY_CLEARED]:      "Memory cleared",
  [EVENTS.SUPERVISOR_ALERT]:    "Supervisor alert",
  [EVENTS.SKILL_CREATED]:       "Skill created",
  [EVENTS.SCHEDULER_CYCLE]:     "Scheduler cycle",
};

/** Events → ControlCenter section mapping */
export const SECTION_FOR_EVENT = {
  [EVENTS.SETTINGS_UPDATED]:    "llm",
  [EVENTS.CONFIG_IMPORTED]:     "system",
  [EVENTS.WORKSPACE_CHANGED]:   "workspaces",
  [EVENTS.GROWTH_UPDATE]:       "self-improvement",
  [EVENTS.INTEGRATION_CHANGED]: "integrations",
  [EVENTS.MCP_CHANGED]:         "mcp",
  [EVENTS.A2A_CHANGED]:         "a2a",
  [EVENTS.BROWSER_CHANGED]:     "browser",
  [EVENTS.MEMORY_CLEARED]:      "memory",
  [EVENTS.PREFERENCES_UPDATED]: "memory",
  [EVENTS.SUPERVISOR_ALERT]:    "supervisor",
  [EVENTS.SKILL_CREATED]:       "skills",
  [EVENTS.SCHEDULER_CYCLE]:     "scheduler",
};
