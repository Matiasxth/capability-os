import { get, post } from "../client.js";

export const growth = {
  gaps: {
    pending: () => get("/gaps/pending"),
    analyze: (id) => post(`/gaps/${id}/analyze`, {}),
    generate: (id, overrides = {}) => post(`/gaps/${id}/generate`, overrides),
    approve: (id) => post(`/gaps/${id}/approve`, {}),
    reject: (id) => post(`/gaps/${id}/reject`, {}),
  },
  optimizations: {
    pending: () => get("/optimizations/pending"),
    approve: (id, proposedContract) => post(`/optimizations/${id}/approve`, { proposed_contract: proposedContract }),
    reject: (id) => post(`/optimizations/${id}/reject`, {}),
  },
  proposals: {
    list: () => get("/proposals"),
    regenerate: (id) => post(`/proposals/${id}/regenerate`, {}),
    approve: (capabilityId) => post(`/proposals/${capabilityId}/approve`, {}),
    reject: (capabilityId) => post(`/proposals/${capabilityId}/reject`, {}),
  },
};
