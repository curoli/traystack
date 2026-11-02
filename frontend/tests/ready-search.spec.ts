import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { uploadAndProcess } from "./support/textual";

async function add(
  page: Page,
  title: string,
  content: string,
  category: string,
) {
  const doc = await uploadAndProcess(page, title, content);
  expect(
    (
      await page.request.patch(`/api/documents/${doc.id}/category`, {
        data: { category },
      })
    ).status(),
  ).toBe(200);
  return doc;
}

test("auto-confirmed passages are counted and hidden, manual reset wins, and document groups cover the category", async ({
  page,
}) => {
  const category = `Match groups ${randomUUID()}`;
  const query = `Buyer${randomUUID().replaceAll("-", "")} shall pay EUR 500 within thirty days`;
  const exact = `Exact ${Date.now()}`,
    approximate = `Changed ${Date.now()}`,
    missing = `Missing ${Date.now()}`;
  await add(page, exact, `${query}. Separate context. `.repeat(2), category);
  await add(page, approximate, `${query.replace("500", "5000")}.`, category);
  await add(
    page,
    missing,
    "A shipping agreement without the requested payment wording.",
    category,
  );
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Store and search documents.",
  );
  await expect(page.getByLabel("Title", { exact: true })).not.toBeVisible();
  await expect(page.getByLabel("Auto-confirm textual minimum")).toHaveValue(
    "100",
  );
  await expect(page.getByLabel("Auto-confirm semantic minimum")).toHaveValue(
    "100",
  );
  await expect(page.getByLabel("Minimum semantic match")).toBeEnabled();
  await expect(
    page.getByLabel("Compare meaning with local embeddings"),
  ).toHaveCount(0);
  await expect(page.getByLabel("Review status", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("checkbox", {
      name: "Search only the open document",
      exact: true,
    }),
  ).toHaveCount(0);
  await page
    .getByLabel("Document category", { exact: true })
    .selectOption(`category:${category}`);
  await page.getByLabel("Text passage", { exact: true }).fill(query);
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: /^Automatically confirmed:/ }),
  ).toHaveText("Automatically confirmed: 2 passages.");
  await expect(page.locator(".passage-choice")).toHaveCount(1);
  const groups = page.getByRole("region", {
    name: "Document match groups",
    exact: true,
  });
  const confirmed = groups.locator("details").nth(0),
    pending = groups.locator("details").nth(1),
    noMatch = groups.locator("details").nth(2);
  await expect(confirmed.locator("summary")).toContainText("(1 document)");
  await expect(pending.locator("summary")).toContainText("(1 document)");
  await expect(noMatch.locator("summary")).toContainText("(1 document)");
  expect(await confirmed.getAttribute("open")).toBeNull();
  await noMatch.locator("summary").click();
  await noMatch.getByRole("button", { name: missing, exact: true }).click();
  await expect(
    page
      .locator(".passage-detail")
      .getByRole("heading", { name: missing, exact: true }),
  ).toBeVisible();
  await expect(page.locator(".textual-occurrence")).toHaveCount(0);
  await page
    .locator(".result-document")
    .filter({ hasText: approximate })
    .locator(".passage-choice")
    .click();
  await page
    .getByRole("button", { name: "Match Dismissed", exact: true })
    .click();
  await expect(pending.locator("summary")).toContainText("(0 documents)");
  await expect(noMatch.locator("summary")).toContainText("(2 documents)");
  await page
    .getByLabel("Show automatically confirmed passages for review")
    .check();
  await expect(page.locator(".passage-choice")).toHaveCount(3);
  await page
    .locator(".result-document")
    .filter({ hasText: exact })
    .locator(".passage-choice")
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "Match Confirmed", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Unreviewed", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Unreviewed", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("status").filter({ hasText: /^Automatically confirmed:/ }),
  ).toHaveText("Automatically confirmed: 1 passage.");
  await page
    .getByLabel("Show automatically confirmed passages for review")
    .uncheck();
  await expect(page.locator(".passage-choice")).toHaveCount(2);
  await page.reload();
  await expect(page.locator(".passage-choice")).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "Unreviewed", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("all automatically confirmed matches can be shown even when the default review list is empty", async ({
  page,
}) => {
  const category = `Auto ${randomUUID()}`,
    token = `Exact${Date.now()}`;
  await add(page, token, token, category);
  await page.goto("/");
  await page
    .getByLabel("Document category", { exact: true })
    .selectOption(`category:${category}`);
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.locator(".passage-choice")).toHaveCount(0);
  await expect(page.locator(".review-workspace")).toContainText(
    "automatically confirmed",
  );
  const confirmed = page
    .getByRole("region", { name: "Document match groups", exact: true })
    .locator("details")
    .first();
  await confirmed.locator("summary").click();
  await confirmed
    .getByRole("link", {
      name: "Passage 1 — Confirmed (automatic)",
      exact: true,
    })
    .click();
  await expect(
    page.getByLabel("Show automatically confirmed passages for review"),
  ).toBeChecked();
  await expect(page.locator(".passage-detail")).toBeFocused();
  await expect(page.locator(".passage-choice")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Match Confirmed", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("categories can be assigned on upload and edited without reprocessing", async ({
  page,
}) => {
  const first = `Supply ${randomUUID()}`,
    second = `Employment ${randomUUID()}`,
    title = `Category upload ${Date.now()}`;
  await page.goto("/");
  await page.getByText("Manage documents", { exact: true }).click();
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByLabel("Category (optional)", { exact: true }).fill(first);
  await page.getByLabel("Original file", { exact: true }).setInputFiles({
    name: "category.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("A synthetic contract for category editing."),
  });
  await page
    .getByRole("button", { name: "Save document", exact: true })
    .click();
  await expect(page.getByLabel("Category", { exact: true })).toHaveValue(first);
  await page.getByLabel("Category", { exact: true }).fill(second);
  await page
    .getByRole("button", { name: "Save category", exact: true })
    .click();
  await expect(page.getByLabel("Category", { exact: true })).toHaveValue(
    second,
  );
  await expect(
    page
      .getByLabel("Document category", { exact: true })
      .locator("option")
      .filter({ hasText: second }),
  ).toHaveCount(1);
  await page.reload();
  await page.getByText("Manage documents", { exact: true }).click();
  await page.locator(".document-row").filter({ hasText: title }).click();
  await expect(page.getByLabel("Category", { exact: true })).toHaveValue(
    second,
  );
});

