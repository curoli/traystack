import { expect, test } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { uploadAndProcess } from "./support/textual";

test("search is ready-only, absence is explicit, and review advances only after successful saves", async ({
  page,
}) => {
  const token = `Ready${randomUUID().replaceAll("-", "")}`;
  const positive = `Ready contract ${Date.now()}`;
  const negative = `Other ready contract ${Date.now()}`;
  await uploadAndProcess(
    page,
    positive,
    `${token} separate context. `.repeat(3),
  );
  await uploadAndProcess(
    page,
    negative,
    "A completely different shipping contract.",
  );
  const pending = `Pending contract ${Date.now()}`;
  await page.request.post("/api/documents/upload", {
    multipart: {
      title: pending,
      file: {
        name: "pending.txt",
        mimeType: "text/plain",
        buffer: Buffer.from(token),
      },
    },
  });
  await page.goto("/");
  await expect(page.getByLabel("Title", { exact: true })).not.toBeVisible();
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByRole("button", { name: "Run search", exact: true }).click();
  const results = page.getByRole("region", {
    name: "Search results",
    exact: true,
  });
  await expect(results).toContainText(positive);
  await expect(results).not.toContainText(pending);
  await expect(
    page.getByRole("region", { name: "Unverifiable documents", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("radio", { name: "Do NOT contain this phrase", exact: true })
    .check();
  await page.getByRole("button", { name: "Run search", exact: true }).click();
  await expect(results).toContainText(negative);
  await expect(results).not.toContainText(positive);
  await expect(results).not.toContainText(pending);
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.locator(".passage-choice")).toHaveCount(3);
  const detail = page.locator(".passage-detail");
  await detail
    .getByRole("button", { name: "View source text", exact: true })
    .click();
  await expect(
    page
      .getByRole("region", { name: "Saved source text", exact: true })
      .locator(".text-preview"),
  ).toBeVisible();
  await detail.getByRole("button", { name: "Keep", exact: true }).click();
  await expect(detail).toContainText("Passage 2 of 3");
  await expect(
    page.getByRole("region", { name: "Saved source text", exact: true }),
  ).toHaveCount(0);
  await expect(
    detail.getByRole("heading", { name: positive, exact: true }),
  ).toBeInViewport();
  await expect(page.locator(".passage-choice").first()).toContainText("Keep");
  await page.route("**/api/reviews", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "Decision could not be saved" },
    }),
  );
  await detail.getByRole("button", { name: "Dismiss", exact: true }).click();
  await expect(detail.getByRole("alert")).toHaveText(
    "Decision could not be saved",
  );
  await expect(detail).toContainText("Passage 2 of 3");
  await expect(detail.locator(".review-status")).toContainText("Not reviewed");
  await page.unroute("**/api/reviews");
  await detail.getByRole("button", { name: "Dismiss", exact: true }).click();
  await expect(detail).toContainText("Passage 3 of 3");
  await detail
    .getByRole("button", { name: "Decide later", exact: true })
    .click();
  await expect(detail).toContainText("Passage 3 of 3");
  await expect(detail.locator(".review-status")).toContainText("Decide later");
});
