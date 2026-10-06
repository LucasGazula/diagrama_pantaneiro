import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiRequest, ApiError } from "../../src/lib/api/client";
import { authStore } from "../../src/lib/stores/auth";

const originalFetch = globalThis.fetch;

describe("apiRequest", () => {
  beforeEach(() => {
    authStore.logout();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("sends JSON body and parses response", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ) as typeof fetch;

    const result = await apiRequest<{ ok: boolean }>("/x", { method: "GET" });
    expect(result).toEqual({ ok: true });
  });

  it("adds Authorization header when token is set", async () => {
    authStore.login("my-token", { id: "u1", email: "a@b.c", is_active: true, is_superuser: false, is_verified: false });

    const fetchMock = vi.fn<typeof fetch>(async () =>
      new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    globalThis.fetch = fetchMock as typeof fetch;

    await apiRequest("/x", { method: "GET" });

    const [, init] = fetchMock.mock.calls[0];
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer my-token");
  });

  it("throws ApiError for 4xx responses", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ detail: "bad credentials" }), { status: 401 }),
    ) as typeof fetch;

    await expect(apiRequest("/x", { method: "GET" })).rejects.toThrow(ApiError);
  });

  it("logs out on 401", async () => {
    authStore.login("stale", { id: "u1", email: "a@b.c", is_active: true, is_superuser: false, is_verified: false });

    globalThis.fetch = vi.fn(async () =>
      new Response("{}", { status: 401 }),
    ) as typeof fetch;

    await expect(apiRequest("/x", { method: "GET" })).rejects.toThrow(ApiError);
    const { get } = await import("svelte/store");
    expect(get(authStore).token).toBeNull();
  });
});

describe("persistent session", () => {
  beforeEach(() => { authStore.logout(); });
  afterEach(() => { globalThis.fetch = originalFetch; });

  it("refreshes JWT and retries original request", async () => {
    authStore.login("expired", { id: "u1", email: "a@b.c", is_active: true, is_superuser: false, is_verified: false });
    const mock = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response("{}", { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "renewed" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    globalThis.fetch = mock;
    expect(await apiRequest("/positions")).toEqual({ ok: true });
    expect(mock.mock.calls[1][0]).toContain("/auth/jwt/refresh");
    expect(mock.mock.calls[1][1]?.credentials).toBe("include");
    expect((mock.mock.calls[2][1]?.headers as Record<string, string>).Authorization).toBe("Bearer renewed");
    expect(localStorage.getItem("auth_token")).toBe("renewed");
  });

  it("parallel failures share one refresh", async () => {
    let renewals = 0;
    const mock = vi.fn<typeof fetch>(async (url, init) => {
      if (String(url).endsWith("/refresh")) {
        renewals++;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return new Response(JSON.stringify({ access_token: "renewed" }), { status: 200 });
      }
      const token = (init?.headers as Record<string, string>).Authorization;
      return new Response("{}", { status: token === "Bearer renewed" ? 200 : 401 });
    });
    globalThis.fetch = mock;
    await Promise.all([apiRequest("/positions"), apiRequest("/targets")]);
    expect(renewals).toBe(1);
  });

  it("temporary refresh failure preserves saved token", async () => {
    authStore.login("expired", { id: "u1", email: "a@b.c", is_active: true, is_superuser: false, is_verified: false });
    globalThis.fetch = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response("{}", { status: 401 }))
      .mockRejectedValueOnce(new TypeError("Network unavailable"));
    await expect(apiRequest("/positions")).rejects.toThrow("Network unavailable");
    expect(localStorage.getItem("auth_token")).toBe("expired");
  });
});
