import { expect, test, type Page } from "@playwright/test";
import { uploadAndProcess, process } from "./support/textual";
import type { TextualSearchResponse, ReviewDecision } from "../src/api";

test.use({ reducedMotion: "reduce" });

async function find(page: Page, query: string) {
  await page.getByLabel("Text passage", { exact: true }).fill(query);
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.locator(".textual-response")).toBeVisible();
}
async function open(page: Page) {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
}
function reviewCommand(
  result: TextualSearchResponse,
  decision: ReviewDecision,
  occurrence = 0,
) {
  const doc = result.results[0].document;
  const item = result.results[0].occurrences[occurrence];
  return {
    occurrence_id: item.occurrence_id,
    document_id: doc.document_id,
    revision_id: doc.revision_id,
    processing_job_id: doc.processing_job_id,
    source_artifact_id: doc.artifact_id,
    normalization_version: doc.normalization_version,
    query: result.query,
    mode: result.mode,
    scorer_version: result.scorer_version,
    candidate_policy: result.candidate_policy,
    start_offset: item.start_offset,
    end_offset: item.end_offset,
    matched_sha256: item.matched_sha256,
    expected_version: item.review.version,
    decision,
  };
}

test("review decisions persist across pages, reload and semantics, and filtered saves refill results", async ({
  page,
}) => {
  const token = `ReviewPersistence${Date.now()}`;
  const title = `Review workflow ${Date.now()}`;
  await uploadAndProcess(page, title, `${token} separate context. `.repeat(8));
  await open(page);
  await find(page, token);
  const items = page.locator(".textual-occurrence");
  const counts = page.getByRole("region", {
    name: "Review counts",
    exact: true,
  });
  for (const [index, decision] of [
    "Keep",
    "Dismiss",
    "Decide later",
  ].entries()) {
    await items
      .nth(index)
      .getByRole("button", { name: decision, exact: true })
      .click();
    await expect(items.nth(index).locator(".review-status")).toContainText(
      `Review: ${decision}`,
    );
  }
  await expect(counts).toContainText(
    "Not reviewed: 5 · Keep: 1 · Dismiss: 1 · Decide later: 1",
  );
  await page
    .getByRole("button", { name: "Next passages", exact: true })
    .click();
  await expect(items).toHaveCount(3);
  await items
    .first()
    .getByRole("button", { name: "Keep", exact: true })
    .click();
  await expect(counts).toContainText("Not reviewed: 4 · Keep: 2");
  await page
    .getByRole("button", { name: "Previous passages", exact: true })
    .click();
  await expect(items.first().locator(".review-status")).toContainText(
    "Review: Keep",
  );
  await page.reload();
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page
    .getByRole("checkbox", { name: "Compare meaning with local embeddings" })
    .check();
  await find(page, token);
  await expect(items.first().locator(".review-status")).toContainText(
    "Review: Keep",
  );
  await expect(items.nth(1).locator(".review-status")).toContainText(
    "Review: Dismiss",
  );
  await expect(items.nth(2).locator(".review-status")).toContainText(
    "Review: Decide later",
  );
  await items
    .first()
    .getByRole("button", { name: "Reset review", exact: true })
    .click();
  await expect(counts).toContainText(
    "Not reviewed: 5 · Keep: 1 · Dismiss: 1 · Decide later: 1",
  );
  await page.getByLabel("Review status", { exact: true }).selectOption("later");
  await find(page, token);
  await expect(items).toHaveCount(1);
  // A filtered save must rerun submitted criteria, even if the form was edited.
  await page
    .getByLabel("Text passage", { exact: true })
    .fill("Unsubmitted expression");
  await page.getByLabel("Minimum semantic match").fill("100");
  await items
    .first()
    .getByRole("button", { name: "Keep", exact: true })
    .click();
  await expect(items).toHaveCount(0);
  await expect(counts).toContainText("Keep: 2 · Dismiss: 1 · Decide later: 0");
  await expect(page.locator(".search-query-summary")).toContainText(token);
  await expect(page.locator(".search-query-summary")).toContainText(
    "minimum semantic 0%",
  );
  await expect(page.getByLabel("Text passage", { exact: true })).toHaveValue(
    "Unsubmitted expression",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("conflicts, failed saves and reprocessed sources never display an unsaved decision", async ({
  page,
}) => {
  const token = `ReviewConflicts${Date.now()}`;
  const doc = await uploadAndProcess(
    page,
    `Review conflicts ${Date.now()}`,
    `${token} separate context.`,
  );
  await open(page);
  await find(page, token);
  const result = await (
    await page.request.post("/api/search/textual", {
      data: { query: token, minimum_score: 100 },
    })
  ).json();
  expect(
    (
      await page.request.post("/api/reviews", {
        data: reviewCommand(result, "keep"),
      })
    ).status(),
  ).toBe(200);
  const item = page.locator(".textual-occurrence").first();
  await item.getByRole("button", { name: "Dismiss", exact: true }).click();
  await expect(item.getByRole("alert")).toContainText("another view");
  await expect(item.locator(".review-status")).toContainText("Not reviewed");
  await find(page, token);
  await expect(item.locator(".review-status")).toContainText("Review: Keep");
  await page.route("**/api/reviews", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "Review storage is unavailable. Please try again." },
    }),
  );
  await item.getByRole("button", { name: "Dismiss", exact: true }).click();
  await expect(item.getByRole("alert")).toContainText("storage is unavailable");
  await expect(item.locator(".review-status")).toContainText("Review: Keep");
  await page.unroute("**/api/reviews");
  await process(page, doc.revisions[0].id);
  await item.getByRole("button", { name: "Decide later", exact: true }).click();
  await expect(item.getByRole("alert")).toContainText(
    "selected source has changed",
  );
  await expect(item.locator(".review-status")).toContainText("Review: Keep");
  await find(page, token);
  await expect(item.locator(".review-status")).toContainText("Not reviewed");
});

