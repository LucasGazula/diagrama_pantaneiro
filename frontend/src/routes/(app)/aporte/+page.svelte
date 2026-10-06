<script lang="ts">
  import { onMount } from "svelte";
  import { createAporte, applyAllocation, excludeAllocation } from "$lib/api/aportes";
  import { listPositions } from "$lib/api/positions";
  import { CLASS_LABELS, CLASS_ORDER } from "$lib/classLabels";
  import { privacyStore } from "$lib/stores/privacy";
  import { formatBrl, formatQty } from "$lib/format";
  import type { AporteEventOut, PositionOut } from "$lib/types/api";

  // Paleta pantaneira — espelha /home donut.
  const CLASS_COLOR: Record<string, string> = {
    acoes_nacionais: "#e8822c",
    acoes_internacionais: "#b85a1d",
    fundos_imobiliarios: "#d9b86a",
    reits: "#8a6a2e",
    criptomoedas: "#4fa8b8",
    rendafixa: "#7eb360",
    rendafixa_internacional: "#3e6b48",
  };
  const CLASS_ABBR: Record<string, string> = {
    acoes_nacionais: "ACN",
    acoes_internacionais: "ACI",
    fundos_imobiliarios: "FII",
    reits: "REI",
    criptomoedas: "CRY",
    rendafixa: "RF",
    rendafixa_internacional: "RFI",
  };

  let amountInput = $state("500");
  let event = $state<AporteEventOut | null>(null);
  let positions = $state<PositionOut[]>([]);
  let calculating = $state(false);
  let applyingId = $state<string | null>(null);
  let excludingId = $state<string | null>(null);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      positions = await listPositions();
    } catch {
      // non-fatal; page still works without enrichment
    }
  });

  let masked = $derived($privacyStore);
  let fmtBRL = $derived((v: number) => formatBrl(v, masked));
  let fmtQty = $derived((v: number, digits = 6) => formatQty(v, masked, digits));

  async function handleCalcular(e: SubmitEvent) {
    e.preventDefault();
    const value = Number(amountInput);
    if (!Number.isFinite(value) || value <= 0) {
      error = "Informe valor positivo para aporte";
      return;
    }
    error = null;
    calculating = true;
    try {
      event = await createAporte(value);
      // Refresh positions so "current value" reflects any prior Aportar clicks.
      positions = await listPositions();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      calculating = false;
    }
  }

  async function handleAportar(allocationId: string) {
    if (!event) return;
    applyingId = allocationId;
    error = null;
    try {
      const updated = await applyAllocation(event.id, allocationId);
      event = {
        ...event,
        allocations: event.allocations.map((a) =>
          a.id === allocationId ? { ...a, ...updated } : a,
        ),
      };
      positions = await listPositions();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      applyingId = null;
    }
  }


  async function handleExclude(allocationId: string) {
    if (!event) return;
    excludingId = allocationId;
    error = null;
    try {
      event = await excludeAllocation(event.id, allocationId);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      excludingId = null;
    }
  }
  let totalSuggested = $derived(
    event ? event.allocations.filter((a) => !a.excluded).reduce((s, a) => s + a.suggestedValueBrl, 0) : 0,
  );
  let totalApplied = $derived(
    event
      ? event.allocations
          .filter((a) => a.applied)
          .reduce((s, a) => s + (a.appliedValueBrl ?? 0), 0)
      : 0,
  );
  let portfolioTotal = $derived(
    positions.reduce((s, p) => s + p.currentValueBrl, 0),
  );

  type EnrichedRow = {
    id: string;
    positionId: string | null;
    name: string;
    assetType: string;
    strength: number | null;
    currentValueBrl: number | null;
    priceAtAporteBrl: number | null;
    suggestedQuantity: number;
    trackingMode: "balance" | "units";
    suggestedValueBrl: number;
    totalAfterPct: number | null;
    applied: boolean;
    appliedValueBrl: number | null;
    excluded: boolean;
  };

  let rows = $derived<EnrichedRow[]>(
    event
      ? event.allocations
          .map((a) => {
            const pos = positions.find((p) => p.id === a.positionId);
            const newTotal = portfolioTotal + Math.max(0, (event?.aporteValueBrl ?? 0) - totalApplied);
            const currentValue = pos?.currentValueBrl ?? null;
            const totalAfterPct =
              pos && newTotal > 0
                ? ((pos.currentValueBrl + (a.applied || a.excluded ? 0 : a.suggestedValueBrl)) / newTotal) * 100
                : null;
            return {
              id: a.id,
              positionId: a.positionId,
              name: a.positionNameSnapshot,
              assetType: a.assetTypeSnapshot,
              strength: pos?.strength ?? null,
              currentValueBrl: currentValue,
              priceAtAporteBrl: a.priceAtAporteBrl,
              suggestedQuantity: a.suggestedQuantity,
              trackingMode: a.trackingModeSnapshot ?? (a.priceAtAporteBrl == null ? "balance" : "units"),
              suggestedValueBrl: a.suggestedValueBrl,
              totalAfterPct,
              applied: a.applied,
              appliedValueBrl: a.appliedValueBrl,
              excluded: a.excluded,
            };
          })
          .sort((a, b) => (a.excluded === b.excluded ? b.suggestedValueBrl - a.suggestedValueBrl : a.excluded ? 1 : -1))
      : [],
  );

  // Donut segments: per-class share of the aporte. All 7 classes always in the
  // legend (0% for those receiving nothing) — mirrors AUVP's complete overview.
  type Segment = { assetType: string; label: string; pct: number; color: string; offset: number };

  let classSuggested = $derived.by(() => {
    const out: Record<string, number> = {};
    for (const c of CLASS_ORDER) out[c] = 0;
    if (event) {
      for (const a of event.allocations) {
        if (a.excluded) continue;
        out[a.assetTypeSnapshot] = (out[a.assetTypeSnapshot] ?? 0) + a.suggestedValueBrl;
      }
    }
    return out;
  });

  let donutSegments = $derived.by<Segment[]>(() => {
    const aporte = event?.aporteValueBrl ?? 0;
    if (aporte <= 0) return [];
    const entries = CLASS_ORDER
      .map((c) => [c, (classSuggested[c] ?? 0) / aporte * 100] as const)
      .filter(([, pct]) => pct > 0.01)
      .sort((a, b) => b[1] - a[1]);
    const segs: Segment[] = [];
    let cursor = 0;
    for (const [assetType, pct] of entries) {
      segs.push({
        assetType,
        label: CLASS_ABBR[assetType] ?? assetType.slice(0, 3).toUpperCase(),
        pct,
        color: CLASS_COLOR[assetType] ?? "#6b7480",
        offset: cursor,
      });
      cursor += pct;
    }
    return segs;
  });

  const RADIUS = 38;
  const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
