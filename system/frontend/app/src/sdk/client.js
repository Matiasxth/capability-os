/**
 * Core HTTP + SSE client. ALL backend communication goes through here.
 * - Centralized auth token injection
 * - Unified SSE parser (written once, used by all streaming endpoints)
 * - 401 detection → auto-logout
 */
import { getToken, clearToken } from "./session.js";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

function authHeaders(extraHeaders) {
  const h = { "Content-Type": "application/json", ...extraHeaders };
  const token = getToken();
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

/**
 * Core request function. Every non-streaming HTTP call goes through here.
 * @param {string} method
 * @param {string} path
 * @param {*} [body]
 * @param {{ headers?: object }} [options]
 * @returns {Promise<any>}
 */
export async function request(method, path, body, options = {}) {
  const headers = authHeaders(options.headers);
  const fetchOpts = { method, headers };
  if (body !== undefined) {
    fetchOpts.body = typeof body === "string" ? body : JSON.stringify(body);
  }

  const response = await fetch(`${BASE_URL}${path}`, fetchOpts);

  if (response.status === 401) {
    clearToken();
    window.location.replace("/login");
    throw new Error("Session expired");
  }

  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error_message || "API request failed.");
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

/** Convenience wrappers */
export const get = (path, opts) => request("GET", path, undefined, opts);
export const post = (path, body, opts) => request("POST", path, body, opts);
export const put = (path, body, opts) => request("PUT", path, body, opts);
export const del = (path, opts) => request("DELETE", path, undefined, opts);
export const delWithBody = (path, body, opts) => request("DELETE", path, body, opts);

/**
 * Unified SSE (Server-Sent Events) streaming parser.
 * Sends auth token (fixes the security bug where streaming had no JWT).
 *
 * @param {string} path - Endpoint path
 * @param {object} body - JSON body to POST
 * @yields {object} Each parsed SSE data frame
 */
export async function* streamSSE(path, body) {
  const headers = authHeaders();
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    if (resp.status === 401) {
      clearToken();
      window.location.replace("/login");
      throw new Error("Session expired");
    }
    let errMsg = "Stream request failed";
    try {
      const errPayload = await resp.json();
      errMsg = errPayload.error_message || errMsg;
    } catch { /* no json body */ }
    throw new Error(errMsg);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    while (buffer.includes("\n\n")) {
      const idx = buffer.indexOf("\n\n");
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (!line.startsWith("data:")) continue;
      try {
        const data = JSON.parse(line.slice(5).trim());
        if (data.done) return;
        if (data.error) throw new Error(data.error);
        yield data;
      } catch (e) {
        if (e.message && e.message !== "Unexpected end of JSON input") throw e;
      }
    }
  }
}
