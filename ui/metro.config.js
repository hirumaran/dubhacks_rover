const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");
const config = withNativeWind(getDefaultConfig(__dirname), {
  input: "./global.css",
});
const originalMiddleware = config.server?.enhanceMiddleware;
config.server = {
  ...config.server,
  enhanceMiddleware: (middleware, server) =>
    require("./scripts/scout-proxy.cjs")(
      originalMiddleware ? originalMiddleware(middleware, server) : middleware,
    ),
};
module.exports = config;
