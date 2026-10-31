import { expect } from "@playwright/test";

export async function uploadAndProcess(
  page: import("@playwright/test").Page,
  title: string,
  text: string,
) {
  const upload = await page.request.post("/api/documents/upload", {
    multipart: {
      title,
      file: {
        name: "textual-search.txt",
        mimeType: "text/plain",
        buffer: Buffer.from(text),
      },
    },
  });
  expect(upload.status()).toBe(201);
  const document = await upload.json();
  await process(page, document.revisions[0].id);
  return document;
}
export async function process(
  page: import("@playwright/test").Page,
  revisionId: string,
) {
  const response = await page.request.post(
    `/api/revisions/${revisionId}/process`,
    { data: {} },
  );
  expect(response.status()).toBe(202);
  const job = await response.json();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/jobs/${job.id}`)).json()).status,
      { timeout: 60_000 },
    )
    .toBe("completed");
}