test("document-group counts prioritize confirmation and links select the relevant state", async ({
  page,
}) => {
  const category = `Priority ${randomUUID()}`,
    token = `Priority${Date.now()}`;
  await add(page, token, `${token} context. `.repeat(3), category);
  await page.goto("/");
  await page
    .getByLabel("Auto-confirm strong matches", { exact: true })
    .uncheck();
  await page
    .getByLabel("Document category", { exact: true })
    .selectOption(`category:${category}`);
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.locator(".passage-choice")).toHaveCount(3);
  const groups = page.getByRole("region", {
    name: "Document match groups",
    exact: true,
  });
  const confirmed = groups.locator("details").nth(0),
    pending = groups.locator("details").nth(1);
  await page
    .getByRole("button", { name: "Match Dismissed", exact: true })
    .click();
  await pending.locator("summary").click();
  await pending.getByRole("button", { name: token, exact: true }).click();
  await expect(page.locator(".passage-detail")).toContainText("Passage 2 of 3");
  await page
    .getByRole("button", { name: "Match Confirmed", exact: true })
    .click();
  await expect(confirmed.locator("summary")).toContainText("(1 document)");
  await expect(pending.locator("summary")).toContainText("(0 documents)");
  await page.locator(".passage-choice").last().click();
  await confirmed.locator("summary").click();
  await confirmed.getByRole("button", { name: token, exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Match Confirmed", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("expanded document lists follow all review transitions and link to exact passages", async ({
  page,
}) => {
  const category = `Live groups ${randomUUID()}`,
    title = `Contract ${randomUUID()}`,
    token = `Live${Date.now()}`;
  await add(page, title, `${token} context. `.repeat(2), category);
  await page.goto("/");
  await page
    .getByLabel("Auto-confirm strong matches", { exact: true })
    .uncheck();
  await page
    .getByLabel("Document category", { exact: true })
    .selectOption(`category:${category}`);
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  const groups = page.getByRole("region", {
    name: "Document match groups",
    exact: true,
  });
  const confirmed = groups.locator("details").nth(0),
    pending = groups.locator("details").nth(1),
    dismissed = groups.locator("details").nth(2);
  for (const group of [confirmed, pending, dismissed])
    await group.locator("summary").click();
  const documentButton = (group: typeof pending) =>
    group.getByRole("button", { name: title, exact: true });
  await expect(documentButton(pending)).toBeVisible();
  await pending
    .getByRole("link", { name: "Passage 2 — Unreviewed", exact: true })
    .click();
  const detail = page.locator(".passage-detail");
  await expect(detail).toContainText("Passage 2 of 2");
  await expect(detail).toBeFocused();
  await detail
    .getByRole("button", { name: "Match Confirmed", exact: true })
    .click();
  await expect(documentButton(confirmed)).toBeVisible();
  await expect(documentButton(pending)).toHaveCount(0);
  await expect(confirmed.locator("summary")).toContainText("(1 document)");
  await confirmed
    .getByRole("link", { name: "Passage 2 — Confirmed", exact: true })
    .click();
  await detail
    .getByRole("button", { name: "Match Dismissed", exact: true })
    .click();
  await expect(documentButton(confirmed)).toHaveCount(0);
  await expect(documentButton(pending)).toBeVisible();
  await pending
    .getByRole("link", { name: "Passage 1 — Unreviewed", exact: true })
    .click();
  await detail
    .getByRole("button", { name: "Match Dismissed", exact: true })
    .click();
  await expect(documentButton(pending)).toHaveCount(0);
  await expect(documentButton(dismissed)).toBeVisible();
  await expect(dismissed.getByRole("link", { name: /Dismissed/ })).toHaveCount(
    2,
  );
  await dismissed
    .getByRole("link", { name: "Passage 2 — Dismissed", exact: true })
    .click();
  await detail.getByRole("button", { name: "Unreviewed", exact: true }).click();
  await expect(documentButton(dismissed)).toHaveCount(0);
  await expect(documentButton(pending)).toBeVisible();
  await page.reload();
  await pending.locator("summary").click();
  await expect(documentButton(pending)).toBeVisible();
  await expect(
    pending.getByRole("link", { name: "Passage 2 — Unreviewed", exact: true }),
  ).toBeVisible();
});

