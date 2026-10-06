import { beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

vi.mock("$lib/api/auth", () => ({ getCurrentUser: vi.fn() }));
vi.mock("$lib/api/portfolios", () => ({ listPortfolios: vi.fn(async () => []) }));

import { load } from "../../src/routes/(app)/+layout";
import { getCurrentUser } from "$lib/api/auth";
import { authStore } from "$lib/stores/auth";

const originalFetch = globalThis.fetch;

describe("session guard", () => {
  beforeEach(() => { authStore.logout(); vi.clearAllMocks(); });

  it("keeps saved login when user lookup fails temporarily", async () => {
    authStore.setToken("saved-token");
    vi.mocked(getCurrentUser).mockRejectedValueOnce(new TypeError("Network unavailable"));
    await expect(load({} as Parameters<typeof load>[0])).rejects.toMatchObject({ status: 503 });
    expect(get(authStore).token).toBe("saved-token");
  });

  it("restores JWT from persistent cookie when local access token is missing", async () => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ access_token: "restored" }), { status: 200 })) as typeof fetch;
    vi.mocked(getCurrentUser).mockResolvedValueOnce({ id: "u1", email: "a@b.c", is_active: true, is_superuser: false, is_verified: false });
    try {
      await load({} as Parameters<typeof load>[0]);
      expect(get(authStore).token).toBe("restored");
      expect(get(authStore).user?.id).toBe("u1");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
