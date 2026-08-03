import fs from "node:fs/promises";
import path from "node:path";

const playwrightModule = await import(process.env.PLAYWRIGHT_ENTRY || "playwright");
const chromium = playwrightModule.chromium ?? playwrightModule.default?.chromium;
if (!chromium) {
  throw new Error("Playwright Chromium is unavailable");
}

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
const VIDEO_DIR = path.join(ROOT, "goaihz", "tmp", "video");
const RAW_DIR = path.join(VIDEO_DIR, "raw");
const OUTPUT_PATH = path.join(VIDEO_DIR, "labtrace-demo-raw.webm");
const BASE_URL = process.env.LABTRACE_DEMO_URL || "http://127.0.0.1:3000/labtrace";

async function pause(page, milliseconds) {
  await page.waitForTimeout(milliseconds);
}

async function moveAndClick(page, locator) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, {
      steps: 24,
    });
  }
  await pause(page, 900);
  await locator.click();
}

async function main() {
  await fs.mkdir(RAW_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
    recordVideo: {
      dir: RAW_DIR,
      size: { width: 1280, height: 720 },
    },
  });
  const page = await context.newPage();
  const video = page.video();

  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await page.evaluate(() => window.scrollTo(0, 0));
  await pause(page, 9000);

  await moveAndClick(page, page.getByRole("button", { name: "载入匿名样例" }));
  await pause(page, 7000);

  const gradeResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/labtrace-api/grade") &&
      response.request().method() === "POST",
  );
  await moveAndClick(page, page.getByRole("button", { name: "运行批改 Agent" }));
  await gradeResponse;
  await pause(page, 8000);

  const score = page.getByText(/建议得分/).first();
  await score.scrollIntoViewIfNeeded();
  await pause(page, 10000);

  const evidence = page.getByText(/逐项评分与证据账本/).first();
  await evidence.scrollIntoViewIfNeeded();
  await pause(page, 18000);

  const adjust = page.getByRole("button", {
    name: /应用教师调整.*10.*12/,
  });
  await moveAndClick(page, adjust);
  await pause(page, 6000);

  const reviewResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/labtrace-api/review") &&
      response.request().method() === "POST",
  );
  await moveAndClick(
    page,
    page.getByRole("button", { name: "确认调整并发布" }),
  );
  await reviewResponse;
  await pause(page, 9000);

  const diagnosis = page.getByText(/从一份批改，走向下一次教学/).first();
  await diagnosis.scrollIntoViewIfNeeded();
  await pause(page, 18000);

  await page.evaluate(() =>
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }),
  );
  await pause(page, 8000);

  await page.close();
  await context.close();
  await video.saveAs(OUTPUT_PATH);
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
