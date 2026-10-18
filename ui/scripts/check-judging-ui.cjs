const path = require("node:path"),
  fs = require("node:fs"),
  assert = require("node:assert/strict");
module.exports = async function checkJudging(page, base) {
  await page.goto(`${base}/report`, { timeout: 120000 });
  await page
    .getByRole("button", { name: "Try backpack photo", exact: true })
    .waitFor();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Choose photo", exact: true }).click();
  await (
    await chooser
  ).setFiles(path.resolve(__dirname, "../assets/demo/backpack.jpg"));
  await page
    .getByText("AI PHOTO ANALYSIS COMPLETE", { exact: true })
    .waitFor({ timeout: 120000 });
  assert.match(
    await page.getByLabel("Item name", { exact: true }).inputValue(),
    /backpack/i,
  );
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page
    .getByRole("button", { name: "Start my search", exact: true })
    .click();
  await page
    .getByText("DEMO FLEET · SIMULATED DISPATCH", { exact: true })
    .waitFor({ timeout: 120000 });
  await page.getByText("Scout · Red Square", { exact: true }).waitFor();
  const output = path.resolve(__dirname, "../.expo/judging-qa");
  fs.mkdirSync(output, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: path.join(output, "phone-search-plan.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(base, { timeout: 120000 });
  await page
    .getByRole("button", { name: "View Everyday backpack", exact: true })
    .waitFor({ timeout: 60000 });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 2,
    ),
    "Desktop has no page-level horizontal overflow",
  );
  await page.screenshot({
    path: path.join(output, "desktop-discover.png"),
    fullPage: true,
  });
  await page.goto(`${base}/item/10000000-0000-0000-0000-000000000001`,{timeout:60000});
  await page.getByRole("button",{name:"This might be mine",exact:true}).waitFor({timeout:60000});
  await page.reload();
  await page.getByRole("button",{name:"This might be mine",exact:true}).waitFor({timeout:60000});
  await page.goto(`${base}/scout`,{timeout:60000});
  await page.getByText("CLOUD JUDGING FEED · NO PAIRING CODE NEEDED",{exact:true}).waitFor();
  await page.goto(`${base}/report`, { timeout: 60000 });
  await page
    .getByRole("button", { name: "Choose photo", exact: true })
    .waitFor();
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 2,
    ),
    "Desktop report form fits its viewport",
  );
  await page.screenshot({
    path: path.join(output, "desktop-report.png"),
    fullPage: true,
  });
  console.log(
    "Hosted judging UI: actual photo upload, cloud AI prefill, private report, rover assignment, responsive desktop, refreshed item links, and unpaired cloud Scout passed.",
  );
};
