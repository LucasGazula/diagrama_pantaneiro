import { beforeEach, describe, expect, it } from "vitest";
import { get } from "svelte/store";

import { authStore } from "../../src/lib/stores/auth";

const user = {
  id: "u1", email: "a@b.c", is_active: true, is_superuser: false, is_verified: false,
};

describe("authStore", () => {
  beforeEach(() => {
    localStorage.clear();
    authStore.logout();
  });

  it("starts unauthenticated", () => {
    const state = get(authStore);
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
  });

  it("login sets token and user", () => {
    authStore.login("tok-123", user);
    const state = get(authStore);
    expect(state.token).toBe("tok-123");
    expect(state.user?.email).toBe("a@b.c");
  });

  it("persists token to localStorage on login", () => {
    authStore.login("tok-xyz", user);
    expect(localStorage.getItem("auth_token")).toBe("tok-xyz");
  });

  it("logout clears token and localStorage", () => {
    authStore.login("tok-xyz", user);
    authStore.logout();
    expect(get(authStore).token).toBeNull();
    expect(localStorage.getItem("auth_token")).toBeNull();
  });
});
