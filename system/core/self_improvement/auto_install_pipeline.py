"""End-to-end pipeline: gap → analyze → generate → validate → propose → install.

Orchestrates all self-improvement components into a single flow.

Rule: ``process_gap`` only creates PROPOSALS.  ``install_proposal`` only
runs when the user explicitly approves.  Nothing is installed automatically.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

from system.capabilities.registry import CapabilityRegistry
from system.core.self_improvement.capability_generator import CapabilityGenerator
from system.core.self_improvement.runtime_analyzer import RuntimeAnalyzer
from system.core.self_improvement.tool_code_generator import ToolCodeGenerator
from system.core.self_improvement.tool_validator import ToolValidator
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime


class AutoInstallPipeline:
    """Orchestrates gap resolution from analysis to installation."""

    def __init__(
        self,
        runtime_analyzer: RuntimeAnalyzer,
        capability_generator: CapabilityGenerator,
        tool_code_generator: ToolCodeGenerator,
        tool_validator: ToolValidator,
        tool_registry: ToolRegistry,
        tool_runtime: ToolRuntime,
        capability_registry: CapabilityRegistry,
        proposals_dir: str | Path,
    ):
        self._analyzer = runtime_analyzer
        self._cap_gen = capability_generator
        self._code_gen = tool_code_generator
        self._validator = tool_validator
        self._tool_registry = tool_registry
        self._tool_runtime = tool_runtime
        self._cap_registry = capability_registry
        self._proposals_dir = Path(proposals_dir).resolve()
        self._proposals: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Phase 1: analyze + generate proposal
    # ------------------------------------------------------------------

    def process_gap(self, gap: dict[str, Any]) -> dict[str, Any]:
        """Analyze a gap and produce a proposal (never installs).

        Returns a proposal dict with strategy, contract, code, validated status.
        """
        analysis = self._analyzer.analyze(gap)
        strategy = analysis["strategy"]
        proposal_id = f"prop_{uuid4().hex[:8]}"

        # Strategies that don't need code generation
        if strategy in ("existing_tool", "mcp", "browser", "cli"):
            proposal = {
                "proposal_id": proposal_id,
                "gap_id": gap.get("id"),
                "strategy": strategy,
                "reason": analysis["reason"],
                "suggestion": analysis["suggestion"],
                "confidence": analysis["confidence"],
                "contract": None,
                "code": None,
                "runtime": None,
                "validated": False,
            }
            self._save_proposal(proposal)
            return deepcopy(proposal)

        if strategy == "not_implementable":
            proposal = {
                "proposal_id": proposal_id,
                "gap_id": gap.get("id"),
                "strategy": "not_implementable",
                "reason": analysis["reason"],
                "suggestion": analysis["suggestion"],
                "confidence": analysis["confidence"],
                "contract": None,
                "code": None,
                "runtime": None,
                "validated": False,
            }
            self._save_proposal(proposal)
            return deepcopy(proposal)

        # Strategy: python or nodejs — generate code
        runtime = strategy  # "python" or "nodejs"

        # Generate capability contract
        cap_result = self._cap_gen.generate_proposal(gap)
        contract = cap_result.get("contract", {})

        # Generate tool code
        code_result = self._code_gen.generate(gap, contract, runtime=runtime)
        code = code_result["code"]

        # Validate in sandbox
        val_result = self._validator.validate(code, contract, runtime=runtime)

        proposal = {
            "proposal_id": proposal_id,
            "gap_id": gap.get("id"),
            "strategy": runtime,
            "reason": analysis["reason"],
            "suggestion": analysis["suggestion"],
            "confidence": analysis["confidence"],
            "contract": contract,
            "code": val_result["code"],  # may be corrected version
            "runtime": runtime,
            "validated": val_result["validated"],
            "validation_attempts": val_result["attempts"],
            "validation_error": val_result["error"],
            "test_output": val_result.get("test_output", {}),
        }
        self._save_proposal(proposal)
        return deepcopy(proposal)

    # ------------------------------------------------------------------
    # Phase 2: install (only when user approves)
    # ------------------------------------------------------------------

    def install_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Install an approved proposal: register tool + capability.

        Returns ``{installed, tool_id, capability_id}`` or raises.
        """
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            raise ValueError(f"Proposal '{proposal_id}' not found.")

        if not proposal.get("validated"):
            raise ValueError(f"Proposal '{proposal_id}' is not validated — cannot install.")

        contract = proposal.get("contract", {})
        code = proposal.get("code", "")
        runtime = proposal.get("runtime", "python")
        cap_id = contract.get("id", f"generated_{proposal_id}")

        # Build tool contract — prefix with "execution_" for schema compliance
        tool_id = f"execution_{cap_id}"
        tool_contract = self._build_tool_contract(tool_id, contract)

        # Register tool contract
        try:
            self._tool_registry.register(tool_contract, source=f"auto_install:{proposal_id}")
        except Exception:
            pass  # may already be registered

        # Register handler
        self._register_handler(tool_id, code, runtime)

        # Register capability contract (update action to point to our tool)
        cap_contract = deepcopy(contract)
        if cap_contract.get("strategy", {}).get("steps"):
            for step in cap_contract["strategy"]["steps"]:
                step["action"] = tool_id
            cap_contract["requirements"]["tools"] = [tool_id]
        cap_contract["lifecycle"]["status"] = "ready"

        try:
            self._cap_registry.register(cap_contract, source=f"auto_install:{proposal_id}")
        except Exception:
            pass  # may already be registered

        # Persist code to disk
        self._persist_code(tool_id, code, runtime)

        return {
            "installed": True,
            "tool_id": tool_id,
            "capability_id": cap_id,
            "proposal_id": proposal_id,
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        if proposal_id in self._proposals:
            return deepcopy(self._proposals[proposal_id])
        path = self._proposals_dir / f"{proposal_id}.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def list_proposals(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if self._proposals_dir.exists():
            for p in sorted(self._proposals_dir.glob("prop_*.json")):
                try:
                    results.append(json.loads(p.read_text(encoding="utf-8")))
                except (json.JSONDecodeError, OSError):
                    pass
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _save_proposal(self, proposal: dict[str, Any]) -> None:
        self._proposals[proposal["proposal_id"]] = proposal
        try:
            self._proposals_dir.mkdir(parents=True, exist_ok=True)
            path = self._proposals_dir / f"{proposal['proposal_id']}.json"
            path.write_text(json.dumps(proposal, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _build_tool_contract(tool_id: str, cap_contract: dict[str, Any]) -> dict[str, Any]:
        inputs = deepcopy(cap_contract.get("inputs", {}))
        outputs = deepcopy(cap_contract.get("outputs", {"status": {"type": "string"}}))
        return {
            "id": tool_id,
            "name": cap_contract.get("name", tool_id),
            "category": "execution",
            "description": cap_contract.get("description", tool_id),
            "inputs": inputs,
            "outputs": outputs,
            "constraints": {"timeout_ms": 30000, "allowlist": [], "workspace_only": False},
            "safety": {"level": "medium", "requires_confirmation": False},
            "lifecycle": {"version": "1.0.0", "status": "ready"},
        }

    def _register_handler(self, tool_id: str, code: str, runtime: str) -> None:
        """Register a ToolRuntime handler that executes the generated code."""
        if runtime == "nodejs":
            from system.core.self_improvement.nodejs_sandbox import NodejsSandbox
            sandbox = NodejsSandbox(self._proposals_dir.parent / "sandbox")

            def _handler(params: dict[str, Any]) -> dict[str, Any]:
                result = sandbox.execute(code, params)
                if not result["success"]:
                    raise RuntimeError(result["error"])
                return result["output"]
        else:
            from system.core.self_improvement.python_sandbox import PythonSandbox
            sandbox = PythonSandbox(self._proposals_dir.parent / "sandbox")

            def _handler(params: dict[str, Any]) -> dict[str, Any]:
                result = sandbox.execute(code, params)
                if not result["success"]:
                    raise RuntimeError(result["error"])
                return result["output"]

        self._tool_runtime.register_handler(tool_id, _handler)

    def _persist_code(self, tool_id: str, code: str, runtime: str) -> None:
        try:
            code_dir = self._proposals_dir.parent / "generated_tools"
            code_dir.mkdir(parents=True, exist_ok=True)
            ext = "js" if runtime == "nodejs" else "py"
            (code_dir / f"{tool_id}.{ext}").write_text(code, encoding="utf-8")
        except OSError:
            pass
