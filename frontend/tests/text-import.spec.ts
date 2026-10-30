import { expect, test } from "@playwright/test";

for (const format of ["txt", "html"]) {
  test(`upload and process ${format} preserves content and exposes logical page provenance`, async ({
    page,
  }) => {
    const title = `Text import ${format} ${Date.now()}`;
    const phrase =
      "The receiving party shall not disclose confidential information.";
    const source =
      format === "txt"
        ? `Reference: Straße\n${phrase}\nEnd of synthetic document.`
        : `<html><body><p>${phrase}</p><script>window.syntheticExecuted = true;</script><img src="https://unwanted.invalid/scan.jpg"></body></html>`;
    const unwanted: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("unwanted.invalid"))
        unwanted.push(request.url());
    });
    await page.goto("/");
    await page.getByLabel("Title", { exact: true }).fill(title);
    await page.getByLabel("Original file", { exact: true }).setInputFiles({
      name: `synthetic.${format}`,
      mimeType: format === "txt" ? "text/plain" : "text/html",
      buffer: Buffer.from(source),
    });
    await page.getByRole("button", { name: "Save document" }).click();
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Start processing" }).click();
    const quality = page.locator(".quality-panel");
    await expect(quality.getByRole("heading")).toHaveText("Fully processed", {
      timeout: 60_000,
    });
    await expect(quality.locator("strong")).toHaveText(
      format === "txt" ? "No known quality issue" : "Manual review required",
    );
    await page.getByRole("button", { name: "View page text" }).click();
    const viewer = page.getByRole("region", {
      name: "Extracted page text",
      exact: true,
    });
    await expect(viewer).toContainText(
      "logical page, not a physical source page",
    );
    await expect(viewer.locator("pre")).toContainText(phrase);
    if (format === "html") {
      await expect(quality).toContainText(
        "without executing scripts or loading images",
      );
      await expect(viewer.locator("pre")).not.toContainText(
        "syntheticExecuted",
      );
      expect(await page.evaluate(() => "syntheticExecuted" in window)).toBe(
        false,
      );
    }
    expect(unwanted).toEqual([]);
  });
}
