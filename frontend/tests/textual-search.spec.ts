import { expect, test } from "@playwright/test";
import { uploadAndProcess, process } from "./support/textual";

test.use({ reducedMotion: "reduce" });

test("textual matches show differences, navigate occurrences and retain submitted criteria", async ({
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
  await page.locator(".document-row").filter({ hasText: title }).click();
  await page
    .getByRole("checkbox", { name: "Search only the open document" })
    .check();
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
  await expect(card.locator(".textual-occurrence")).toHaveCount(1);
  await expect(card.locator(".textual-score").first()).toHaveText(
    "Textual match: 100.00%",
  );
  await expect(card.locator("mark").first()).toHaveText(query.toLowerCase());
  // Editing the form must not change the query/threshold used for existing result pagination.
  await page
    .getByLabel("Text passage", { exact: true })
    .fill("different unsubmitted query");
  await page.getByLabel("Minimum textual match").fill("100");
  await expect(page.locator(".passage-choice")).toHaveCount(8);
  await page.locator(".passage-choice").nth(7).click();
  await expect(card.locator(".textual-occurrence")).toHaveCount(1);
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
    name: "Saved source text",
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
  // A saved run retains its original source and pages after reprocessing.
  const archivedIdentity = await viewer.locator(".identifier").textContent();
  await process(page, document.revisions[0].id);
  await page.locator(".passage-choice").first().click();
  await expect(card.locator(".textual-occurrence")).toHaveCount(1);
  await expect(card.getByRole("alert")).toHaveCount(0);
  await card.getByRole("button", { name: "View source text" }).first().click();
  await expect(viewer).toBeFocused();
  await expect(viewer.locator(".identifier")).toHaveText(archivedIdentity!);
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
  await page
    .getByText("Submitted search guidance", { exact: true })
    .first()
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

test("a failed workspace load offers retry without showing partial passages", async ({
  page,
}) => {
  const token = `WorkspaceFailure${Date.now()}`;
  await uploadAndProcess(page, token, `${token} context`);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page.route("**/workspace?**", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "Saved passages unavailable" },
    }),
  );
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Saved passages unavailable",
  );
  await expect(page.locator(".textual-occurrence")).toHaveCount(0);
  await page.unroute("**/workspace?**");
  await page
    .getByRole("button", { name: "Retry loading passages", exact: true })
    .click();
  await expect(page.locator(".textual-occurrence")).toHaveCount(1);
});

test("a delayed workspace failure cannot clear a newer search", async ({
  page,
}) => {
  const old = `OldWorkspace${Date.now()}`;
  const next = `NewWorkspace${Date.now()}`;
  await uploadAndProcess(page, old, `${old} context ${next}`);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  let release!: () => void;
  let entered!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const started = new Promise<void>((resolve) => {
    entered = resolve;
  });
  let first = true;
  await page.route("**/workspace?**", async (route) => {
    if (!first) return route.continue();
    first = false;
    entered();
    await gate;
    await route
      .fulfill({
        status: 422,
        json: {
          detail: {
            code: "textual_search_aborted",
            reason: "document_passage_limit",
            message: "Old load stopped",
            resource: "retained_passages_in_document",
            limit: 250,
            observed_at_least: 251,
            documents_inspected: 1,
            results_complete: false,
          },
        },
      })
      .catch(() => {});
  });
  await page.getByLabel("Text passage", { exact: true }).fill(old);
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await started;
  await page.getByLabel("Text passage", { exact: true }).fill(next);
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.locator(".textual-occurrence")).toHaveCount(1);
  release();
  await page.waitForLoadState("networkidle");
  await expect(page.locator(".search-query-summary")).toContainText(next);
  await expect(page.locator(".search-stopped")).toHaveCount(0);
  await expect(page.locator(".textual-occurrence")).toHaveCount(1);
});

