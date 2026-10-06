import { writable } from "svelte/store";
import type { UserRead } from "$lib/types/api";

interface AuthState {
  token: string | null;
  user: UserRead | null;
}

function readInitial(): AuthState {
  if (typeof localStorage === "undefined") {
    return { token: null, user: null };
  }
  const token = localStorage.getItem("auth_token");
  return { token, user: null };
}

function createAuthStore() {
  const { subscribe, set, update } = writable<AuthState>(readInitial());

  return {
    subscribe,
    login(token: string, user: UserRead) {
      localStorage.setItem("auth_token", token);
      set({ token, user });
    },
    setToken(token: string) {
      localStorage.setItem("auth_token", token);
      update((s) => ({ ...s, token }));
    },
    setUser(user: UserRead) {
      update((s) => ({ ...s, user }));
    },
    logout() {
      localStorage.removeItem("auth_token");
      set({ token: null, user: null });
    },
  };
}

export const authStore = createAuthStore();
