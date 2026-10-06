import { afterEach, describe, expect, it, vi } from "vitest";

import { login, register, getCurrentUser } from "../../src/lib/api/auth";

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("auth api", () => {
  it("register POSTs to /api/auth/register with JSON body", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      new Response(
        JSON.stringify({ id: "u1", email: "a@b.c", is_active: true, is_superuser: false, is_verified: false }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    globalThis.fetch = fetchMock as typeof fetch;

    const user = await register("a@b.c", "Pw!123456");

    expect(user.email).toBe("a@b.c");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/auth/register");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ email: "a@b.c", password: "Pw!123456" }));
  });

  it("login POSTs form-encoded body to /api/auth/jwt/login", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      new Response(JSON.stringify({ access_token: "tok", token_type: "bearer" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    globalThis.fetch = fetchMock as typeof fetch;

    const result = await login("a@b.c", "Pw!123456");
    expect(result.access_token).toBe("tok");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/auth/jwt/login");
    expect(init?.headers).toMatchObject({ "Content-Type": "application/x-www-form-urlencoded" });
    expect(String(init?.body)).toContain("username=a%40b.c");
    expect(String(init?.body)).toContain("password=Pw%21123456");
  });

  it("getCurrentUser GETs /api/users/me", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () =>
      new Response(
        JSON.stringify({ id: "u1", email: "me@x.y", is_active: true, is_superuser: false, is_verified: false }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    globalThis.fetch = fetchMock as typeof fetch;

    const user = await getCurrentUser();
    expect(user.email).toBe("me@x.y");
  });
});
