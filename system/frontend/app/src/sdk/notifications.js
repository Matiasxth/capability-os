/**
 * Push notification support.
 * Requests permission, subscribes to push, and provides local notification fallback.
 */

let _swRegistration = null;

/** Register the service worker. Call once on app init. */
export async function registerSW() {
  if (!("serviceWorker" in navigator)) return null;
  try {
    _swRegistration = await navigator.serviceWorker.register("/sw.js");
    return _swRegistration;
  } catch {
    return null;
  }
}

/** @returns {"granted"|"denied"|"default"} */
export function getPermission() {
  if (!("Notification" in window)) return "denied";
  return Notification.permission;
}

/** Request notification permission from the user. */
export async function requestPermission() {
  if (!("Notification" in window)) return "denied";
  return Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
}

/**
 * Show a local notification (no push server needed).
 * Falls back gracefully if permission denied.
 */
export function showLocalNotification(title, body, options = {}) {
  if (getPermission() !== "granted") return;
  if (_swRegistration) {
    _swRegistration.showNotification(title, { body, icon: "/icons/icon-192.svg", badge: "/icons/icon-192.svg", ...options });
  } else if ("Notification" in window) {
    new Notification(title, { body, icon: "/icons/icon-192.svg", ...options });
  }
}

/** Check if app is running in standalone (installed) mode. */
export function isInstalled() {
  return window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
}
