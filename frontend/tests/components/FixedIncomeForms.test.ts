import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/svelte";
import "@testing-library/jest-dom/vitest";

const mockPage = {
  params: { id: "pos-cdb" },
};

vi.mock("$app/state", () => ({
  get page() {
    return mockPage;
  },
}));

vi.mock("$app/navigation", () => ({
  goto: vi.fn(),
}));

vi.mock("$lib/api/positions", () => ({
  createPosition: vi.fn(),
  listPositions: vi.fn(),
  updatePosition: vi.fn(),
  deletePosition: vi.fn(),
}));

vi.mock("$lib/api/catalog", () => ({
  searchCatalog: vi.fn(async () => []),
}));

vi.mock("$lib/api/diagram", () => ({
  listDiagramQuestions: vi.fn(async () => []),
}));

import NewPositionPage from "../../src/routes/(app)/home/new/+page.svelte";
import EditPositionPage from "../../src/routes/(app)/home/[id]/+page.svelte";
import { createPosition, listPositions, updatePosition } from "$lib/api/positions";
import type { PositionOut } from "$lib/types/api";

const MOCK_CDB_POSITION: PositionOut = {
  id: "pos-cdb",
  name: "CDB Banco Inter",
  assetType: "rendafixa",
  amount: 1000,
  currentPrice: 500,
  currentValueBrl: 1000,
  trackingMode: "balance",
  strength: 0,
  source: "manual",
  externalId: null,
  diagramResponses: null,
};

describe("Fixed Income Forms (new and edit)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPage.params.id = "pos-cdb";
  });

  it("new form: selecting Renda Fixa defaults to balance mode, Valor (R$), preserves mode on price fill and submits correct payload", async () => {
    render(NewPositionPage);

    // Select class Renda Fixa
    const classSelect = screen.getByRole("combobox", { name: "Classe" }) as HTMLSelectElement;
    await fireEvent.change(classSelect, { target: { value: "rendafixa" } });

    // Acompanhamento select should be visible and defaulted to balance
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Acompanhamento" })).toBeInTheDocument();
    });

    const trackingSelect = screen.getByRole("combobox", { name: "Acompanhamento" }) as HTMLSelectElement;
    expect(trackingSelect.value).toBe("balance");

    // Label should indicate Valor (R$)
    expect(screen.getByText(/Valor \(R\$\)/i)).toBeInTheDocument();

    // Fill name (via text input in AutocompleteInput)
    const nameInput = screen.getByPlaceholderText(/tesouro renda/i);
    await fireEvent.input(nameInput, { target: { value: "CDB Banco Inter" } });

    // Fill amount: 1000
    const amountInput = screen.getByLabelText(/Valor \(R\$\)/i);
    await fireEvent.input(amountInput, { target: { value: "1000" } });

    // Fill price: 500
    const priceInput = screen.getByLabelText(/Preço atual/i);
    await fireEvent.input(priceInput, { target: { value: "500" } });

    // Verify trackingMode did NOT automatically switch to units just because price was entered
    expect(trackingSelect.value).toBe("balance");

    // Fill manual strength: 0
    const strengthInput = screen.getByLabelText(/Força/i);
    await fireEvent.input(strengthInput, { target: { value: "0" } });

    // Submit form
    const submitBtn = screen.getByRole("button", { name: /Adicionar posição/i });
    await fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(createPosition).toHaveBeenCalledTimes(1);
      expect(createPosition).toHaveBeenCalledWith({
        name: "CDB Banco Inter",
        assetType: "rendafixa",
        amount: 1000,
        currentPrice: 500,
        trackingMode: "balance",
        externalId: null,
        strength: 0,
        diagramResponses: null,
      });
    });
  });

  it("edit form: loads existing balance-tracked position, saving sends amount and balance mode without changing units", async () => {
    vi.mocked(listPositions).mockResolvedValue([MOCK_CDB_POSITION]);

    render(EditPositionPage);

    await waitFor(() => {
      expect(screen.getByText("Editar CDB Banco Inter")).toBeInTheDocument();
    });

    // Verify fields loaded
    const trackingSelect = screen.getByRole("combobox", { name: "Acompanhamento" }) as HTMLSelectElement;
    expect(trackingSelect.value).toBe("balance");

    const amountInput = screen.getByLabelText(/Valor \(R\$\)/i) as HTMLInputElement;
    expect(amountInput.value).toBe("1000");

    const priceInput = screen.getByLabelText(/Preço atual/i) as HTMLInputElement;
    expect(priceInput.value).toBe("500");

    // Click Salvar
    const saveBtn = screen.getByRole("button", { name: "Salvar" });
    await fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(updatePosition).toHaveBeenCalledTimes(1);
      expect(updatePosition).toHaveBeenCalledWith("pos-cdb", {
        amount: 1000,
        trackingMode: "balance",
        currentPrice: 500,
        strength: 0,
        name: "CDB Banco Inter",
        externalId: null,
      });
    });
  });

  it("edit form: switching to units disables amount input, displays conversion notice, and save omits amount", async () => {
    vi.mocked(listPositions).mockResolvedValue([MOCK_CDB_POSITION]);

    render(EditPositionPage);

    await waitFor(() => {
      expect(screen.getByText("Editar CDB Banco Inter")).toBeInTheDocument();
    });

    const trackingSelect = screen.getByRole("combobox", { name: "Acompanhamento" }) as HTMLSelectElement;
    const amountInput = screen.getByLabelText(/Valor \(R\$\)/i) as HTMLInputElement;

    // Change tracking mode to "units"
    await fireEvent.change(trackingSelect, { target: { value: "units" } });

    // Amount input must be disabled
    expect(amountInput).toBeDisabled();

    // Conversion notice should be shown
    expect(
      screen.getByText(
        "Salvar converte saldo atual usando preço da unidade. Depois, edite quantidade ou saldo.",
      ),
    ).toBeInTheDocument();

    // Click Salvar
    const saveBtn = screen.getByRole("button", { name: "Salvar" });
    await fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(updatePosition).toHaveBeenCalledTimes(1);
      expect(updatePosition).toHaveBeenCalledWith("pos-cdb", {
        trackingMode: "units",
        currentPrice: 500,
        strength: 0,
        name: "CDB Banco Inter",
        externalId: null,
      });
    });
  });
});
