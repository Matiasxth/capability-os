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
 * @param {Array} messages
 */
export function saveChatMessages(messages) {
  try {
    sessionStorage.setItem(CHAT_KEY, JSON.stringify(messages));
  } catch { /* quota exceeded — silently ignore */ }
}

/** @returns {Array} */
export function restoreChatMessages() {
  try {
    const raw = sessionStorage.getItem(CHAT_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function clearChatMessages() {
  sessionStorage.removeItem(CHAT_KEY);
}
