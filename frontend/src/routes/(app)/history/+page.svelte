<script lang="ts">
  import { onMount } from "svelte";
  import { listAportes } from "$lib/api/aportes";
  import { privacyStore } from "$lib/stores/privacy";
  import { formatBrl } from "$lib/format";
  import type { AporteEventOut } from "$lib/types/api";

  let events = $state<AporteEventOut[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      events = await listAportes();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  });

  let masked = $derived($privacyStore);
  let fmtBRL = $derived((v: number) => formatBrl(v, masked));

  function fmtDate(iso: string): string {
    return new Date(iso).toLocaleString("pt-BR", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  }

  function appliedCount(e: AporteEventOut): number {
    return e.allocations.filter((a) => a.applied).length;
  }

  function totalApplied(e: AporteEventOut): number {
    return e.allocations
      .filter((a) => a.applied)
      .reduce((s, a) => s + (a.appliedValueBrl ?? 0), 0);
  }
</script>

<section class="responsive-page mx-auto mt-8 max-w-5xl p-6">
  <header class="page-header mb-6 flex items-center justify-between">
    <h1 class="text-2xl font-bold">Histórico de aportes</h1>
    <a href="/home" class="text-sm text-slate-600 underline">← voltar</a>
  </header>

  {#if loading}
    <p class="text-slate-500">Carregando…</p>
  {:else if error}
    <p class="rounded bg-red-50 p-4 text-red-700">Erro: {error}</p>
  {:else if events.length === 0}
    <div class="rounded border border-slate-200 bg-white p-8 text-center">
      <p class="text-slate-600">Nenhum aporte ainda.</p>
      <a href="/aporte" class="mt-3 inline-block text-sm underline">
        Criar seu primeiro aporte →
      </a>
    </div>
  {:else}
    <!-- svelte-ignore a11y_no_noninteractive_tabindex (Scrollable region needs keyboard focus.) -->
    <div class="table-scroll rounded border border-slate-200 bg-white" role="region" aria-label="Histórico de aportes, role para ver todas as colunas" tabindex="0">
      <table class="w-full text-sm">
        <thead class="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
          <tr>
            <th class="px-4 py-2">Quando</th>
            <th class="px-4 py-2 text-right">Valor</th>
            <th class="px-4 py-2 text-right">Sugestões</th>
            <th class="px-4 py-2 text-right">Aplicado</th>
            <th class="px-4 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {#each events as e (e.id)}
            {@const applied = appliedCount(e)}
            {@const total = e.allocations.length}
            <tr class="border-b border-slate-100 last:border-0">
              <td class="px-4 py-2">{fmtDate(e.createdAt)}</td>
              <td class="px-4 py-2 text-right tabular-nums font-semibold">
                {fmtBRL(e.aporteValueBrl)}
              </td>
              <td class="px-4 py-2 text-right tabular-nums text-slate-600">
                {total}
              </td>
              <td
                class="px-4 py-2 text-right tabular-nums"
                class:text-emerald-700={applied > 0}
                class:text-slate-400={applied === 0}
              >
                {applied}/{total}{#if applied > 0}
                  · {fmtBRL(totalApplied(e))}{/if}
              </td>
              <td class="px-4 py-2 text-right">
                <a
                  href="/history/{e.id}"
                  class="text-sm text-slate-600 underline hover:text-slate-900"
                >
                  detalhes →
                </a>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>
