import { expect, test } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { uploadAndProcess, process } from "./support/textual";

test.use({ reducedMotion: "reduce" });

test("a bookmarked run preserves every result, scope and historical source while Run again creates a separate run", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const token = `Snapshot${randomUUID().replaceAll("-", "")}`;
  const name = `Saved review ${Date.now()}`;
  const title = `Snapshot source ${Date.now()}`;
  const doc = await uploadAndProcess(
    page,
    title,
    `${token} original context. `.repeat(7),
  );
  const pendingTitle = `Pending at capture ${Date.now()}`;
  const pending = await (
    await page.request.post("/api/documents/upload", {
      multipart: {
        title: pendingTitle,
        file: {
          name: "pending.txt",
          mimeType: "text/plain",
          buffer: Buffer.from("An unrelated pending source."),
        },
      },
    })
  ).json();
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page.getByLabel("Search name", { exact: true }).fill(name);
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/search-runs") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  const run = await (await created).json();
  expect(run.run_id).toBeTruthy();
  expect(run.summary.occurrences_total).toBe(7);
  await expect(page).toHaveURL(new RegExp(`search_run=${run.run_id}`));
  const card = page.getByRole("region", {
    name: `Matches in ${title}`,
    exact: true,
  });
  await expect(card.locator(".textual-occurrence")).toHaveCount(1);
  await expect(page.locator(".passage-choice")).toHaveCount(7);
  await page.locator(".passage-choice").nth(5).click();
  await expect(card.locator(".textual-occurrence")).toHaveCount(1);
  await card
    .getByRole("button", { name: "View source text", exact: true })
    .first()
    .click();
  const viewer = page.getByRole("region", {
    name: "Saved source text",
    exact: true,
  });
  await expect(viewer).toBeFocused();
  const job = run.results[0].document.processing_job_id;
  await expect(viewer.locator(".identifier")).toContainText(job);
  await page
    .getByRole("button", { name: "Close saved text", exact: true })
    .click();
  await uploadAndProcess(
    page,
    `New library match ${Date.now()}`,
    `${token} new context.`,
  );
  const reprocess = await (
    await page.request.post(`/api/revisions/${doc.revisions[0].id}/process`, {
      data: { requires_manual_review: true },
    })
  ).json();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/jobs/${reprocess.id}`)).json())
          .status,
    )
    .toBe("completed");
  await process(page, pending.revisions[0].id);
  // Opening the URL may read only saved state; it must not submit a new search.
  await page.route("**/api/search-runs", (route) => route.abort());
  await page.route("**/api/search/textual", (route) => route.abort());
  await page.reload();
  await expect(page.locator(".textual-response")).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Saved search run", exact: true }),
  ).toContainText(name);
  await expect(page.locator(".textual-response")).toContainText("7 passages");
  await expect(page.locator(".textual-response")).toContainText(pendingTitle);
  await expect(card.locator(".textual-occurrence")).toHaveCount(1);
  await card
    .getByRole("button", { name: "View source text", exact: true })
    .first()
    .click();
  await expect(viewer).toBeFocused();
  await expect(viewer.locator(".identifier")).toContainText(job);
  await expect(viewer.locator(".identifier")).not.toContainText(reprocess.id);
  await expect(viewer.locator(".text-preview")).toContainText(
    "original context",
  );
  await page
    .getByRole("button", { name: "Close saved text", exact: true })
    .click();
  await card
    .locator(".textual-occurrence")
    .first()
    .getByRole("button", { name: "Decide later", exact: true })
    .click();
  await expect(card.locator(".review-status").first()).toContainText(
    "Review: Decide later",
  );
  await page
    .getByLabel("Review saved results", { exact: true })
    .selectOption("later");
  await expect(card.locator(".textual-occurrence")).toHaveCount(1);
  await expect(page).toHaveURL(new RegExp(`search_run=${run.run_id}`));
  await page
    .getByLabel("Review saved results", { exact: true })
    .selectOption("all");
  await expect(card.locator(".textual-occurrence")).toHaveCount(1);
  await page.getByLabel("Search name", { exact: true }).fill(`${name} renamed`);
  await page.getByRole("button", { name: "Save name", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Saved search run", exact: true }),
  ).toContainText(`${name} renamed`);
  await page.unroute("**/api/search-runs");
  await page.unroute("**/api/search/textual");
  const rerun = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/search-runs") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Run again", exact: true }).click();
  const fresh = await (await rerun).json();
  expect(fresh.parent_run_id).toBe(run.run_id);
  expect(fresh.run_id).not.toBe(run.run_id);
  expect(fresh.summary.occurrences_total).toBe(8);
  expect(fresh.review_counts.later).toBe(0);
  await expect(page).toHaveURL(new RegExp(`search_run=${fresh.run_id}`));
  await page
    .getByRole("button", { name: "Open previous run", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`search_run=${run.run_id}`));
  await expect(page.locator(".textual-response")).toContainText("7 passages");
  await expect(
    page.getByRole("region", { name: "Review counts", exact: true }),
  ).toContainText("Decide later: 1");
});

test("saved semantic results reopen without the search service and list names remain usable", async ({
  page,
}) => {
  const token = `SemanticSnapshot${randomUUID().replaceAll("-", "")}`;
  const name = `Semantic saved ${Date.now()}`;
  await uploadAndProcess(
    page,
    `Saved semantic source ${Date.now()}`,
    `${token} shall pay EUR 500 within thirty days.`,
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page.getByLabel("Search name", { exact: true }).fill(name);
  await page
    .getByLabel("Text passage", { exact: true })
    .fill(`${token} shall pay EUR 5000 within thirty days.`);
  await page.getByLabel("Minimum textual match").fill("85");
  await page
    .getByRole("checkbox", { name: "Compare meaning with local embeddings" })
    .check();
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.locator(".semantic-score")).toHaveCount(1);
  const score = await page.locator(".semantic-score").textContent();
  const snapshot = page.url();
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page.getByText(/^Saved searches \(/).click();
  await page.route("**/api/search-runs", (route) => route.abort());
  await page.route("**/api/search/textual", (route) => route.abort());
  await page.getByRole("button", { name: `Open ${name}`, exact: true }).click();
  await expect(page).toHaveURL(snapshot);
  await expect(page.locator(".semantic-score")).toHaveText(score!);
  await expect(page.getByLabel("Text passage", { exact: true })).toHaveValue(
    `${token} shall pay EUR 5000 within thirty days.`,
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
