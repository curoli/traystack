import { expect, test } from "@playwright/test";
import { uploadAndProcess } from "./support/textual";
import { randomUUID } from "node:crypto";

test.use({ reducedMotion: "reduce" });

test("workspace navigation spans documents and old page boundaries with keyboard and preserved source text", async ({
  page,
}) => {
  const token = `Workspace${randomUUID().replaceAll("-", "")}`;
  const oldTitle = `Earlier contract ${Date.now()}`;
  const newTitle = `Later contract ${Date.now()}`;
  await uploadAndProcess(
    page,
    oldTitle,
    `${token} earlier context. `.repeat(7),
  );
  await uploadAndProcess(page, newTitle, `${token} later context. `.repeat(7));
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  const choices = page.locator(".passage-choice");
  const detail = page.locator(".passage-detail");
  await expect(choices).toHaveCount(14);
  await expect(page.locator(".textual-occurrence")).toHaveCount(1);
  await expect(
    detail.getByRole("heading", { name: newTitle, exact: true }),
  ).toBeVisible();
  await choices.first().focus();
  await page.keyboard.press("End");
  await expect(choices.last()).toBeFocused();
  await expect(
    detail.getByRole("heading", { name: oldTitle, exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Home");
  await expect(choices.first()).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(choices.nth(1)).toBeFocused();
  await expect(detail).toContainText("Passage 2 of 14");
  await choices.nth(6).click();
  await detail.getByRole("button", { name: "Keep", exact: true }).click();
  await expect(
    page.getByRole("progressbar", { name: "Final review decisions" }),
  ).toHaveAttribute("value", "1");
  await detail
    .getByRole("button", { name: "Next unreviewed", exact: true })
    .click();
  await expect(detail).toContainText("Passage 8 of 14");
  await expect(
    detail.getByRole("heading", { name: oldTitle, exact: true }),
  ).toBeVisible();
  await detail.getByRole("button", { name: "Dismiss", exact: true }).click();
  await expect(
    page.getByRole("progressbar", { name: "Final review decisions" }),
  ).toHaveAttribute("value", "2");
  await detail
    .getByRole("button", { name: "Next passage", exact: true })
    .click();
  await detail
    .getByRole("button", { name: "Decide later", exact: true })
    .click();
  await expect(detail.locator(".review-status")).toContainText(
    "Review: Decide later",
  );
  await expect(
    page.getByRole("progressbar", { name: "Final review decisions" }),
  ).toHaveAttribute("value", "2");
  await page
    .getByRole("button", { name: "Refresh reviews", exact: true })
    .click();
  await expect(detail).toContainText("Passage 9 of 14");
  await detail
    .getByRole("button", { name: "View source text", exact: true })
    .click();
  const source = page.getByRole("region", {
    name: "Saved source text",
    exact: true,
  });
  await expect(source).toBeFocused();
  await expect(source.locator(".text-preview")).toContainText(
    "earlier context",
  );
  await choices.last().click();
  await expect(source).toHaveCount(0);
  await detail
    .getByRole("button", { name: "Next unreviewed", exact: true })
    .click();
  await expect(detail).toContainText("Passage 1 of 14");
  await page.getByText("Search parameters", { exact: true }).click();
  await expect(
    page.getByLabel("Text passage", { exact: true }),
  ).not.toBeVisible();
  await detail
    .getByRole("button", { name: "Next passage", exact: true })
    .focus();
  await page.keyboard.press("Enter");
  await expect(detail).toContainText("Passage 2 of 14");
  await page.getByText("Search parameters", { exact: true }).click();
  await expect(page.getByLabel("Text passage", { exact: true })).toHaveValue(
    token,
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const listBox = await page
    .getByRole("navigation", { name: "Passage list", exact: true })
    .boundingBox();
  const detailBox = await detail.boundingBox();
  expect(detailBox!.y).toBeGreaterThan(listBox!.y);
  await detail
    .getByRole("button", { name: "View source text", exact: true })
    .click();
  await expect(source.locator(".text-preview")).toBeVisible();
  const sourceHeading = source.getByRole("heading", {
    name: "Saved source text",
    exact: true,
  });
  await expect(sourceHeading).toBeInViewport();
  expect(
    await sourceHeading.evaluate((element) => {
      const box = element.getBoundingClientRect();
      const top = document.elementFromPoint(
        box.x + box.width / 2,
        box.y + box.height / 2,
      );
      return top === element || element.contains(top);
    }),
  ).toBe(true);
  await expect(
    detail.getByRole("button", { name: "Keep", exact: true }),
  ).toBeInViewport();
});

test("filtered decisions advance to the next remaining passage and final progress excludes deferred decisions", async ({
  page,
}) => {
  const token = `FilteredWorkspace${randomUUID().replaceAll("-", "")}`;
  await uploadAndProcess(
    page,
    `Filtered review ${Date.now()}`,
    `${token} separate context. `.repeat(3),
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: "Similar passages", exact: true })
    .click();
  await page.getByLabel("Text passage", { exact: true }).fill(token);
  await page.getByLabel("Minimum textual match").fill("100");
  await page
    .getByLabel("Review status", { exact: true })
    .selectOption("unreviewed");
  await page
    .getByRole("button", { name: "Find passages", exact: true })
    .click();
  const choices = page.locator(".passage-choice");
  const detail = page.locator(".passage-detail");
  await expect(choices).toHaveCount(3);
  await page
    .getByLabel("Text passage", { exact: true })
    .fill("Unsubmitted changes");
  for (const [decision, remaining] of [
    ["Keep", 2],
    ["Dismiss", 1],
    ["Decide later", 0],
  ] as const) {
    await detail.getByRole("button", { name: decision, exact: true }).click();
    await expect(choices).toHaveCount(remaining);
    await expect(detail).toBeFocused();
  }
  await expect(
    page.getByRole("progressbar", { name: "Final review decisions" }),
  ).toHaveAttribute("value", "2");
  await expect(
    page.getByRole("region", { name: "Review counts", exact: true }),
  ).toContainText("Not reviewed: 0 · Keep: 1 · Dismiss: 1 · Decide later: 1");
  await expect(
    detail.getByRole("button", { name: "Next unreviewed", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel("Review saved results", { exact: true })
    .selectOption("all");
  await expect(choices).toHaveCount(3);
  await expect(choices.nth(0)).toContainText("Keep");
  await expect(choices.nth(1)).toContainText("Dismiss");
  await expect(choices.nth(2)).toContainText("Decide later");
  await expect(page.getByLabel("Text passage", { exact: true })).toHaveValue(
    "Unsubmitted changes",
  );
});
