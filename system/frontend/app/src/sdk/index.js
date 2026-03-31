/**
 * CapOS Frontend SDK — Single gateway to the backend.
 *
 * Usage:
 *   import sdk from "../sdk";
 *   const caps = await sdk.capabilities.list();
 *   for await (const chunk of sdk.capabilities.streamChat("hello", "User")) { ... }
 *   sdk.events.on("execution_complete", (e) => { ... });
 */
import { auth } from "./domains/auth.js";
import { agents } from "./domains/agents.js";
import { capabilities } from "./domains/capabilities.js";
import { integrations } from "./domains/integrations.js";
import { memory } from "./domains/memory.js";
import { system } from "./domains/system.js";
import { workspaces } from "./domains/workspaces.js";
import { mcp } from "./domains/mcp.js";
import { a2a } from "./domains/a2a.js";
import { workflows } from "./domains/workflows.js";
import { skills } from "./domains/skills.js";
import { growth } from "./domains/growth.js";
import { createEventBus } from "./events.js";
import * as session from "./session.js";

const events = createEventBus();

const sdk = {
  auth,
  agents,
  capabilities,
  integrations,
  memory,
  system,
  workspaces,
  mcp,
  a2a,
  workflows,
  skills,
  growth,
  events,
  session,
};

export default sdk;

// Also export domains individually for tree-shaking
export { auth, agents, capabilities, integrations, memory, system, workspaces, mcp, a2a, workflows, skills, growth, events, session };
