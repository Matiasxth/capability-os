import React, { useState, useEffect, useCallback, useRef } from "react";
import { useNodesState, useEdgesState, addEdge, ReactFlowProvider } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import WorkflowCanvas from "../components/workflow/WorkflowCanvas";
import NodePalette from "../components/workflow/NodePalette";
import NodeConfigPanel from "../components/workflow/NodeConfigPanel";
import sdk from "../sdk";

/* ── Status badge color map ── */
const STATUS_COLORS = {
  idle: "var(--text-muted)",
  saving: "var(--warning)",
  saved: "var(--success)",
  running: "var(--running)",
  success: "var(--success)",
  error: "var(--error)",
};

export default function WorkflowEditor() {
  /* ── Workflow list ── */
  const [workflows, setWorkflows] = useState([]);
  const [selectedId, setSelectedId] = useState(() => sessionStorage.getItem("capos_wf_selected") || null);
  const [wfName, setWfName] = useState("");
  const [wfDesc, setWfDesc] = useState("");

  /* ── Canvas state ── */
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  /* ── UI state ── */
  const [selectedNode, setSelectedNode] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | saving | saved | running | success | error
  const [runResult, setRunResult] = useState(null);
  const [showRunPanel, setShowRunPanel] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");

  /* ── Load workflow list ── */
  const loadWorkflows = useCallback(async () => {
    try {
      const data = await sdk.workflows.list();
      setWorkflows(data.workflows || data || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWorkflows().then(() => {
      const saved = sessionStorage.getItem("capos_wf_selected");
      if (saved) selectWorkflow(saved);
    });
  }, []);

  /* ── Persist selected workflow ID ── */
  useEffect(() => {
    if (selectedId) sessionStorage.setItem("capos_wf_selected", selectedId);
    else sessionStorage.removeItem("capos_wf_selected");
  }, [selectedId]);

  /* ── Select & load a workflow ── */
  const selectWorkflow = useCallback(async (id) => {
    if (!id) {
      setSelectedId(null);
      setNodes([]);
      setEdges([]);
      setWfName("");
      setWfDesc("");
      setSelectedNode(null);
      setRunResult(null);
      setShowRunPanel(false);
      return;
    }
    try {
      const resp = await sdk.workflows.get(id);
      const wf = resp.workflow || resp;
      setSelectedId(id);
      setWfName(wf.name || "");
      setWfDesc(wf.description || "");
      setNodes(wf.nodes || []);
      setEdges(wf.edges || []);
      setSelectedNode(null);
      setRunResult(null);
      setShowRunPanel(false);
      setStatus("idle");
    } catch (e) {
      setError(e.message);
    }
  }, [setNodes, setEdges]);

  /* ── Edge connect handler ── */
  const onConnect = useCallback(
    (params) => setEdges((eds) => addEdge({ ...params, animated: true, style: { stroke: "var(--accent)" } }, eds)),
    [setEdges]
  );

  /* ── Node config update ── */
  const handleNodeDataChange = useCallback(
    (nodeId, newData) => {
      setNodes((nds) =>
        nds.map((n) => (n.id === nodeId ? { ...n, data: newData } : n))
      );
      setSelectedNode((prev) =>
        prev && prev.id === nodeId ? { ...prev, data: newData } : prev
      );
    },
    [setNodes]
  );

  /* ── Save ── */
  const handleSave = useCallback(async () => {
    if (!selectedId) return;
    setStatus("saving");
    try {
      const resp = await sdk.workflows.update(selectedId, {
        name: wfName,
        description: wfDesc,
        nodes,
        edges,
      });
      // Confirm persistence from server response
      const saved = resp.workflow || resp;
      if (saved.nodes) setNodes(saved.nodes);
      if (saved.edges) setEdges(saved.edges);
      setStatus("saved");
      setTimeout(() => setStatus((s) => (s === "saved" ? "idle" : s)), 2000);
    } catch (e) {
      setStatus("error");
      setError(e.message);
    }
  }, [selectedId, wfName, wfDesc, nodes, edges, setNodes, setEdges]);

  /* ── Auto-save after 2s of inactivity ── */
  const autoSaveRef = useRef(null);
  const nodeCountRef = useRef(0);
  useEffect(() => {
    if (!selectedId || nodes.length === 0) return;
    // Skip initial load (don't auto-save when loading from server)
    if (nodeCountRef.current === 0) { nodeCountRef.current = nodes.length; return; }
    nodeCountRef.current = nodes.length;
    if (autoSaveRef.current) clearTimeout(autoSaveRef.current);
    autoSaveRef.current = setTimeout(() => handleSave(), 2000);
    return () => { if (autoSaveRef.current) clearTimeout(autoSaveRef.current); };
  }, [nodes, edges, selectedId]);

  /* ── Run ── */
  const handleRun = useCallback(async () => {
    if (!selectedId) return;
    // Save before run
    await handleSave();
    setStatus("running");
    setRunResult(null);
    setShowRunPanel(true);
    try {
      const result = await sdk.workflows.run(selectedId);
      setRunResult(result);
      // Highlight nodes with execution results
      if (result.results) {
        setNodes(nds => nds.map(n => ({
          ...n,
          data: { ...n.data, _runStatus: result.results[n.id]?.status || null },
        })));
      }
      setStatus(result.status === "success" ? "success" : "error");
      setTimeout(() => setStatus((s) => (s === "success" || s === "error" ? "idle" : s)), 3000);
    } catch (e) {
      setRunResult({ error: e.message });
      setStatus("error");
    }
  }, [selectedId, handleSave, setNodes]);

  /* ── Create workflow ── */
  const handleCreate = useCallback(async () => {
    if (!newName.trim()) return;
    try {
      const resp = await sdk.workflows.create(newName.trim(), newDesc.trim());
      const wf = resp.workflow || resp;
      setNewName("");
      setNewDesc("");
      setCreateDialogOpen(false);
      await loadWorkflows();
      selectWorkflow(wf.id);
    } catch (e) {
      setError(e.message);
    }
  }, [newName, newDesc, loadWorkflows, selectWorkflow]);

  /* ── Delete workflow ── */
  const handleDelete = useCallback(async (id) => {
    if (!window.confirm("Delete this workflow?")) return;
    try {
      await sdk.workflows.delete(id);
      if (selectedId === id) {
        setSelectedId(null);
        setNodes([]);
        setEdges([]);
        setWfName("");
        setWfDesc("");
      }
      await loadWorkflows();
    } catch (e) {
      setError(e.message);
    }
  }, [selectedId, setNodes, setEdges, loadWorkflows]);

  /* ── Keep selectedNode in sync with nodes state ── */
  useEffect(() => {
    if (selectedNode) {
      const current = nodes.find((n) => n.id === selectedNode.id);
      if (current && current.data !== selectedNode.data) {
        setSelectedNode(current);
      }
    }
  }, [nodes, selectedNode]);

  return (
    <div className="wf-editor">
      {/* ── Sidebar: workflow list ── */}
      <aside className="wf-sidebar">
        <div className="wf-sidebar-header">
          <span className="wf-sidebar-title">Workflows</span>
          <button className="wf-btn-sm wf-btn-accent" onClick={() => setCreateDialogOpen(true)}>+ New</button>
        </div>

        {createDialogOpen && (
          <div className="wf-create-dialog">
            <input
              className="wf-cfg-input"
              placeholder="Workflow name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              autoFocus
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            />
            <input
              className="wf-cfg-input"
              placeholder="Description (optional)"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            />
            <div className="wf-create-actions">
              <button className="wf-btn-sm wf-btn-accent" onClick={handleCreate}>Create</button>
              <button className="wf-btn-sm wf-btn-dim" onClick={() => setCreateDialogOpen(false)}>Cancel</button>
            </div>
          </div>
        )}

        <div className="wf-sidebar-list">
          {loading && <div className="wf-sidebar-empty">Loading...</div>}
          {!loading && workflows.length === 0 && (
            <div className="wf-sidebar-empty">No workflows yet</div>
          )}
          {workflows.map((wf) => (
            <div
              key={wf.id}
              className={`wf-sidebar-item ${selectedId === wf.id ? "is-active" : ""}`}
              onClick={() => selectWorkflow(wf.id)}
            >
              <div className="wf-sidebar-item-name">{wf.name}</div>
              {wf.description && <div className="wf-sidebar-item-desc">{wf.description}</div>}
              <button
                className="wf-sidebar-delete"
                onClick={(e) => { e.stopPropagation(); handleDelete(wf.id); }}
                title="Delete"
              >
                x
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* ── Main area ── */}
      <div className="wf-main">
        {/* Top bar */}
        {selectedId && (
          <div className="wf-topbar">
            <input
              className="wf-topbar-name"
              value={wfName}
              onChange={(e) => setWfName(e.target.value)}
              placeholder="Workflow name"
            />
            <div className="wf-topbar-actions">
              <span
                className="wf-status-dot"
                style={{ background: STATUS_COLORS[status] || "var(--text-muted)" }}
                title={status}
              />
              <span className="wf-status-label">{status}</span>
              <button className="wf-btn wf-btn-save" onClick={handleSave}>Save</button>
              <button className="wf-btn wf-btn-run" onClick={handleRun}>Run</button>
            </div>
          </div>
        )}

        {/* Canvas area with palette */}
        <div className="wf-canvas-area">
          <NodePalette />
          <div className="wf-canvas-center">
            {selectedId ? (
              <ReactFlowProvider>
                <WorkflowCanvas
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onConnect={onConnect}
                  onNodeSelect={setSelectedNode}
                  onAddNode={(node) => setNodes((prev) => [...prev, node])}
                />
              </ReactFlowProvider>
            ) : (
              <div className="wf-empty-canvas">
                <div className="wf-empty-icon">&#9881;</div>
                <div className="wf-empty-text">Select or create a workflow to begin</div>
              </div>
            )}
          </div>
          <NodeConfigPanel node={selectedNode} onChange={handleNodeDataChange} />
        </div>

        {/* Run result panel */}
        {showRunPanel && (
          <div className="wf-run-panel">
            <div className="wf-run-panel-header">
              <span>Execution Result</span>
              <button className="wf-btn-sm wf-btn-dim" onClick={() => setShowRunPanel(false)}>Close</button>
            </div>
            <pre className="wf-run-panel-output">
              {runResult ? JSON.stringify(runResult, null, 2) : "Running..."}
            </pre>
          </div>
        )}
      </div>

      {/* Error toast */}
      {error && (
        <div className="wf-error-toast" onClick={() => setError(null)}>
          {error}
        </div>
      )}
    </div>
  );
}
