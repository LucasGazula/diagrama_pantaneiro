<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import {
    listPortfolios,
    createPortfolio,
    renamePortfolio,
    deletePortfolio,
  } from "$lib/api/portfolios";
  import { portfolioStore } from "$lib/stores/portfolio";
  import type { PortfolioOut } from "$lib/types/api";

  let portfolios = $state<PortfolioOut[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);

  let newName = $state("");
  let creating = $state(false);

  let editingId = $state<string | null>(null);
  let editingName = $state("");

  let deletingId = $state<string | null>(null);

  async function reload() {
    const list = await listPortfolios();
    portfolios = list;
    portfolioStore.setAll(list);
  }

  onMount(async () => {
    try {
      await reload();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  });

  async function handleCreate(e: SubmitEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    creating = true;
    error = null;
    try {
      await createPortfolio(name);
      newName = "";
      await reload();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      creating = false;
    }
  }

  function beginEdit(p: PortfolioOut) {
    editingId = p.id;
    editingName = p.name;
  }

  async function commitRename(id: string) {
    const name = editingName.trim();
    if (!name) {
      editingId = null;
      return;
    }
    error = null;
    try {
      await renamePortfolio(id, name);
      editingId = null;
      await reload();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function handleDelete(p: PortfolioOut) {
    if (portfolios.length <= 1) return;
    const ok = confirm(
      `Deletar "${p.name}"? Todas as posições, targets e histórico desta carteira serão perdidos. Esta ação não pode ser desfeita.`,
    );
    if (!ok) return;
    deletingId = p.id;
    error = null;
    try {
      await deletePortfolio(p.id);
      // If the deleted one was active, the store auto-heals on setAll().
      await reload();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      deletingId = null;
    }
  }
</script>

<section class="wrap">
  <div class="topbar">
    <div class="brand">
      <img src="/logo.png" alt="diagrama_pantaneiro" class="brand-logo" />
      <span class="prompt">$</span>
      <span class="brand-name">diagrama_pantaneiro</span>
      <span class="sep">//</span>
      <span class="title">gerenciar carteiras</span>
    </div>
    <nav class="nav">
      <a class="btn" href="/home">› voltar</a>
    </nav>
  </div>

  <div class="panel">
    <div class="corner-bracket bracket-tl"></div>
    <div class="corner-bracket bracket-tr"></div>
    <div class="corner-bracket bracket-bl"></div>
    <div class="corner-bracket bracket-br"></div>

    <header class="panel-head">
      <h2>── carteiras ──</h2>
      <span class="count">{portfolios.length} total</span>
    </header>

    {#if error}
      <p class="err">› erro: {error}</p>
    {/if}

    {#if loading}
      <p class="loading">carregando…</p>
    {:else}
      <ul class="list">
        {#each portfolios as p (p.id)}
          <li class="row">
            <span class="mark">›</span>
            {#if editingId === p.id}
              <input
                class="input-inline"
                type="text"
                bind:value={editingName}
                onblur={() => commitRename(p.id)}
                onkeydown={(e) => {
                  if (e.key === "Enter") commitRename(p.id);
                  if (e.key === "Escape") (editingId = null);
                }}
                autofocus
              />
            {:else}
              <button
                type="button"
                class="row-name"
                onclick={() => beginEdit(p)}
                title="Clique para renomear"
              >
                {p.name}
              </button>
            {/if}
            {#if p.isDefault}
              <span class="tag">padrão</span>
            {/if}
            <span class="row-date">
              {new Date(p.createdAt).toLocaleDateString("pt-BR")}
            </span>
            <button
              type="button"
              class="btn btn-danger"
              onclick={() => handleDelete(p)}
              disabled={portfolios.length <= 1 || deletingId === p.id}
              title={portfolios.length <= 1
                ? "não é possível deletar a última carteira"
                : "deletar carteira"}
            >
              {deletingId === p.id ? "deletando…" : "× deletar"}
            </button>
          </li>
        {/each}
      </ul>
    {/if}

    <div class="divider">┼─────────────────────────────────</div>

    <form class="new-form" onsubmit={handleCreate}>
      <span class="mark">+</span>
      <input
        type="text"
        class="input-inline grow"
        placeholder="nome da nova carteira (ex: carteira do meu pai)"
        bind:value={newName}
        maxlength="64"
        required
      />
      <button
        type="submit"
        class="btn btn-accent"
        disabled={creating || newName.trim().length === 0}
      >
        {creating ? "criando…" : "› criar"}
      </button>
    </form>
  </div>
</section>

<style>
  .wrap {
    max-width: 900px;
    margin: 0 auto;
    padding: 32px 28px 96px;
    color: var(--ink);
  }
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    padding: 10px 14px;
    border: 1px solid var(--hairline);
    background: var(--surface);
    margin-bottom: 20px;
    font-size: 12px;
    letter-spacing: 0.02em;
  }
  .brand { display: flex; align-items: center; gap: 10px; }
  .brand-logo { height: 56px; width: auto; display: block; }
  .brand-name { color: var(--accent); font-weight: 700; letter-spacing: 0.05em; }
  .prompt { color: var(--accent); font-weight: 700; }
  .sep { color: var(--ink-muted); }
  .title { color: var(--ink-dim); }
  .nav { display: flex; gap: 4px; }

  .btn {
    background: transparent;
    border: 1px solid var(--hairline);
    color: var(--ink-dim);
    padding: 6px 10px;
    font: inherit;
    font-size: 12px;
    cursor: pointer;
    text-decoration: none;
    letter-spacing: 0.02em;
    transition: color 120ms, border-color 120ms, background 120ms;
  }
  .btn:hover:not(:disabled) {
    color: var(--accent);
    border-color: var(--accent-dim);
    background: #14201a;
  }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-accent {
    color: var(--bg);
    background: var(--accent);
    border-color: var(--accent);
    font-weight: 700;
  }
  .btn-accent:hover:not(:disabled) { background: #f59640; color: var(--bg); }
  .btn-danger { color: var(--negative); border-color: #3a1a1a; }
  .btn-danger:hover:not(:disabled) {
    background: #1a0e0e;
    color: var(--negative);
    border-color: var(--negative);
  }

  .panel {
    position: relative;
    border: 1px solid var(--hairline-strong);
    background: var(--surface);
    padding: 20px 22px;
  }
  .corner-bracket {
    position: absolute;
    width: 10px;
    height: 10px;
    border-color: var(--accent);
    border-style: solid;
    border-width: 0;
  }
  .bracket-tl { top: -1px; left: -1px; border-top-width: 1px; border-left-width: 1px; }
  .bracket-tr { top: -1px; right: -1px; border-top-width: 1px; border-right-width: 1px; }
  .bracket-bl { bottom: -1px; left: -1px; border-bottom-width: 1px; border-left-width: 1px; }
  .bracket-br { bottom: -1px; right: -1px; border-bottom-width: 1px; border-right-width: 1px; }

  .panel-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 14px;
  }
  .panel-head h2 {
    font-size: 13px;
    color: var(--ink-dim);
    font-weight: 500;
    letter-spacing: 0.05em;
    margin: 0;
  }
  .count { color: var(--ink-muted); font-size: 11px; }

  .err {
    margin: 0 0 12px;
    padding: 8px 12px;
    border: 1px solid #3a1a1a;
    background: #1a0e0e;
    color: var(--negative);
    font-size: 12px;
  }
  .loading { color: var(--ink-dim); font-size: 12px; padding: 12px 0; }

  .list { list-style: none; margin: 0; padding: 0; }
  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 4px;
    border-bottom: 1px solid var(--hairline);
    font-size: 13px;
  }
  .row:last-child { border-bottom: none; }
  .mark { color: var(--accent); width: 12px; }
  .row-name {
    flex: 1;
    background: transparent;
    border: none;
    color: var(--ink);
    font: inherit;
    font-weight: 500;
    text-align: left;
    cursor: text;
    padding: 2px 0;
    letter-spacing: 0.02em;
  }
  .row-name:hover { color: var(--accent); }
  .tag {
    padding: 2px 8px;
    font-size: 10px;
    color: var(--bg);
    background: var(--accent-dim);
    letter-spacing: 0.05em;
  }
  .row-date { color: var(--ink-muted); font-size: 11px; }

  .input-inline {
    background: var(--surface-raised);
    border: 1px solid var(--hairline);
    color: var(--ink);
    padding: 6px 10px;
    font: inherit;
    font-size: 13px;
    letter-spacing: 0.02em;
  }
  .input-inline:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent-dim);
  }
  .grow { flex: 1; }

  .divider {
    color: var(--hairline-strong);
    font-size: 11px;
    margin: 18px 0 14px;
    user-select: none;
  }

  .new-form {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  @media (max-width: 640px) {
    .wrap { padding: 16px 12px 48px; }
    .brand-logo { height: 36px; }
    .brand-name { font-size: 11px; }
    .panel { padding: 20px 12px; }
    .panel-head { flex-wrap: wrap; gap: 8px; }
    .row { flex-wrap: wrap; gap: 8px; }
    .row-name { min-width: 0; flex-basis: calc(100% - 28px); overflow-wrap: anywhere; }
    .row-date { margin-left: auto; }
    .row .btn, .new-form .btn { min-height: 44px; }
    .input-inline { min-width: 0; max-width: 100%; }
    .new-form { flex-wrap: wrap; }
    .new-form .grow { flex-basis: calc(100% - 28px); }
    .new-form .btn { width: 100%; }
    .divider { overflow: hidden; white-space: nowrap; }
  }
</style>
