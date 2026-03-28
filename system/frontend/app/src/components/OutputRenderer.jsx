import React, { useState } from "react";

/* ── Icon map by file extension ── */
const EXT_ICONS = {
  py: "\uD83D\uDC0D", pyw: "\uD83D\uDC0D",
  jsx: "\u269B", tsx: "\u269B",
  js: "\uD83D\uDCD8", ts: "\uD83D\uDCD8", mjs: "\uD83D\uDCD8",
  json: "{}", jsonc: "{}",
  css: "\uD83C\uDFA8", scss: "\uD83C\uDFA8", less: "\uD83C\uDFA8",
  html: "\uD83C\uDF10", htm: "\uD83C\uDF10", xml: "\uD83C\uDF10", svg: "\uD83C\uDF10",
  md: "\uD83D\uDCC4", txt: "\uD83D\uDCC4", pdf: "\uD83D\uDCC4", doc: "\uD83D\uDCC4", docx: "\uD83D\uDCC4",
  png: "\uD83D\uDDBC", jpg: "\uD83D\uDDBC", jpeg: "\uD83D\uDDBC", gif: "\uD83D\uDDBC", ico: "\uD83D\uDDBC", webp: "\uD83D\uDDBC",
  zip: "\uD83D\uDCE6", tar: "\uD83D\uDCE6", gz: "\uD83D\uDCE6", rar: "\uD83D\uDCE6",
  sh: "\uD83D\uDCBB", bash: "\uD83D\uDCBB", bat: "\uD83D\uDCBB", cmd: "\uD83D\uDCBB", ps1: "\uD83D\uDCBB",
  yaml: "\u2699", yml: "\u2699", toml: "\u2699", ini: "\u2699", env: "\u2699", cfg: "\u2699",
  lock: "\uD83D\uDD12",
};
const DIR_ICON = "\uD83D\uDCC1";
const FILE_ICON = "\uD83D\uDCC4";

function fileIcon(name, type) {
  if (type === "directory") return DIR_ICON;
  const ext = (name || "").split(".").pop().toLowerCase();
  return EXT_ICONS[ext] || FILE_ICON;
}

