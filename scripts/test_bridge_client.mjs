import assert from "node:assert/strict";
import { createClip, resolveSource, validateBridgeBase, validateBridgeEnvelope, validatePageUrl } from "../public_boundary/client/bridge_client.js";

assert.deepEqual(
  validateBridgeEnvelope({ schema_version: "1.0", request_id: "r1", data: { state: "ready" } }),
  { schema_version: "1.0", request_id: "r1", data: { state: "ready" } },
);

for (const payload of [
  { schema_version: "0.9", data: {} },
  { schema_version: "1.0" },
  { schema_version: "1.0", data: {}, error: {} },
  { schema_version: "1.0", error: "bad" },
]) {
  assert.throws(() => validateBridgeEnvelope(payload), /Bridge returned/);
}

let capturedRequest = null;
const originalFetch = globalThis.fetch;
globalThis.fetch = async (url, options) => {
  capturedRequest = { url: String(url), options };
  return new Response(JSON.stringify({
    schema_version: "1.0",
    request_id: "r2",
    data: { source_url: "https://example.com/video", matches: [] },
  }), { status: 200, headers: { "content-type": "application/json" } });
};
try {
  await resolveSource("http://127.0.0.1:5188", "https://example.com/video?utm_source=test");
  assert.equal(capturedRequest.options.credentials, "omit");
  assert.deepEqual(Object.fromEntries(capturedRequest.options.headers), { accept: "application/json" });
  assert.match(capturedRequest.url, /\/v1\/knowledge\/resolve\?source_url=https%3A%2F%2Fexample\.com%2Fvideo/);
  await createClip("http://127.0.0.1:5188", { target: { knowledge_id: "demo" } }, "clip-runtime-key");
  assert.deepEqual(Object.fromEntries(capturedRequest.options.headers), {
    accept: "application/json",
    "content-type": "application/json",
    "idempotency-key": "clip-runtime-key",
  });
  assert.throws(() => validateBridgeBase("https://remote.example"), /本地回环/);
  assert.throws(() => validatePageUrl("https://user:secret@example.com/video"), /不能包含凭据/);
  assert.equal(validatePageUrl("https://example.com/video#private-fragment"), "https://example.com/video");
} finally {
  globalThis.fetch = originalFetch;
}

console.log("bridge envelope and credential-free request checks passed");
