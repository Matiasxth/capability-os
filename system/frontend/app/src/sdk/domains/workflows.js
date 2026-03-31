import { get, post, put, del } from "../client.js";

export const workflows = {
  list: () => get("/workflows"),
  create: (name, description) => post("/workflows", { name, description }),
  get: (id) => get(`/workflows/${id}`),
  update: (id, data) => put(`/workflows/${id}`, data),
  delete: (id) => del(`/workflows/${id}`),
  run: (id) => post(`/workflows/${id}/run`),
};
