import { expect, type Page } from "@playwright/test";

export async function scopeToDocument(page: Page, title: string) {
  const listing = await (
    await page.request.get("/api/documents?limit=100")
  ).json();
  const document = listing.items.find(
    (item: { title: string }) => item.title === title,
  );
  expect(document).toBeTruthy();
  const changed = await page.request.patch(
    `/api/documents/${document.id}/category`,
    { data: { category: title } },
  );
  expect(changed.status()).toBe(200);
  await page.evaluate(() =>
    window.dispatchEvent(new Event("categories-changed")),
  );
  await page
    .getByLabel("Document category", { exact: true })
    .selectOption(`category:${title}`);
}
