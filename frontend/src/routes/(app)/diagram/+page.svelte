<script lang="ts">
  import { onMount } from "svelte";
  import {
    listDiagramQuestions,
    createDiagramQuestion,
    updateDiagramQuestion,
    deleteDiagramQuestion,
  } from "$lib/api/diagram";
  import type { DiagramQuestionOut } from "$lib/types/api";

  let questions = $state<DiagramQuestionOut[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let busyId = $state<string | null>(null);

  // Editing state: which question is being edited + its draft values
  let editingId = $state<string | null>(null);
  let editCriterias = $state("");
  let editText = $state("");

  // Add-form state per diagram
  let addingFor = $state<string | null>(null);
  let newCriterias = $state("");
  let newText = $state("");

  async function load() {
    loading = true;
    error = null;
    try {
      questions = await listDiagramQuestions();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  onMount(load);

  let cerrado = $derived(
    questions.filter((q) => q.diagramType === "diagrama-do-cerrado"),
  );
  let imobiliarios = $derived(
    questions.filter((q) => q.diagramType === "investimentos-imobiliarios"),
  );

  function startEdit(q: DiagramQuestionOut) {
    editingId = q.id;
    editCriterias = q.criterias;
    editText = q.questionText;
  }

  function cancelEdit() {
    editingId = null;
  }

  async function saveEdit(id: string) {
    busyId = id;
    error = null;
    try {
      await updateDiagramQuestion(id, {
        criterias: editCriterias,
        questionText: editText,
      });
      editingId = null;
      await load();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busyId = null;
    }
  }

  async function remove(q: DiagramQuestionOut) {
    if (
      !confirm(
        `Deletar "${q.criterias || q.questionText}"?\n\n` +
          `Isso rebalanceia a força de todas as ações: N diminui em 1 e qualquer ` +
          `resposta "sim" para esta pergunta é removida. Esta ação não pode ser desfeita.`,
      )
    )
      return;
    busyId = q.id;
    error = null;
    try {
      await deleteDiagramQuestion(q.id);
      await load();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busyId = null;
    }
  }

  function startAdd(diagramType: string) {
    addingFor = diagramType;
    newCriterias = "";
    newText = "";
  }

  function cancelAdd() {
    addingFor = null;
  }

  async function submitAdd(diagramType: string) {
    if (!newText.trim()) {
      error = "O texto da pergunta é obrigatório";
      return;
    }
    busyId = "new";
    error = null;
    try {
      await createDiagramQuestion({
        diagramType,
        criterias: newCriterias,
        questionText: newText,
      });
      addingFor = null;
      await load();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busyId = null;
    }
  }
</script>

<section class="responsive-page mx-auto mt-8 max-w-5xl p-6">
  <header class="page-header mb-6 flex items-center justify-between">
    <div>
      <h1 class="text-2xl font-bold">Diagrama — critérios de pontuação</h1>
      <p class="text-sm text-slate-600">
        Força =
        <code class="rounded bg-slate-100 px-1">2 × sim − N</code>.
        Adicionar ou deletar uma pergunta recalcula a força de todas as ações.
      </p>
    </div>
    <a href="/home" class="text-sm text-slate-600 underline">← voltar</a>
  </header>

  {#if error}
    <p class="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">Erro: {error}</p>
  {/if}

  {#if loading}
    <p class="text-slate-500">Carregando…</p>
  {:else}
    <div class="grid gap-6 md:grid-cols-2">
      {#each [{ type: "diagrama-do-cerrado", label: "Diagrama Pantaneiro", subtitle: "Ações nacionais + internacionais", list: cerrado }, { type: "investimentos-imobiliarios", label: "Investimentos Imobiliários", subtitle: "FIIs + REITs", list: imobiliarios }] as bank (bank.type)}
        <div class="rounded border border-slate-200 bg-white p-4">
          <div class="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500">
                {bank.label}
              </h2>
              <p class="text-xs text-slate-500">
                {bank.subtitle} · {bank.list.length} perguntas
              </p>
            </div>
            {#if addingFor !== bank.type}
              <button
                onclick={() => startAdd(bank.type)}
                class="rounded bg-slate-900 px-2 py-1 text-xs font-medium text-white hover:bg-slate-700"
              >
                + Adicionar
              </button>
            {/if}
          </div>

          <ol class="list-decimal space-y-2 pl-5 text-sm">
            {#each bank.list as q (q.id)}
              <li>
                {#if editingId === q.id}
                  <div class="space-y-2">
                    <input
                      type="text"
                      bind:value={editCriterias}
                      placeholder="Rótulo curto (ex: ROE)"
                      class="block w-full rounded border-slate-300 px-2 py-1 text-sm"
                    />
                    <textarea
                      bind:value={editText}
                      rows="2"
                      placeholder="Pergunta completa"
                      class="block w-full rounded border-slate-300 px-2 py-1 text-sm"
                    ></textarea>
                    <div class="flex gap-2">
                      <button
                        type="button"
                        disabled={busyId === q.id}
                        onclick={() => saveEdit(q.id)}
                        class="rounded bg-slate-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
                      >
                        Salvar
                      </button>
                      <button
                        type="button"
                        onclick={cancelEdit}
                        class="rounded bg-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-300"
                      >
                        Cancelar
                      </button>
                    </div>
                  </div>
                {:else}
                  <div class="flex items-start justify-between gap-2">
                    <span class="flex-1">
                      {#if q.criterias}<strong>{q.criterias}</strong>{/if}
                      {#if q.questionText && q.questionText !== q.criterias}
                        <span class="text-slate-600">
                          {q.criterias ? " — " : ""}{q.questionText}
                        </span>
                      {/if}
                    </span>
                    <span class="flex shrink-0 gap-1">
                      <button
                        type="button"
                        onclick={() => startEdit(q)}
                        class="text-xs text-slate-600 underline hover:text-slate-900"
                        title="Editar"
                      >
                        editar
                      </button>
                      <button
                        type="button"
                        disabled={busyId === q.id}
                        onclick={() => remove(q)}
                        class="text-xs text-red-600 underline hover:text-red-800 disabled:opacity-50"
                        title="Deletar"
                      >
                        deletar
                      </button>
                    </span>
                  </div>
                {/if}
              </li>
            {/each}
          </ol>

          {#if addingFor === bank.type}
            <div class="mt-3 space-y-2 rounded bg-slate-50 p-3">
              <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Adicionar pergunta
              </p>
              <input
                type="text"
                bind:value={newCriterias}
                placeholder="Rótulo curto (opcional, ex: P/L)"
                class="block w-full rounded border-slate-300 px-2 py-1 text-sm"
              />
              <textarea
                bind:value={newText}
                rows="2"
                placeholder="Full question"
                class="block w-full rounded border-slate-300 px-2 py-1 text-sm"
              ></textarea>
              <div class="flex gap-2">
                <button
                  type="button"
                  disabled={busyId === "new"}
                  onclick={() => submitAdd(bank.type)}
                  class="rounded bg-slate-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
                >
                  {busyId === "new" ? "Adicionando…" : "Adicionar"}
                </button>
                <button
                  type="button"
                  onclick={cancelAdd}
                  class="rounded bg-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-300"
                >
                  Cancelar
                </button>
              </div>
            </div>
          {/if}
        </div>
      {/each}
    </div>

    <p class="mt-6 text-sm text-slate-500">
      Atenção: adicionar ou deletar perguntas desloca a força de todas as ações —
      confira o painel/posições após edições em massa.
    </p>
  {/if}
</section>
