import { get, post, put, del, publicGet, publicPost } from "../client.js";

export const auth = {
  // Public endpoints (no token, no 401 redirect)
  status: () => publicGet("/auth/status"),
  setup: (username, password, displayName) => publicPost("/auth/setup", { username, password, display_name: displayName || username }),
  login: (username, password) => publicPost("/auth/login", { username, password }),

  // Authenticated endpoints
  me: () => get("/auth/me"),
  listUsers: () => get("/auth/users"),
  createUser: (user) => post("/auth/users", user),
  updateUser: (userId, fields) => put(`/auth/users/${userId}`, fields),
  deleteUser: (userId) => del(`/auth/users/${userId}`),
};
