"""Execute a workflow definition in topological order.

Supports 13 node types: trigger, tool, agent, condition, delay, transform,
output, loop, http, notification, script, prompt, file.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from string import Template
from typing import Any

logger = logging.getLogger(__name__)


class WorkflowExecutionError(RuntimeError):
    """Raised when a workflow execution fails fatally."""


class WorkflowExecutor:
    """Executes a workflow graph by walking nodes in topological order."""

    def __init__(self, tool_runtime: Any, agent_loop: Any | None = None, llm: Any | None = None) -> None:
        self._tool_runtime = tool_runtime
        self._agent_loop = agent_loop
        self._llm = llm

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def execute(self, workflow: dict[str, Any]) -> dict[str, Any]:
        """Run a workflow end-to-end.

        Returns::

            {
                "status": "success" | "error",
                "results": {node_id: result, ...},
                "error": "...",           # only if status == "error"
                "failed_node": "n3",      # only if status == "error"
                "duration_ms": 123,
            }
        """
        t0 = time.monotonic()
        nodes_by_id: dict[str, dict[str, Any]] = {
            n["id"]: n for n in workflow.get("nodes", [])
        }
        edges = workflow.get("edges", [])

        try:
            order = self._topological_sort(nodes_by_id, edges)
        except WorkflowExecutionError as exc:
            return {
                "status": "error",
                "results": {},
                "error": str(exc),
                "duration_ms": self._elapsed(t0),
            }

        results: dict[str, Any] = {}
        context: dict[str, Any] = {
            "previous_results": results,
            "variables": {},
        }

        parallel = workflow.get("parallel", False)

        if parallel:
            return self._execute_parallel(nodes_by_id, edges, context, t0)

        for node_id in order:
            node = nodes_by_id[node_id]
            try:
                result = self._execute_node(node, context, edges)
                results[node_id] = result
            except Exception as exc:
                logger.exception("Workflow node %s failed", node_id)
                results[node_id] = {"error": str(exc)}
                return {
                    "status": "error",
                    "results": results,
                    "error": str(exc),
                    "failed_node": node_id,
                    "duration_ms": self._elapsed(t0),
                }

        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("workflow_completed", {"workflow_id": workflow.get("id", ""), "status": "success", "node_count": len(results), "duration_ms": self._elapsed(t0)})
        except Exception:
            pass
        return {
            "status": "success",
            "results": results,
            "duration_ms": self._elapsed(t0),
        }

    def _execute_parallel(
        self,
        nodes_by_id: dict[str, dict[str, Any]],
        edges: list[dict[str, Any]],
        context: dict[str, Any],
        t0: float,
    ) -> dict[str, Any]:
        """Execute workflow with level-based parallelism.

        Nodes at the same topological level (all predecessors completed)
        run concurrently. Condition nodes always run sequentially.
        """
        results = context["previous_results"]

        # Build adjacency and in-degree
        in_degree: dict[str, int] = {nid: 0 for nid in nodes_by_id}
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            adjacency[edge["source"]].append(edge["target"])
            in_degree[edge["target"]] = in_degree.get(edge["target"], 0) + 1

        # Process level by level
        ready = [nid for nid, deg in in_degree.items() if deg == 0]

        while ready:
            # Separate condition nodes (must run sequentially)
            parallel_batch = []
            sequential_batch = []
            for nid in ready:
                node = nodes_by_id[nid]
                if node.get("type") == "condition":
                    sequential_batch.append(nid)
                else:
                    parallel_batch.append(nid)

            # Run parallel batch concurrently
            if len(parallel_batch) > 1:
                with ThreadPoolExecutor(max_workers=min(len(parallel_batch), 8)) as pool:
                    futures = {
                        pool.submit(self._execute_node, nodes_by_id[nid], context, edges): nid
                        for nid in parallel_batch
                    }
                    for future in as_completed(futures):
                        nid = futures[future]
                        try:
                            results[nid] = future.result()
                        except Exception as exc:
                            results[nid] = {"error": str(exc)}
                            return {
                                "status": "error", "results": results,
                                "error": str(exc), "failed_node": nid,
                                "duration_ms": self._elapsed(t0),
                            }
            elif parallel_batch:
                nid = parallel_batch[0]
                try:
                    results[nid] = self._execute_node(nodes_by_id[nid], context, edges)
                except Exception as exc:
                    results[nid] = {"error": str(exc)}
                    return {
                        "status": "error", "results": results,
                        "error": str(exc), "failed_node": nid,
                        "duration_ms": self._elapsed(t0),
                    }

            # Run sequential batch one by one
            for nid in sequential_batch:
                try:
                    results[nid] = self._execute_node(nodes_by_id[nid], context, edges)
                except Exception as exc:
                    results[nid] = {"error": str(exc)}
                    return {
                        "status": "error", "results": results,
                        "error": str(exc), "failed_node": nid,
                        "duration_ms": self._elapsed(t0),
                    }

            # Find next level: decrease in-degree for successors
            next_ready = []
            for nid in ready:
                for neighbor in adjacency.get(nid, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_ready.append(neighbor)
            ready = next_ready

        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("workflow_completed", {"workflow_id": "", "status": "success", "node_count": len(results), "duration_ms": self._elapsed(t0)})
        except Exception:
            pass
        return {
            "status": "success",
            "results": results,
            "duration_ms": self._elapsed(t0),
        }

    # ------------------------------------------------------------------
    # Node execution
    # ------------------------------------------------------------------

    def _execute_node(
        self,
        node: dict[str, Any],
        context: dict[str, Any],
        edges: list[dict[str, Any]],
    ) -> Any:
        ntype = node.get("type", "trigger")
        data = node.get("data", {})

        if ntype == "trigger":
            return self._exec_trigger(data)
        elif ntype == "tool":
            return self._exec_tool(data, context)
        elif ntype == "agent":
            return self._exec_agent(data, context)
        elif ntype == "condition":
            return self._exec_condition(node, data, context, edges)
        elif ntype == "delay":
            return self._exec_delay(data)
        elif ntype == "transform":
            return self._exec_transform(data, context)
        elif ntype == "output":
            return self._exec_output(data, context)
        elif ntype == "loop":
            return self._exec_loop(node, data, context, edges)
        elif ntype == "http":
            return self._exec_http(data, context)
        elif ntype == "notification":
            return self._exec_notification(data, context)
        elif ntype == "script":
            return self._exec_script(data, context)
        elif ntype == "prompt":
            return self._exec_prompt(data, context)
        elif ntype == "file":
            return self._exec_file(data, context)
        else:
            logger.warning("Unknown node type: %s — treating as no-op", ntype)
            return {"skipped": True, "reason": f"unknown type '{ntype}'"}

    def _exec_trigger(self, data: dict[str, Any]) -> dict[str, Any]:
        """Trigger nodes are entry points — no-op."""
        return {"triggered": True, "schedule": data.get("schedule", "")}

    def _exec_tool(self, data: dict[str, Any], context: dict[str, Any]) -> Any:
        """Execute a registered tool via the ToolRuntime."""
        tool_id = data.get("tool_id", "")
        params = dict(data.get("params", {}))
        # Allow params to reference previous results via $node_id placeholders
        params = self._resolve_placeholders(params, context)
        if not tool_id:
            raise WorkflowExecutionError("Tool node missing 'tool_id'")
        if self._tool_runtime is None:
            raise WorkflowExecutionError("ToolRuntime not available")
        return self._tool_runtime.execute(tool_id, params)

    def _exec_agent(self, data: dict[str, Any], context: dict[str, Any]) -> Any:
        """Send a message to the agent loop and return its response."""
        message = data.get("message", "")
        message = self._apply_template(message, context)
        if not message:
            raise WorkflowExecutionError("Agent node missing 'message'")
        if self._agent_loop is None:
            raise WorkflowExecutionError("AgentLoop not available")
        return self._agent_loop.run(message)

    def _exec_condition(
        self,
        node: dict[str, Any],
        data: dict[str, Any],
        context: dict[str, Any],
        edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Evaluate an expression on previous results.

        The condition ``data`` should contain:
        - ``expression``: a simple Python-safe expression referencing ``result``
        - ``source_node``: the node_id whose result to evaluate

        Returns ``{"branch": "true_path" | "false_path", "value": <eval result>}``.
        """
        source_node = data.get("source_node", "")
        expression = data.get("expression", "True")
        result = context["previous_results"].get(source_node)
        try:
            from system.core.strategy.safe_expression import safe_eval
            outcome = bool(safe_eval(expression, {"result": result}))
        except Exception as exc:
            logger.warning("Condition expression failed: %s", exc)
            outcome = False
        return {"branch": "true_path" if outcome else "false_path", "value": outcome}

    def _exec_delay(self, data: dict[str, Any]) -> dict[str, Any]:
        """Sleep for a specified number of seconds."""
        seconds = float(data.get("seconds", 0))
        if seconds > 0:
            time.sleep(seconds)
        return {"delayed": True, "seconds": seconds}

    def _exec_transform(self, data: dict[str, Any], context: dict[str, Any]) -> Any:
        """Apply a simple template mapping to the data.

        ``data.mapping`` is a dict where values are ``$node_id`` style
        placeholders resolved from previous results.
        """
        mapping = data.get("mapping", {})
        resolved: dict[str, Any] = {}
        for key, tpl in mapping.items():
            if isinstance(tpl, str) and tpl.startswith("$"):
                ref = tpl[1:]
                resolved[key] = context["previous_results"].get(ref, tpl)
            else:
                resolved[key] = tpl
        return resolved

    def _exec_output(self, data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Format a result string using a template."""
        template = data.get("template", "")
        text = self._apply_template(template, context)
        return {"text": text}

    # ------------------------------------------------------------------
    # New node type handlers
    # ------------------------------------------------------------------

    def _exec_loop(self, node: dict, data: dict, context: dict, edges: list) -> Any:
        """Iterate over a collection or fixed count."""
        iterations = data.get("iterations")
        collection_expr = data.get("collection", "")
        results = []
        if collection_expr:
            try:
                from system.core.strategy.safe_expression import safe_eval
                items = safe_eval(collection_expr, {"result": context.get("previous_result")})
                if hasattr(items, "__iter__"):
                    results = list(items)
            except Exception as exc:
                logger.warning("Loop collection eval failed: %s", exc)
        elif iterations:
            results = list(range(int(iterations)))
        return {"items": results, "count": len(results)}

    def _exec_http(self, data: dict, context: dict) -> dict:
        """Make an HTTP request."""
        import json as _json
        from urllib.request import Request, urlopen
        method = data.get("method", "GET")
        url = self._apply_template(data.get("url", ""), context)
        if not url:
            raise WorkflowExecutionError("HTTP node missing 'url'")
        headers = {}
        if data.get("headers_json"):
            try:
                headers = _json.loads(data["headers_json"])
            except Exception:
                pass
        body = None
        if data.get("body_json"):
            body_str = self._apply_template(data["body_json"], context)
            body = body_str.encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        req = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                try:
                    return {"status": resp.status, "body": _json.loads(content)}
                except Exception:
                    return {"status": resp.status, "body": content}
        except Exception as exc:
            return {"status": 0, "error": str(exc)}

    def _exec_notification(self, data: dict, context: dict) -> dict:
        """Send notification to a channel."""
        channel = data.get("channel", "ui")
        message = self._apply_template(data.get("message", ""), context)
        if not message:
            return {"sent": False, "reason": "empty message"}
        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("notification", {"channel": channel, "message": message, "recipient": data.get("recipient")})
        except Exception:
            pass
        return {"sent": True, "channel": channel, "message": message}

    def _exec_script(self, data: dict, context: dict) -> Any:
        """Execute a script in sandbox."""
        language = data.get("language", "python")
        code = data.get("code", "")
        if not code:
            raise WorkflowExecutionError("Script node missing 'code'")
        prev = context.get("previous_result", {})
        if language == "python":
            safe_globals = {"__builtins__": {}, "result": prev, "str": str, "int": int, "float": float, "list": list, "dict": dict, "len": len, "range": range, "print": lambda *a: None}
            local_vars = {}
            try:
                exec(code, safe_globals, local_vars)
                return local_vars.get("output", local_vars) or {"executed": True}
            except Exception as exc:
                return {"error": str(exc)}
        return {"error": f"Unsupported language: {language}"}

    def _exec_prompt(self, data: dict, context: dict) -> dict:
        """Send prompt to LLM."""
        prompt = self._apply_template(data.get("prompt", ""), context)
        if not prompt:
            raise WorkflowExecutionError("Prompt node missing 'prompt'")
        if self._llm is None:
            raise WorkflowExecutionError("LLM client not available")
        try:
            response = self._llm.chat(prompt, system=data.get("system_prompt"), model=data.get("model"))
            return {"response": response.get("content") or response.get("text") or str(response)}
        except Exception as exc:
            return {"error": str(exc)}

    def _exec_file(self, data: dict, context: dict) -> dict:
        """Read/write/append file operations."""
        from pathlib import Path
        operation = data.get("operation", "read")
        path_str = self._apply_template(data.get("path", ""), context)
        if not path_str:
            raise WorkflowExecutionError("File node missing 'path'")
        path = Path(path_str)
        try:
            if operation == "read":
                return {"content": path.read_text(encoding="utf-8"), "path": str(path)}
            elif operation == "write":
                content = self._apply_template(data.get("content", ""), context)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                return {"written": True, "path": str(path), "bytes": len(content)}
            elif operation == "append":
                content = self._apply_template(data.get("content", ""), context)
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(content)
                return {"appended": True, "path": str(path), "bytes": len(content)}
            elif operation == "list":
                if path.is_dir():
                    items = [{"name": p.name, "is_dir": p.is_dir()} for p in sorted(path.iterdir())]
                    return {"items": items, "count": len(items), "path": str(path)}
                return {"error": f"Not a directory: {path}"}
            else:
                return {"error": f"Unknown operation: {operation}"}
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _elapsed(t0: float) -> int:
        return int((time.monotonic() - t0) * 1000)

    @staticmethod
    def _topological_sort(
        nodes_by_id: dict[str, dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> list[str]:
        """Kahn's algorithm — returns node ids in execution order."""
        in_degree: dict[str, int] = defaultdict(int)
        adjacency: dict[str, list[str]] = defaultdict(list)

        for nid in nodes_by_id:
            in_degree.setdefault(nid, 0)

        for edge in edges:
            src = edge["source"]
            tgt = edge["target"]
            adjacency[src].append(tgt)
            in_degree[tgt] = in_degree.get(tgt, 0) + 1

        queue: deque[str] = deque(
            nid for nid, deg in in_degree.items() if deg == 0
        )
        order: list[str] = []

        while queue:
            nid = queue.popleft()
            order.append(nid)
            for neighbor in adjacency.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(nodes_by_id):
            raise WorkflowExecutionError(
                "Workflow contains a cycle — cannot determine execution order"
            )
        return order

    @staticmethod
    def _resolve_placeholders(
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Replace string values like ``$n1`` with results of node n1."""
        resolved = {}
        for key, val in params.items():
            if isinstance(val, str) and val.startswith("$"):
                ref = val[1:]
                resolved[key] = context["previous_results"].get(ref, val)
            else:
                resolved[key] = val
        return resolved

    @staticmethod
    def _apply_template(template: str, context: dict[str, Any]) -> str:
        """Safe template substitution using $node_id references."""
        if not template:
            return template
        flat: dict[str, str] = {}
        for nid, res in context["previous_results"].items():
            flat[nid] = str(res) if not isinstance(res, str) else res
        for vk, vv in context.get("variables", {}).items():
            flat[vk] = str(vv) if not isinstance(vv, str) else vv
        try:
            return Template(template).safe_substitute(flat)
        except Exception:
            return template
