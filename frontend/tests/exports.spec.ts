import { expect, test, type Download } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { uploadAndProcess } from "./support/textual";

async function contents(download: Download) {
  expect(await download.failure()).toBeNull();
  return readFile((await download.path())!, "utf8");
}

test("CSV and JSON download complete saved results with current filters and frozen semantic scores", async ({
  page,
}) => {
  const token = `Export${randomUUID().replaceAll("-", "")}`;
  const query = `${token} shall pay EUR 5000 within thirty days.`;
  const title = `Export source ${Date.now()}`;
  await uploadAndProcess(
    page,
    title,
    `${token} shall pay EUR 500 within thirty days. `.repeat(7),
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page.getByLabel("Text passage", { exact: true }).fill(query);
  await page.getByLabel("Minimum textual match").fill("85");
  await page
    .getByRole("checkbox", { name: "Compare meaning with local embeddings" })
    .check();
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/search-runs") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  const run = await (await created).json();
  expect(run.summary.occurrences_total).toBe(7);
  const card = page.getByRole("region", {
    name: `Matches in ${title}`,
    exact: true,
  });
  await expect(card.locator(".textual-occurrence")).toHaveCount(5);
  await card
    .locator(".textual-occurrence")
    .first()
    .getByRole("button", { name: "Keep", exact: true })
    .click();
  await expect(card.locator(".review-status").first()).toContainText(
    "Review: Keep",
  );
  // Unsubmitted edits and the visible occurrence page must never define the export.
  await page
    .getByLabel("Text passage", { exact: true })
    .fill("Unsubmitted expression");
  await page.getByText("Export results", { exact: true }).click();
  await page
    .getByLabel("Export review status", { exact: true })
    .selectOption("keep");
  await page.route("**/api/search-runs", (route) => route.abort());
  await page.route("**/api/search/textual", (route) => route.abort());
  let downloading = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download JSON", exact: true })
    .click();
  let download = await downloading;
  expect(download.suggestedFilename()).toBe(
    `traystack-search-${run.run_id}-keep.json`,
  );
  const kept = JSON.parse(await contents(download));
  expect(kept.result.query).toBe(query);
  expect(kept.result.summary.occurrences_total).toBe(1);
  expect(kept.result.results[0].occurrences[0].review.decision).toBe("keep");
  expect(kept.result.results[0].occurrences[0].review_at_capture.decision).toBe(
    "unreviewed",
  );
  expect(kept.result.results[0].occurrences[0].semantic_score).toBe(
    run.results[0].occurrences[0].semantic_score,
  );
  expect(kept.result.semantic).toEqual(run.semantic);
  expect(kept.result.searched_at).toBe(run.searched_at);
  expect(kept.exported_at).toBeTruthy();
  await expect(card.locator(".textual-occurrence")).toHaveCount(5);
  await page
    .getByLabel("Export review status", { exact: true })
    .selectOption("all");
  downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV", exact: true }).click();
  download = await downloading;
  const csv = await contents(download);
  expect(csv.charCodeAt(0)).toBe(0xfeff);
  expect(csv).toContain('"searched_at","exported_at"');
  expect(
    csv.split("\r\n").filter((line) => line.startsWith('"passage",')),
  ).toHaveLength(7);
  expect(csv).toContain('"keep"');
  downloading = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download JSON", exact: true })
    .click();
  const full = JSON.parse(await contents(await downloading));
  expect(full.result.results[0].occurrences).toHaveLength(7);
  expect(full.result.summary.occurrences_total).toBe(7);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("failed exports retain results and a superseded export cannot download into a new run", async ({
  page,
}) => {
  const token = `ExportFailure${randomUUID().replaceAll("-", "")}`;
  await uploadAndProcess(
    page,
    `Export errors ${Date.now()}`,
    `${token} context`,
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.locator(".textual-occurrence")).toHaveCount(1);
  await page.getByText("Export results", { exact: true }).click();
  await page.route("**/export?**", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Saved search integrity check failed" }),
    }),
  );
  await page
    .getByRole("button", { name: "Download JSON", exact: true })
    .click();
  await expect(page.getByRole("alert")).toHaveText(
    "Saved search integrity check failed",
  );
  await expect(page.locator(".textual-occurrence")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Download JSON", exact: true }),
  ).toBeEnabled();
  await page.unroute("**/export?**");
  let release!: () => void;
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  let entered!: () => void;
  const requested = new Promise<void>((resolve) => {
    entered = resolve;
  });
  const downloads: Download[] = [];
  page.on("download", (download) => downloads.push(download));
  await page.route("**/export?**", async (route) => {
    const response = await route.fetch();
    entered();
    await blocked;
    await route.fulfill({ response }).catch(() => {});
  });
  await page
    .getByRole("button", { name: "Download JSON", exact: true })
    .click();
  await requested;
  await page
    .getByLabel("Text passage", { exact: true })
    .fill(`${token} different query`);
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/search-runs") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await created;
  await expect(page.locator(".textual-response")).toContainText(
    "different query",
  );
  release();
  await page.waitForLoadState("networkidle");
  expect(downloads).toHaveLength(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
});
