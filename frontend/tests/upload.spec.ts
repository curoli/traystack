import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

// App language and date formatting must stay English on a German browser.
test.use({ locale: "de-DE", timezoneId: "Europe/Berlin" });

// Runs against a live local stack. Creates a synthetic document, without deleting data.
test("upload, inspect, reload and download identical original bytes", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const filename = path.resolve(
    "../examples/synthetic-contracts/A-confidentiality.pdf",
  );
  const original = await readFile(filename);
  const sha = createHash("sha256").update(original).digest("hex");
  const title = `Kündigung – Straße ${Date.now()}`;
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page).toHaveTitle("TrayStack · Contract library");
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page
    .getByLabel("Original file", { exact: true })
    .setInputFiles(filename);
  await page.getByRole("checkbox").check();
  const uploadResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/documents/upload") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Save document" }).click();
  const response = await uploadResponse;
  expect(response.status()).toBe(201);
  const document = await response.json();
  const displayedDate = new Date(document.created_at).toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    hour12: false,
    timeZone: "Europe/Berlin",
  });
  await expect(
    page.locator(".document-row").filter({ hasText: title }).locator("small"),
  ).toHaveText(`${displayedDate} · 1 revision`);
  await expect(
    page.getByRole("status").filter({ hasText: "was saved" }),
  ).toContainText("was saved");
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await expect(page.getByText(sha, { exact: true })).toBeVisible();
  await expect(
    page.getByText("Not processed yet · Flagged for manual review"),
  ).toBeVisible();
  await page.reload();
  await page
    .locator(".document-list")
    .getByRole("button", { name: new RegExp(title) })
    .click();
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download original" }).click();
  const download = await downloaded;
  expect(download.suggestedFilename()).toBe("A-confidentiality.pdf");
  const savedPath = await download.path();
  expect(savedPath).not.toBeNull();
  expect(await readFile(savedPath!)).toEqual(original);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});

// Loading the docs must work with all external network requests blocked.
test("API explorer renders the current schema without a CDN", async ({
  page,
}) => {
  const externalRequests: string[] = [];
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) {
      externalRequests.push(url.href);
      await route.abort();
    } else {
      await route.continue();
    }
  });
  await page.goto("/docs");
  await expect(
    page.getByRole("heading", { name: "TrayStack", exact: false }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("/api/documents/upload", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("Unable to render this definition")).toHaveCount(
    0,
  );
  expect(externalRequests).toEqual([]);
});

test("invalid upload shows the real API error in English", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Title", { exact: true }).fill("Invalid file demo");
  await page.getByLabel("Original file", { exact: true }).setInputFiles({
    name: "invalid.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("This is not a PDF"),
  });
  await page.getByRole("button", { name: "Save document" }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "File content does not match PDF extension",
  );
});

test("network and validation failures have English fallback messages", async ({
  page,
}) => {
  // Isolate transport/validation failures; normal workflows above use the live API.
  await page.route("**/api/documents?*", (route) => route.abort());
  await page.route("**/api/search", (route) =>
    route.fulfill({
      status: 422,
      json: { detail: [{ type: "string_too_long", loc: ["body", "query"] }] },
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("alert")).toHaveText(
    "Unable to reach the server. Please check your connection and try again.",
  );
  await page.getByLabel("Text passage", { exact: true }).fill("target");
  await page.getByRole("button", { name: "Run search" }).click();
  await expect(page.locator(".search-panel").getByRole("alert")).toHaveText(
    "Please check your input and file format.",
  );
});