test("document counters survive translated headings and repeated decisions", async ({
  page,
}) => {
  const category = `Counter ${randomUUID()}`,
    token = `Count${Date.now()}`;
  await add(page, `First ${token}`, token, category);
  await add(page, `Second ${token}`, token, category);
  await page.goto("/");
  await page
    .getByLabel("Auto-confirm strong matches", { exact: true })
    .uncheck();
  await page
    .getByLabel("Document category", { exact: true })
    .selectOption(`category:${category}`);
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  const groups = page.getByRole("region", {
    name: "Document match groups",
    exact: true,
  });
  const detail = page.locator(".passage-detail");
  async function counts(expected: number[]) {
    for (let i = 0; i < 3; i++) {
      const group = groups.locator("details").nth(i);
      if ((await group.getAttribute("open")) !== null)
        await expect(group.locator(".document-outcome")).toHaveCount(
          expected[i],
        );
      await expect(group.locator("summary")).toContainText(
        `(${expected[i]} ${expected[i] === 1 ? "document" : "documents"})`,
      );
    }
  }
  async function decide(state: string, expected: number[]) {
    await detail.getByRole("button", { name: state, exact: true }).click();
    await expect(
      detail.getByRole("button", { name: state, exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await counts(expected);
  }
  await counts([0, 2, 0]);
  await decide("Match Confirmed", [1, 1, 0]);
  await groups.locator("summary").first().click();
  // Browser translators can replace text nodes with font wrappers. React retains
  // references to the old nodes, so unprotected numeric text stops updating.
  await groups.locator("summary").evaluateAll((summaries) => {
    for (const summary of summaries) {
      const walker = document.createTreeWalker(summary, NodeFilter.SHOW_TEXT);
      const nodes: Text[] = [];
      while (walker.nextNode()) nodes.push(walker.currentNode as Text);
      for (const node of nodes) {
        if (
          !node.textContent?.trim() ||
          node.parentElement?.closest('[translate="no"]')
        )
          continue;
        const wrapper = document.createElement("font");
        wrapper.textContent = node.textContent;
        node.replaceWith(wrapper);
      }
    }
  });
  await detail.getByRole("button", { name: "Next", exact: true }).click();
  await decide("Match Confirmed", [2, 0, 0]);
  for (const group of await groups.locator("details").all())
    if ((await group.getAttribute("open")) === null)
      await group.locator("summary").click();
  await detail.getByRole("button", { name: "Previous", exact: true }).click();
  await decide("Match Dismissed", [1, 0, 1]);
  await detail.getByRole("button", { name: "Next", exact: true }).click();
  await decide("Unreviewed", [0, 1, 1]);
  await decide("Match Confirmed", [1, 0, 1]);
  await detail.getByRole("button", { name: "Previous", exact: true }).click();
  await decide("Unreviewed", [1, 1, 0]);
});

test("confirming several passages in one document shows distinct document and passage counts", async ({
  page,
}) => {
  const token = `Distinguish${Date.now()}`,
    category = `Counts ${randomUUID()}`;
  await add(page, `Other ${token}`, token, category);
  await add(page, `Many ${token}`, `${token} context. `.repeat(7), category);
  await page.goto("/");
  await page
    .getByLabel("Auto-confirm strong matches", { exact: true })
    .uncheck();
  await page
    .getByLabel("Document category", { exact: true })
    .selectOption(`category:${category}`);
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page.getByLabel("Minimum semantic match").fill("0");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  const detail = page.locator(".passage-detail");
  const confirmed = page
    .getByRole("region", { name: "Document match groups", exact: true })
    .locator("summary")
    .first();
  for (let i = 1; i <= 3; i++) {
    await detail
      .getByRole("button", { name: "Match Confirmed", exact: true })
      .click();
    await expect(confirmed).toContainText("(1 document)");
    await expect(confirmed).toContainText(
      `${i} confirmed ${i === 1 ? "passage" : "passages"}`,
    );
    if (i < 3)
      await detail.getByRole("button", { name: "Next", exact: true }).click();
  }
  await page.locator(".passage-choice").last().click();
  await expect(detail).toContainText("Passage 8 of 8");
  await detail
    .getByRole("button", { name: "Match Confirmed", exact: true })
    .click();
  await expect(confirmed).toContainText("(2 documents)");
  await expect(confirmed).toContainText("4 confirmed passages");
});
