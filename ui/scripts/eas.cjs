// EAS CLI is a pinned external tool, not an Expo application dependency.
const fs = require("node:fs"),
  path = require("node:path"),
  { spawn } = require("node:child_process");
const npm = process.env.npm_execpath;
const npx = npm && path.join(path.dirname(npm), "npx-cli.js");
if (!npx || !fs.existsSync(npx)) {
  console.error(
    "Use npm run publish:judging to run the pinned EAS deployment tool.",
  );
  process.exit(1);
}
const child = spawn(
  process.execPath,
  [npx, "--yes", "eas-cli@25.2.0", ...process.argv.slice(2)],
  { stdio: "inherit", env: process.env, cwd: path.resolve(__dirname, "..") },
);
child.on("error", (error) => {
  console.error(error.message);
  process.exitCode = 1;
});
process.on("SIGINT", () => {});
child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
