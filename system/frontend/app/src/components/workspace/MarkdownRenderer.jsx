import React, { useMemo } from "react";

/**
 * Zero-dependency markdown renderer for LLM output.
 * Supports: headers, bold, italic, code, code blocks, lists, links, blockquotes, HR.
 * All output is React elements (no dangerouslySetInnerHTML).
 */

function parseInline(text) {
  const parts = [];
  let i = 0;
  const len = text.length;

  while (i < len) {
    // Code span
    if (text[i] === "`" && text[i + 1] !== "`") {
      const end = text.indexOf("`", i + 1);
      if (end !== -1) {
        parts.push(<code key={i} className="md-code">{text.slice(i + 1, end)}</code>);
        i = end + 1; continue;
      }
    }
    // Bold
    if (text[i] === "*" && text[i + 1] === "*") {
      const end = text.indexOf("**", i + 2);
      if (end !== -1) {
        parts.push(<strong key={i}>{text.slice(i + 2, end)}</strong>);
        i = end + 2; continue;
      }
    }
    // Italic
    if (text[i] === "*" && text[i + 1] !== "*") {
      const end = text.indexOf("*", i + 1);
      if (end !== -1 && end > i + 1) {
        parts.push(<em key={i}>{text.slice(i + 1, end)}</em>);
        i = end + 1; continue;
      }
    }
    // Link [text](url)
    if (text[i] === "[") {
      const closeBracket = text.indexOf("]", i);
      if (closeBracket !== -1 && text[closeBracket + 1] === "(") {
        const closeParen = text.indexOf(")", closeBracket + 2);
        if (closeParen !== -1) {
          const linkText = text.slice(i + 1, closeBracket);
          const url = text.slice(closeBracket + 2, closeParen);
          parts.push(<a key={i} href={url} target="_blank" rel="noopener noreferrer">{linkText}</a>);
          i = closeParen + 1; continue;
        }
      }
    }
    // Plain text — accumulate until next special char
    let next = i + 1;
    while (next < len && !"`*[".includes(text[next])) next++;
    parts.push(text.slice(i, next));
    i = next;
  }
  return parts.length === 1 && typeof parts[0] === "string" ? parts[0] : parts;
}

function parseMarkdown(text) {
  if (!text || typeof text !== "string") return null;
  const lines = text.split("\n");
  const elements = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Code block
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      elements.push(<pre key={elements.length} className="md-pre"><code>{codeLines.join("\n")}</code></pre>);
      continue;
    }
    // Headers
    if (line.startsWith("### ")) { elements.push(<h4 key={elements.length}>{parseInline(line.slice(4))}</h4>); i++; continue; }
    if (line.startsWith("## ")) { elements.push(<h3 key={elements.length}>{parseInline(line.slice(3))}</h3>); i++; continue; }
    if (line.startsWith("# ")) { elements.push(<h2 key={elements.length}>{parseInline(line.slice(2))}</h2>); i++; continue; }
    // HR
    if (/^---+$/.test(line.trim())) { elements.push(<hr key={elements.length} className="md-hr" />); i++; continue; }
    // Blockquote
    if (line.startsWith("> ")) { elements.push(<blockquote key={elements.length} className="md-blockquote">{parseInline(line.slice(2))}</blockquote>); i++; continue; }
    // Unordered list
    if (/^[-*] /.test(line)) {
      const items = [];
      while (i < lines.length && /^[-*] /.test(lines[i])) {
        items.push(<li key={items.length}>{parseInline(lines[i].slice(2))}</li>);
        i++;
      }
      elements.push(<ul key={elements.length} className="md-list">{items}</ul>);
      continue;
    }
    // Ordered list
    if (/^\d+\. /.test(line)) {
      const items = [];
      while (i < lines.length && /^\d+\. /.test(lines[i])) {
        items.push(<li key={items.length}>{parseInline(lines[i].replace(/^\d+\.\s*/, ""))}</li>);
        i++;
      }
      elements.push(<ol key={elements.length} className="md-list">{items}</ol>);
      continue;
    }
    // Empty line
    if (!line.trim()) { i++; continue; }
    // Paragraph
    elements.push(<p key={elements.length}>{parseInline(line)}</p>);
    i++;
  }
  return elements;
}

export default function MarkdownRenderer({ text }) {
  const elements = useMemo(() => parseMarkdown(text), [text]);
  if (!elements || elements.length === 0) return <span>{text}</span>;
  return <div className="msg-markdown">{elements}</div>;
}
