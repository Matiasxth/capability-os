/**
 * Session & token lifecycle management.
 * Single source of truth for auth token and chat persistence.
 */

const TOKEN_KEY = "capos_token";
const CHAT_KEY = "capos_chat_session";
const USERNAME_KEY = "capos_username";

/** @returns {string|null} */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

/** @param {string} token */
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

/** @returns {string} */
export function getUsername() {
  return localStorage.getItem(USERNAME_KEY) || "User";
}

/** @param {string} name */
export function setUsername(name) {
  localStorage.setItem(USERNAME_KEY, name);
}

/**
 * Persist chat messages to sessionStorage (survives refresh, cleared on tab close).
 * Deduplicates by content+role before saving.
 * @param {Array} messages
 */
export function saveChatMessages(messages) {
  try {
    const deduped = deduplicateMessages(messages);
    sessionStorage.setItem(CHAT_KEY, JSON.stringify(deduped));
  } catch { /* quota exceeded — silently ignore */ }
}

/** @returns {Array} */
export function restoreChatMessages() {
  try {
    const raw = sessionStorage.getItem(CHAT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return deduplicateMessages(parsed);
  } catch {
    return [];
  }
}

/**
 * Remove duplicate messages by matching role + content.
 * Keeps the first occurrence of each unique message.
 * @param {Array} messages
 * @returns {Array}
 */
function deduplicateMessages(messages) {
  if (!Array.isArray(messages)) return [];
  const seen = new Set();
  return messages.filter(m => {
    const content = typeof m.content === "string" ? m.content : JSON.stringify(m.content);
    // Skip dedup for loading/executing placeholders
    if (m.meta?.loading || m.meta?.executing) return true;
    const key = `${m.role}:${content}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function clearChatMessages() {
  sessionStorage.removeItem(CHAT_KEY);
}
