import { get, post, put, del } from "../client.js";

export const auth = {
  status: () => get("/auth/status"),
  setup: (username, password, displayName) => post("/auth/setup", { username, password, display_name: displayName || username }),
  login: (username, password) => post("/auth/login", { username, password }),
  me: () => get("/auth/me"),
  listUsers: () => get("/auth/users"),
  createUser: (user) => post("/auth/users", user),
  updateUser: (userId, fields) => put(`/auth/users/${userId}`, fields),
  deleteUser: (userId) => del(`/auth/users/${userId}`),
};
