import { apiRequest } from "./client";
import type { RefreshSummaryOut } from "$lib/types/api";

export const refreshPrices = (scope: "active" | "all" = "all", force = true) =>
  apiRequest<RefreshSummaryOut>(`/prices/refresh?scope=${scope}&force=${force}`, { method: "POST" });
