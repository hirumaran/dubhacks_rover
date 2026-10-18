const fs = require("node:fs"),
  path = require("node:path"),
  { spawnSync } = require("node:child_process");
const result = spawnSync(
  "supabase",
  [
    "projects",
    "api-keys",
    "--project-ref",
    "salsusdncqbtrkcqxdkg",
    "-o",
    "json",
  ],
  { encoding: "utf8", windowsHide: true },
);
if (result.status !== 0) {
  console.error(
    "Sign into the Supabase CLI before configuring the operator relay.",
  );
  process.exit(1);
}
const keys = JSON.parse(result.stdout),
  anon = keys.find((key) => key.name === "anon" || key.type === "anon");
if (!anon?.api_key) {
  console.error("No public legacy anon JWT is available for the gateway.");
  process.exit(1);
}
const destination = path.resolve(
  __dirname,
  "../../webcam/.runtime/cloud-config.json",
);
fs.mkdirSync(path.dirname(destination), { recursive: true });
fs.writeFileSync(
  destination,
  JSON.stringify({
    url: "https://salsusdncqbtrkcqxdkg.supabase.co",
    anon_key: anon.api_key,
  }),
);
console.log(
  "Operator relay configured. No service-role key was stored. Click Share with judging link on the laptop camera page to publish.",
);
