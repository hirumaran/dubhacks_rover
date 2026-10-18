// Real UI/camera capture + production gateway, with an explicit offline model fixture.
const { spawn } = require("node:child_process");
const path = require("node:path");
module.exports = async function checkScout(page, base) {
  const child = spawn(
    process.env.PYTHON || (process.platform === "win32" ? "python" : "python3"),
    [path.resolve(__dirname, "../../webcam/tests/mobile_fixture.py")],
    { stdio: ["ignore", "pipe", "inherit"] },
  );
  let desktop;
  try {
    const link = await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("Scout test gateway did not start.")),
        15000,
      );
      let buffer = "";
      child.stdout.on("data", (data) => {
        buffer += data.toString();
        if (buffer.includes("\n")) {
          clearTimeout(timer);
          try {
            resolve(JSON.parse(buffer.split("\n")[0]).url);
          } catch (error) {
            reject(error);
          }
        }
      });
      child.on("error", (error) => {
        clearTimeout(timer);
        reject(error);
      });
      child.on("exit", (code) => {
        clearTimeout(timer);
        reject(new Error(`Scout fixture exited: ${code}`));
      });
    });
    await page.goto(`${base}/scout`, { timeout: 120000 });
    await page
      .getByLabel("Scout pairing code")
      .fill(new URL(link).hash.slice(1));
    await page
      .getByRole("button", { name: "Connect to Scout", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Phone camera", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Enable camera", exact: true })
      .click({ timeout: 60000 });
    const scan = page.getByRole("button", {
      name: "Scan this view",
      exact: true,
    });
    await scan.click({ timeout: 60000 });
    await page
      .getByText("Black backpack", { exact: true })
      .first()
      .waitFor({ timeout: 60000 });
    await page
      .getByRole("button", { name: "Start 5-second scans", exact: true })
      .click();
    await page
      .getByText(/Seen in 2 consecutive scans/)
      .waitFor({ timeout: 30000 });
    await page
      .getByRole("button", { name: "Pause scans", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Stop camera", exact: true })
      .click();
    await page.getByRole("button", { name: "Live feed", exact: true }).click();
    await page.getByRole("button", { name: "Rover", exact: true }).click();
    await page
      .getByText("Fixture bottle", { exact: true })
      .first()
      .waitFor({ timeout: 15000 });
    await page
      .getByRole("button", { name: "Laptop webcam", exact: true })
      .click();
    await page.getByText("OFFLINE / WAITING", { exact: true }).waitFor();
    desktop = await page.context().newPage();
    await desktop.setViewportSize({ width: 1280, height: 900 });
    // A deterministic moving laptop source avoids depending on a physical
    // camera or Chromium's cross-origin fake-device availability on Windows.
    await desktop.addInitScript(() => {
      Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
        configurable: true,
        value: async () => {
          const canvas = document.createElement("canvas");
          canvas.width = 640;
          canvas.height = 480;
          const context = canvas.getContext("2d");
          let tick = 0;
          const draw = () => {
            context.fillStyle = "#476955";
            context.fillRect(0, 0, 640, 480);
            context.fillStyle = "#FCCFA5";
            context.fillRect((tick * 13) % 500, 100, 100, 150);
            context.fillStyle = "white";
            context.font = "32px sans-serif";
            context.fillText(`Test camera ${tick++}`, 30, 400);
          };
          draw();
          const timer = setInterval(draw, 66);
          const stream = canvas.captureStream(15);
          for (const track of stream.getTracks()) {
            const stop = track.stop.bind(track);
            track.stop = () => {
              clearInterval(timer);
              stop();
            };
          }
          return stream;
        },
      });
      Object.defineProperty(navigator.mediaDevices, "enumerateDevices", {
        configurable: true,
        value: async () => [
          {
            kind: "videoinput",
            deviceId: "test-laptop",
            label: "Moving test camera",
            groupId: "test",
          },
        ],
      });
    });
    await desktop.bringToFront();
    let injectedUploadFailure = false;
    await desktop.route("**/api/preview", async (route) => {
      const body = JSON.parse(route.request().postData() || "{}");
      if (body.image && !injectedUploadFailure) {
        injectedUploadFailure = true;
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: '{"error":"Temporary upload interruption (test)"}',
        });
      } else await route.continue();
    });
    await desktop.goto(new URL(link).origin);
    await desktop
      .getByRole("button", { name: "Enable webcam", exact: true })
      .click();
    await desktop.waitForFunction(() => {
      const video = document.querySelector("video");
      return video?.readyState >= 2 && video.videoWidth > 0;
    });
    await desktop
      .getByRole("button", { name: "Stop sharing preview", exact: true })
      .waitFor();
    await page
      .getByText("LIVE · SAMPLED FRAMES", { exact: true })
      .waitFor({ timeout: 15000 });
    const initialPreview = await page.evaluate(() => {
      const counter = document.querySelector(
        '[data-testid="live-frame-counter"]',
      );
      const image = document.querySelector(
        '[aria-label="Live camera preview"]',
      );
      return {
        count: Number(counter?.textContent?.match(/frame (\d+)/)?.[1]),
        pixels:
          image?.querySelector("img")?.src || image?.style.backgroundImage,
      };
    });
    // Reproduce a minimized/background laptop tab after the first frame arrives.
    await desktop.evaluate(() =>
      Object.defineProperty(document, "hidden", {
        configurable: true,
        get: () => true,
      }),
    );
    await page.waitForFunction(
      (initial) => {
        const counter = document.querySelector(
          '[data-testid="live-frame-counter"]',
        );
        const image = document.querySelector(
          '[aria-label="Live camera preview"]',
        );
        const pixels =
          image?.querySelector("img")?.src || image?.style.backgroundImage;
        return (
          Number(counter?.textContent?.match(/frame (\d+)/)?.[1]) >=
            initial.count + 4 &&
          pixels &&
          pixels !== initial.pixels
        );
      },
      initialPreview,
      { timeout: 25000 },
    );
    console.log(
      "Laptop preview delivered multiple changing images after an upload failure and with a hidden laptop tab.",
    );
    await desktop
      .getByRole("button", { name: "Scan this view", exact: true })
      .click();
    await page
      .getByText("Latest laptop analysis", { exact: true })
      .waitFor({ timeout: 15000 });
    await page
      .getByRole("button", { name: "Start 5-second scans", exact: true })
      .click();
    await page
      .getByText("Your last 3 scans", { exact: true })
      .waitFor({ timeout: 30000 });
    await page
      .getByRole("button", { name: "Pause scans", exact: true })
      .click();
    await desktop
      .getByRole("button", { name: "Stop camera", exact: true })
      .click();
    await page
      .getByText("OFFLINE / WAITING", { exact: true })
      .waitFor({ timeout: 15000 });
    await page
      .getByRole("button", { name: "Disconnect Scout", exact: true })
      .click();
    await page.getByLabel("Scout pairing code").waitFor();
    console.log(
      "Scout pairing, camera capture, automatic/repeat scans, rover feed, webcam sharing/offline states, and disconnect passed (offline model fixture).",
    );
  } catch (error) {
    if (desktop && !desktop.isClosed()) {
      console.error(
        "Laptop preview diagnostics:",
        await desktop
          .evaluate(() => {
            const video = document.querySelector("video");
            return {
              status: document.getElementById("status")?.textContent,
              sharing: document.getElementById("share-status")?.textContent,
              readyState: video?.readyState,
              paused: video?.paused,
              track: video?.srcObject?.getVideoTracks?.()[0]?.readyState,
            };
          })
          .catch(() => "unavailable"),
      );
    }
    throw error;
  } finally {
    await desktop?.close();
    child.kill();
  }
};
