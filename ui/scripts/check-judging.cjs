const fs = require("node:fs");
const assert = require("node:assert/strict");
const { createClient } = require("@supabase/supabase-js");
const env = Object.fromEntries(
  fs
    .readFileSync(".env", "utf8")
    .split(/\r?\n/)
    .filter((l) => l.includes("=") && !l.startsWith("#"))
    .map((l) => {
      const n = l.indexOf("=");
      return [l.slice(0, n), l.slice(n + 1)];
    }),
);
const client = createClient(
  env.EXPO_PUBLIC_SUPABASE_URL,
  env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  { auth: { persistSession: false, autoRefreshToken: false } },
);
async function call(name, body) {
  const { data, error } = await client.functions.invoke(name, { body });
  if (error) {
    let message = error.message;
    try {
      message = JSON.stringify(await error.context.json());
    } catch {}
    throw new Error(`${name}: ${message}`);
  }
  return data;
}
async function main() {
  let user, photo;
  try {
    const login = await client.auth.signInAnonymously();
    if (login.error) throw login.error;
    user = login.data.user;
    const initialized = await client.rpc("initialize_demo");
    if (initialized.error) throw initialized.error;
    photo = `${user.id}/judging-validation.jpg`;
    const upload = await client.storage
      .from("missing-photos")
      .upload(photo, fs.readFileSync("assets/demo/backpack.jpg"), {
        contentType: "image/jpeg",
      });
    if (upload.error) throw upload.error;
    const analysis = await call("analyze-missing-photo", { image_path: photo });
    assert.equal(
      analysis.item_visible,
      true,
      "real campus photo has an identifiable item",
    );
    console.log(
      `Cloud photo analysis: ${analysis.title} · ${analysis.category} · ${analysis.color}`,
    );
    const report = await client
      .from("missing_reports")
      .insert({
        user_id: user.id,
        title: analysis.title,
        description: analysis.description,
        category: analysis.category,
        color: analysis.color,
        image_path: photo,
        last_seen_location: "Odegaard Library",
        latitude: 47.6566,
        longitude: -122.3102,
        last_seen_at: new Date().toISOString(),
      })
      .select()
      .single();
    if (report.error) throw report.error;
    const plan = await call("plan-search", { report_id: report.data.id });
    assert.ok(plan.rover_id);
    assert.equal(plan.demo, true);
    assert.equal(plan.brief.target, analysis.title);
    const again = await call("plan-search", { report_id: report.data.id });
    assert.equal(again.request_id, plan.request_id);
    const candidate = await client
      .from("item_matches")
      .select("id")
      .eq("missing_report_id", report.data.id)
      .eq("found_item_id", "10000000-0000-0000-0000-000000000002")
      .maybeSingle();
    if (candidate.data) {
      const comparison = await call("compare-items", {
        match_id: candidate.data.id,
      });
      assert.ok(Number.isFinite(comparison.similarity));
      console.log(
        `Cloud visual comparison: ${comparison.similarity}/100 · ${comparison.verdict}`,
      );
    }
    console.log(
      `Cloud rover assignment: ${plan.rover_name} · ${plan.distance_m} m · ${plan.status} · demo fleet`,
    );
    console.log(
      "Photo upload → real hosted model → private report → idempotent cloud rover plan passed.",
    );
    const current = await call("judging-feed", {
      action: "read",
      source: "webcam",
    });
    if (!current.online && fs.existsSync(".expo/cloud-test.json")) {
      const config = JSON.parse(
        fs.readFileSync("../webcam/.runtime/cloud-config.json", "utf8"),
      );
      const privateEnv = Object.fromEntries(
        fs
          .readFileSync("../edge-functions/.env", "utf8")
          .split(/\r?\n/)
          .filter((l) => l.includes("="))
          .map((l) => {
            const n = l.indexOf("=");
            return [l.slice(0, n), l.slice(n + 1)];
          }),
      );
      const endpoint = config.url + "/functions/v1/judging-feed";
      const publish = async (body, secret = privateEnv.ROVER_INGEST_SECRET) =>
        fetch(endpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${config.anon_key}`,
            "x-ingest-secret": secret,
          },
          body: JSON.stringify({ source: "webcam", ...body }),
        });
      assert.equal((await publish({ action: "clear" }, "invalid")).status, 403);
      try {
        const metadata = JSON.parse(
          fs.readFileSync(".expo/cloud-test.json", "utf8"),
        );
        const published = await publish({
          action: "publish",
          ...metadata,
          image:
            "data:image/jpeg;base64," +
            fs.readFileSync(".expo/cloud-test.jpg").toString("base64"),
          frame_id: 1,
        });
        assert.equal(published.status, 200);
        const viewed = await call("judging-feed", {
          action: "read",
          source: "webcam",
        });
        assert.equal(viewed.online, true);
        assert.equal(viewed.frame_id, 1);
        console.log(
          "Authenticated operator publish → cloud judge feed passed; invalid operator secret rejected.",
        );
      } finally {
        await publish({ action: "clear" });
      }
    }
  } finally {
    if (photo) {
      const cleanup = await client.storage
        .from("missing-photos")
        .remove([photo]);
      if (cleanup.error) console.error("Photo cleanup:", cleanup.error.message);
    }
    if (user) {
      const cleanup = await client.rpc("delete_my_account");
      if (cleanup.error) throw cleanup.error;
      console.log("Temporary judging account and photo removed.");
    }
  }
}
main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
