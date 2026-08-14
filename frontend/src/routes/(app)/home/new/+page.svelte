<script lang="ts">
  import { goto } from "$app/navigation";
  import { createPosition } from "$lib/api/positions";
  import DiagramChecklist from "$lib/components/DiagramChecklist.svelte";
  import AutocompleteInput from "$lib/components/AutocompleteInput.svelte";
  import type { CandidateOut } from "$lib/types/api";

  let name = $state("");
  let assetType = $state("acoes_nacionais");
  let amountInput = $state("");
  let currentPriceInput = $state("");
  let strengthInput = $state("0");
  let diagramResponses = $state<string[]>([]);
  let submitting = $state(false);
  let error = $state<string | null>(null);

  const TYPES = [
    { v: "acoes_nacionais", l: "Ações Nacionais" },
    { v: "acoes_internacionais", l: "Ações Internacionais" },
    { v: "fundos_imobiliarios", l: "Fundos Imobiliários" },
    { v: "reits", l: "REITs" },
    { v: "criptomoedas", l: "Criptomoedas" },
    { v: "rendafixa", l: "Renda Fixa" },
    { v: "rendafixa_internacional", l: "Renda Fixa Internacional" },
  ];

  let isRF = $derived(
    assetType === "rendafixa" || assetType === "rendafixa_internacional",
  );
  let hasDiagram = $derived(
    assetType === "acoes_nacionais" ||
      assetType === "acoes_internacionais" ||
      assetType === "fundos_imobiliarios" ||
      assetType === "reits",
  );
  // Which asset types have catalog search support (backend returns [] for others)
  let searchable = $derived(
    assetType === "acoes_nacionais" ||
      assetType === "acoes_internacionais" ||
      assetType === "fundos_imobiliarios" ||
      assetType === "reits" ||
      assetType === "criptomoedas" ||
      assetType === "rendafixa",
  );
  let rfHasPrice = $derived(
    isRF && currentPriceInput !== "" && Number(currentPriceInput) > 0,
  );

  function handleCandidatePick(c: CandidateOut) {
    name = c.name;
    if (c.currentPriceBrl != null) {
      currentPriceInput = String(c.currentPriceBrl);
    }
  }

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    submitting = true;
    error = null;
    try {
      const amount = Number(amountInput);
      // For RF, price is optional: if user left it blank, treat as
      // private/unpriced (amount = BRL). Otherwise priced (amount = units).
      let currentPrice: number | null;
      if (isRF) {
        currentPrice =
          currentPriceInput !== "" && Number(currentPriceInput) > 0
            ? Number(currentPriceInput)
            : null;
      } else {
        currentPrice = Number(currentPriceInput);
      }
      await createPosition({
        name,
        assetType,
        amount,
        currentPrice,
        // Strength is server-recomputed from diagram_responses for equities;
        // for non-diagram assets (crypto, RF), we send the manual value.
        strength: hasDiagram ? 0 : parseInt(strengthInput, 10),
        diagramResponses: hasDiagram ? diagramResponses : null,
      });
      await goto("/home");
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      submitting = false;
    }
  }
</script>

<section class="mx-auto mt-8 max-w-2xl p-6">
  <header class="mb-6 flex items-center justify-between">
    <h1 class="text-2xl font-bold">Adicionar posição</h1>
    <a href="/home" class="text-sm text-slate-600 underline">← voltar</a>
  </header>

  <form onsubmit={handleSubmit} class="space-y-4">
    <label class="block">
      <span class="text-sm text-slate-700">
        Nome / ticker
        {#if searchable}
          <span class="text-xs text-slate-500">
            (digite para buscar — resultados de {assetType === "criptomoedas"
              ? "CoinGecko"
              : assetType === "rendafixa"
                ? "Tesouro Direto"
                : assetType === "acoes_internacionais" || assetType === "reits"
                  ? "Yahoo Finance"
                  : "Brapi"})
          </span>
        {/if}
      </span>
      {#if searchable}
        <AutocompleteInput
          value={name}
          {assetType}
          placeholder={isRF ? "tesouro renda" : (assetType === "acoes_internacionais" || assetType === "reits" ? "AAPL / O" : "PETR")}
          oninput={(v) => (name = v)}
          onselect={handleCandidatePick}
        />
      {:else}
        <input
          type="text"
          required
          bind:value={name}
          class="mt-1 block w-full rounded border-slate-300 px-3 py-2"
          placeholder={isRF ? "LCI INTER 90,00" : "VTI"}
        />
      {/if}
    </label>

    <label class="block">
      <span class="text-sm text-slate-700">Classe</span>
      <select
        bind:value={assetType}
        class="mt-1 block w-full rounded border-slate-300 px-3 py-2"
      >
        {#each TYPES as t}
          <option value={t.v}>{t.l}</option>
        {/each}
      </select>
    </label>

    <label class="block">
      <span class="text-sm text-slate-700">
        {#if isRF}
          {rfHasPrice ? "Quantidade (unidades)" : "Valor (R$)"}
          <span class="text-xs text-slate-500">
            — preencha o preço à direita se for precificado por unidade (Tesouro);
            deixe em branco para RF privada acompanhada em BRL
          </span>
        {:else}
          Quantidade (ações / moedas)
        {/if}
      </span>
      <input
        type="number"
        step="any"
        required
        bind:value={amountInput}
        class="mt-1 block w-full rounded border-slate-300 px-3 py-2"
      />
    </label>

    <label class="block">
      <span class="text-sm text-slate-700">
        Preço atual (R$ por unidade)
        {#if isRF}
          <span class="text-xs text-slate-500">— opcional para RF privada</span>
        {/if}
      </span>
      <input
        type="number"
        step="any"
        required={!isRF}
        bind:value={currentPriceInput}
        class="mt-1 block w-full rounded border-slate-300 px-3 py-2"
      />
    </label>

    {#if hasDiagram}
      <DiagramChecklist
        {assetType}
        responses={diagramResponses}
        onchange={(ids) => (diagramResponses = ids)}
      />
    {:else}
      <label class="block">
        <span class="text-sm text-slate-700">
          Força (sem diagrama para esta classe — digite um número manualmente)
        </span>
        <input
          type="number"
          step="1"
          required
          bind:value={strengthInput}
          class="mt-1 block w-full rounded border-slate-300 px-3 py-2"
        />
      </label>
    {/if}

    {#if error}
      <p class="text-sm text-red-700">{error}</p>
    {/if}

    <div class="flex gap-2">
      <button
        type="submit"
        disabled={submitting}
        class="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-50"
      >
        {submitting ? "Salvando…" : "Adicionar posição"}
      </button>
      <a
        href="/home"
        class="rounded bg-slate-200 px-4 py-2 font-medium text-slate-800 hover:bg-slate-300"
      >
        Cancelar
      </a>
    </div>
  </form>
</section>
