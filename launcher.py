"""Capability OS Launcher — cyberpunk-styled web UI for managing the system.

Double-click CapabilityOS.bat (or run ``python launcher.py``) to open the
launcher dashboard in your default browser.  From there you can start, stop,
restart the system and watch live logs — all without touching the terminal.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent
LAUNCHER_PORT = 9000
SYSTEM_PORT = 8000
WS_PORT = 8001
SYSTEM_CMD = [sys.executable, str(PROJECT_ROOT / "docker-entrypoint.py")]


# ═══════════════════════════════════════════════════════════════════
# System process manager
# ═══════════════════════════════════════════════════════════════════

class SystemManager:
    """Manages the Capability OS server process."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._logs: deque[str] = deque(maxlen=800)
        self._started_at: float | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> dict:
        with self._lock:
            if self.running:
                return {"ok": True, "action": "already_running"}
            self._logs.clear()
            try:
                self._process = subprocess.Popen(
                    SYSTEM_CMD,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(PROJECT_ROOT),
                    text=True,
                    bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                )
            except FileNotFoundError:
                return {"ok": False, "error": "Python not found in PATH"}
            self._started_at = time.time()
            threading.Thread(target=self._drain_stdout, daemon=True).start()
            return {"ok": True, "action": "started", "pid": self._process.pid}

    def stop(self) -> dict:
        with self._lock:
            if not self.running:
                return {"ok": True, "action": "not_running"}
            proc = self._process
            self._process = None
            self._started_at = None
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        return {"ok": True, "action": "stopped"}

    def restart(self) -> dict:
        self.stop()
        time.sleep(1)
        return self.start()

    def status(self) -> dict:
        health = None
        if self.running:
            try:
                req = Request(f"http://localhost:{SYSTEM_PORT}/health")
                with urlopen(req, timeout=3) as r:
                    health = json.loads(r.read().decode())
            except Exception:
                pass
        uptime = None
        if self._started_at:
            uptime = int(time.time() - self._started_at)
        return {
            "running": self.running,
            "pid": self._process.pid if self.running else None,
            "uptime_s": uptime,
            "health": health,
            "system_port": SYSTEM_PORT,
        }

    def logs(self, after: int = 0) -> list[str]:
        items = list(self._logs)
        return items[after:] if after < len(items) else []

    def log_count(self) -> int:
        return len(self._logs)

    def _drain_stdout(self) -> None:
        proc = self._process
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                self._logs.append(line.rstrip("\n\r"))
        except Exception:
            pass


manager = SystemManager()


# ═══════════════════════════════════════════════════════════════════
# HTTP handler
# ═══════════════════════════════════════════════════════════════════

class LauncherHandler(BaseHTTPRequestHandler):
    server_version = "CapOS-Launcher/1.0"

    def log_message(self, *_a) -> None:  # silence default logs
        pass

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            self._json(manager.status())
        elif path.startswith("/api/logs"):
            after = 0
            try:
                after = int(urlparse(self.path).query.split("=")[-1])
            except Exception:
                pass
            self._json({"lines": manager.logs(after), "total": manager.log_count()})
        elif path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self._serve_html()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        actions = {
            "/api/start": manager.start,
            "/api/stop": manager.stop,
            "/api/restart": manager.restart,
        }
        fn = actions.get(path)
        if fn:
            self._json(fn())
        else:
            self.send_error(404)

    def _json(self, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self) -> None:
        body = HTML_PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ═══════════════════════════════════════════════════════════════════
# Embedded HTML  — cyberpunk dashboard
# ═══════════════════════════════════════════════════════════════════

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Capability OS</title>
<style>
/* ── Reset & base ──────────────────────────────────── */
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#06060e;--bg2:#0b0b1a;--card:#0d0f1e;--border:#161a3a;
  --cyan:#00f0ff;--magenta:#ff2d6f;--purple:#7b2dff;
  --green:#00ff88;--yellow:#ffaa00;--red:#ff3344;
  --text:#cccde0;--dim:#4a4c6a;
  --glow-c:0 0 12px #00f0ff44,0 0 30px #00f0ff18;
  --glow-m:0 0 12px #ff2d6f44,0 0 30px #ff2d6f18;
  --glow-g:0 0 12px #00ff8844;
}
html{background:var(--bg);color:var(--text);font:13px/1.5 'Cascadia Code','Fira Code','JetBrains Mono','Consolas',monospace}
body{min-height:100vh;overflow-x:hidden}

