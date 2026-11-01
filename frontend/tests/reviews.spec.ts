import { expect, test } from "@playwright/test";
import { uploadAndProcess } from "./support/textual";

async function setup(page: import("@playwright/test").Page) {
  const token = `ManualReview${Date.now()}`;
  await uploadAndProcess(page, token, `${token} context. `.repeat(2));
  await page.goto("/");
  await page
    .getByLabel("Auto-confirm strong matches", { exact: true })
    .uncheck();
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.locator(".passage-choice")).toHaveCount(2);
}

test("three mutually exclusive states stay on the same passage and persist across reload", async ({
  page,
}) => {
  await setup(page);
  const detail = page.locator(".passage-detail");
  for (const state of [
    "Unreviewed",
    "Confirm match",
    "Dismiss match",
    "Unreviewed",
  ]) {
    const button = detail.getByRole("button", { name: state, exact: true });
    if (
      state !== "Unreviewed" ||
      (await button.getAttribute("aria-pressed")) !== "true"
    )
      await button.click();
    await expect(button).toHaveAttribute("aria-pressed", "true");
    await expect(
      detail.locator('.review-buttons button[aria-pressed="true"]'),
    ).toHaveCount(1);
    await expect(detail).toContainText("Passage 1 of 2");
  }
  await detail
    .getByRole("button", { name: "Dismiss match", exact: true })
    .click();
  await expect(detail.locator(".review-status")).toContainText("Dismiss match");
  await page.reload();
  await expect(page.locator(".review-status")).toContainText("Dismiss match");
});

test("a failed state save keeps the previous state and selection", async ({
  page,
}) => {
  await setup(page);
  await page.route("**/api/reviews", (route) =>
    route.fulfill({ status: 503, json: { detail: "Review unavailable" } }),
  );
  const detail = page.locator(".passage-detail");
  await detail
    .getByRole("button", { name: "Confirm match", exact: true })
    .click();
  await expect(detail.getByRole("alert")).toHaveText("Review unavailable");
  await expect(
    detail.getByRole("button", { name: "Unreviewed", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(detail).toContainText("Passage 1 of 2");
});

test("a late state save cannot affect a replacement search", async ({
  page,
}) => {
  await setup(page);
  let release!: () => void, entered!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const started = new Promise<void>((resolve) => {
    entered = resolve;
  });
  await page.route("**/api/reviews", async (route) => {
    const response = await route.fetch();
    entered();
    await gate;
    await route.fulfill({ response }).catch(() => {});
  });
  await page
    .getByRole("button", { name: "Confirm match", exact: true })
    .click();
  await started;
  await page
    .getByLabel("Text passage", { exact: true })
    .fill(`Missing${Date.now()}`);
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.locator(".textual-response")).toContainText("Missing");
  release();
  await page.waitForLoadState("networkidle");
  await expect(page.locator(".textual-occurrence")).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "Review counts", exact: true }),
  ).toContainText("Confirmed: 0");
});
