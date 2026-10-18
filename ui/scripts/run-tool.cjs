// Use the same supported Node runtime on developer machines and CI.
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const root = path.resolve(__dirname, "..");
const binaryName = process.platform === "win32" ? "node.exe" : "node";
const localNode = path.join(root, "node_modules", "node", "bin", binaryName);
const commands = {
  expo: "node_modules/expo/bin/cli",
  tsc: "node_modules/typescript/bin/tsc",
  tsx: "node_modules/tsx/dist/cli.mjs",
  "expo-doctor": "node_modules/expo-doctor/build/index.js",
  backend: "scripts/check-backend.cjs",
  browser: "scripts/check-app.cjs",
  scout: "scripts/start-scout.cjs",
};
const [tool, ...args] = process.argv.slice(2);
if (!commands[tool] || !fs.existsSync(localNode)) {
  console.error(
    "Run npm ci to install HuskyFind tools and its Node 24 runtime.",
  );
  process.exit(1);
}
const entry = path.join(root, commands[tool]);
const env = { ...process.env };
if (tool === "expo" && args[0] === "login" && args.includes("--browser")) {
  // Expo's Windows browser launcher can fail on URLs with query parameters.
  // Keep its local login callback running and let the user open the printed URL.
  env.BROWSER = "none";
  console.log(
    "Open the login URL printed below in your computer's browser. Keep this terminal running until login completes.",
  );
}
if (env.FORCE_COLOR !== undefined) delete env.NO_COLOR;
const pathKey =
  Object.keys(env).find((key) => key.toLowerCase() === "path") || "PATH";
env[pathKey] =
  `${path.dirname(localNode)}${path.delimiter}${env[pathKey] || ""}`;
const child = spawn(localNode, [entry, ...args], {
  cwd: root,
  env,
  stdio: "inherit",
});
child.on("error", (error) => {
  console.error(error.message);
  process.exitCode = 1;
});
// Let the interactive child receive Ctrl+C and perform its own cleanup.
process.on("SIGINT", () => {});
child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
