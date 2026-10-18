// Real browser startup check using a fresh, isolated anonymous test account.
// Never use an existing browser profile or save authentication tokens to disk.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { setTimeout: delay } = require("node:timers/promises");
const { chromium } = require("playwright-core");

async function main() {
  const executablePath =
    process.env.CHROME_PATH ||
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
  if (!fs.existsSync(executablePath))
    throw new Error(
      "Set CHROME_PATH to an installed Chromium/Chrome/Edge executable.",
    );
  const base = process.env.HUSKYFIND_TEST_URL || "http://localhost:8082";
  const deadline = Date.now() + 90000;
  while (true) {
    try {
      const response = await fetch(base, { signal: AbortSignal.timeout(5000) });
      if (response.ok) break;
    } catch {}
    if (Date.now() > deadline)
      throw new Error(
        `Metro is not ready at ${base}. Start it before running the browser check.`,
      );
    await delay(500);
  }
  const browser = await chromium.launch({
    executablePath,
    headless: true,
    args:
      process.env.HUSKYFIND_SCOUT_SMOKE === "1"
        ? [
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
          ]
        : [],
  });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const page = await context.newPage();
  const runtimeErrors = [];
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  try {
    await page.goto(base, { timeout: 120000 });
    await page
      .getByRole("button", { name: "Explore Demo", exact: true })
      .click({ timeout: 120000 });
    const bottle = page
      .getByRole("button", {
        name: "View Black insulated bottle",
        exact: true,
      })
      .first();
    await bottle.waitFor({ timeout: 60000 });
    console.log("Demo sign-in and initialized Discover feed rendered.");

    const search = page.getByLabel("Search found items");
    await search.fill("headphones");
    await page
      .getByRole("button", { name: "View Wireless headphones", exact: true })
      .waitFor();
    await page
      .getByRole("button", { name: "View Everyday backpack", exact: true })
      .waitFor({ state: "hidden" });
    await search.fill("");
    await bottle.waitFor();
    console.log("Live listing search passed.");

    await bottle.click();
    await page
      .getByRole("button", { name: "This might be mine", exact: true })
      .waitFor();
    await page.getByRole("button", { name: "Save item", exact: true }).click();
    await page
      .getByRole("button", { name: "Remove from saved", exact: true })
      .waitFor();
    await page
      .getByRole("button", { name: "Remove from saved", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Save item", exact: true })
      .waitFor();
    console.log("Item details and saved-item writes passed.");

    await page.goto(`${base}/activity`, { timeout: 60000 });
    await page
      .getByText("My black water bottle (demo)", { exact: true })
      .waitFor({ timeout: 60000 });
    await page.getByText("queued", { exact: true }).waitFor();
    await page.goto(`${base}/profile`, { timeout: 60000 });
    await page
      .getByText("DEMO EXPLORER", { exact: true })
      .waitFor({ timeout: 60000 });
    await page.goto(base, { timeout: 60000 });
    await bottle.waitFor({ timeout: 60000 });
    console.log("Activity, Profile, and session restoration passed.");
    if (process.env.HUSKYFIND_ACTIONS_SMOKE === "1") await require("./check-judging-actions.cjs")(page,base);
    if (process.env.HUSKYFIND_JUDGING_SMOKE === "1") await require("./check-judging-ui.cjs")(page,base);
    if (process.env.HUSKYFIND_SCOUT_SMOKE === "1")
      await require("./check-scout.cjs")(page, base);
    assert.deepEqual(runtimeErrors, [], "No uncaught browser runtime errors");
  } catch (error) {
    console.error("Uncaught runtime errors:", runtimeErrors);
    console.error(
      "Visible page:",
      (
        await page
          .locator("body")
          .innerText()
          .catch(() => "unavailable")
      ).slice(0, 3000),
    );
    throw error;
  } finally {
    try {
      const env = Object.fromEntries(
        fs
          .readFileSync(path.join(__dirname, "..", ".env"), "utf8")
          .split(/\r?\n/)
          .filter((line) => line.includes("="))
          .map((line) => {
            const split = line.indexOf("=");
            return [line.slice(0, split), line.slice(split + 1)];
          }),
      );
      const removed = await page.evaluate(
        async ({ url, key }) => {
          let storageKeys;
          try {
            storageKeys = Object.keys(localStorage);
          } catch {
            return false;
          }
          for (const storageKey of storageKeys) {
            let session;
            try {
              session = JSON.parse(localStorage.getItem(storageKey));
            } catch {
              continue;
            }
            if (!session?.access_token || !session?.user?.is_anonymous)
              continue;
            const storageHeaders={apikey:key,Authorization:`Bearer ${session.access_token}`,"Content-Type":"application/json"};
            const files=await fetch(`${url}/storage/v1/object/list/missing-photos`,{method:"POST",headers:storageHeaders,body:JSON.stringify({prefix:session.user.id+"/",limit:100})});
            if(files.ok){const photos=await files.json();const prefixes=photos.filter(p=>p.name.endsWith(".jpg")).map(p=>session.user.id+"/"+p.name);if(prefixes.length)await fetch(`${url}/storage/v1/object/missing-photos`,{method:"DELETE",headers:storageHeaders,body:JSON.stringify({prefixes})});}
            const response = await fetch(
              `${url}/rest/v1/rpc/delete_my_account`,
              {
                method: "POST",
                headers: {
                  apikey: key,
                  Authorization: `Bearer ${session.access_token}`,
                  "Content-Type": "application/json",
                },
                body: "{}",
              },
            );
            if (!response.ok)
              throw new Error(
                `Test account cleanup returned ${response.status}`,
              );
            localStorage.removeItem(storageKey);
            return true;
          }
          return false;
        },
        {
          url: env.EXPO_PUBLIC_SUPABASE_URL,
          key: env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
        },
      );
      if (removed) console.log("Temporary browser test account removed.");
    } finally {
      await context.close();
      await browser.close();
    }
  }
}
main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