test("local semantic scores filter actual passages and preserve submitted navigation criteria", async ({
  page,
}) => {
  const title = `Semantic comparison ${Date.now()}`;
  const query = `Buyer${Date.now()} shall pay EUR 500 within thirty days`;
  await uploadAndProcess(
    page,
    title,
    `${query}. Separate context. `.repeat(7) +
      `${query.replace("500", "5000")}.`,
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page.locator(".document-row").filter({ hasText: title }).click();
  await page
    .getByRole("checkbox", { name: "Search only the open document" })
    .check();
  await page.getByLabel("Text passage", { exact: true }).fill(query);
  await page.getByLabel("Minimum textual match").fill("85");
  await page
    .getByRole("checkbox", { name: "Compare meaning with local embeddings" })
    .check();
  await page.getByLabel("Minimum semantic match").fill("0");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  const card = page.getByRole("region", {
    name: `Matches in ${title}`,
    exact: true,
  });
  await expect(card.locator(".semantic-score")).toHaveCount(1);
  await expect(card.locator(".semantic-score").first()).toHaveText(
    "Semantic match: 100.00%",
  );
  await expect(page.locator(".textual-response")).toContainText("8 passages");
  // Edits to the form must not change the semantic filter for the submitted search.
  await page.getByLabel("Minimum semantic match").fill("100");
  await page.locator(".passage-choice").nth(7).click();
  await expect(card.locator(".semantic-score")).toHaveCount(1);
  const changed = card
    .locator(".textual-occurrence")
    .filter({ hasText: "5000" });
  // Restrict to the matched/comparison text; snippets can include nearby occurrences.
  const changedScore = await card
    .locator(".semantic-score")
    .last()
    .textContent();
  expect(changedScore).not.toBe("Semantic match: 100.00%");
  await expect(changed).not.toHaveCount(0);
  await expect(page.locator(".search-query-summary")).toContainText(
    "minimum semantic 0%",
  );
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.locator(".search-query-summary")).toContainText(
    "minimum semantic 100%",
  );
  await expect(page.locator(".passage-choice")).toHaveCount(7);
  await page.locator(".passage-choice").last().click();
  await expect(card.locator(".semantic-score")).toHaveCount(1);
  await expect(card.locator(".semantic-score").last()).toHaveText(
    "Semantic match: 100.00%",
  );
  await page.getByText("Semantic comparison method", { exact: true }).click();
  await expect(page.locator(".textual-response")).toContainText(
    "8 textual candidates assessed",
  );
  await expect(page.locator(".textual-response")).toContainText(
    "Negations, names and amounts",
  );
  // A server/model update must not mix a new scoring method into an old card.
  await page.route("**/workspace?**", async (route) => {
    const result = await route.fetch();
    const body = await result.json();
    body.semantic.pipeline += "-changed";
    await route.fulfill({ response: result, json: body });
  });
  await page
    .getByRole("button", { name: "Refresh reviews", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("comparison metadata");
  await expect(page.locator(".semantic-score")).toHaveCount(0);
});

test("semantic validation and unavailable-model errors never show textual results as semantic success", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page
    .getByLabel("Text passage", { exact: true })
    .fill("Confidential information");
  await page
    .getByRole("checkbox", { name: "Compare meaning with local embeddings" })
    .check();
  await page.getByLabel("Minimum semantic match").fill("101");
  await expect(
    page.getByRole("button", { name: "Find passages", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("alert")).toContainText(
    "semantic threshold from 0 to 100",
  );
  await page.getByLabel("Minimum semantic match").fill("60");
  await page.route("**/api/search-runs", async (route) => {
    expect(route.request().postDataJSON().search.minimum_semantic_score).toBe(
      60,
    );
    await route.fulfill({
      status: 503,
      json: {
        detail:
          "Semantic model is unavailable. Prepare the pinned model during setup.",
      },
    });
  });
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Semantic model is unavailable",
  );
  await expect(page.locator(".textual-response")).toHaveCount(0);
  await expect(page.getByLabel("Minimum semantic match")).toHaveValue("60");
});
