import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock session before importing client
vi.mock("../session.js", () => ({
  getToken: vi.fn(() => "test-jwt-token"),
  clearToken: vi.fn(),
}));

const { request, get, post, put, del, streamSSE } = await import("../client.js");
const { getToken, clearToken } = await import("../session.js");

describe("client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    getToken.mockReturnValue("test-jwt-token");
    global.fetch = vi.fn();
  });

  describe("request()", () => {
    it("sends GET with auth header", async () => {
      global.fetch.mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({ data: 1 }) });
      const result = await get("/test");
      expect(global.fetch).toHaveBeenCalledWith("/test", expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({ Authorization: "Bearer test-jwt-token" }),
      }));
      expect(result).toEqual({ data: 1 });
    });

    it("sends POST with body and auth", async () => {
      global.fetch.mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) });
      await post("/create", { name: "test" });
      expect(global.fetch).toHaveBeenCalledWith("/create", expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "test" }),
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          Authorization: "Bearer test-jwt-token",
        }),
      }));
    });

    it("sends PUT", async () => {
      global.fetch.mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({}) });
      await put("/update/1", { x: 1 });
      expect(global.fetch).toHaveBeenCalledWith("/update/1", expect.objectContaining({ method: "PUT" }));
    });

    it("sends DELETE", async () => {
      global.fetch.mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({}) });
      await del("/remove/1");
      expect(global.fetch).toHaveBeenCalledWith("/remove/1", expect.objectContaining({ method: "DELETE" }));
    });

    it("throws on non-ok response with error_message", async () => {
      global.fetch.mockResolvedValue({
        ok: false, status: 400,
        json: () => Promise.resolve({ error_message: "Bad input" }),
      });
      await expect(get("/fail")).rejects.toThrow("Bad input");
    });

    it("attaches payload and status to error", async () => {
      const payload = { error_message: "Not found", error_code: "NOT_FOUND" };
      global.fetch.mockResolvedValue({ ok: false, status: 404, json: () => Promise.resolve(payload) });
      try {
        await get("/missing");
        expect.fail("should throw");
      } catch (e) {
        expect(e.payload).toEqual(payload);
        expect(e.status).toBe(404);
      }
    });

    it("clears token and redirects on 401", async () => {
      delete window.location;
      window.location = { replace: vi.fn() };
      global.fetch.mockResolvedValue({ ok: false, status: 401, json: () => Promise.resolve({}) });
      await expect(get("/auth-fail")).rejects.toThrow("Session expired");
      expect(clearToken).toHaveBeenCalled();
      expect(window.location.replace).toHaveBeenCalledWith("/login");
    });

    it("omits auth header when no token", async () => {
      getToken.mockReturnValue(null);
      global.fetch.mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({}) });
      await get("/public");
      const headers = global.fetch.mock.calls[0][1].headers;
      expect(headers.Authorization).toBeUndefined();
    });
  });
});
