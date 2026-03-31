import React, { useCallback, useRef } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  addEdge,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { nodeTypes } from "./CustomNodes";

let nextId = 1;
function getId() {
  return `node_${Date.now()}_${nextId++}`;
}

const DEFAULT_LABELS = {
  trigger: "Trigger",
  tool: "Tool",
  agent: "Agent",
  condition: "Condition",
  loop: "Loop",
  transform: "Transform",
  delay: "Delay",
  output: "Output",
  http: "HTTP Request",
  notification: "Notification",
  script: "Script",
  prompt: "AI Prompt",
  file: "File",
};

export default function WorkflowCanvas({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onNodeSelect,
  onAddNode,
}) {
  const wrapperRef = useRef(null);
  const { screenToFlowPosition } = useReactFlow();

  const handleConnect = useCallback(
    (params) => {
      onConnect(params);
    },
    [onConnect]
  );

  const onDragOver = useCallback((e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (e) => {
      e.preventDefault();
      const type = e.dataTransfer.getData("application/reactflow");
      if (!type) return;

      const position = screenToFlowPosition({
        x: e.clientX,
        y: e.clientY,
      });

      const newNode = {
        id: getId(),
        type,
        position,
        data: { label: DEFAULT_LABELS[type] || type },
      };

      onAddNode(newNode);
    },
    [onAddNode, screenToFlowPosition]
  );

  const onNodeClick = useCallback(
    (_event, node) => {
      if (onNodeSelect) onNodeSelect(node);
    },
    [onNodeSelect]
  );

  const onPaneClick = useCallback(() => {
    if (onNodeSelect) onNodeSelect(null);
  }, [onNodeSelect]);

  return (
    <div className="wf-canvas-wrapper" ref={wrapperRef}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={handleConnect}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        fitView
        deleteKeyCode={["Backspace", "Delete"]}
        proOptions={{ hideAttribution: true }}
        style={{ background: "var(--bg-root)" }}
      >
        <Controls
          style={{
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-md)",
          }}
        />
        <Background color="var(--border)" gap={20} size={1} />
        <MiniMap
          nodeColor={(n) => {
            const accentMap = {
              trigger: "#00ff88",
              tool: "#3b82f6",
              agent: "#06b6d4",
              condition: "#eab308",
              loop: "#a855f7",
              transform: "#f97316",
              delay: "#6b7280",
              output: "#ec4899",
              http: "#10b981",
              notification: "#f43f5e",
              script: "#8b5cf6",
              prompt: "#0ea5e9",
              file: "#d97706",
            };
            return accentMap[n.type] || "#888";
          }}
          maskColor="rgba(6,6,14,0.8)"
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-md)",
          }}
        />
      </ReactFlow>
    </div>
  );
}
