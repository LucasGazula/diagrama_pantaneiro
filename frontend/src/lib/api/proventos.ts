import { apiRequest } from "./client";
import type { DividendCalendarOut, DividendSyncOut } from "$lib/types/api";

export const getProventos = (year: number, month: number, dateMode: "payment" | "ex" = "payment") =>
  apiRequest<DividendCalendarOut>(`/proventos?year=${year}&month=${month}&date_mode=${dateMode}`);

export const syncProventos = () =>
  apiRequest<DividendSyncOut>("/proventos/sync", { method: "POST" });
