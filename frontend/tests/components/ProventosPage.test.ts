import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/svelte";
import "@testing-library/jest-dom/vitest";

vi.mock("$lib/api/proventos", () => ({
  getProventos: vi.fn(),
  syncProventos: vi.fn(),
}));

vi.mock("$lib/api/portfolios", () => ({
  listPortfolios: vi.fn(async () => [
    { id: "p-1", name: "Principal", isDefault: true, createdAt: "2026-01-01" },
  ]),
}));

vi.mock("$lib/stores/privacy", () => ({
  privacyStore: { subscribe: vi.fn((fn) => { fn(false); return () => {}; }) },
}));

vi.mock("$lib/format", () => ({
  formatBrl: (v: number) => `R$ ${v.toFixed(2)}`,
  formatQty: (v: number) => `${v.toFixed(2)}`,
}));

vi.mock("$lib/classLabels", () => ({
  CLASS_LABELS: {
    acoes_nacionais: "Ações Nacionais",
    fundos_imobiliarios: "Fundos Imobiliários",
    acoes_internacionais: "Ações Internacionais",
    reits: "REITs",
  },
}));

import ProventosPage from "../../src/routes/(app)/proventos/+page.svelte";
import { getProventos, syncProventos } from "$lib/api/proventos";

const MOCK_CALENDAR_DATA = {
  year: 2026,
  month: 9,
  dateMode: "payment" as const,
  usdRate: 5.0,
  totalReceivedBrl: 100.0,
  totalReceivedNetBrl: 85.0,
  totalProjectedBrl: 100.0,
  totalProjectedNetBrl: 100.0,
  totalMonthBrl: 200.0,
  totalMonthNetBrl: 185.0,
  totalTaxBrl: 15.0,
  items: [
    {
      id: "div-1",
      ticker: "BBAS3",
      assetType: "acoes_nacionais",
      paymentDate: "2026-09-02",
      exDate: "2026-09-01",
      amountShares: 100,
      rateNative: 1.0,
      currency: "BRL",
      rateBrl: 1.0,
      rateNetBrl: 0.85,
      totalNative: 100.0,
      totalBrl: 100.0,
      totalNetBrl: 85.0,
      taxRate: 0.15,
      taxBrl: 15.0,
      isJcp: true,
      dividendType: "JRS CAP PROPRIO",
      status: "pago" as const,
    },
    {
      id: "div-2",
      ticker: "AAPL",
      assetType: "acoes_internacionais",
      paymentDate: "2026-09-20",
      exDate: "2026-09-10",
      amountShares: 10,
      rateNative: 2.0,
      currency: "USD",
      rateBrl: 10.0,
      rateNetBrl: 10.0,
      totalNative: 20.0,
      totalBrl: 100.0,
      totalNetBrl: 100.0,
      taxRate: 0.0,
      taxBrl: 0.0,
      isJcp: false,
      dividendType: "Dividendo",
      status: "previsto" as const,
    },
  ],
};

describe("ProventosPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getProventos).mockResolvedValue(MOCK_CALENDAR_DATA);
  });

  it("renders calendar with summary totals and events", async () => {
    render(ProventosPage);

    await waitFor(() => {
      expect(screen.getByText("CALENDÁRIO DE PROVENTOS")).toBeInTheDocument();
    });

    await waitFor(() => {
      // Default valueMode is net:
      // Received net = 85.00, Projected net = 100.00, Month net = 185.00
      expect(screen.getAllByText("R$ 85.00").length).toBeGreaterThan(0);
      expect(screen.getAllByText("R$ 100.00").length).toBeGreaterThan(0);
      expect(screen.getByText("R$ 185.00")).toBeInTheDocument();
    });

    // Check tickers appear in table
    expect(screen.getAllByText("BBAS3").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    // Check JCP tag
    expect(screen.getByText("-15% IR")).toBeInTheDocument();
  });

  it("toggles value mode between net and gross", async () => {
    render(ProventosPage);

    await waitFor(() => {
      expect(screen.getByText("CALENDÁRIO DE PROVENTOS")).toBeInTheDocument();
      expect(screen.getByText("R$ 185.00")).toBeInTheDocument();
    });

    const grossBtn = screen.getByText("bruto");
    await fireEvent.click(grossBtn);

    await waitFor(() => {
      // Gross month total is 200.00
      expect(screen.getByText("R$ 200.00")).toBeInTheDocument();
    });
  });

  it("calls syncProventos when sync button clicked", async () => {
    vi.mocked(syncProventos).mockResolvedValue({
      syncedTickers: 2,
      failedTickers: [],
      totalDividendsStored: 5,
    });

    render(ProventosPage);

    await waitFor(() => {
      expect(screen.getByText("CALENDÁRIO DE PROVENTOS")).toBeInTheDocument();
    });

    const syncBtn = screen.getByTitle("Buscar proventos atualizados na API");
    await fireEvent.click(syncBtn);

    await waitFor(() => {
      expect(syncProventos).toHaveBeenCalledTimes(1);
      expect(screen.getByText(/Sincronizados 2 ativos/)).toBeInTheDocument();
    });
  });

  it("toggles date mode between payment and ex", async () => {
    render(ProventosPage);

    await waitFor(() => {
      expect(screen.getByText("CALENDÁRIO DE PROVENTOS")).toBeInTheDocument();
    });

    const exToggle = screen.getByText("data-com (ex)");
    await fireEvent.click(exToggle);

    await waitFor(() => {
      expect(getProventos).toHaveBeenCalledWith(
        expect.any(Number),
        expect.any(Number),
        "ex",
      );
    });
  });
});
