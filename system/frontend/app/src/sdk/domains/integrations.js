import { get, post, del } from "../client.js";

/** Generic channel helpers — avoids copy-paste for telegram/slack/discord/whatsapp */
function channelDomain(prefix) {
  return {
    status: () => get(`${prefix}/status`),
    configure: (config) => post(`${prefix}/configure`, typeof config === "object" ? config : {}),
    test: () => post(`${prefix}/test`, {}),
    startPolling: () => post(`${prefix}/polling/start`, {}),
    stopPolling: () => post(`${prefix}/polling/stop`, {}),
    pollingStatus: () => get(`${prefix}/polling/status`),
  };
}

export const integrations = {
  list: () => get("/integrations"),
  get: (id) => get(`/integrations/${id}`),
  validate: (id) => post(`/integrations/${id}/validate`, {}),
  enable: (id) => post(`/integrations/${id}/enable`, {}),
  disable: (id) => post(`/integrations/${id}/disable`, {}),

  telegram: {
    ...channelDomain("/integrations/telegram"),
    configure: (botToken, defaultChatId, allowedUserIds) =>
      post("/integrations/telegram/configure", {
        bot_token: botToken,
        default_chat_id: defaultChatId || "",
        allowed_user_ids: allowedUserIds || [],
      }),
  },

  slack: channelDomain("/integrations/slack"),
  discord: channelDomain("/integrations/discord"),

  whatsapp: {
    status: () => get("/integrations/whatsapp/session-status"),
    start: () => post("/integrations/whatsapp/start", {}),
    stop: () => post("/integrations/whatsapp/stop", {}),
    closeSession: () => post("/integrations/whatsapp/close-session", {}),
    qr: () => get("/integrations/whatsapp/qr"),
    configure: (config) => post("/integrations/whatsapp/configure", config),
    switchBackend: (backend) => post("/integrations/whatsapp/switch-backend", { backend }),
    listBackends: () => get("/integrations/whatsapp/backends"),
  },

  // New channels (Sprint 9)
  signal: channelDomain("/integrations/signal"),
  matrix: channelDomain("/integrations/matrix"),
  teams: channelDomain("/integrations/teams"),
  email: channelDomain("/integrations/email"),
  webhook: channelDomain("/integrations/webhook"),
};
