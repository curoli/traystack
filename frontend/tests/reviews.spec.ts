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
  await expect(
    page
      .locator(".passage-detail")
      .getByRole("button", { name: "Unreviewed", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page
      .locator(".passage-detail")
      .getByRole("button", { name: "Match Confirmed", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
}

test("three mutually exclusive states stay on the same passage and persist across reload", async ({
  page,
}) => {
  await setup(page);
  const detail = page.locator(".passage-detail");
  for (const state of [
    "Unreviewed",
    "Match Confirmed",
    "Match Dismissed",
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
    .getByRole("button", { name: "Match Dismissed", exact: true })
    .click();
  await expect(detail.locator(".review-status")).toContainText(
    "Match Dismissed",
  );
  await page.reload();
  await expect(page.locator(".review-status")).toContainText("Match Dismissed");
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
    .getByRole("button", { name: "Match Confirmed", exact: true })
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
    .getByRole("button", { name: "Match Confirmed", exact: true })
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

test("a new identical search starts fresh while reopening retains each run's decisions", async ({
  page,
}) => {
  await setup(page);
  const firstUrl = page.url();
  await page
    .getByRole("button", { name: "Match Confirmed", exact: true })
    .click();
  await expect(page.locator(".review-status")).toContainText("Match Confirmed");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page).not.toHaveURL(firstUrl);
  const secondUrl = page.url();
  await expect(page.locator(".passage-detail")).toContainText("Passage 1 of 2");
  await expect(
    page.getByRole("button", { name: "Unreviewed", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page
    .getByRole("button", { name: "Match Dismissed", exact: true })
    .click();
  await expect(page.locator(".review-status")).toContainText("Match Dismissed");
  await page.goto(firstUrl);
  await expect(
    page.getByRole("button", { name: "Match Confirmed", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.goto(secondUrl);
  await expect(
    page.getByRole("button", { name: "Match Dismissed", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Run again", exact: true }).click();
  await expect(page).not.toHaveURL(secondUrl);
  await expect(
    page.getByRole("button", { name: "Unreviewed", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});
