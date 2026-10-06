import { redirect, error } from "@sveltejs/kit";
import { get } from "svelte/store";

import { getCurrentUser } from "$lib/api/auth";
import { listPortfolios } from "$lib/api/portfolios";
import { ApiError, refreshSession } from "$lib/api/client";
import { authStore } from "$lib/stores/auth";
import { portfolioStore } from "$lib/stores/portfolio";

import type { LayoutLoad } from "./$types";

export const ssr = false;

export const load: LayoutLoad = async () => {
  let state = get(authStore);
  if (!state.token) {
    let renewed: boolean;
    try {
      renewed = await refreshSession();
    } catch {
      throw error(503, "Não foi possível verificar sessão. Atualize página para tentar novamente.");
    }
    if (!renewed) throw redirect(307, "/login");
    state = get(authStore);
  }

  if (!state.user) {
    try {
      const user = await getCurrentUser();
      authStore.setUser(user);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) throw redirect(307, "/login");
      throw error(503, "Não foi possível verificar sessão. Atualize página para tentar novamente.");
    }
  }

  // Fetch portfolios once per session so every downstream API call has
  // a valid X-Portfolio-Id header from the store.
  if (get(portfolioStore).all.length === 0) {
    try {
      const portfolios = await listPortfolios();
      portfolioStore.setAll(portfolios);
    } catch {
      // Swallow: the backend has a default-portfolio fallback in the
      // get_active_portfolio dep, so the app still works even if this fails.
    }
  }

  return {};
};
