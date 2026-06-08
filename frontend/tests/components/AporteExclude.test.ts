import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, fireEvent, screen, waitFor } from "@testing-library/svelte";
import "@testing-library/jest-dom/vitest";

vi.mock("$lib/api/aportes", () => ({
  createAporte: vi.fn(),
  applyAllocation: vi.fn(),
  excludeAllocation: vi.fn(),
}));

vi.mock("$lib/api/positions", () => ({
  listPositions: vi.fn(async () => []),
}));

vi.mock("$lib/stores/privacy", () => ({
  privacyStore: { subscribe: vi.fn(() => ({ unsubscribe: vi.fn() })) },
}));

vi.mock("$lib/format", () => ({
  formatBrl: (_v: number, _masked: boolean) => "R$ 100,00",
  formatQty: (_v: number, _masked: boolean, _d: number) => "1.0000",
}));

vi.mock("$lib/classLabels", () => ({
  CLASS_LABELS: {
    acoes_nacionais: "Ações Nacionais",
    rendafixa: "Renda Fixa",
  },
  CLASS_ORDER: ["rendafixa", "acoes_nacionais"],
}));

import AportePage from "../../src/routes/(app)/aporte/+page.svelte";
import { createAporte, excludeAllocation } from "$lib/api/aportes";

const MOCK_EVENT = {
  id: "evt-1",
  aporteValueBrl: 1000,
  createdAt: "2026-06-08T00:00:00Z",
  allocations: [
    {
      id: "alloc-1",
      aporteEventId: "evt-1",
      positionId: "pos-1",
      positionNameSnapshot: "PETR4",
      assetTypeSnapshot: "acoes_nacionais",
      priceAtApPorteBrl: 30,
      suggestedValueBrl: 600,
      suggestedQuantity: 20,
      applied: false,
      appliedValueBrl: null,
      appliedQuantity: null,
      excluded: false,
    },
    {
      id: "alloc-2",
      aporteEventId: "evt-1",
      positionId: "pos-2",
      positionNameSnapshot: "CDB XP",
      assetTypeSnapshot: "rendafixa",
      priceAtApPorteBrl: null,
      suggestedValueBrl: 400,
      suggestedQuantity: 400,
      applied: false,
      appliedValueBrl: null,
      appliedQuantity: null,
      excluded: false,
    },
  ],
};

const MOCK_REBALANCED = {
  ...MOCK_EVENT,
  allocations: [
    { ...MOCK_EVENT.allocations[0], excluded: true, suggestedValueBrl: 0, suggestedQuantity: 0 },
    {
      ...MOCK_EVENT.allocations[1],
      suggestedValueBrl: 1000,
      suggestedQuantity: 1000,
    },
  ],
};

describe("Aporte exclude", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (createAporte as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_EVENT);
    (excludeAllocation as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_REBALANCED);
  });

  it("calls excludeAllocation when X button clicked", async () => {
    render(AportePage);

    const input = screen.getByRole("spinbutton");
    await fireEvent.input(input, { target: { value: "1000" } });
    await fireEvent.click(screen.getByRole("button", { name: /calcular/i }));

    await waitFor(() => {
      expect(screen.getByText("PETR4")).toBeInTheDocument();
    });

    const excludeButtons = screen.getAllByText("✕");
    await fireEvent.click(excludeButtons[0]);

    await waitFor(() => {
      expect(excludeAllocation).toHaveBeenCalledWith("evt-1", "alloc-1");
    });
  });

  it("shows excluded row with reduced opacity", async () => {
    render(AportePage);

    const input = screen.getByRole("spinbutton");
    await fireEvent.input(input, { target: { value: "1000" } });
    await fireEvent.click(screen.getByRole("button", { name: /calcular/i }));

    await waitFor(() => {
      expect(screen.getByText("PETR4")).toBeInTheDocument();
    });

    const excludeButtons = screen.getAllByText("✕");
    await fireEvent.click(excludeButtons[0]);

    await waitFor(() => {
      expect(excludeAllocation).toHaveBeenCalled();
    });

    const petrRow = screen.getByText("PETR4").closest("tr");
    expect(petrRow).toHaveClass("opacity-40");

    const ticker = screen.getByText("PETR4");
    expect(ticker).toHaveClass("line-through");
  });

  it("hides X button for excluded rows", async () => {
    render(AportePage);

    const input = screen.getByRole("spinbutton");
    await fireEvent.input(input, { target: { value: "1000" } });
    await fireEvent.click(screen.getByRole("button", { name: /calcular/i }));

    await waitFor(() => {
      expect(screen.getByText("PETR4")).toBeInTheDocument();
    });

    expect(screen.getAllByText("✕")).toHaveLength(2);

    const excludeButtons = screen.getAllByText("✕");
    await fireEvent.click(excludeButtons[0]);

    await waitFor(() => {
      expect(excludeAllocation).toHaveBeenCalled();
    });

    expect(screen.getAllByText("✕")).toHaveLength(1);
  });
});
