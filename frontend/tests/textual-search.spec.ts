import { expect, test } from "@playwright/test";

test.use({ reducedMotion: "reduce" });

async function uploadAndProcess(
  page: import("@playwright/test").Page,
  title: string,
  text: string,
) {
  const upload = await page.request.post("/api/documents/upload", {
    multipart: {
      title,
      file: {
        name: "textual-search.txt",
        mimeType: "text/plain",
        buffer: Buffer.from(text),
      },
    },
  });
  expect(upload.status()).toBe(201);
  const document = await upload.json();
  await process(page, document.revisions[0].id);
  return document;
}
async function process(
  page: import("@playwright/test").Page,
  revisionId: string,
) {
  const response = await page.request.post(
    `/api/revisions/${revisionId}/process`,
    { data: {} },
  );
  expect(response.status()).toBe(202);
  const job = await response.json();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/jobs/${job.id}`)).json()).status,
      { timeout: 60_000 },
    )
    .toBe("completed");
}

test("textual matches show differences, page through occurrences and retain submitted criteria", async ({
  page,
}) => {
  const title = `Textual comparison ${Date.now()}`;
  const query =
    "The receiving party shall not disclose confidential information";
  const text = `Start of synthetic document.\n${Array.from({ length: 7 }, (_, index) => `${query}.\nSeparate background paragraph number ${index}.`).join("\n")}\nThe receiving party shall disclose confidential information.\nEnd.`;
  const document = await uploadAndProcess(page, title, text);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page.getByLabel("Text passage", { exact: true }).fill(query);
  await page.getByLabel("Minimum textual match").fill("85");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  const card = page.getByRole("region", {
    name: `Matches in ${title}`,
    exact: true,
  });
  await expect(card).toBeVisible();
  await expect(card.locator(".textual-occurrence")).toHaveCount(5);
  await expect(card.locator(".textual-score").first()).toHaveText(
    "Textual match: 100.00%",
  );
  await expect(card.locator("mark").first()).toHaveText(query.toLowerCase());
  // Editing the form must not change the query/threshold used for existing result pagination.
  await page
    .getByLabel("Text passage", { exact: true })
    .fill("different unsubmitted query");
  await page.getByLabel("Minimum textual match").fill("100");
  await card.getByRole("button", { name: "Next passages" }).click();
  await expect(card.locator(".textual-occurrence")).toHaveCount(3);
  const changed = card
    .locator(".textual-occurrence")
    .filter({ hasText: "Possible match" });
  await expect(changed).toHaveCount(1);
  await expect(changed.locator("del")).toContainText(["not "]);
  await expect(card.locator(".text-comparison").first()).toContainText(
    query.toLowerCase(),
  );
  await expect(page.locator(".search-query-summary")).toContainText(
    "minimum 85%",
  );
  await card.getByRole("button", { name: "View source text" }).first().click();
  const viewer = page.getByRole("region", {
    name: "Extracted page text",
    exact: true,
  });
  await expect(viewer).toBeFocused();
  await expect(viewer).toBeInViewport();
  // Repeat the same navigation, exercising the cached viewer request handling.
  await card.getByRole("button", { name: "View source text" }).first().click();
  await expect(viewer).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  // A page of matches from another run must not be mixed into the old result snapshot.
  await process(page, document.revisions[0].id);
  await card.getByRole("button", { name: "Previous passages" }).click();
  await expect(card.getByRole("alert")).toContainText(
    "Please run the search again",
  );
});

test("zero is blocked, scope can be narrowed, and exact mode is preserved", async ({
  page,
}) => {
  const title = `Unrelated text ${Date.now()}`;
  await uploadAndProcess(
    page,
    title,
    "An unrelated shipping note is stored here.",
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page
    .getByLabel("Text passage", { exact: true })
    .fill("Completely different target wording");
  await page.getByLabel("Minimum textual match").fill("0");
  await expect(page.getByRole("alert")).toContainText("greater than 0");
  await expect(
    page.getByRole("button", { name: "Find passages", exact: true }),
  ).toBeDisabled();
  await page.locator(".document-row").filter({ hasText: title }).click();
  await page
    .getByRole("checkbox", { name: "Search only the open document" })
    .check();
  await page.getByLabel("Minimum textual match").fill("1");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: `Matches in ${title}`, exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Text passage", { exact: true })
    .fill("AN UNRELATED SHIPPING NOTE");
  await page.getByLabel("Minimum textual match").fill("100");
  await page.getByLabel("Text comparison mode").selectOption("exact");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Similar passage results", exact: true }),
  ).toContainText("No candidate passages");
  await page.getByLabel("Text comparison mode").selectOption("normalized");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: `Matches in ${title}`, exact: true }),
  ).toContainText("Textual match: 100.00%");
  // Server warnings use the effective normalized query, even if its original
  // whitespace made it look longer in the form.
  await page.getByLabel("Text passage", { exact: true }).fill("A        n");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(
    page.getByRole("region", {
      name: "Submitted search guidance",
      exact: true,
    }),
  ).toContainText("very few letters or digits");
});

test("too many real passages abort without partial results and can be refined", async ({
  page,
}) => {
  const token = `ControlProbe${Date.now()}`;
  const ending = "end of synthetic control contract.";
  await uploadAndProcess(
    page,
    `Dense controls ${Date.now()}`,
    `${(token + " ").repeat(251)}${ending}`,
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
  await expect(page.locator(".search-stopped")).toContainText(
    "Too many candidate passages in one document",
  );
  await expect(page.locator(".search-stopped")).toContainText("251");
  await expect(page.locator(".textual-response")).toHaveCount(0);
  await expect(page.getByLabel("Minimum textual match")).toHaveValue("100");
  await expect(
    page.getByRole("button", { name: "Find passages", exact: true }),
  ).toBeEnabled();
  await page
    .getByLabel("Text passage", { exact: true })
    .fill(`${token} ${ending}`);
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.locator(".textual-occurrence")).toHaveCount(1);
  await expect(page.locator(".search-stopped")).toHaveCount(0);
});

test("an occurrence-pagination abort clears the old complete snapshot", async ({
  page,
}) => {
  const token = `PagingProbe${Date.now()}`;
  await uploadAndProcess(
    page,
    `Paging controls ${Date.now()}`,
    `${token} separate paragraph. `.repeat(7),
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
  await expect(page.locator(".textual-occurrence")).toHaveCount(5);
  // Isolated error-rendering contract; successful search above uses the real API.
  await page.route("**/api/search/textual", async (route) => {
    if (route.request().postDataJSON().occurrence_offset > 0) {
      await route.fulfill({
        status: 422,
        json: {
          detail: {
            code: "textual_search_aborted",
            reason: "document_passage_limit",
            message:
              "Too many candidate passages in one document. Increase textual similarity.",
            resource: "retained_passages_in_document",
            limit: 250,
            observed_at_least: 251,
            documents_inspected: 1,
            results_complete: false,
          },
        },
      });
    } else await route.continue();
  });
  await page
    .getByRole("button", { name: "Next passages", exact: true })
    .click();
  await expect(page.locator(".search-stopped")).toContainText(
    "Search stopped — no results returned",
  );
  await expect(page.locator(".textual-response")).toHaveCount(0);
  await expect(page.getByLabel("Minimum textual match")).toHaveValue("100");
  await expect(
    page.getByRole("button", { name: "Find passages", exact: true }),
  ).toBeEnabled();
});
