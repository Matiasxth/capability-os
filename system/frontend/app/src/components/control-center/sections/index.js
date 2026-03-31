import SystemSection from "./SystemSection";
import WorkspacesSection from "./WorkspacesSection";
import LLMSection from "./LLMSection";
import MetricsSection from "./MetricsSection";
import OptimizeSection from "./OptimizeSection";
import AutoGrowthSection from "./AutoGrowthSection";
import MCPSection from "./MCPSection";
import A2ASection from "./A2ASection";
import MemorySection from "./MemorySection";
import IntegrationsSection from "./IntegrationsSection";
import BrowserSection from "./BrowserSection";
import SkillsSection from "./SkillsSection";
import SupervisorSection from "./SupervisorSection";
import SchedulerSection from "./SchedulerSection";
import AgentsSection from "./AgentsSection";
import ProjectStatesSection from "./ProjectStatesSection";

const sections = {
  "system": SystemSection,
  "workspaces": WorkspacesSection,
  "llm": LLMSection,
  "metrics": MetricsSection,
  "self-improvement": OptimizeSection,
  "auto-growth": AutoGrowthSection,
  "mcp": MCPSection,
  "a2a": A2ASection,
  "memory": MemorySection,
  "integrations": IntegrationsSection,
  "browser": BrowserSection,
  "skills": SkillsSection,
  "supervisor": SupervisorSection,
  "scheduler": SchedulerSection,
  "agents": AgentsSection,
  "project-states": ProjectStatesSection,
};

export default sections;
