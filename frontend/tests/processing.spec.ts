import { expect, test } from "@playwright/test";
import path from "node:path";

for (const fixture of [
  { file: "A-confidentiality.pdf", review: false, complete: true },
  { file: "P-printed-scan.jpg", review: true, complete: true },
  { file: "E-difficult-scan.jpg", review: true, complete: false },
]) {
  test(`worker processes ${fixture.file} with honest quality and downloadable derivatives`, async ({
    page,
  }) => {
    const title = `Processing demo ${fixture.file} ${Date.now()}`;
    await page.goto("/");
    await page.getByLabel("Title", { exact: true }).fill(title);
    await page
      .getByLabel("Original file", { exact: true })
      .setInputFiles(
        path.resolve("../examples/synthetic-contracts", fixture.file),
      );
    if (fixture.review)
      await page
        .getByRole("checkbox", { name: /Manual review required/ })
        .check();
    const uploaded = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/documents/upload") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Save document" }).click();
    const document = await (await uploaded).json();
    const revisionId = document.revisions[0].id;
    const queued = page.waitForResponse((response) =>
      response.url().endsWith(`/api/revisions/${revisionId}/process`),
    );
    await page.getByRole("button", { name: "Start processing" }).click();
    const response = await queued;
    expect(response.status()).toBe(202);
    const job = await response.json();
    const quality = page.locator(".quality-panel");
    await expect(quality).toContainText(job.id, { timeout: 60_000 });
    if (fixture.complete)
      await expect(quality.getByRole("heading")).toHaveText("Fully processed");
    await expect(quality.locator("strong")).toHaveText(
      fixture.review ? "Manual review required" : "No known quality issue",
    );
    if (fixture.review)
      await expect(page.locator(".review-group")).toContainText(title);
    await page.getByRole("button", { name: "View page text" }).click();
    const viewer = page.getByRole("region", {
      name: "Extracted page text",
    });
    await expect(viewer).toBeVisible();
    if (fixture.complete) {
      const text = await viewer.locator("pre").innerText();
      expect(text.replace(/\s+/g, " ").toLowerCase()).toContain(
        "the receiving party shall not disclose confidential information",
      );
    }
    const structured = page
      .locator(".artifact")
      .filter({ hasText: "Structured extraction · JSON" });
    await structured
      .getByRole("button", { name: "Text preview", exact: true })
      .click();
    await expect(structured.locator("pre")).toContainText(job.id);
    await expect(page.getByRole("link", { name: "Download file" })).toHaveCount(
      2,
    );
    if (!fixture.review) {
      const requeued = page.waitForResponse((response) =>
        response.url().endsWith(`/api/revisions/${revisionId}/process`),
      );
      await page.getByRole("button", { name: "Reprocess" }).click();
      const nextJob = await (await requeued).json();
      expect(nextJob.id).not.toBe(job.id);
      await expect(quality).toContainText(nextJob.id, { timeout: 60_000 });
      await expect(page.locator(".artifact")).toHaveCount(5);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  });
}
