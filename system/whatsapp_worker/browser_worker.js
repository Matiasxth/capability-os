/**
 * Capability OS — WhatsApp Browser Worker (Puppeteer)
 *
 * Standalone Node.js process that opens WhatsApp Web in headless Chromium
 * via Puppeteer. Communicates with Python backend over stdin/stdout
 * JSON-RPC (one JSON object per line) — same protocol as worker.js (Baileys).
 */
const path = require("path");
const readline = require("readline");

const SESSION_DIR = path.join(__dirname, "browser-session");

let browser = null;
let page = null;
let connectionStatus = "disconnected"; // disconnected | connecting | connected
let lastSeenMessages = new Set();
let pollTimer = null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

function reply(id, payload) {
  send({ id, ...payload });
}

// ---------------------------------------------------------------------------
// Boot Puppeteer
// ---------------------------------------------------------------------------

async function launchBrowser() {
  let puppeteer;
  try {
    puppeteer = require("puppeteer");
  } catch (e) {
    send({ type: "fatal", error: "Puppeteer not installed. Run: cd system/whatsapp_worker && npm install" });
    process.exit(1);
  }

  connectionStatus = "connecting";
  send({ type: "status", status: "connecting" });

  const fs = require("fs");

  // Try userDataDir for session persistence; fall back to temp profile if locked
  let launchOpts = {
    headless: "new",
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-blink-features=AutomationControlled",
      "--disable-dev-shm-usage",
    ],
  };

  // Check if session dir is usable (no lockfile from zombie process)
  const lockfile = path.join(SESSION_DIR, "lockfile");
  let canUseSession = true;
  try {
    if (fs.existsSync(lockfile)) {
      fs.unlinkSync(lockfile);
    }
    fs.mkdirSync(SESSION_DIR, { recursive: true });
    launchOpts.userDataDir = SESSION_DIR;
  } catch {
    canUseSession = false;
    // Skip userDataDir — use temp profile (no session persistence but at least it works)
    send({ type: "status", status: "connecting", note: "Using temporary profile (session dir locked)" });
  }

  try {
    browser = await puppeteer.launch(launchOpts);

    page = await browser.newPage();
    await page.setUserAgent(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    );
    await page.setViewport({ width: 1280, height: 900 });
    await page.goto("https://web.whatsapp.com", { waitUntil: "domcontentloaded", timeout: 30000 });

    // Wait for either QR or logged-in state
    await waitForQRorLogin();
  } catch (e) {
    connectionStatus = "disconnected";
    send({ type: "fatal", error: `Browser launch failed: ${e.message}` });
  }
}

async function waitForQRorLogin() {
  const deadline = Date.now() + 30000;

  while (Date.now() < deadline) {
    // IMPORTANT: check for QR FIRST — if QR exists, we're NOT logged in
    const qrImage = await captureQR();
    if (qrImage) {
      send({ type: "qr", qr_image: qrImage });
      // Keep polling for login after QR
      pollForLogin();
      return;
    }

    // No QR found — check if already logged in
    if (await checkLoggedIn()) {
      connectionStatus = "connected";
      send({ type: "ready" });
      startMessagePolling();
      return;
    }

    await sleep(1000);
  }

  send({ type: "status", status: "timeout", error: "Timeout waiting for WhatsApp Web" });
}

async function pollForLogin() {
  const interval = setInterval(async () => {
    try {
      // Only consider logged in if QR is gone
      const qr = await captureQR();
      if (qr) {
        send({ type: "qr", qr_image: qr });
        return;
      }
      if (await checkLoggedIn()) {
        clearInterval(interval);
        connectionStatus = "connected";
        send({ type: "ready" });
        startMessagePolling();
        return;
      }
    } catch {
      // page might be navigating
    }
  }, 3000);
}

async function checkLoggedIn() {
  if (!page) return false;
  try {
    // If QR canvas exists, definitely NOT logged in
    const hasCanvas = await page.$('canvas');
    if (hasCanvas) return false;

    // Check for chat indicators that only exist when logged in
    const indicators = [
      '#side',
      'div[aria-label="Chat list"]',
      'div[aria-label="Lista de chats"]',
      'div[data-testid="chat-list"]',
      'span[data-icon="menu"]',
      'div[data-tab="3"][contenteditable="true"]',
    ];
    for (const sel of indicators) {
      const el = await page.$(sel);
      if (el) return true;
    }
    // No fallbacks — only trust explicit selectors
  } catch {
    // ignore
  }
  return false;
}

