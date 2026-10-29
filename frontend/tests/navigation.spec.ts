import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";

// Visibility alone does not prove the user can see details below a long library.
test.use({ reducedMotion: "reduce" });

for (const viewport of [
  { width: 1440, height: 720 },
  { width: 390, height: 844 },
]) {
  test(`opening a document reveals and focuses details at ${viewport.width}px`, async ({
    page,
  }) => {
    const title = `Navigation ${viewport.width} ${Date.now()}`;
    const response = await page.request.post("/api/documents/upload", {
      multipart: {
        title,
        requires_manual_review: "true",
        file: {
          name: "A-confidentiality.pdf",
          mimeType: "application/pdf",
          buffer: await readFile(
            path.resolve(
              "../examples/synthetic-contracts/A-confidentiality.pdf",
            ),
          ),
        },
      },
    });
    expect(response.status()).toBe(201);
    const document = await response.json();
    await page.setViewportSize(viewport);
    await page.goto("/");
    const row = page.locator(".document-row").filter({ hasText: title });
    const heading = page.getByRole("heading", { name: title, exact: true });

    await row.click();
    await expect(heading).toBeInViewport({ ratio: 1 });
    await expect(heading).toBeFocused();

    // Reopening the same selection with the keyboard must navigate again.
    await row.scrollIntoViewIfNeeded();
    await row.focus();
    await page.keyboard.press("Enter");
    await expect(heading).toBeInViewport({ ratio: 1 });
    await expect(heading).toBeFocused();

    // The review list uses the same navigation and must reveal the details too.
    await page.locator(".review-link").filter({ hasText: title }).click();
    await expect(heading).toBeInViewport({ ratio: 1 });
    await expect(heading).toBeFocused();

    // Background refresh must allow the user to scroll away without jumping back.
    const refresh = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/documents/${document.id}`) &&
        response.request().method() === "GET",
    );
    await page.evaluate(() => window.scrollTo(0, 0));
    await refresh;
    await page.evaluate(
      () =>
        new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)),
        ),
    );
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  });
}
