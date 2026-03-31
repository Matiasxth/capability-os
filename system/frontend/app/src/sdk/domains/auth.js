import { get, post, put, del } from "../client.js";

export const auth = {
  status: () => get("/auth/status"),
  setup: (username, password) => post("/auth/setup", { username, password }),
  login: (username, password) => post("/auth/login", { username, password }),
  me: () => get("/auth/me"),
  listUsers: () => get("/auth/users"),
  createUser: (user) => post("/auth/users", user),
  updateUser: (userId, fields) => put(`/auth/users/${userId}`, fields),
  deleteUser: (userId) => del(`/auth/users/${userId}`),
};