</script>

<section class="responsive-page mx-auto mt-8 max-w-5xl p-6">
  <header class="page-header mb-6 flex items-center justify-between">
    <h1 class="text-2xl font-bold">Novo aporte</h1>
    <a
      href="/home"
      class="text-sm text-slate-600 underline hover:text-slate-900"
    >
      ← voltar à carteira
    </a>
  </header>

  <form onsubmit={handleCalcular} class="mb-6 flex flex-col items-stretch gap-3 sm:flex-row sm:items-end">
    <label class="min-w-0 flex-1 sm:max-w-xs">
      <span class="text-sm text-slate-700">Valor do aporte (R$)</span>
      <input
        type="number"
        step="0.01"
        min="0"
        required
        bind:value={amountInput}
        class="mt-1 block w-full rounded border-slate-300 px-3 py-2"
      />
    </label>
    <button
      type="submit"
      disabled={calculating || applyingId !== null || excludingId !== null}
      class="rounded bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-50"
    >
      {calculating ? "Calculando…" : "Calcular"}
    </button>
  </form>

  {#if error}
    <p class="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>
  {/if}

  {#if event}
    <!-- Summary line -->
    <div class="mb-4 flex flex-wrap gap-6 text-sm text-slate-600">
      <div>
        <span class="text-xs uppercase tracking-wide text-slate-500">Aporte</span>
        <p class="text-lg font-bold text-slate-900">{fmtBRL(event.aporteValueBrl)}</p>
      </div>
      <div>
        <span class="text-xs uppercase tracking-wide text-slate-500">Total sugerido</span>
        <p class="text-lg font-bold text-slate-900">{fmtBRL(totalSuggested)}</p>
      </div>
      {#if totalApplied > 0}
        <div>
          <span class="text-xs uppercase tracking-wide text-slate-500">Aplicado</span>
          <p class="text-lg font-bold text-emerald-700">{fmtBRL(totalApplied)}</p>
        </div>
      {/if}
      {#if event.aporteValueBrl - totalSuggested > 0.01}
        {@const freed = event.aporteValueBrl - totalSuggested}
        <div>
          <span class="text-xs uppercase tracking-wide text-slate-500">Saldo disponível</span>
          <p class="text-lg font-bold text-amber-600">{fmtBRL(freed)}</p>
        </div>
      {/if}
    </div>

    <!-- Distribution donut + legend -->
    <div class="mb-6 rounded border border-slate-200 bg-white p-5">
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Distribuição do aporte
      </h2>
      <div class="flex flex-col items-start gap-6 sm:flex-row sm:flex-wrap sm:items-center">
        <div class="relative h-48 w-48 shrink-0">
          <svg viewBox="0 0 100 100" class="h-full w-full">
            {#each donutSegments as s (s.assetType)}
              {@const len = (s.pct / 100) * CIRCUMFERENCE}
              {@const dashOffset = -((s.offset / 100) * CIRCUMFERENCE)}
              <circle
                cx="50"
                cy="50"
                r={RADIUS}
                fill="none"
                stroke={s.color}
                stroke-width="12"
                stroke-dasharray="{len} {CIRCUMFERENCE - len}"
                stroke-dashoffset={dashOffset}
                transform="rotate(-90 50 50)"
              />
            {/each}
            <text
              x="50"
              y="48"
              text-anchor="middle"
              class="text-[4px] uppercase tracking-wide"
              style="fill: var(--ink-muted)"
            >aporte</text>
            <text
              x="50"
              y="58"
              text-anchor="middle"
              class="text-[7px] font-bold"
              style="fill: var(--accent)"
            >{fmtBRL(event.aporteValueBrl)}</text>
          </svg>
        </div>
        <ul class="flex min-w-0 flex-1 flex-wrap gap-x-6 gap-y-1 text-sm">
          {#each CLASS_ORDER as cls (cls)}
            {@const pct = event.aporteValueBrl > 0 ? (classSuggested[cls] / event.aporteValueBrl) * 100 : 0}
            <li class="flex items-center gap-2">
              <span
                class="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                style="background: {CLASS_COLOR[cls]}"
              ></span>
              <span class:text-slate-500={pct === 0}>
                {CLASS_LABELS[cls]}
                <span class="tabular-nums text-slate-500">({pct.toFixed(pct < 1 && pct > 0 ? 2 : 0)}%)</span>
              </span>
            </li>
          {/each}
        </ul>
      </div>
    </div>

    <!-- Suggestions table -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex (Scrollable region needs keyboard focus.) -->
    <div class="table-scroll rounded border border-slate-200 bg-white" role="region" aria-label="Sugestões de aporte, role para ver todas as colunas" tabindex="0">
      <table class="w-full text-sm">
        <thead class="border-b border-slate-200 text-left text-xs uppercase text-slate-500">
          <tr>
            <th class="px-3 py-2">Tipo</th>
            <th class="px-3 py-2">Ticker</th>
            <th class="px-3 py-2 text-right">Atual ($)</th>
            <th class="px-3 py-2 text-right">Preço atual ($)</th>
            <th class="px-3 py-2 text-right">Nota</th>
            <th class="px-3 py-2 text-right">Total após aporte</th>
            <th class="px-3 py-2 text-right">Sugest. ($)</th>
            <th class="px-3 py-2 text-right">Sugest. (un)</th>
            <th class="px-3 py-2 text-right">Aportar!</th>
            <th class="w-10"></th>
          </tr>
        </thead>
        <tbody>
          {#each rows as r (r.id)}
            <tr class="border-b border-slate-100 last:border-0" class:opacity-60={r.applied} class:opacity-40={r.excluded}>
              <td class="px-3 py-2">
                <span
                  class="inline-block px-2 py-0.5 text-[11px] font-semibold"
                  style="background: {CLASS_COLOR[r.assetType]}1a; color: {CLASS_COLOR[r.assetType]}; border: 1px solid {CLASS_COLOR[r.assetType]}66"
                >
                  {CLASS_LABELS[r.assetType] ?? r.assetType}
                </span>
              </td>
              <td class="px-3 py-2 font-medium" class:line-through={r.excluded}>{r.name}</td>
              <td class="px-3 py-2 text-right tabular-nums text-slate-600">
                {r.currentValueBrl !== null ? fmtBRL(r.currentValueBrl) : "—"}
              </td>
              <td class="px-3 py-2 text-right tabular-nums text-slate-600">
                {r.priceAtAporteBrl !== null ? fmtBRL(r.priceAtAporteBrl) : "—"}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {#if r.strength !== null}
                  <span
                    class:text-emerald-700={r.strength > 0}
                    class:text-red-700={r.strength < 0}
                    class:text-slate-500={r.strength === 0}
                  >{r.strength > 0 ? "+" : ""}{r.strength}</span>
                {:else}—{/if}
              </td>
              <td class="px-3 py-2 text-right tabular-nums text-slate-600">
                {r.totalAfterPct !== null ? `${r.totalAfterPct.toFixed(2)}%` : "—"}
              </td>
              <td class="px-3 py-2 text-right tabular-nums font-semibold">
                {fmtBRL(r.suggestedValueBrl)}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {r.trackingMode === "balance" ? "—" : fmtQty(r.suggestedQuantity, r.assetType === "criptomoedas" ? 8 : 4)}
              </td>
              <td class="px-3 py-2 text-right">
                {#if r.applied}
                  <span class="text-xs font-semibold uppercase text-emerald-700">
                    ✓ aplicado
                  </span>
                {:else}
                  <button
                    onclick={() => handleAportar(r.id)}
                    disabled={calculating || applyingId !== null || excludingId !== null || r.excluded || r.suggestedValueBrl <= 0}
                    class="rounded bg-slate-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                  >
                    {applyingId === r.id ? "Aportando…" : "$ Aportar"}
                  </button>
                {/if}
              </td>
              <td class="px-3 py-2 text-right">
                {#if r.applied || r.excluded}
                  <!-- no action -->
                {:else}
                  <button
                    onclick={() => handleExclude(r.id)}
                    disabled={calculating || applyingId !== null || excludingId !== null}
                    title="Excluir e recalcular respeitando metas"
                      aria-label={`Excluir ${r.name} e recalcular aporte`}
                    class="rounded px-2 py-1 text-xs text-red-500 hover:bg-red-50 hover:text-red-700 disabled:opacity-50"
                  >
                    ✕
                  </button>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <p class="text-slate-500">
      Informe o valor do aporte e clique em Calcular para ver onde alocar o dinheiro.
    </p>
  {/if}
</section>
