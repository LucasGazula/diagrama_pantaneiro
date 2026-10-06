<script lang="ts">
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import { onMount } from "svelte";
  import {
    listPositions,
    updatePosition,
    deletePosition,
  } from "$lib/api/positions";
  import DiagramChecklist from "$lib/components/DiagramChecklist.svelte";
  import AutocompleteInput from "$lib/components/AutocompleteInput.svelte";
  import type { CandidateOut } from "$lib/types/api";
  import type { PositionOut } from "$lib/types/api";

  let positionId = $derived(page.params.id);

  let position = $state<PositionOut | null>(null);
  let trackingMode = $state<"balance" | "units">("units");
  let amountInput = $state("");
  let name = $state("");
  let externalId = $state<string | null>(null);
  let currentPriceInput = $state("");
  let strengthInput = $state("");
  let diagramResponses = $state<string[]>([]);
  let submitting = $state(false);
  let deleting = $state(false);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      const all = await listPositions();
      const p = all.find((x) => x.id === positionId);
      if (!p) {
        error = "posição não encontrada";
        return;
      }
      position = p;
      name = p.name;
      externalId = p.externalId ?? null;
      trackingMode = p.trackingMode ?? (p.currentPrice == null ? "balance" : "units");
      amountInput = String(p.amount);
      currentPriceInput = p.currentPrice != null ? String(p.currentPrice) : "";
      strengthInput = String(p.strength);
      diagramResponses = p.diagramResponses ?? [];
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });

  let isRF = $derived(
    position?.assetType === "rendafixa" ||
      position?.assetType === "rendafixa_internacional",
  );
  let hasDiagram = $derived(
    position?.assetType === "acoes_nacionais" ||
      position?.assetType === "acoes_internacionais" ||
      position?.assetType === "fundos_imobiliarios" ||
      position?.assetType === "reits",
  );
  let originalMode = $derived(position?.trackingMode ?? (position?.currentPrice == null ? "balance" : "units"));
  let rfHasPrice = $derived(
    isRF && trackingMode === "units",
  );

  function selectTitle(c: CandidateOut) {
    name = c.name;
    externalId = c.externalId ?? null;
    if (c.currentPriceBrl != null) currentPriceInput = String(c.currentPriceBrl);
  }

  async function handleSave(e: SubmitEvent) {
    e.preventDefault();
    if (!position) return;
    submitting = true;
    error = null;
    try {
      // RF: price optional (blank means private RF tracked in BRL).
      // Non-RF: price required.
      let currentPrice: number | null;
      if (isRF) {
        currentPrice =
          currentPriceInput !== "" && Number(currentPriceInput) > 0
            ? Number(currentPriceInput)
            : null;
      } else {
        currentPrice = Number(currentPriceInput);
      }
      const body: {
        amount?: number;
        name?: string;
        externalId?: string | null;
        trackingMode: "balance" | "units";
        currentPrice: number | null;
        strength?: number;
        diagramResponses?: string[] | null;
      } = {
        ...(trackingMode === (position.trackingMode ?? (position.currentPrice == null ? "balance" : "units"))
          ? { amount: Number(amountInput) } : {}),
        trackingMode,
        currentPrice,
        ...(position.assetType === "rendafixa" ? { name, externalId } : {}),
      };
      if (hasDiagram) {
        body.diagramResponses = diagramResponses;
        // strength omitted on purpose — backend recomputes
      } else {
        body.strength = parseInt(strengthInput, 10);
      }
      await updatePosition(position.id, body);
      await goto("/home");
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      submitting = false;
    }
  }

  async function handleDelete() {
    if (!position) return;
    if (!confirm(`Deletar ${position.name}? Esta ação não pode ser desfeita.`)) return;
    deleting = true;
    error = null;
    try {
      await deletePosition(position.id);
      await goto("/home");
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
      deleting = false;
    }
  }
</script>

<section class="responsive-page mx-auto mt-8 max-w-2xl p-6">
  <header class="page-header mb-6 flex items-center justify-between">
    <h1 class="text-2xl font-bold">
      {position ? `Editar ${position.name}` : "Carregando…"}
    </h1>
    <a href="/home" class="text-sm text-slate-600 underline">← voltar</a>
  </header>

  {#if error}
    <p class="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>
  {/if}

  {#if position}
    <form onsubmit={handleSave} class="space-y-4">
      <div class="rounded bg-slate-50 p-3 text-sm text-slate-600">
        <p>
          <strong>{position.name}</strong> · {position.assetType} · origem: {position.source}
        </p>
      </div>

      {#if position.assetType === "rendafixa"}
        <label class="block">
          <span class="text-sm text-slate-700">Título / nome da posição</span>
          <AutocompleteInput value={name} assetType={position.assetType} placeholder="Tesouro IPCA+ 2035"
            oninput={(v) => { name = v; externalId = null; }} onselect={selectTitle} />
          <span class="text-xs text-slate-500">Selecione título completo para corrigir ano ou variante com juros semestrais.</span>
        </label>
      {/if}

      {#if isRF}
        <label class="block">
          <span class="text-sm text-slate-700">Acompanhamento</span>
          <select bind:value={trackingMode} class="mt-1 block w-full rounded border-slate-300 px-3 py-2">
            <option value="balance">Saldo manual em reais</option>
            <option value="units">Quantidade de títulos × preço da unidade</option>
          </select>
        </label>
        {#if trackingMode !== originalMode}
          <p class="text-sm text-slate-600">Salvar converte saldo atual usando preço da unidade. Depois, edite quantidade ou saldo.</p>
        {/if}
      {/if}

      <label class="block">
        <span class="text-sm text-slate-700">
          {#if isRF}
            {rfHasPrice ? "Quantidade (unidades)" : "Valor (R$)"}
          {:else}
            Quantidade
          {/if}
        </span>
        <input
          type="number"
          step="any"
          required
          disabled={trackingMode !== originalMode}
          bind:value={amountInput}
          class="mt-1 block w-full rounded border-slate-300 px-3 py-2"
        />
      </label>

      <label class="block">
        <span class="text-sm text-slate-700">
          Preço atual
          {#if isRF}
            <span class="text-xs text-slate-500">— opcional no saldo manual; não muda acompanhamento</span>
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
          assetType={position.assetType}
          responses={diagramResponses}
          onchange={(ids) => (diagramResponses = ids)}
        />
      {:else}
        <label class="block">
          <span class="text-sm text-slate-700">
            Força (manual — sem diagrama para esta classe)
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

      <div class="form-actions flex justify-between">
        <div class="flex gap-2">
          <button
            type="submit"
            disabled={submitting || deleting}
            class="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-50"
          >
            {submitting ? "Salvando…" : "Salvar"}
          </button>
          <a
            href="/home"
            class="rounded bg-slate-200 px-4 py-2 font-medium text-slate-800 hover:bg-slate-300"
          >
            Cancelar
          </a>
        </div>
        <button
          type="button"
          onclick={handleDelete}
          disabled={submitting || deleting}
          class="rounded bg-red-600 px-4 py-2 font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          {deleting ? "Deletando…" : "Deletar"}
        </button>
      </div>
    </form>
  {/if}
</section>