async function captureQR() {
  if (!page) return null;
  try {
    const canvas = await page.$('canvas[aria-label="Scan this QR code to link a device!"]')
      || await page.$('div[data-ref] canvas')
      || await page.$('canvas');
    if (!canvas) return null;
    const screenshot = await canvas.screenshot({ type: "png", encoding: "base64" });
    return `data:image/png;base64,${screenshot}`;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Incoming message detection
// ---------------------------------------------------------------------------

function startMessagePolling() {
  if (pollTimer) clearInterval(pollTimer);
  // Poll by clicking on chats with unread badges and reading their messages
  pollTimer = setInterval(async () => {
    try {
      if (connectionStatus !== "connected" || !page) return;
      await checkForNewMessages();
    } catch {
      // ignore
    }
  }, 5000);
}

async function checkForNewMessages() {
  if (!page) return;

  // Force page to process pending updates
  await page.evaluate(() => window.dispatchEvent(new Event('focus'))).catch(() => {});

  // Find chats with unread badges — detect by numeric span content inside chat rows
  const unreadChats = await page.evaluate(() => {
    const results = [];
    const rows = document.querySelectorAll('[role="row"], [role="listitem"]');
    for (const row of rows) {
      const nameEl = row.querySelector('span[dir="auto"][title]');
      if (!nameEl) continue;
      const name = nameEl.getAttribute('title') || '';
      if (!name) continue;

      // Find unread badge: a span with only digits (1-99) that's NOT a timestamp
      const spans = row.querySelectorAll('span');
      let hasUnread = false;
      for (const s of spans) {
        const txt = s.textContent?.trim();
        if (txt && /^\d{1,2}$/.test(txt) && parseInt(txt) > 0) {
          // Verify it's a badge by checking it's small and has background
          const rect = s.getBoundingClientRect();
          if (rect.width < 30 && rect.height < 30) {
            hasUnread = true;
            break;
          }
        }
      }
      if (!hasUnread) continue;

      results.push({ name });
    }
    return results;
  });

  // For each unread chat, get the preview text from the sidebar row directly
  for (const chat of unreadChats) {
    const preview = await page.evaluate((chatName) => {
      const spans = document.querySelectorAll('span[dir="auto"][title]');
      for (const s of spans) {
        if (s.getAttribute('title') !== chatName) continue;
        // Navigate to the row
        const row = s.closest('[role="row"]') || s.closest('[role="listitem"]') || s.parentElement?.parentElement?.parentElement;
        if (!row) continue;
        // Read all text spans in the row, find the message preview (last meaningful text)
        const allSpans = row.querySelectorAll('span');
        let preview = '';
        for (const sp of allSpans) {
          const txt = sp.textContent?.trim() || '';
          if (txt === chatName) continue;
          if (/^\d{1,2}:\d{2}$/.test(txt)) continue; // time
          if (/^\d{1,2}$/.test(txt)) continue; // badge number
          if (txt.length < 2 || txt.length > 300) continue;
          if (/^(ayer|hoy|yesterday|today|Todos|No le)/i.test(txt)) continue;
          preview = txt;
        }
        return preview;
      }
      return '';
    }, chat.name);

    if (!preview) continue;
    const key = `${chat.name}:${preview}`;
    if (!lastSeenMessages.has(key)) {
      lastSeenMessages.add(key);
      if (lastSeenMessages.size > 500) {
        const first = lastSeenMessages.values().next().value;
        lastSeenMessages.delete(first);
      }
      send({
        type: "incoming_message",
        from: chat.name,
        pushName: chat.name,
        text: preview.substring(0, 200),
        messageId: `browser_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        timestamp: Math.floor(Date.now() / 1000),
      });
    }
  }
}

// ---------------------------------------------------------------------------
// Command handlers
// ---------------------------------------------------------------------------

async function handleCommand(cmd) {
  const { id, action } = cmd;
  if (!id || !action) return;

  try {
    if (action === "status") {
      const loggedIn = connectionStatus === "connected" || (await checkLoggedIn());
      reply(id, {
        type: "status",
        connected: loggedIn,
        status: loggedIn ? "connected" : connectionStatus,
        seen_count: lastSeenMessages.size,
      });
      return;
    }

    if (action === "debug_chats") {
      // Dump raw DOM info to find correct selectors
      const debug = await page.evaluate(() => {
        const info = { rows: 0, badges: [], chatNames: [] };
        // Count rows
        const allRows = document.querySelectorAll('[role="row"], [role="listitem"], [data-testid="cell-frame-container"]');
        info.rows = allRows.length;
        // Find all green badge-like elements
        const allSpans = document.querySelectorAll('span');
        for (const s of allSpans) {
          const txt = s.textContent?.trim();
          if (txt && /^\d+$/.test(txt) && parseInt(txt) > 0 && parseInt(txt) < 100) {
            const style = window.getComputedStyle(s);
            const bg = style.backgroundColor;
            if (bg.includes('rgb') && !bg.includes('0, 0, 0')) {
              info.badges.push({
                text: txt,
                tag: s.tagName,
                class: s.className?.substring(0, 50),
                testid: s.getAttribute('data-testid') || '',
                parentTestid: s.parentElement?.getAttribute('data-testid') || '',
              });
            }
          }
        }
        // Chat names
        const nameSpans = document.querySelectorAll('span[dir="auto"][title]');
        for (const ns of nameSpans) {
          info.chatNames.push(ns.getAttribute('title'));
        }
        return info;
      });
      reply(id, { type: "debug", ...debug, seen_count: lastSeenMessages.size });
      return;
    }

    if (action === "get_qr") {
      const qr = await captureQR();
      reply(id, { type: "qr", qr_image: qr });
      return;
    }

    if (action === "check_login") {
      const loggedIn = await checkLoggedIn();
      if (loggedIn && connectionStatus !== "connected") {
        connectionStatus = "connected";
        startMessagePolling();
      }
      reply(id, { type: "status", connected: loggedIn });
      return;
    }

    if (action === "send_message") {
      if (connectionStatus !== "connected" || !page) {
        reply(id, { type: "error", error: "Not connected" });
        return;
      }
      const to = cmd.to || "";
      const message = cmd.message || "";
      if (!to || !message) {
        reply(id, { type: "error", error: "Fields 'to' and 'message' required" });
        return;
      }

      try {
        // Find and click on the chat in the sidebar by name
        const chatClicked = await page.evaluate((name) => {
          const spans = document.querySelectorAll('span[dir="auto"][title]');
          for (const s of spans) {
            if (s.getAttribute('title') === name) {
              s.closest('[tabindex]')?.click() || s.click();
              return true;
            }
          }
          return false;
        }, to);

        if (!chatClicked) {
          // Try search approach
          const searchBox = await page.$('div[contenteditable="true"][data-tab="3"]')
            || await page.$('div[contenteditable="true"][role="textbox"]')
            || await page.$('#side div[contenteditable="true"]');
          if (!searchBox) {
            reply(id, { type: "error", error: "Search box not found" });
            return;
          }
          await searchBox.click();
          await searchBox.evaluate(el => el.textContent = "");
          await page.keyboard.type(to, { delay: 40 });
          await sleep(2000);
          await page.keyboard.press("Enter");
          await sleep(1000);
        } else {
          await sleep(500);
        }

        // Find message input — try multiple selectors
        const msgInput = await page.$('div[contenteditable="true"][data-tab="10"]')
          || await page.$('footer div[contenteditable="true"]')
          || await page.$('div[contenteditable="true"][title*="mensaje"]')
          || await page.$('div[contenteditable="true"][title*="message"]')
          || await page.$('#main div[contenteditable="true"]');

        if (!msgInput) {
          reply(id, { type: "error", error: "Message input not found" });
          return;
        }

        await msgInput.click();
        await page.keyboard.type(message, { delay: 15 });
        await sleep(200);
        await page.keyboard.press("Enter");
        await sleep(500);

        reply(id, { type: "success", to, message, confirmation: "sent" });
      } catch (e) {
        reply(id, { type: "error", error: `Send failed: ${e.message}` });
      }
      return;
    }

    if (action === "search_contact") {
      if (connectionStatus !== "connected" || !page) {
        reply(id, { type: "error", error: "Not connected" });
        return;
      }
      const query = cmd.query || "";
      const searchSel = 'div[contenteditable="true"][data-tab="3"]';
      await page.waitForSelector(searchSel, { timeout: 10000 });
      await page.click(searchSel);
      await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (el) el.textContent = "";
      }, searchSel);
      await page.type(searchSel, query, { delay: 50 });
      await sleep(1500);

      // Read results
      const contacts = await page.evaluate(() => {
        const results = [];
        const items = document.querySelectorAll('div[role="listitem"] span[dir="auto"][title]');
        for (const item of items) {
          results.push({ name: item.getAttribute("title") || "", jid: "" });
        }
        return results.slice(0, 10);
      });

      // Clear search
      await page.keyboard.press("Escape");

      reply(id, { type: "contacts", contacts });
      return;
    }

    if (action === "close") {
      if (pollTimer) clearInterval(pollTimer);
      if (browser) {
        await browser.close().catch(() => {});
        browser = null;
        page = null;
      }
      connectionStatus = "disconnected";
      reply(id, { type: "success", action: "close" });
      return;
    }

    if (action === "screenshot") {
      if (!page) {
        reply(id, { type: "error", error: "No page" });
        return;
      }
      const screenshot = await page.screenshot({ type: "png", encoding: "base64" });
      reply(id, { type: "screenshot", image: `data:image/png;base64,${screenshot}` });
      return;
    }

    reply(id, { type: "error", error: `Unknown action: ${action}` });
  } catch (e) {
    reply(id, { type: "error", error: e.message || String(e) });
  }
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// stdin listener
// ---------------------------------------------------------------------------

const rl = readline.createInterface({ input: process.stdin });
rl.on("line", (line) => {
  try {
    const cmd = JSON.parse(line.trim());
    handleCommand(cmd);
  } catch {
    // Ignore malformed JSON
  }
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

launchBrowser().catch((e) => {
  send({ type: "fatal", error: e.message || String(e) });
  process.exit(1);
});