/* ── Scanline overlay ──────────────────────────────── */
body::after{
  content:'';position:fixed;inset:0;pointer-events:none;z-index:9999;
  background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,.04) 2px,rgba(0,0,0,.04) 4px);
}

/* ── Grid shell ────────────────────────────────────── */
.shell{max-width:960px;margin:0 auto;padding:24px 16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}
@media(max-width:640px){.grid{grid-template-columns:1fr}}

/* ── Header ────────────────────────────────────────── */
header{text-align:center;padding:18px 0 6px}
h1{font-size:28px;font-weight:800;letter-spacing:6px;
   background:linear-gradient(90deg,var(--cyan),var(--purple),var(--magenta));
   -webkit-background-clip:text;-webkit-text-fill-color:transparent;
   filter:drop-shadow(0 0 18px #00f0ff55);
   text-transform:uppercase}
.subtitle{font-size:10px;letter-spacing:4px;color:var(--dim);margin-top:2px;text-transform:uppercase}
.hbar{height:1px;margin:14px auto 0;width:80%;
  background:linear-gradient(90deg,transparent,var(--cyan),var(--purple),var(--magenta),transparent)}

/* ── Card ──────────────────────────────────────────── */
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;position:relative;overflow:hidden}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,var(--cyan) 30%,var(--purple) 70%,transparent)}
.card-title{font-size:9px;letter-spacing:3px;text-transform:uppercase;color:var(--dim);margin-bottom:12px;display:flex;align-items:center;gap:6px}
.card-title .icon{font-size:13px}

