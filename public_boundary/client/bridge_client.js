/* Viewledge Bridge client: product data only, no private implementation imports. */

export const DEFAULT_BRIDGE_BASE = "http://127.0.0.1:5188";

function trimBase(value) {
  const raw = String(value || "").trim().replace(/\/+$/, "");
  if (!/^https?:\/\//i.test(raw)) throw new Error("Bridge \u5730\u5740\u5fc5\u987b\u4f7f\u7528 HTTP \u6216 HTTPS\u3002");
  return raw;
}

function isLoopbackHost(hostname) {
  const normalized = String(hostname || "").toLowerCase();
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "[::1]";
}

export function validateBridgeBase(value) {
  const raw = trimBase(value);
  let parsed;
  try { parsed = new URL(raw); } catch { throw new Error("Bridge \u5730\u5740\u65e0\u6548\u3002"); }
  if (!isLoopbackHost(parsed.hostname)) throw new Error("Bridge \u5730\u5740\u5fc5\u987b\u4f7f\u7528\u672c\u5730\u56de\u73af\u4e3b\u673a\u3002");
  if (parsed.username || parsed.password || parsed.search || parsed.hash || (parsed.pathname && parsed.pathname !== "/")) {
    throw new Error("Bridge \u5730\u5740\u4e0d\u80fd\u5305\u542b\u51ed\u636e\u3001\u8def\u5f84\u6216\u67e5\u8be2\u53c2\u6570\u3002");
  }
  return parsed.origin;
}

function assertHttpUrl(value, field = "URL") {
  let parsed;
  try { parsed = new URL(String(value || "")); } catch { throw new Error(`${field} \u65e0\u6548\u3002`); }
  if (!/^https?:$/.test(parsed.protocol)) throw new Error(`${field} \u5fc5\u987b\u4f7f\u7528 HTTP \u6216 HTTPS\u3002`);
  if (parsed.username || parsed.password) throw new Error(`${field} \u4e0d\u80fd\u5305\u542b\u51ed\u636e\u3002`);
  parsed.hash = "";
  return parsed.toString();
}

function requestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function validateBridgeEnvelope(payload) {
  if (!payload || payload.schema_version !== "1.0") {
    throw new Error("Bridge returned an unsupported response version.");
  }
  const hasData = Object.prototype.hasOwnProperty.call(payload, "data");
  const hasError = Object.prototype.hasOwnProperty.call(payload, "error");
  if (hasData === hasError) {
    throw new Error("Bridge returned an invalid response envelope.");
  }
  if (hasError && (!payload.error || typeof payload.error !== "object")) {
    throw new Error("Bridge returned an invalid error envelope.");
  }
  return payload;
}

async function requestJson(base, path, options = {}) {
  const headers = new Headers({ Accept: "application/json" });
  for (const [name, value] of new Headers(options.headers || {})) {
    const normalized = name.toLowerCase();
    if (normalized === "content-type") headers.set("Content-Type", value);
    if (normalized === "idempotency-key") headers.set("Idempotency-Key", value);
  }
  const response = await fetch(`${validateBridgeBase(base)}${path}`, {
    ...options,
    // Keep the public client credential-free even if a future caller passes
    // an options object with a conflicting credentials value.
    credentials: "omit",
    headers,
  });
  let payload;
  try { payload = await response.json(); } catch { throw new Error(`Bridge returned an unreadable response (${response.status}).`); }
  validateBridgeEnvelope(payload);
  if (!response.ok || payload.error) {
    const error = new Error(String(payload?.error?.message || "Bridge request failed."));
    error.code = String(payload?.error?.code || `http_${response.status}`);
    error.retryable = Boolean(payload?.error?.retryable);
    throw error;
  }
  return payload.data;
}

export function validatePageUrl(value) { return assertHttpUrl(value, "\u5f53\u524d\u9875\u9762 URL"); }

export async function resolveSource(base, sourceUrl) {
  const query = new URLSearchParams({ source_url: validatePageUrl(sourceUrl) });
  return requestJson(base, `/v1/knowledge/resolve?${query.toString()}`);
}

export async function readTranscript(base, knowledgeId) {
  const id = String(knowledgeId || "").trim();
  if (!id || id.length > 200 || /[\\/]/.test(id)) throw new Error("\u77e5\u8bc6\u8bb0\u5f55\u6807\u8bc6\u65e0\u6548\u3002");
  return requestJson(base, `/v1/knowledge/${encodeURIComponent(id)}/transcript`);
}

export async function createClip(base, payload, idempotencyKey = requestId()) {
  return requestJson(base, "/v1/clips", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ schema_version: "1.0", client_request_id: idempotencyKey, ...payload }),
  });
}

export async function createIntake(base, payload, idempotencyKey = requestId()) {
  return requestJson(base, "/v1/intakes", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ schema_version: "1.0", client_request_id: idempotencyKey, ...payload }),
  });
}