function fmtSize(bytes) {
  if (bytes == null || bytes === undefined) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ── Shared inline styles ── */
const S = {
  card: {
    background: "#111114",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: 10,
    overflow: "hidden",
    marginTop: 6,
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "10px 14px",
    borderBottom: "1px solid rgba(255,255,255,0.04)",
    fontSize: 12,
    color: "#888",
    fontFamily: "var(--font-mono)",
  },
  row: (isDir) => ({
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "7px 14px",
    fontSize: 13,
    cursor: isDir ? "pointer" : "default",
    transition: "background .1s",
    borderBottom: "1px solid rgba(255,255,255,0.02)",
  }),
  rowHover: { background: "rgba(255,255,255,0.03)" },
  icon: { width: 20, textAlign: "center", flexShrink: 0, fontSize: 14 },
  name: (isDir) => ({
    flex: 1,
    color: isDir ? "#00ff88" : "#d0d0d0",
    fontWeight: isDir ? 500 : 400,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  }),
  size: { color: "#555", fontSize: 11, fontFamily: "var(--font-mono)", minWidth: 60, textAlign: "right" },
  arrow: { color: "#333", fontSize: 12 },
  footer: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px 14px",
    fontSize: 11,
    color: "#555",
    borderTop: "1px solid rgba(255,255,255,0.04)",
  },
  toggleBtn: {
    background: "none",
    border: "none",
    color: "#00ff88",
    fontSize: 11,
    cursor: "pointer",
    padding: "2px 0",
    fontFamily: "inherit",
  },
  crumb: {
    background: "none",
    border: "none",
    color: "#888",
    fontSize: 12,
    cursor: "pointer",
    padding: "0 1px",
    fontFamily: "var(--font-mono)",
  },
  crumbSep: { color: "#444", margin: "0 2px", fontSize: 11 },
  crumbActive: { color: "#d0d0d0" },
  pre: {
    margin: 0,
    padding: "12px 14px",
    fontSize: 12,
    lineHeight: 1.5,
    color: "#c8c8c8",
    fontFamily: "var(--font-mono)",
    overflowX: "auto",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  terminal: {
    margin: 0,
    padding: "12px 14px",
    fontSize: 12,
    lineHeight: 1.5,
    color: "#a0d0a0",
    fontFamily: "var(--font-mono)",
    background: "#0a0a0c",
    overflowX: "auto",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
};

/* ── Breadcrumb path ── */
function PathBreadcrumb({ fullPath, onNavigate }) {
  if (!fullPath) return null;
  // Normalize separators
  const normalized = fullPath.replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);

  // Handle Windows drive letter: "C:" → "C:\\"
  const isWindows = /^[a-zA-Z]:/.test(fullPath);

  const segments = [];
  for (let i = 0; i < parts.length; i++) {
    let segPath;
    if (isWindows) {
      segPath = parts.slice(0, i + 1).join("\\");
      if (i === 0) segPath += "\\"; // C:\
    } else {
      segPath = "/" + parts.slice(0, i + 1).join("/");
    }
    segments.push({ label: parts[i], path: segPath });
  }

  return (
    <span>
      {segments.map((seg, i) => (
        <span key={i}>
          {i > 0 && <span style={S.crumbSep}>&gt;</span>}
          <button
            style={{
              ...S.crumb,
              ...(i === segments.length - 1 ? S.crumbActive : {}),
            }}
            onClick={() => onNavigate(seg.path)}
            title={seg.path}
          >
            {seg.label}
          </button>
        </span>
      ))}
    </span>
  );
}

/* ── File row ── */
function FileRow({ item, onDirClick }) {
  const [hov, setHov] = useState(false);
  const isDir = item.type === "directory";
  const icon = fileIcon(item.name, item.type);

  return (
    <div
      style={{ ...S.row(isDir), ...(hov ? S.rowHover : {}) }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      onClick={isDir ? () => onDirClick(item.path || item.name) : undefined}
    >
      <span style={S.icon}>{icon}</span>
      <span style={S.name(isDir)}>{item.name}</span>
      {!isDir && <span style={S.size}>{fmtSize(item.size_bytes)}</span>}
      {isDir && <span style={S.arrow}>&rsaquo;</span>}
    </div>
  );
}

/* ── Directory listing output ── */
function DirectoryOutput({ output, onNavigate }) {
  const [expanded, setExpanded] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const items = output.items || [];
  const dirPath = output.path || output.project_path || "";
  const LIMIT = 8;
  const visible = expanded ? items : items.slice(0, LIMIT);
  const hidden = items.length - LIMIT;
  const dirs = items.filter((i) => i.type === "directory").length;
  const files = items.length - dirs;

  if (showJson) {
    return (
      <div style={S.card}>
        <div style={S.footer}>
          <span>{items.length} items</span>
          <button style={S.toggleBtn} onClick={() => setShowJson(false)}>
            Explorer view
          </button>
        </div>
        <pre style={S.pre}>{JSON.stringify(output, null, 2)}</pre>
      </div>
    );
  }

  return (
    <div style={S.card}>
      <div style={S.header}>
        <span style={{ fontSize: 14 }}>{DIR_ICON}</span>
        <PathBreadcrumb fullPath={dirPath} onNavigate={onNavigate} />
      </div>
      {visible.map((item, i) => (
        <FileRow key={i} item={item} onDirClick={onNavigate} />
      ))}
      <div style={S.footer}>
        <span>
          {files} file{files !== 1 ? "s" : ""}, {dirs} folder
          {dirs !== 1 ? "s" : ""}
        </span>
        <span style={{ display: "flex", gap: 12 }}>
          {hidden > 0 && (
            <button style={S.toggleBtn} onClick={() => setExpanded(!expanded)}>
              {expanded ? "Show less" : `${hidden} more...`}
            </button>
          )}
          <button style={S.toggleBtn} onClick={() => setShowJson(true)}>
            JSON
          </button>
        </span>
      </div>
    </div>
  );
}

/* ── File content output ── */
function FileContentOutput({ output }) {
  const [expanded, setExpanded] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const content = output.content || "";
  const lines = content.split("\n");
  const MAX_LINES = 20;
  const truncated = !expanded && lines.length > MAX_LINES;
  const display = truncated ? lines.slice(0, MAX_LINES).join("\n") + "\n..." : content;
  const filePath = output.path || "";
  const fileName = filePath.split(/[/\\]/).pop() || "file";

  if (showJson) {
    return (
      <div style={S.card}>
        <div style={S.footer}>
          <span>{fileName}</span>
          <button style={S.toggleBtn} onClick={() => setShowJson(false)}>
            Formatted view
          </button>
        </div>
        <pre style={S.pre}>{JSON.stringify(output, null, 2)}</pre>
      </div>
    );
  }

  return (
    <div style={S.card}>
      <div style={S.header}>
        <span style={{ fontSize: 14 }}>{fileIcon(fileName, "file")}</span>
        <span style={{ color: "#d0d0d0" }}>{fileName}</span>
        <span style={{ marginLeft: "auto", fontSize: 11 }}>
          {lines.length} lines
          {output.size_bytes != null && ` \u00B7 ${fmtSize(output.size_bytes)}`}
        </span>
      </div>
      <pre style={S.pre}>{display}</pre>
      <div style={S.footer}>
        <span />
        <span style={{ display: "flex", gap: 12 }}>
          {lines.length > MAX_LINES && (
            <button style={S.toggleBtn} onClick={() => setExpanded(!expanded)}>
              {expanded ? "Show less" : `Show all ${lines.length} lines`}
            </button>
          )}
          <button style={S.toggleBtn} onClick={() => setShowJson(true)}>
            JSON
          </button>
        </span>
      </div>
    </div>
  );
}

/* ── Command / terminal output ── */
function CommandOutput({ output }) {
  const [expanded, setExpanded] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const stdout = output.stdout || "";
  const stderr = output.stderr || "";
  const exitCode = output.exit_code;
  const text = stdout || stderr;
  const lines = text.split("\n");
  const MAX_LINES = 10;
  const truncated = !expanded && lines.length > MAX_LINES;
  const display = truncated ? lines.slice(0, MAX_LINES).join("\n") + "\n..." : text;

  if (showJson) {
    return (
      <div style={S.card}>
        <div style={S.footer}>
          <span>Command output</span>
          <button style={S.toggleBtn} onClick={() => setShowJson(false)}>
            Terminal view
          </button>
        </div>
        <pre style={S.pre}>{JSON.stringify(output, null, 2)}</pre>
      </div>
    );
  }

  return (
    <div style={S.card}>
      <div style={S.header}>
        <span style={{ fontSize: 14 }}>{"\uD83D\uDCBB"}</span>
        <span>Terminal</span>
        {exitCode != null && (
          <span
            style={{
              marginLeft: "auto",
              color: exitCode === 0 ? "#00ff88" : "#ff4444",
              fontSize: 11,
            }}
          >
            exit {exitCode}
          </span>
        )}
      </div>
      <pre style={{ ...S.terminal, ...(stderr && !stdout ? { color: "#ff8888" } : {}) }}>
        {display || "(no output)"}
      </pre>
      <div style={S.footer}>
        <span />
        <span style={{ display: "flex", gap: 12 }}>
          {lines.length > MAX_LINES && (
            <button style={S.toggleBtn} onClick={() => setExpanded(!expanded)}>
              {expanded ? "Show less" : `Show all ${lines.length} lines`}
            </button>
          )}
          <button style={S.toggleBtn} onClick={() => setShowJson(true)}>
            JSON
          </button>
        </span>
      </div>
    </div>
  );
}

/* ── Generic JSON output (fallback) ── */
function JsonOutput({ output }) {
  const [expanded, setExpanded] = useState(false);
  const json = JSON.stringify(output, null, 2);
  const lines = json.split("\n");
  const MAX_LINES = 15;
  const truncated = !expanded && lines.length > MAX_LINES;
  const display = truncated ? lines.slice(0, MAX_LINES).join("\n") + "\n..." : json;

  return (
    <div style={S.card}>
      <div style={S.header}>
        <span style={{ fontSize: 14 }}>{"{}"}</span>
        <span>Output</span>
      </div>
      <pre style={S.pre}>{display}</pre>
      {lines.length > MAX_LINES && (
        <div style={S.footer}>
          <span />
          <button style={S.toggleBtn} onClick={() => setExpanded(!expanded)}>
            {expanded ? "Show less" : `Show all ${lines.length} lines`}
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Main dispatcher ── */
export default function OutputRenderer({ output, onNavigate }) {
  if (!output || typeof output !== "object" || Object.keys(output).length === 0) {
    return null;
  }

  // list_directory output
  if (Array.isArray(output.items) && (output.path || output.project_path)) {
    return <DirectoryOutput output={output} onNavigate={onNavigate} />;
  }

  // read_file output
  if (typeof output.content === "string" && output.path) {
    return <FileContentOutput output={output} />;
  }

  // command output (stdout/stderr/exit_code)
  if (("stdout" in output || "stderr" in output) && "exit_code" in output) {
    return <CommandOutput output={output} />;
  }

  // Fallback: formatted JSON
  return <JsonOutput output={output} />;
}
