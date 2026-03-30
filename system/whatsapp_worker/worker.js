/**
 * Capability OS — WhatsApp Worker (Baileys)
 *
 * Standalone Node.js process that connects to WhatsApp via the
 * multi-device protocol. Communicates with the Python backend
 * over stdin/stdout JSON-RPC (one JSON object per line).
 */
const path = require("path");
const readline = require("readline");

const SESSION_DIR = path.join(__dirname, "session");

let sock = null;
let currentQR = null;
let connectionStatus = "disconnected"; // disconnected | connecting | connected
let sockUser = null;

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
// Boot Baileys
// ---------------------------------------------------------------------------

async function startSocket() {
  // Dynamic import — Baileys is ESM in recent versions
  let makeWASocket, useMultiFileAuthState, DisconnectReason, makeCacheableSignalKeyStore;
  try {
    const baileys = require("@whiskeysockets/baileys");
    makeWASocket = baileys.default || baileys.makeWASocket;
    useMultiFileAuthState = baileys.useMultiFileAuthState;
    DisconnectReason = baileys.DisconnectReason;
    makeCacheableSignalKeyStore = baileys.makeCacheableSignalKeyStore;
  } catch (e) {
    send({ type: "fatal", error: "Baileys not installed. Run: cd system/whatsapp_worker && npm install" });
    process.exit(1);
  }

  const pino = require("pino");
  const logger = pino({ level: "silent" });

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);

  connectionStatus = "connecting";
  send({ type: "status", status: "connecting" });

  sock = makeWASocket({
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore
        ? makeCacheableSignalKeyStore(state.keys, logger)
        : state.keys,
    },
    printQRInTerminal: false,
    logger,
    browser: ["CapabilityOS", "Chrome", "1.0.0"],
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      currentQR = qr;
      send({ type: "qr", qr });
    }

    if (connection === "open") {
      connectionStatus = "connected";
      currentQR = null;
      sockUser = sock.user || null;
      send({ type: "ready", user: sockUser });
    }

    if (connection === "close") {
      connectionStatus = "disconnected";
      sockUser = null;
      const code = lastDisconnect?.error?.output?.statusCode;
      const loggedOut = code === (DisconnectReason?.loggedOut ?? 401);
      const reason = lastDisconnect?.error?.output?.payload?.message || "";
      send({ type: "disconnected", code, loggedOut, reason });
      // 405 = blocked by WhatsApp servers, don't retry
      if (code === 405) {
        send({ type: "fatal", error: "WhatsApp blocked this connection (405). The Baileys protocol is currently blocked by WhatsApp servers. Use browser-based WhatsApp Web instead." });
        return;
      }
      if (!loggedOut) {
        setTimeout(() => startSocket(), 3000);
      }
    }
  });

  // Forward incoming messages to Python via stdout
  sock.ev.on("messages.upsert", ({ messages: msgs }) => {
    for (const msg of msgs) {
      if (msg.key.fromMe || !msg.message) continue;
      const text =
        msg.message.conversation ||
        msg.message.extendedTextMessage?.text ||
        "";
      if (!text) continue;
      send({
        type: "incoming_message",
        from: msg.key.remoteJid || "",
        pushName: msg.pushName || "",
        text,
        messageId: msg.key.id || "",
        timestamp: Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000),
      });
    }
  });
}

// ---------------------------------------------------------------------------
// Command handlers
// ---------------------------------------------------------------------------

async function handleCommand(cmd) {
  const { id, action } = cmd;
  if (!id || !action) return;

  try {
    if (action === "status") {
      reply(id, {
        type: "status",
        connected: connectionStatus === "connected",
        status: connectionStatus,
        user: sockUser,
        qr: currentQR,
      });
      return;
    }

    if (action === "send_message") {
      if (connectionStatus !== "connected" || !sock) {
        reply(id, { type: "error", error: "WhatsApp not connected." });
        return;
      }
      const to = cmd.to || "";
      const message = cmd.message || "";
      if (!to || !message) {
        reply(id, { type: "error", error: "Fields 'to' and 'message' are required." });
        return;
      }

      // Resolve JID — try phone number first, then contact name search
      let jid = null;
      // If it looks like a phone number (digits, +, spaces)
      const cleaned = to.replace(/[\s\-()]/g, "");
      if (/^\+?\d{7,15}$/.test(cleaned)) {
        const phone = cleaned.startsWith("+") ? cleaned.slice(1) : cleaned;
        jid = phone + "@s.whatsapp.net";
        // Verify it exists
        try {
          const exists = await sock.onWhatsApp(jid);
          if (!exists || !exists.length || !exists[0].exists) {
            jid = null;
          }
        } catch {
          jid = null;
        }
      }

      // If not a phone or phone not found, search by name in contacts
      if (!jid) {
        try {
          // Try as phone number with country code
          const results = await sock.onWhatsApp(cleaned);
          if (results && results.length > 0 && results[0].exists) {
            jid = results[0].jid;
          }
        } catch {
          // onWhatsApp failed — contact search not available without phone
        }
      }

      if (!jid) {
        reply(id, {
          type: "error",
          error: `Contact '${to}' not found. Use a phone number with country code (e.g. +56912345678) or the exact name as it appears in your contacts.`,
        });
        return;
      }

      await sock.sendMessage(jid, { text: message });
      reply(id, { type: "success", jid, message, confirmation: "sent" });
      return;
    }

    if (action === "search_contact") {
      if (connectionStatus !== "connected" || !sock) {
        reply(id, { type: "error", error: "WhatsApp not connected." });
        return;
      }
      const query = cmd.query || "";
      if (!query) {
        reply(id, { type: "error", error: "Field 'query' is required." });
        return;
      }
      try {
        const results = await sock.onWhatsApp(query);
        reply(id, { type: "contacts", contacts: results || [] });
      } catch (e) {
        reply(id, { type: "error", error: e.message });
      }
      return;
    }

    if (action === "get_qr") {
      reply(id, { type: "qr", qr: currentQR });
      return;
    }

    if (action === "logout") {
      if (sock) {
        try { await sock.logout(); } catch {}
      }
      connectionStatus = "disconnected";
      sockUser = null;
      currentQR = null;
      reply(id, { type: "success", action: "logout" });
      return;
    }

    reply(id, { type: "error", error: `Unknown action: ${action}` });
  } catch (e) {
    reply(id, { type: "error", error: e.message || String(e) });
  }
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

startSocket().catch((e) => {
  send({ type: "fatal", error: e.message || String(e) });
  process.exit(1);
});
