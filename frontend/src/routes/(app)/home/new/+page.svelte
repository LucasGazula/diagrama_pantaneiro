<script lang="ts">
  import { goto } from "$app/navigation";
  import { createPosition } from "$lib/api/positions";
  import DiagramChecklist from "$lib/components/DiagramChecklist.svelte";
  import AutocompleteInput from "$lib/components/AutocompleteInput.svelte";
  import type { CandidateOut } from "$lib/types/api";

  let name = $state("");
  let trackingMode = $state<"balance" | "units">("units");
  let externalId = $state<string | null>(null);
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
  let rfHasPrice = $derived(isRF && trackingMode === "units");

  function handleCandidatePick(c: CandidateOut) {
    name = c.name;
    externalId = c.externalId ?? null;
    if (c.currentPriceBrl != null) {
      if (trackingMode === "balance" && amountInput !== "") {
        amountInput = String(Number(amountInput) / c.currentPriceBrl);
      }
      currentPriceInput = String(c.currentPriceBrl);
      trackingMode = "units";
    }
  }

  function changeClass() {
    trackingMode = assetType === "rendafixa" || assetType === "rendafixa_internacional" ? "balance" : "units";
    name = "";
    externalId = null;
    currentPriceInput = "";
    amountInput = "";
  }

  function changeMode(e: Event) {
    const next = (e.currentTarget as HTMLSelectElement).value as "balance" | "units";
    const price = Number(currentPriceInput);
    if (amountInput !== "" && price > 0 && next !== trackingMode) {
      amountInput = String(next === "units" ? Number(amountInput) / price : Number(amountInput) * price);
    } else if (amountInput !== "" && next !== trackingMode) {
      error = "Informe preço da unidade para converter saldo.";
      (e.currentTarget as HTMLSelectElement).value = trackingMode;
      return;
    }
    trackingMode = next;
    error = null;
  }

  async function handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    submitting = true;
    error = null;
    try {
      const amount = Number(amountInput);
      // Tracking mode defines amount independently of quote availability.
      let currentPrice: number | null;
      if (isRF && trackingMode === "balance") {
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
        trackingMode,
        externalId,
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

<section class="responsive-page mx-auto mt-8 max-w-2xl p-6">
  <header class="page-header mb-6 flex items-center justify-between">
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
          oninput={(v) => { name = v; externalId = null; }}
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
        onchange={changeClass}
        class="mt-1 block w-full rounded border-slate-300 px-3 py-2"
      >
        {#each TYPES as t}
          <option value={t.v}>{t.l}</option>
        {/each}
      </select>
    </label>

    {#if isRF}
      <label class="block">
        <span class="text-sm text-slate-700">Acompanhamento</span>
        <select value={trackingMode} onchange={changeMode} class="mt-1 block w-full rounded border-slate-300 px-3 py-2">
          <option value="balance">Saldo manual em reais</option>
          <option value="units">Quantidade de títulos × preço da unidade</option>
        </select>
      </label>
    {/if}

    <label class="block">
      <span class="text-sm text-slate-700">
        {#if isRF}
          {rfHasPrice ? "Quantidade (unidades)" : "Valor (R$)"}
          <span class="text-xs text-slate-500">
            — {rfHasPrice ? "informe quantidade de títulos na corretora" : "informe saldo atualizado em reais"}
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
          <span class="text-xs text-slate-500">— opcional no saldo manual; preencher preço não muda acompanhamento</span>
        {/if}
      </span>
      <input
        type="number"
        step="any"
        required={!isRF || trackingMode === "units"}
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
