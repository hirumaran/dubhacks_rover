import assert from "node:assert/strict";
import http, { Server } from "node:http";
import { test } from "node:test";
const scoutProxy = require("../scripts/scout-proxy.cjs");
const token = "a".repeat(43);
test("unrelated Expo Router pages retain middleware fallthrough", () => {
  let reached = false;
  const middleware = scoutProxy(
    (_req: unknown, _res: unknown, after: () => void) => after(),
  );
  middleware({ url: "/activity" }, {}, () => {
    reached = true;
  });
  assert.equal(reached, true);
});
async function listen(server: Server) {
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  return (server.address() as { port: number }).port;
}
async function close(server: Server) {
  server.closeAllConnections();
  await new Promise<void>((resolve) => server.close(() => resolve()));
}
test("Expo proxy forwards paired scans/feed, denies private routes and reports a stopped gateway", async () => {
  let calls = 0;
  const gateway = http.createServer(async (req, res) => {
    calls++;
    assert.equal(req.headers.authorization, `Bearer ${token}`);
    let body = "";
    for await (const chunk of req) body += chunk;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ path: req.url, method: req.method, body }));
  });
  const gatewayPort = await listen(gateway);
  const proxy = http.createServer(
    scoutProxy((_req: unknown, res: http.ServerResponse) => {
      res.writeHead(404);
      res.end();
    }, gatewayPort),
  );
  const base = `http://127.0.0.1:${await listen(proxy)}`;
  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
  try {
    const status = await fetch(`${base}/api/mobile/status`, { headers });
    assert.equal(status.status, 200);
    const scan = await fetch(`${base}/api/mobile/analyze`, {
      method: "POST",
      headers,
      body: JSON.stringify({ image: "pixels" }),
    });
    assert.equal((await scan.json()).body, '{"image":"pixels"}');
    const feed = await fetch(`${base}/api/mobile/feed?source=webcam`, {
      headers,
    });
    assert.equal((await feed.json()).path, "/api/mobile/feed?source=webcam");
    assert.equal((await fetch(`${base}/api/mobile/status`)).status, 403);
    assert.equal((await fetch(`${base}/api/config`, { headers })).status, 404);
    assert.equal(
      (await fetch(`${base}/api/mobile/../config`, { headers })).status,
      404,
    );
    assert.equal(calls, 3);
    await close(gateway);
    const stopped = await fetch(`${base}/api/mobile/status`, { headers });
    assert.equal(stopped.status, 503);
    assert.match((await stopped.json()).error, /scout:gateway/);
  } finally {
    if (gateway.listening) await close(gateway);
    await close(proxy);
  }
});
