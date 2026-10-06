<script lang="ts">
  import { onMount } from "svelte";
  import {
    createPreset,
    deletePreset,
    listPresets,
    updateTargets,
  } from "$lib/api/targets";
  import { CLASS_LABELS, CLASS_ORDER } from "$lib/classLabels";
  import type {
    PresetOut,
    TargetOut,
    TargetsUpdateBody,
  } from "$lib/types/api";

  interface Props {
    initialTargets: TargetOut[];
    onsaved: (updated: TargetOut[]) => void;
    onclose: () => void;
  }

  let { initialTargets, onsaved, onclose }: Props = $props();

  function seedValues(): Record<string, number> {
    const out: Record<string, number> = {};
    for (const c of CLASS_ORDER) out[c] = 0;
    for (const t of initialTargets) {
      out[t.assetType] = Math.round(t.targetPercentage);
    }
    return out;
  }

  let values = $state<Record<string, number>>(seedValues());
  let sum = $derived(CLASS_ORDER.reduce((s, c) => s + (values[c] ?? 0), 0));
  let sumOk = $derived(sum === 100);

  let saving = $state(false);
  let serverError = $state<string | null>(null);

  let presets = $state<PresetOut[]>([]);
  let presetsLoading = $state(true);

  let addingPreset = $state(false);
  let newName = $state("");
  let newError = $state<string | null>(null);

  let confirmRemoveId = $state<string | null>(null);
  let confirmTimer: ReturnType<typeof setTimeout> | null = null;

  onMount(() => {
    listPresets()
      .then((list) => {
        presets = list;
      })
      .catch(() => {
        presets = [];
      })
      .finally(() => {
        presetsLoading = false;
      });
  });

  function handleInput(cls: string, raw: string) {
    const n = Number(raw);
    if (!Number.isFinite(n)) return;
    values[cls] = Math.max(0, Math.min(100, Math.round(n)));
  }

  function applyPreset(p: PresetOut) {
    for (const c of CLASS_ORDER) {
      values[c] = Math.round(p.values[c] ?? 0);
    }
  }

  function startRemove(id: string) {
    if (confirmRemoveId === id) return;
    confirmRemoveId = id;
    if (confirmTimer) clearTimeout(confirmTimer);
    confirmTimer = setTimeout(() => {
      confirmRemoveId = null;
    }, 3000);
  }

  async function confirmRemove(id: string) {
    if (confirmTimer) clearTimeout(confirmTimer);
    confirmTimer = null;
    confirmRemoveId = null;
    try {
      await deletePreset(id);
      presets = presets.filter((p) => p.id !== id);
    } catch (e) {
      serverError = e instanceof Error ? e.message : String(e);
    }
  }

  async function saveNewPreset() {
    newError = null;
    if (!newName.trim()) {
      newError = "Nome obrigatório";
      return;
    }
    try {
      const created = await createPreset({
        name: newName.trim(),
        values: { ...values },
      });
      presets = [...presets, created];
      newName = "";
      addingPreset = false;
    } catch (e) {
      newError = e instanceof Error ? e.message : String(e);
    }
  }

  async function save() {
    if (!sumOk) return;
    saving = true;
    serverError = null;
    const body: TargetsUpdateBody = {
      targets: CLASS_ORDER.map((c) => ({
        assetType: c,
        targetPercentage: values[c],
      })),
    };
    try {
      const updated = await updateTargets(body);
      onsaved(updated);
    } catch (e) {
      serverError = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }
</script>

<div
  class="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/50 p-4"
  role="presentation"
  onclick={(e) => {
    if (e.target === e.currentTarget) onclose();
  }}
>
  <div
    role="dialog"
    aria-modal="true"
    aria-labelledby="edit-targets-title"
    class="max-h-[calc(100dvh-2rem)] w-full max-w-md overflow-y-auto rounded bg-white p-5 shadow-xl"
  >
    <div class="mb-3 flex items-center justify-between">
      <h2 id="edit-targets-title" class="text-base font-semibold">Edit targets</h2>
      <button
        type="button"
        class="rounded px-2 py-1 text-slate-500 hover:bg-slate-100"
        aria-label="Close"
        onclick={onclose}
      >×</button>
    </div>

    <div class="mb-3">
      <div class="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Presets
      </div>
      {#if presetsLoading}
        <p class="text-sm text-slate-400">Carregando…</p>
      {:else}
        {#if presets.length === 0 && !addingPreset}
          <p class="mb-1 text-sm text-slate-400">
            Nenhum preset salvo.
          </p>
        {/if}
        <div class="flex flex-wrap items-center gap-1.5">
          {#each presets as p (p.id)}
            <div
              class="inline-flex items-center gap-1 rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-sm"
            >
              <button
                type="button"
                class="max-w-[10rem] truncate hover:underline"
                title={p.name}
                onclick={() => applyPreset(p)}
              >{p.name}</button>
              {#if confirmRemoveId === p.id}
                <button
                  type="button"
                  class="text-xs text-red-700 hover:underline"
                  onclick={() => confirmRemove(p.id)}
                >Remove?</button>
              {:else}
                <button
                  type="button"
                  class="text-slate-400 hover:text-red-600"
                  aria-label="Remove preset {p.name}"
                  onclick={() => startRemove(p.id)}
                >×</button>
              {/if}
            </div>
          {/each}
          {#if !addingPreset}
            <button
              type="button"
              class="rounded border border-dashed border-slate-300 px-2 py-0.5 text-sm text-slate-600 hover:bg-slate-50"
              onclick={() => { addingPreset = true; newError = null; }}
            >+ Novo</button>
          {/if}
        </div>
      {/if}

      {#if addingPreset}
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <input
            type="text"
            maxlength="48"
            placeholder="Nome do preset"
            bind:value={newName}
            class="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
          />
          <button
            type="button"
            class="rounded bg-slate-900 px-2 py-1 text-xs font-medium text-white disabled:bg-slate-300"
            disabled={!sumOk || !newName.trim()}
            title={!sumOk ? "Os valores precisam somar 100%" : ""}
            onclick={saveNewPreset}
          >Salvar</button>
          <button
            type="button"
            class="rounded px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
            onclick={() => { addingPreset = false; newName = ""; newError = null; }}
          >Cancelar</button>
        </div>
        {#if newError}
          <p class="mt-1 text-xs text-red-700">{newError}</p>
        {/if}
      {/if}
    </div>

    <hr class="my-3 border-slate-200" />

    <div class="space-y-2">
      {#each CLASS_ORDER as cls (cls)}
        <label class="flex items-center justify-between gap-3 text-sm">
          <span class="text-slate-700">{CLASS_LABELS[cls]}</span>
          <span class="flex items-center gap-1">
            <input
              type="number"
              min="0"
              max="100"
              step="1"
              inputmode="numeric"
              value={values[cls]}
              oninput={(e) => handleInput(cls, (e.currentTarget as HTMLInputElement).value)}
              class="w-16 rounded border border-slate-300 px-2 py-1 text-right tabular-nums"
              data-testid="target-input-{cls}"
            />
            <span class="text-slate-400">%</span>
          </span>
        </label>
      {/each}
    </div>

    <hr class="my-3 border-slate-200" />

    <div class="flex flex-wrap items-center justify-between gap-3">
      <p
        class="text-sm tabular-nums"
        class:text-emerald-600={sumOk}
        class:text-red-600={!sumOk}
        data-testid="total-indicator"
      >
        Total: {sum}% / 100%
      </p>
      <div class="flex gap-2">
        <button
          type="button"
          class="rounded bg-slate-200 px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-300"
          onclick={onclose}
        >Cancel</button>
        <button
          type="button"
          class="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:bg-slate-300"
          disabled={!sumOk || saving}
          onclick={save}
          data-testid="save-button"
        >{saving ? "Saving…" : "Save"}</button>
      </div>
    </div>

    {#if serverError}
      <p class="mt-2 rounded bg-red-50 px-2 py-1 text-xs text-red-700">{serverError}</p>
    {/if}
  </div>
</div>
