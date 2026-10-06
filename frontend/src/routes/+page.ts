import { redirect } from "@sveltejs/kit";
import { get } from "svelte/store";

import { authStore } from "$lib/stores/auth";
import type { PageLoad } from "./$types";

export const ssr = false;

export const load: PageLoad = () => {
  const state = get(authStore);
  if (state.token) {
    throw redirect(307, "/home");
  }
  throw redirect(307, "/login");
};
