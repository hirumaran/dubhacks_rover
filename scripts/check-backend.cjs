// Live smoke test: uses the publishable key, never privileged credentials.
const fs = require("node:fs");
const { createClient } = require("@supabase/supabase-js");
const env = { ...process.env };
if (fs.existsSync(".env")) {
  for (const line of fs.readFileSync(".env", "utf8").split(/\r?\n/)) {
    const match = line.match(/^([A-Z_]+)=(.*)$/);
    if (match && env[match[1]] === undefined)
      env[match[1]] = match[2].trim().replace(/^['"]|['"]$/g, "");
  }
}
async function main() {
  const url = env.EXPO_PUBLIC_SUPABASE_URL;
  const key = env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key)
    throw new Error("Set the Supabase URL and publishable key in .env.");
  const db = createClient(url, key, { auth: { persistSession: false } });
  if (env.EXPO_PUBLIC_ENABLE_DEMO_AUTH !== "true") {
    const response = await fetch(`${url}/auth/v1/settings`, {
      headers: { apikey: key },
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok)
      throw new Error(`Authentication service returned ${response.status}.`);
    const settings = await response.json();
    console.log(
      `Authentication reachable; email provider: ${!!settings.external?.email}; anonymous sign-in: ${!!settings.external?.anonymous_users}.`,
    );
    const schema = await db.from("found_items").select("id").limit(0);
    if (schema.error) throw schema.error;
    console.log("Found-item API schema is reachable.");
    if (!env.HUSKYFIND_TEST_EMAIL || !env.HUSKYFIND_TEST_PASSWORD) {
      console.log(
        "Authenticated flow checks require an existing tester account (HUSKYFIND_TEST_EMAIL and HUSKYFIND_TEST_PASSWORD). No account created or authentication settings changed.",
      );
      return;
    }
    const signedIn = await db.auth.signInWithPassword({
      email: env.HUSKYFIND_TEST_EMAIL,
      password: env.HUSKYFIND_TEST_PASSWORD,
    });
    if (signedIn.error) throw signedIn.error;
    try {
      for (const table of [
        "profiles",
        "found_items",
        "missing_reports",
        "item_matches",
        "search_requests",
        "claims",
      ]) {
        const result = await db
          .from(table)
          .select("*", { count: "exact", head: true });
        if (result.error) throw result.error;
        console.log(`${table}: read permitted (${result.count} visible rows)`);
      }
    } finally {
      await db.auth.signOut({ scope: "local" });
    }
    return;
  }
  const { error: signInError } = await db.auth.signInAnonymously();
  if (signInError)
    throw new Error(
      `Demo sign-in failed: ${signInError.message}. Enable Anonymous Sign-Ins in Supabase Authentication / Sign In / Providers.`,
    );
  try {
    const init = await db.rpc("initialize_demo");
    if (init.error) throw init.error;
    for (const table of [
      "found_items",
      "missing_reports",
      "item_matches",
      "search_requests",
      "claims",
    ]) {
      const result = await db
        .from(table)
        .select("*", { count: "exact", head: true });
      if (result.error) throw result.error;
      if (!result.count)
        throw new Error(`${table} has no accessible demo rows.`);
      console.log(`${table}: ${result.count} accessible demo rows`);
    }
    console.log(
      "Live demo authentication, RLS reads, and server matching passed.",
    );
  } finally {
    const { error } = await db.rpc("delete_my_account");
    if (error)
      throw new Error(`Smoke-test account cleanup failed: ${error.message}`);
    await db.auth.signOut({ scope: "local" });
    console.log("Temporary test account removed.");
  }
}
main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
