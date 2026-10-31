import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";

test("a contract batch supports source inspection, material differences and saved reviews", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const corpus = JSON.parse(
    readFileSync(
      new URL(
        "../../examples/search-evaluation/corpus-sample.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const marker = randomUUID().replaceAll("-", "");
  const stamp = Date.now();
  const rows = Array.from({ length: 32 }, (_, index) => {
    const sample = corpus.documents[index % 8];
    const background = sample.text.split("\n\n").slice(1, 4).join("\n\n");
    return {
      title: `Workload ${stamp} ${index}`,
      text: (background.repeat(5) + sample.text).replaceAll(
        corpus.marker,
        marker,
      ),
    };
  });
  const jobs: string[] = [];
  for (let offset = 0; offset < rows.length; offset += 4) {
    await Promise.all(
      rows.slice(offset, offset + 4).map(async (row) => {
        const upload = await page.request.post("/api/documents/upload", {
          multipart: {
            title: row.title,
            file: {
              name: "workload.txt",
              mimeType: "text/plain",
              buffer: Buffer.from(row.text),
            },
          },
        });
        expect(upload.status()).toBe(201);
        const doc = await upload.json();
        const process = await page.request.post(
          `/api/revisions/${doc.revisions[0].id}/process`,
          { data: {} },
        );
        expect(process.status()).toBe(202);
        jobs.push((await process.json()).id);
      }),
    );
  }
  await expect
    .poll(
      async () => {
        const statuses = await Promise.all(
          jobs.map(
            async (id) =>
              (await (await page.request.get(`/api/jobs/${id}`)).json()).status,
          ),
        );
        expect(statuses).not.toContain("failed");
        return statuses.every((status) => status === "completed");
      },
      { timeout: 60_000 },
    )
    .toBe(true);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page.getByLabel("Minimum textual match").fill("85");
  const query = (family: string) =>
    corpus.queries[family].replaceAll(corpus.marker, marker);
  async function find(family: string) {
    await page.getByLabel("Text passage", { exact: true }).fill(query(family));
    await page
      .getByRole("button", { name: "Find passages", exact: true })
      .click();
    await expect(page.locator(".textual-response")).toBeVisible();
    await expect(page.locator(".search-duration")).toContainText(
      /Search completed in \d+\.\d{2} s/,
    );
  }
  await find("confidentiality");
  await expect(page.locator(".passage-choice")).toHaveCount(24);
  await expect(page.locator(".textual-response")).toContainText(
    "24 with candidate passages",
  );
  const first = page.locator(".textual-occurrence").first();
  await first
    .getByRole("button", { name: "View source text", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Saved source text", exact: true }),
  ).toBeFocused();
  await first.getByRole("button", { name: "Keep", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Review counts", exact: true }),
  ).toContainText("Keep: 1");
  await page.locator(".passage-choice").nth(11).click();
  await expect(page.locator(".passage-choice")).toHaveCount(24);
  // One recent contract contains changed negation, amount, name and German negation.
  await page
    .locator(".document-row")
    .filter({ hasText: rows[29].title })
    .click();
  await page
    .getByRole("checkbox", { name: "Search only the open document" })
    .check();
  await page
    .getByRole("checkbox", { name: "Compare meaning with local embeddings" })
    .check();
  await find("confidentiality");
  await expect(page.locator(".textual-occurrence")).toHaveCount(1);
  await expect(page.locator(".text-comparison del")).toContainText(["not"]);
  await first.getByRole("button", { name: "Dismiss", exact: true }).click();
  await expect(first.locator(".review-status")).toContainText(
    "Review: Dismiss",
  );
  await find("amount");
  await expect(page.locator(".text-comparison ins")).toContainText(["5000"]);
  await expect(page.locator(".semantic-score")).not.toHaveText(
    "Semantic match: 100.00%",
  );
  await first
    .getByRole("button", { name: "Decide later", exact: true })
    .click();
  await expect(first.locator(".review-status")).toContainText(
    "Review: Decide later",
  );
  await find("name");
  await expect(page.locator(".text-comparison ins")).toContainText(["beta"]);
  await find("german");
  await expect(page.locator(".text-comparison ins")).toContainText(["nicht"]);
  await find("amount");
  await expect(first.locator(".review-status")).toContainText(
    "Review: Decide later",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
