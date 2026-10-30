import { expect, test, type APIRequestContext } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";

const PHRASE =
  "The receiving party shall not disclose confidential information";
test.use({ reducedMotion: "reduce" });

async function upload(
  request: APIRequestContext,
  filename: string,
  title: string,
  manual = false,
) {
  const response = await request.post("/api/documents/upload", {
    multipart: {
      title,
      requires_manual_review: String(manual),
      file: {
        name: filename,
        mimeType: "application/pdf",
        buffer: await readFile(
          path.resolve("../examples/synthetic-contracts", filename),
        ),
      },
    },
  });
  expect(response.status()).toBe(201);
  return response.json();
}
async function process(request: APIRequestContext, revisionId: string) {
  const response = await request.post(`/api/revisions/${revisionId}/process`, {
    data: {},
  });
  expect(response.status()).toBe(202);
  const job = await response.json();
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/jobs/${job.id}`)).json()).status,
      { timeout: 60_000 },
    )
    .toBe("completed");
  return job;
}

test("real full-text search separates negative and unverifiable results and opens source pages", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const tag = Date.now();
  const positive = await upload(
    page.request,
    "A-confidentiality.pdf",
    `Search positive ${tag}`,
  );
  const negative = await upload(
    page.request,
    "D-delivery.pdf",
    `Search negative ${tag}`,
  );
  const review = await upload(
    page.request,
    "D-delivery.pdf",
    `Search review ${tag}`,
    true,
  );
  const pending = await upload(
    page.request,
    "A-confidentiality.pdf",
    `Search unprocessed ${tag}`,
  );
  for (const document of [positive, negative, review])
    await process(page.request, document.revisions[0].id);
  await page.goto("/");
  await page
    .getByLabel("Text passage", { exact: true })
    .fill("THE receiving party\n shall not disclose confidential information");
  await page.getByRole("button", { name: "Run search" }).click();
  const hits = page.getByRole("region", {
    name: "Search results",
    exact: true,
  });
  const unknown = page.getByRole("region", {
    name: "Unverifiable documents",
    exact: true,
  });
  const card = hits
    .locator(".search-result")
    .filter({ hasText: positive.title });
  await expect(card).toBeVisible();
  await expect(card.locator("mark")).toHaveText(PHRASE.toLowerCase());
  await card.getByRole("button", { name: "View page 1" }).click();
  const viewer = page.getByRole("region", {
    name: "Extracted page text",
    exact: true,
  });
  await expect(viewer).toBeFocused();
  await expect(viewer).toBeInViewport();
  await expect(viewer.locator("pre")).toContainText("shall not disclose");

  // Reopening the same result must finish at the viewer even with text cached.
  for (let reopen = 0; reopen < 2; reopen++) {
    const textResponse = page.waitForResponse(
      (response) =>
        response
          .url()
          .includes(`/revisions/${positive.revisions[0].id}/text`) &&
        response.status() === 200,
    );
    await card.getByRole("button", { name: "View page 1" }).click();
    await textResponse;
    await expect(viewer).toBeFocused();
    await expect(viewer).toBeInViewport();
    await expect(viewer.locator("pre")).toContainText("shall not disclose");
  }

  await page.getByLabel("Find documents").selectOption("lacks");
  await page.getByRole("button", { name: "Run search" }).click();
  await expect(hits).toContainText(negative.title);
  await expect(hits).not.toContainText(review.title);
  await expect(hits).not.toContainText(pending.title);
  await expect(unknown).toContainText(review.title);
  await expect(unknown).toContainText(pending.title);
  await expect(unknown).toContainText("No selected text yet");

  await page.getByLabel("Search mode").selectOption("exact");
  await page.getByLabel("Find documents").selectOption("contains");
  await page
    .getByLabel("Text passage", { exact: true })
    .fill(PHRASE.toLowerCase());
  await page.getByRole("button", { name: "Run search" }).click();
  await expect(page.locator(".search-query-summary")).toContainText("Exact");
  await expect(hits).not.toContainText(positive.title);

  await page.getByLabel("Search mode").selectOption("normalized");
  await page.getByRole("button", { name: "Run search" }).click();
  await expect(card).toBeVisible();
  await process(page.request, positive.revisions[0].id); // Change the selected run after the search snapshot.
  await card.getByRole("button", { name: "View page 1" }).click();
  await expect(page.locator(".details").getByRole("alert")).toContainText(
    "changed since the search",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("search highlighting respects code-point offsets before non-BMP characters", async ({
  page,
}) => {
  // Isolated renderer contract: the production UI receives offsets in Unicode code points.
  await page.route("**/api/search", (route) =>
    route.fulfill({
      json: {
        query: "target",
        effective_query: "target",
        mode: "normalized",
        relation: "contains",
        scope: "latest",
        searched_at: "2026-10-29T12:00:00Z",
        summary: {
          documents_total: 1,
          found: 1,
          not_found_in_processed_text: 0,
          unverifiable: 0,
        },
        total: 1,
        limit: 10,
        offset: 0,
        unverifiable: [],
        unverifiable_total: 0,
        unverifiable_limit: 10,
        unverifiable_offset: 0,
        results: [
          {
            document_id: "fixture",
            title: "Unicode snippet",
            revision_id: "fixture",
            revision_number: 1,
            artifact_id: null,
            processing_job_id: "fixture",
            normalization_version: "nfc-whitespace-casefold-v1",
            processor_versions: {},
            mode: "normalized",
            status: "found",
            coverage: "complete",
            quality_status: "no_known_issue",
            pages_total: 1,
            pages_processed: 1,
            pages_failed: 0,
            warnings: [],
            latest_job: null,
            matched_text: "target",
            snippet: "😀 target 🧾",
            snippet_start_offset: 0,
            start_offset: 2,
            end_offset: 8,
            page_number: null,
            end_page_number: null,
            page_numbers: [],
            offset_basis: "normalized_text",
          },
        ],
      },
    }),
  );
  await page.goto("/");
  await page.getByLabel("Text passage", { exact: true }).fill("target");
  await page.getByRole("button", { name: "Run search" }).click();
  await expect(page.locator(".search-snippet mark")).toHaveText("target");
  await expect(page.locator(".search-snippet")).toHaveText("😀 target 🧾");
});
