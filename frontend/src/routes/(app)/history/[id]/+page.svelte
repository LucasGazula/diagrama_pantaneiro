<script lang="ts">
  import { onMount } from "svelte";
  import { page } from "$app/state";
  import { getAporte } from "$lib/api/aportes";
  import { privacyStore } from "$lib/stores/privacy";
  import { formatBrl, formatQty } from "$lib/format";
  import type { AporteEventOut } from "$lib/types/api";

  let eventId = $derived(page.params.id);

  let event = $state<AporteEventOut | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);

  onMount(async () => {
    if (!eventId) return;
    try {
      event = await getAporte(eventId);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  });

  const CLASS_LABELS: Record<string, string> = {
    acoes_nacionais: "Ações Nacionais",
    acoes_internacionais: "Ações Internacionais",
    fundos_imobiliarios: "Fundos Imobiliários",
    reits: "REITs",
    criptomoedas: "Criptomoedas",
    rendafixa: "Renda Fixa",
    rendafixa_internacional: "Renda Fixa Internacional",
  };

  let masked = $derived($privacyStore);
  let fmtBRL = $derived((v: number) => formatBrl(v, masked));
  let fmtQty = $derived((v: number, digits = 4) => formatQty(v, masked, digits));

  function fmtDate(iso: string): string {
    return new Date(iso).toLocaleString("pt-BR", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  }
</script>

<section class="responsive-page mx-auto mt-8 max-w-5xl p-6">
  <header class="page-header mb-6 flex items-center justify-between">
    <h1 class="text-2xl font-bold">Detalhe do aporte</h1>
    <a href="/history" class="text-sm text-slate-600 underline">← histórico</a>
  </header>

  {#if loading}
    <p class="text-slate-500">Carregando…</p>
  {:else if error}
    <p class="rounded bg-red-50 p-4 text-red-700">Erro: {error}</p>
  {:else if event}
    <div class="mb-4 rounded border border-slate-200 bg-white p-4">
      <p class="text-sm text-slate-600">{fmtDate(event.createdAt)}</p>
      <p class="mt-1 text-3xl font-bold">{fmtBRL(event.aporteValueBrl)}</p>
      <p class="mt-1 text-sm text-slate-500">
        {event.allocations.length} sugestões
        · {event.allocations.filter((a) => a.applied).length} aplicadas
      </p>
    </div>

    <!-- svelte-ignore a11y_no_noninteractive_tabindex (Scrollable region needs keyboard focus.) -->
    <div class="table-scroll rounded border border-slate-200 bg-white" role="region" aria-label="Detalhes do aporte, role para ver todas as colunas" tabindex="0">
      <table class="w-full text-sm">
        <thead class="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
          <tr>
            <th class="px-4 py-2">Ativo</th>
            <th class="px-4 py-2">Classe</th>
            <th class="px-4 py-2 text-right">Qtd. sugerida</th>
            <th class="px-4 py-2 text-right">BRL sugerido</th>
            <th class="px-4 py-2 text-right">Status</th>
          </tr>
        </thead>
        <tbody>
          {#each event.allocations as a (a.id)}
            <tr class="border-b border-slate-100 last:border-0" class:bg-emerald-50={a.applied}>
              <td class="px-4 py-2 font-medium">{a.positionNameSnapshot}</td>
              <td class="px-4 py-2 text-slate-600">
                {CLASS_LABELS[a.assetTypeSnapshot] ?? a.assetTypeSnapshot}
              </td>
              <td class="px-4 py-2 text-right tabular-nums">
                {a.trackingModeSnapshot === "balance" ? "—" : fmtQty(a.suggestedQuantity, a.assetTypeSnapshot === "criptomoedas" ? 8 : 4)}
              </td>
              <td class="px-4 py-2 text-right tabular-nums">
                {fmtBRL(a.suggestedValueBrl)}
              </td>
              <td class="px-4 py-2 text-right text-xs">
                {#if a.applied}
                  <span class="font-semibold uppercase text-emerald-700">
                    ✓ aplicado
                    {#if a.appliedValueBrl != null}
                      · {fmtBRL(a.appliedValueBrl)}
                    {/if}
                  </span>
                {:else}
                  <span class="text-slate-400">ignorado</span>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>