for (const filter of ["all", "unreviewed"]) {
  test(`a delayed review save cannot change a newer search (${filter})`, async ({
    page,
  }) => {
    const oldToken = `OldReview${Date.now()}`;
    const newToken = `NewReview${Date.now()}`;
    await uploadAndProcess(
      page,
      `Delayed review ${Date.now()}`,
      `${oldToken} context. ${newToken} other context.`,
    );
    await open(page);
    await page
      .getByLabel("Review status", { exact: true })
      .selectOption(filter);
    await find(page, oldToken);
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let notifySaved!: () => void;
    const saved = new Promise<void>((resolve) => {
      notifySaved = resolve;
    });
    await page.route("**/api/reviews", async (route) => {
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      notifySaved();
      await gate;
      await route.fulfill({ response });
    });
    await page
      .locator(".textual-occurrence")
      .first()
      .getByRole("button", { name: "Keep", exact: true })
      .click();
    await saved;
    await find(page, newToken);
    const oldResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/reviews"),
    );
    release();
    await (await oldResponse).finished();
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    );
    await expect(page.locator(".search-query-summary")).toContainText(newToken);
    await expect(page.locator(".review-status")).toContainText("Not reviewed");
    await expect(
      page.getByRole("region", { name: "Review counts", exact: true }),
    ).toContainText("Not reviewed: 1 · Keep: 0");
    const old = await (
      await page.request.post("/api/search/textual", {
        data: { query: oldToken, minimum_score: 100 },
      })
    ).json();
    expect(old.review_counts.keep).toBe(1);
  });
}

test("fresh review states from another view keep global counts consistent while paging", async ({
  page,
}) => {
  const token = `ReviewPageCounts${Date.now()}`;
  await uploadAndProcess(
    page,
    `Review page counts ${Date.now()}`,
    `${token} context. `.repeat(7),
  );
  await open(page);
  await find(page, token);
  const counts = page.getByRole("region", {
    name: "Review counts",
    exact: true,
  });
  await expect(counts).toContainText("Not reviewed: 7 · Keep: 0");
  const result = await (
    await page.request.post("/api/search/textual", {
      data: { query: token, minimum_score: 100, occurrence_limit: 25 },
    })
  ).json();
  expect(
    (
      await page.request.post("/api/reviews", {
        data: reviewCommand(result, "keep", 5),
      })
    ).status(),
  ).toBe(200);
  await page
    .getByRole("button", { name: "Next passages", exact: true })
    .click();
  await expect(
    page.locator(".textual-occurrence").first().locator(".review-status"),
  ).toContainText("Review: Keep");
  await expect(counts).toContainText("Not reviewed: 6 · Keep: 1");
  await page
    .locator(".textual-occurrence")
    .first()
    .getByRole("button", { name: "Dismiss", exact: true })
    .click();
  await expect(counts).toContainText("Not reviewed: 6 · Keep: 0 · Dismiss: 1");
  await page
    .getByRole("button", { name: "Previous passages", exact: true })
    .click();
  await expect(page.locator(".textual-occurrence")).toHaveCount(5);
  await expect(counts).toContainText("Not reviewed: 6 · Keep: 0 · Dismiss: 1");
  await find(page, token);
  await expect(counts).toContainText("Not reviewed: 6 · Keep: 0 · Dismiss: 1");
});
