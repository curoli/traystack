import { expect, test } from "@playwright/test";
import { uploadAndProcess } from "./support/textual";

test("exact search is available in the unified UI with correct Unicode highlighting", async ({
  page,
}) => {
  const token = `Unicode${Date.now()}`;
  await uploadAndProcess(page, token, `😀 prefix ${token} suffix`);
  await page.goto("/");
  await expect(page.getByLabel("Minimum semantic match")).toHaveValue("50");
  await expect(page.getByLabel("Auto-confirm semantic minimum")).toHaveValue(
    "100",
  );
  await expect(
    page.getByRole("button", { name: "Literal search", exact: true }),
  ).toHaveCount(0);
  await page
    .getByLabel("Auto-confirm strong matches", { exact: true })
    .uncheck();
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page
    .getByLabel("Text comparison mode")
    .selectOption({ label: "Original" });
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  await expect(page.locator(".textual-occurrence mark")).toHaveText(token);
  await expect(page.locator(".textual-score")).toHaveText(
    "Textual match: 100.00%",
  );
});
