import { expect, test } from "@playwright/test";
import { uploadAndProcess } from "./support/textual";
import { randomUUID } from "node:crypto";

test("passage navigation and keyboard selection never change review state", async ({
  page,
}) => {
  const token = `Navigate${randomUUID().replaceAll("-", "")}`;
  const titles = [`Earlier ${Date.now()}`, `Later ${Date.now()}`];
  for (const title of titles)
    await uploadAndProcess(page, title, `${token} context. `.repeat(2));
  await page.goto("/");
  await page
    .getByLabel("Auto-confirm strong matches", { exact: true })
    .uncheck();
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  const choices = page.locator(".passage-choice"),
    detail = page.locator(".passage-detail");
  await expect(choices).toHaveCount(4);
  let writes = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/reviews") && request.method() === "POST")
      writes++;
  });
  await expect(detail).toContainText(titles[1]);
  await detail.getByRole("button", { name: "Next", exact: true }).click();
  await expect(detail).toContainText(titles[1]);
  await expect(detail).toContainText("Passage 2 of 4");
  await detail
    .getByRole("button", { name: "Previous unreviewed", exact: true })
    .click();
  await expect(detail).toContainText("Passage 1 of 4");
  await detail
    .getByRole("button", { name: "Next unreviewed", exact: true })
    .click();
  await expect(detail).toContainText("Passage 2 of 4");
  expect(writes).toBe(0);
  await detail
    .getByRole("button", { name: "Confirm match", exact: true })
    .click();
  await expect(detail).toContainText("Passage 2 of 4");
  await expect(
    detail.getByRole("button", { name: "Confirm match", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await choices.first().focus();
  await page.keyboard.press("End");
  await expect(choices.last()).toBeFocused();
  await expect(detail).toContainText("Passage 4 of 4");
  await page.keyboard.press("Home");
  await expect(choices.first()).toBeFocused();
  await detail
    .getByRole("button", { name: "View source text", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Saved source text", exact: true }),
  ).toBeFocused();
  await choices.last().click();
  await expect(
    page.getByRole("region", { name: "Saved source text", exact: true }),
  ).toHaveCount(0);
});

test("navigation reaches every passage in one document and skips reviewed passages", async ({
  page,
}) => {
  const token = `Single${randomUUID().replaceAll("-", "")}`;
  await uploadAndProcess(
    page,
    `Single document ${Date.now()}`,
    `${token} context. `.repeat(3),
  );
  await page.goto("/");
  await page
    .getByLabel("Auto-confirm strong matches", { exact: true })
    .uncheck();
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page.getByLabel("Minimum semantic match").fill("0");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  const detail = page.locator(".passage-detail");
  await expect(page.locator(".passage-choice")).toHaveCount(3);
  await expect(
    detail.getByRole("button", { name: "Previous", exact: true }),
  ).toBeDisabled();
  await detail.getByRole("button", { name: "Next", exact: true }).click();
  await expect(detail).toContainText("Passage 2 of 3");
  await detail
    .getByRole("button", { name: "Confirm match", exact: true })
    .click();
  await expect(
    detail.getByRole("button", { name: "Confirm match", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  let writes = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/reviews") && request.method() === "POST")
      writes++;
  });
  await detail.getByRole("button", { name: "Previous", exact: true }).click();
  await detail
    .getByRole("button", { name: "Next unreviewed", exact: true })
    .click();
  await expect(detail).toContainText("Passage 3 of 3");
  await expect(
    detail.getByRole("button", { name: "Next", exact: true }),
  ).toBeDisabled();
  await expect(
    detail.getByRole("button", { name: "Next unreviewed", exact: true }),
  ).toBeDisabled();
  await detail
    .getByRole("button", { name: "Previous unreviewed", exact: true })
    .click();
  await expect(detail).toContainText("Passage 1 of 3");
  expect(writes).toBe(0);
});
