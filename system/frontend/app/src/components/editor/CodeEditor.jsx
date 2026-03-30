import React, { useRef, useCallback } from "react";
import Editor from "@monaco-editor/react";

export default function CodeEditor({ file, onChange, onSave }) {
  const editorRef = useRef(null);

  const handleMount = useCallback((editor) => {
    editorRef.current = editor;
    // Ctrl+S to save
    editor.addCommand(2048 | 49 /* KeyS */, () => {
      if (onSave) onSave(editor.getValue());
    });
  }, [onSave]);

  if (!file) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--text-muted)", fontSize: 14 }}>
        Select a file to edit
      </div>
    );
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "6px 12px", background: "var(--bg-elevated)", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8, fontSize: 12, flexShrink: 0 }}>
        <span style={{ color: "var(--text)" }}>{file.path}</span>
        <span style={{ color: "var(--text-muted)", fontSize: 10 }}>{file.language}</span>
        <span style={{ flex: 1 }} />
        {onSave && <button onClick={() => onSave(editorRef.current?.getValue())} style={{ height: 24, fontSize: 10, padding: "0 10px" }}>Save (Ctrl+S)</button>}
      </div>
      <div style={{ flex: 1 }}>
        <Editor
          height="100%"
          language={file.language || "plaintext"}
          value={file.content || ""}
          theme="vs-dark"
          onChange={onChange}
          onMount={handleMount}
          options={{
            fontSize: 13,
            minimap: { enabled: false },
            lineNumbers: "on",
            wordWrap: "on",
            scrollBeyondLastLine: false,
            automaticLayout: true,
            tabSize: 2,
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          }}
        />
      </div>
    </div>
  );
}
