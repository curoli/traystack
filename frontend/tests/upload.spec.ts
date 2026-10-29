import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";

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
  const title = `Browser-Demo ${Date.now()}`;
  await page.goto("/");
  await page.getByLabel("Titel", { exact: true }).fill(title);
  await page
    .getByLabel("Originaldatei", { exact: true })
    .setInputFiles(filename);
  await page.getByRole("checkbox").check();
  const uploadResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/documents/upload") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Dokument speichern" }).click();
  expect((await uploadResponse).status()).toBe(201);
  await expect(
    page.getByRole("status").filter({ hasText: "wurde gespeichert" }),
  ).toContainText("wurde gespeichert");
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await expect(page.getByText(sha, { exact: true })).toBeVisible();
  await expect(
    page.getByText("Noch nicht verarbeitet · Manuelle Prüfung vorgemerkt"),
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
  await page.getByRole("link", { name: "Original herunterladen" }).click();
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
