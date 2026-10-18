const { spawn } = require("node:child_process");
const path = require("node:path");
const command =
  process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const child = spawn(
  command,
  [path.resolve(__dirname, "../../webcam/launch.py"), "--mobile"],
  {
    cwd: path.resolve(__dirname, "../.."),
    stdio: "inherit",
    env: process.env,
  },
);
child.on("error", (error) => {
  console.error(
    `Could not start Python: ${error.message}. Install Python 3 and Pillow (python -m pip install Pillow).`,
  );
  process.exitCode = 1;
});
process.on("SIGINT", () => {});
child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