/* ── Status indicator ──────────────────────────────── */
.status-row{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.dot-on{background:var(--green);box-shadow:var(--glow-g);animation:pulse 2s ease infinite}
.dot-off{background:var(--red);opacity:.7}
.dot-warn{background:var(--yellow);animation:pulse 1.5s ease infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.status-label{font-size:18px;font-weight:700}
.status-label.on{color:var(--green);text-shadow:var(--glow-g)}
.status-label.off{color:var(--red)}
.meta{color:var(--dim);font-size:11px;margin-top:2px}
.meta span{color:var(--text);margin-left:2px}

/* ── Service badges ────────────────────────────────── */
.svc{display:flex;align-items:center;gap:8px;padding:8px 10px;
  background:#080818;border:1px solid var(--border);border-radius:6px;margin-bottom:6px}
.svc .lbl{flex:1;font-size:11px}
.svc .val{font-size:11px;font-weight:600}
.svc .val.ok{color:var(--green)}.svc .val.err{color:var(--red)}.svc .val.na{color:var(--dim)}

/* ── Buttons ───────────────────────────────────────── */
.btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}
.btn{flex:1;min-width:100px;height:42px;border:1px solid var(--border);border-radius:6px;
  font:inherit;font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;
  cursor:pointer;transition:all .2s;display:flex;align-items:center;justify-content:center;gap:6px}
.btn:active{transform:scale(.97)}
.btn:disabled{opacity:.35;cursor:not-allowed;transform:none}

.btn-start{background:linear-gradient(135deg,#00261a,#002a20);color:var(--green);border-color:#00ff8833}
.btn-start:hover:not(:disabled){box-shadow:0 0 20px #00ff8833;border-color:var(--green)}
.btn-stop{background:linear-gradient(135deg,#1a0a0a,#200c0c);color:var(--red);border-color:#ff334433}
.btn-stop:hover:not(:disabled){box-shadow:0 0 20px #ff334433;border-color:var(--red)}
.btn-restart{background:linear-gradient(135deg,#0a0a2a,#0c0c30);color:var(--cyan);border-color:#00f0ff33}
.btn-restart:hover:not(:disabled){box-shadow:0 0 20px #00f0ff33;border-color:var(--cyan)}
.btn-open{background:linear-gradient(135deg,#1a0a2a,#200c30);color:var(--magenta);border-color:#ff2d6f33}
.btn-open:hover:not(:disabled){box-shadow:0 0 20px #ff2d6f33;border-color:var(--magenta)}

/* ── Terminal ──────────────────────────────────────── */
.term{grid-column:1/-1}
.term-body{background:#020208;border:1px solid var(--border);border-radius:6px;
  height:220px;overflow-y:auto;padding:10px 12px;font-size:11px;line-height:1.7;color:#7a7c9a;
  scrollbar-width:thin;scrollbar-color:#1a1a3a transparent}
.term-body::-webkit-scrollbar{width:5px}
.term-body::-webkit-scrollbar-thumb{background:#1a1a3a;border-radius:4px}
.term-line{white-space:pre-wrap;word-break:break-all}
.term-line:hover{color:var(--text)}

/* ── Toast ─────────────────────────────────────────── */
.toast{position:fixed;top:16px;right:16px;padding:10px 18px;border-radius:6px;font-size:12px;font-weight:600;
  transform:translateX(120%);transition:transform .3s;z-index:10000;
  background:var(--card);border:1px solid var(--cyan);color:var(--cyan);box-shadow:var(--glow-c)}
.toast.show{transform:translateX(0)}
.toast.err{border-color:var(--red);color:var(--red);box-shadow:var(--glow-m)}

/* ── Decorative corners ────────────────────────────── */
.corner-tl,.corner-br{position:fixed;width:60px;height:60px;pointer-events:none;z-index:1}
.corner-tl{top:0;left:0;border-top:2px solid var(--cyan);border-left:2px solid var(--cyan);opacity:.25}
.corner-br{bottom:0;right:0;border-bottom:2px solid var(--magenta);border-right:2px solid var(--magenta);opacity:.25}

/* ── Spinner ───────────────────────────────────────── */
.spinner{display:inline-block;width:14px;height:14px;border:2px solid transparent;
  border-top-color:currentColor;border-radius:50%;animation:spin .6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div class="corner-tl"></div>
<div class="corner-br"></div>
<div id="toast" class="toast"></div>

<div class="shell">
  <header>
    <h1>Capability OS</h1>
    <div class="subtitle">System Launcher</div>
    <div class="hbar"></div>
  </header>

  <div class="grid">
    <!-- Status card -->
    <div class="card" id="status-card">
      <div class="card-title"><span class="icon">&#9881;</span> System Status</div>
      <div class="status-row">
        <div class="dot dot-off" id="dot"></div>
        <div class="status-label off" id="status-label">OFFLINE</div>
      </div>
      <div class="meta">PID <span id="pid">—</span></div>
      <div class="meta">Uptime <span id="uptime">—</span></div>
      <div class="meta">Port <span id="port">""" + str(SYSTEM_PORT) + """</span></div>
    </div>

    <!-- Services card -->
    <div class="card" id="svc-card">
      <div class="card-title"><span class="icon">&#9729;</span> Services</div>
      <div class="svc"><span class="lbl">LLM Provider</span><span class="val na" id="s-llm">—</span></div>
      <div class="svc"><span class="lbl">Model</span><span class="val na" id="s-model">—</span></div>
      <div class="svc"><span class="lbl">Browser</span><span class="val na" id="s-browser">—</span></div>
      <div class="svc"><span class="lbl">Integrations</span><span class="val na" id="s-integ">—</span></div>
    </div>

    <!-- Controls -->
    <div class="card">
      <div class="card-title"><span class="icon">&#9654;</span> Controls</div>
      <div class="btns">
        <button class="btn btn-start" id="b-start" onclick="action('start')">&#9654; Start</button>
        <button class="btn btn-stop" id="b-stop" onclick="action('stop')">&#9632; Stop</button>
      </div>
      <div class="btns" style="margin-top:8px">
        <button class="btn btn-restart" id="b-restart" onclick="action('restart')">&#8635; Restart</button>
        <button class="btn btn-open" id="b-open" onclick="openApp()">&#8599; Open App</button>
      </div>
    </div>

    <!-- Quick info -->
    <div class="card">
      <div class="card-title"><span class="icon">&#9889;</span> Quick Info</div>
      <div class="svc"><span class="lbl">App URL</span><span class="val" style="color:var(--cyan)">localhost:""" + str(SYSTEM_PORT) + """</span></div>
      <div class="svc"><span class="lbl">WebSocket</span><span class="val" style="color:var(--purple)">ws://localhost:""" + str(WS_PORT) + """</span></div>
      <div class="svc"><span class="lbl">Launcher</span><span class="val" style="color:var(--magenta)">localhost:""" + str(LAUNCHER_PORT) + """</span></div>
      <div class="svc"><span class="lbl">Error Notifier</span><span class="val" style="color:var(--green)">Active</span></div>
    </div>

    <!-- Terminal -->
    <div class="card term">
      <div class="card-title"><span class="icon">&#9002;</span> Live Logs</div>
      <div class="term-body" id="term"></div>
    </div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
let busy = false, logOffset = 0, autoScroll = true;

// ── Toast ───────────────────────────────────────────
function toast(msg, err) {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'toast show' + (err ? ' err' : '');
  clearTimeout(t._tid);
  t._tid = setTimeout(() => t.className = 'toast', 3000);
}

// ── Actions ─────────────────────────────────────────
async function action(name) {
  if (busy) return;
  busy = true;
  setBtns(true);
  try {
    const r = await fetch('/api/' + name, { method: 'POST' });
    const d = await r.json();
    if (d.ok) toast(name.charAt(0).toUpperCase() + name.slice(1) + (d.action === 'already_running' ? ' (already running)' : 'ed'));
    else toast(d.error || 'Failed', true);
  } catch (e) { toast('Connection error', true); }
  busy = false;
  setBtns(false);
  pollStatus();
}

function openApp() { window.open('http://localhost:""" + str(SYSTEM_PORT) + """', '_blank'); }

function setBtns(disabled) {
  ['b-start','b-stop','b-restart'].forEach(id => $(id).disabled = disabled);
}

// ── Status polling ──────────────────────────────────
async function pollStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    const on = d.running;
    $('dot').className = 'dot ' + (on ? 'dot-on' : 'dot-off');
    $('status-label').className = 'status-label ' + (on ? 'on' : 'off');
    $('status-label').textContent = on ? 'ONLINE' : 'OFFLINE';
    $('pid').textContent = d.pid || '\u2014';
    $('uptime').textContent = d.uptime_s != null ? fmtTime(d.uptime_s) : '\u2014';
    $('b-open').disabled = !on;

    const h = d.health;
    if (h) {
      const llm = h.llm || {};
      setVal('s-llm', llm.provider || '\u2014', llm.status === 'ready');
      setVal('s-model', llm.model || '\u2014', llm.status === 'ready');
      const bw = h.browser_worker || {};
      setVal('s-browser', bw.status || '\u2014', bw.status === 'ready');
      const ig = h.integrations || {};
      const igTxt = (ig.enabled || 0) + '/' + (ig.total || 0) + ' enabled';
      setVal('s-integ', igTxt, (ig.enabled || 0) > 0);
    } else if (!on) {
      ['s-llm','s-model','s-browser','s-integ'].forEach(id => setVal(id, '\u2014', null));
    }
  } catch {}
}

function setVal(id, txt, ok) {
  const el = $(id);
  el.textContent = txt;
  el.className = 'val ' + (ok === true ? 'ok' : ok === false ? 'err' : 'na');
}

function fmtTime(s) {
  if (s < 60) return s + 's';
  if (s < 3600) return Math.floor(s / 60) + 'm ' + (s % 60) + 's';
  const h = Math.floor(s / 3600);
  return h + 'h ' + Math.floor((s % 3600) / 60) + 'm';
}

// ── Log polling ─────────────────────────────────────
async function pollLogs() {
  try {
    const r = await fetch('/api/logs?after=' + logOffset);
    const d = await r.json();
    if (d.lines.length) {
      const term = $('term');
      const frag = document.createDocumentFragment();
      d.lines.forEach(l => {
        const div = document.createElement('div');
        div.className = 'term-line';
        div.textContent = l;
        frag.appendChild(div);
      });
      term.appendChild(frag);
      logOffset = d.total;
      if (autoScroll) term.scrollTop = term.scrollHeight;
    }
  } catch {}
}

$('term').addEventListener('scroll', function () {
  const el = this;
  autoScroll = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
});

// ── Poll loops ──────────────────────────────────────
setInterval(pollStatus, 2000);
setInterval(pollLogs, 1000);
pollStatus();
pollLogs();
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main() -> None:
    # Ensure UTF-8 output on Windows
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass

    host = "127.0.0.1"
    server = ThreadingHTTPServer((host, LAUNCHER_PORT), LauncherHandler)

    print()
    print("  +==========================================+")
    print("  |   C A P A B I L I T Y   O S              |")
    print("  |   System Launcher                        |")
    print("  +==========================================+")
    print()
    print(f"  Dashboard:  http://{host}:{LAUNCHER_PORT}")
    print(f"  System:     http://{host}:{SYSTEM_PORT}")
    print(f"  Press       Ctrl+C to quit launcher")
    print()

    webbrowser.open(f"http://{host}:{LAUNCHER_PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        if manager.running:
            manager.stop()
            print("  System process stopped.")
        server.server_close()
        print("  Done.\n")


if __name__ == "__main__":
    main()
