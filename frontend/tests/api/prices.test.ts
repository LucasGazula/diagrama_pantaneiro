import { afterEach, describe, expect, it, vi } from "vitest";
import { refreshPrices } from "../../src/lib/api/prices";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

describe("price refresh", () => {
  it.each([true, false])("preserves forced refresh choice: %s", async (force) => {
    const fetchMock = vi.fn<typeof fetch>(async () => new Response(
      JSON.stringify({ refreshed: 0, skippedManual: 0, failed: [] }),
      { headers: { "Content-Type": "application/json" } },
    ));
    globalThis.fetch = fetchMock;
    await refreshPrices("all", force);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain(`/prices/refresh?scope=all&force=${force}`);
    expect(init?.method).toBe("POST");
  });
});
