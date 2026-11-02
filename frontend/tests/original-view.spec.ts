import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

for (const kind of ["pdf", "jpg", "png", "txt", "html"] as const) {
  test(`View original opens ${kind} in a separate browser tab`, async ({
    page,
  }) => {
    const title = `Browser original ${kind} ${Date.now()}`;
    let bytes: Buffer;
    if (kind === "pdf" || kind === "jpg") {
      bytes = await readFile(
        `../examples/synthetic-contracts/${kind === "pdf" ? "A-confidentiality.pdf" : "P-printed-scan.jpg"}`,
      );
    } else if (kind === "png") {
      bytes = Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg==",
        "base64",
      );
    } else {
      bytes = Buffer.from(
        kind === "txt"
          ? "Original contract text"
          : '<h1>Original contract</h1><script>window.originalScriptRan = true; fetch("/api/documents");</script><img src="https://unwanted.invalid/contract.jpg">',
      );
    }
    const uploaded = await page.request.post("/api/documents/upload", {
      multipart: {
        title,
        file: {
          name: `original.${kind}`,
          mimeType: "application/octet-stream",
          buffer: bytes,
        },
      },
    });
    expect(uploaded.status()).toBe(201);
    const doc = await uploaded.json();
    const artifact = doc.revisions[0].artifacts[0];
    await page.goto("/");
    await page.getByText("Manage documents", { exact: true }).click();
    await page.locator(".document-row").filter({ hasText: title }).click();
    const view = page
      .locator(".artifact")
      .getByRole("link", { name: "View original", exact: false });
    await expect(view).toHaveAttribute("target", "_blank");
    let downloads = 0;
    page.on("download", () => downloads++);
    const requests: string[] = [];
    await page.context().route("https://unwanted.invalid/**", async (route) => {
      requests.push(route.request().url());
      await route.abort();
    });
    const opened = page.waitForEvent("popup");
    await view.click();
    const popup = await opened;
    popup.on("download", () => downloads++);
    await popup.waitForLoadState("load");
    await expect(popup).toHaveURL(
      new RegExp(`/api/artifacts/${artifact.id}/content\\?view=true$`),
    );
    if (kind === "txt")
      await expect(popup.locator("body")).toContainText(
        "Original contract text",
      );
    if (kind === "html") {
      await expect(
        popup.getByRole("heading", { name: "Original contract" }),
      ).toBeVisible();
      expect(
        await popup.evaluate(
          () =>
            (window as unknown as { originalScriptRan?: boolean })
              .originalScriptRan,
        ),
      ).toBeUndefined();
      expect(requests).toEqual([]);
    }
    if (kind === "jpg" || kind === "png")
      expect(
        await popup
          .locator("img")
          .evaluate((img: HTMLImageElement) => img.naturalWidth),
      ).toBeGreaterThan(0);
    expect(downloads).toBe(0);
    await popup.close();
    const downloaded = await page.request.get(
      `/api/artifacts/${artifact.id}/content`,
    );
    expect(downloaded.headers()["content-disposition"]).toContain(
      "attachment;",
    );
    expect(await downloaded.body()).toEqual(bytes);
    await expect(
      page
        .locator(".artifact")
        .getByRole("link", { name: "Download original", exact: false }),
    ).toBeVisible();
  });
}
