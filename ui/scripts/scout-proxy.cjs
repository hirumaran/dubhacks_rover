// Use Metro's existing Expo tunnel for the paired camera API. No LAN IP needed.
const http = require("node:http");
const routes = new Map([
  ["/api/mobile/status", "GET"],
  ["/api/mobile/feed", "GET"],
  ["/api/mobile/analyze", "POST"],
]);
module.exports = function scoutProxy(
  next,
  port = Number(process.env.WEBCAM_PORT || 8769),
) {
  if (!Number.isInteger(port) || port < 1 || port > 65535)
    throw new Error("Invalid WEBCAM_PORT");
  return (req, res, after) => {
    const pathname = new URL(req.url, "http://localhost").pathname;
    if (!pathname.startsWith("/api/mobile/")) return next(req, res, after);
    const reply = (status, error) => {
      if (res.headersSent || res.destroyed) return;
      res.writeHead(status, {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      });
      res.end(JSON.stringify({ error }));
    };
    if (routes.get(pathname) !== req.method)
      return reply(404, "Unknown Scout endpoint.");
    if (!/^Bearer [\w-]{32,128}$/.test(req.headers.authorization || ""))
      return reply(403, "Enter the pairing code printed by scout:gateway.");
    const upstream = http.request(
      {
        hostname: "127.0.0.1",
        port,
        path: req.url,
        method: req.method,
        headers: {
          authorization: req.headers.authorization,
          ...(req.headers["content-type"]
            ? { "content-type": req.headers["content-type"] }
            : {}),
          ...(req.headers["content-length"]
            ? { "content-length": req.headers["content-length"] }
            : {}),
        },
      },
      (response) => {
        if (res.destroyed) {
          response.destroy();
          return;
        }
        res.writeHead(response.statusCode, {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        });
        response.pipe(res);
      },
    );
    upstream.setTimeout(200000, () =>
      upstream.destroy(new Error("Scout request timed out")),
    );
    upstream.on("error", () =>
      reply(
        503,
        "Scout gateway is not running on this computer. Start npm run scout:gateway in a second terminal, then reconnect.",
      ),
    );
    req.on("aborted", () => upstream.destroy());
    res.on("close", () => {
      if (!res.writableEnded) upstream.destroy();
    });
    req.pipe(upstream);
  };
};
