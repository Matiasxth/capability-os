import { describe, it, expect, beforeEach } from "vitest";
import { getToken, setToken, clearToken, saveChatMessages, restoreChatMessages, clearChatMessages } from "../session.js";

describe("session", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  describe("token management", () => {
    it("returns null when no token", () => {
      expect(getToken()).toBeNull();
    });

    it("stores and retrieves token", () => {
      setToken("abc123");
      expect(getToken()).toBe("abc123");
    });

    it("clears token", () => {
      setToken("abc123");
      clearToken();
      expect(getToken()).toBeNull();
    });
  });

  describe("chat persistence", () => {
    it("returns empty array when nothing saved", () => {
      expect(restoreChatMessages()).toEqual([]);
    });

    it("persists and restores messages", () => {
      const msgs = [
        { id: 1, role: "user", content: "hello" },
        { id: 2, role: "system", content: "hi" },
      ];
      saveChatMessages(msgs);
      expect(restoreChatMessages()).toEqual(msgs);
    });

    it("clears messages", () => {
      saveChatMessages([{ id: 1, content: "test" }]);
      clearChatMessages();
      expect(restoreChatMessages()).toEqual([]);
    });

    it("handles corrupted JSON gracefully", () => {
      sessionStorage.setItem("capos_chat_session", "not-json");
      expect(restoreChatMessages()).toEqual([]);
    });
  });
});
